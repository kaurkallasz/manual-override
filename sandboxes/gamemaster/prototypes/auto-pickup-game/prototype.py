"""
Auto Pick and Place game — gamemaster master controller.

Two players (green + purple), each independent. Player controllers ask for a
name before registering. The operator can calibrate robot poses against
ArUco markers rendered by Playfield Areas, then click the webcam view to map a
detected screen location into a robot cartesian move. Every finished run is
appended to ``auto-pickup-log.csv``.

Player controllers (green/purple sandboxes) drive their own arm via
joint-angles-test and forward name/start here; only the gamemaster can mark a
run finished.
"""

import csv
import datetime as _dt
import hashlib
import io
import json
import logging
import math
import os
import copy
import threading
import time
import uuid
import zipfile

from flask import Blueprint, Response, jsonify, request, send_from_directory

import live
from tracking_output import CalibrationProjection, IntentStore
from lesson import LessonStore, atomic_json

HERE = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(HERE, "auto-pickup-log.csv")
CALIBRATION_PATH = os.path.join(HERE, "auto-calibration.json")
CALIBRATION2_PATH = os.path.join(HERE, "auto-calibration-2.json")
FIXED_CAL2_PLAYFIELD_PATH = os.path.join(
    HERE, "fixed-auto-pp-cal-2-playfield.json")
PLAYFIELD_SNAPSHOT_PATH = os.path.join(HERE, "auto-playfield.json")
HIGHSCORE_RESET_PATH = os.path.join(HERE, "auto-highscore-reset.json")
LOG_FIELDS = [
    "logged_at", "player", "team", "elapsed_seconds",
    "started_at", "completed_at",
]
TEAMS = ("green", "purple")
CALIBRATION_POINTS = (
    ("top_left", "Top left", 0.25, 0.25, 20),
    ("top_right", "Top right", 0.75, 0.25, 21),
    ("bottom_right", "Bottom right", 0.75, 0.75, 22),
    ("bottom_left", "Bottom left", 0.25, 0.75, 23),
)
PLAYFIELD_MARKERS = CALIBRATION_POINTS + (
    ("center", "Center", 0.5, 0.5, 24),
)
CORNER_KEYS = tuple(key for key, _label, _u, _v, _marker in CALIBRATION_POINTS)
CORNER_MARKERS = tuple(marker for _key, _label, _u, _v, marker in CALIBRATION_POINTS)
CORNERS_BY_MARKER = {
    20: (0.0, 0.0), 21: (1.0, 0.0),
    22: (1.0, 1.0), 23: (0.0, 1.0),
}
CENTER_MARKER = 24
CALIBRATION_TAG_SIZE = 2.8
CALIBRATION_TAG_SPAN_X = 7.5
CALIBRATION_TAG_SPAN_Z = 4.0
ROBOT_IP = "192.168.1.6"
DEFAULT_LINKS = {
    "purple": {"local_ip": "192.168.1.50"},
    "green": {"local_ip": "192.168.1.51"},
}
SUCK_DO_INDEX = 2
BLOW_DO_INDEX = 1
DIRECT_MAX_LIN_VEL = 20.0
DIRECT_MAX_ANG_VEL = 9.0
DIRECT_RAMP_SECS = 0.50
WORKSPACE = {
    "x": [-450.0, 450.0],
    "y": [-450.0, 450.0],
    "z": [-150.0, 230.0],
    "r": [-160.0, 160.0],
}
RADIUS_MIN = 150.0
RADIUS_MAX = 440.0
CAL2_REACH_MARGIN_MM = 1.0
CAL2_YAW_LIMIT_DEG = 155.0  # 5 degrees inside the configured +/-160 J1 limit.
# Auto PP applies a stricter 200..400 mm motion ring than the robot's raw
# 150..440 mm workspace. Keep Cal 2 targets another 20 mm inside that ring.
CAL2_RADIUS_MIN = 220.0
CAL2_RADIUS_MAX = 380.0
CAL2_MARKERS = tuple(range(30, 36))
CAL2_PARALLAX_MARKERS = (31, 35, 33, 34)

MANIFEST = {
    "name": "Auto Pick and Place",
    "description": "Auto pick-and-place game: each player enters a name, "
                   "the gamemaster marks finishes, all logged to CSV.",
    "default_page": "game",
    "pages": [{"path": "game", "label": "Auto Pick and Place"}],
}
bp = Blueprint("auto_pickup_game", __name__)

_state_lock = threading.Lock()
_calibration_lock = threading.Lock()
_live = live.LiveState()
_hub_ctx = None
_direct_robots = {side: None for side in TEAMS}
_direct_locks = {side: threading.Lock() for side in TEAMS}
_calibration_access = {
    side: {"enabled": False, "updated_at": None}
    for side in TEAMS
}


def _team_state():
    return {
        "player": "",
        "phase": "idle",            # idle | ready | running | done
        "started_at": None,         # epoch seconds
        "completed_at": None,
        "elapsed_seconds": None,
    }


_state = {
    "teams": {t: _team_state() for t in TEAMS},
    "best_seconds": None,
    "best_player": "",
    "best_team": "",
    "highscore_reset_at": 0.0,
    "updated_at": time.time(),
}


def _empty_pose():
    return {"set": False, "x": None, "y": None, "z": None, "r": None}


def _empty_cal2_parallax_points():
    return {
        str(marker): {"marker": marker, "ground": None, "raised": None}
        for marker in CAL2_PARALLAX_MARKERS
    }


def _clean_cal2_parallax_sample(marker, value):
    try:
        marker = int(marker)
        if marker not in CAL2_PARALLAX_MARKERS or not isinstance(value, dict):
            raise ValueError
        ground, raised = value["ground"], value["raised"]
        sample = {
            "marker": marker,
            "ground": {
                "u": round(float(ground["u"]), 8),
                "v": round(float(ground["v"]), 8),
            },
            "raised": {
                "u": round(float(raised["u"]), 8),
                "v": round(float(raised["v"]), 8),
            },
        }
        if not all(
            0 <= sample[level][axis] <= 1
            for level in ("ground", "raised") for axis in ("u", "v")
        ):
            raise ValueError
        return sample
    except (KeyError, TypeError, ValueError):
        raise ValueError("valid marker, ground and raised camera coordinates required")


def _default_calibration():
    return {
        "playfield": {
            "active_area": {"sMin": 0.0, "sMax": 1.0, "tMin": 0.0, "tMax": 1.0},
            "marker_cache": None,
            "areas": {
                key: {
                    "key": key,
                    "label": label,
                    "u": u,
                    "v": v,
                    "marker": marker,
                    "area_id": None,
                }
                for key, label, u, v, marker in PLAYFIELD_MARKERS
            },
            "corner_map": {
                key: marker for key, _label, _u, _v, marker in CALIBRATION_POINTS
            },
            "updated_at": None,
        },
        "arms": {
            side: {
                "points": {
                    key: {
                        "key": key,
                        "label": label,
                        "u": u,
                        "v": v,
                        "marker": marker,
                        "pose": _empty_pose(),
                    }
                    for key, label, u, v, marker in CALIBRATION_POINTS
                },
                "center": _empty_pose(),
                "corner_map": {
                    key: marker for key, _label, _u, _v, marker in CALIBRATION_POINTS
                },
                "marker_cache": None,
                "pickup_height": {"set": False, "z": None},
                "transport_height": {"set": False, "z": None},
                "updated_at": None,
            }
            for side in TEAMS
        },
    }


_calibration = _default_calibration()


def _default_calibration2():
    targets = {
        f"p{i + 1}": {
            "key": f"p{i + 1}", "label": f"Point {i + 1}",
            "marker": marker, "s": None, "t": None, "area_id": None,
        }
        for i, marker in enumerate(CAL2_MARKERS)
    }
    return {
        "format": "auto-pp-calibration-2-v1",
        "revision": 1,
        "shared_z": {"transport_height": None},
        "playfield": {
            "active_area": {"sMin": 0.0, "sMax": 1.0, "tMin": 0.0, "tMax": 1.0},
            "targets": targets,
            "saved_areas": None,
            "saved_settings": None,
            "saved_camera_view": "normal",
            "updated_at": None,
        },
        "arms": {
            side: {
                "camera_view": "normal",
                "parallax_points": _empty_cal2_parallax_points(),
                "pickup_height": None,
                # Raise a drop by one physical tag when its destination is
                # another 100-series tag. Each arm can tune this separately.
                "stack_drop_offset": 31.5,
                "points": {
                    key: {**target, "camera": None, "pose": _empty_pose()}
                    for key, target in targets.items()
                },
                "updated_at": None,
            }
            for side in TEAMS
        },
    }


_calibration2 = _default_calibration2()
_tracking_intents = IntentStore()
_tracking_projection_lock = threading.Lock()
_tracking_projection_cache = (None, None)
_lessons = None


def _enabled_module(slug):
    return _hub_ctx.get_prototype(slug) if _hub_ctx and _hub_ctx.is_prototype_enabled(slug) else None


def _read_contract(slug, function, name, *args):
    module = _enabled_module(slug)
    if module is None or not callable(getattr(module, function, None)):
        raise ValueError(f'{slug} unavailable')
    value = getattr(module, function)(*args)
    if not isinstance(value, dict) or value.get('contract') != name or type(value.get('version')) is not int or value['version'] != 1 or value.get('status') != 'ready':
        raise ValueError(f'{name} v1 unavailable')
    return value


def _start_lessons():
    global _lessons
    _lessons = LessonStore(os.path.join(HERE, 'data', 'calibration-lessons.json'))


def calibration_session_snapshot():
    if _lessons is None:
        return {'contract':'hhh.cal2.session','version':1,'status':'unavailable','error':'not initialized'}
    value=_lessons.snapshot()
    value['motion_blocked'] = bool(value.get('pending_stops'))
    value['motion_error'] = ('Connect '+', '.join(value['pending_stops'])+' to confirm the previous calibration stop. Screen selection remains available.'
                             if value['motion_blocked'] else None)
    value['rig_revision'] = _calibration2_public().get('revision',1)
    if _enabled_module('playfield-areas'):
        field=_read_contract('playfield-areas','display_snapshot','hhh.playfield')
        reservation=field.get('display_session')
        preparation=value.get('marker_preparation')
        if preparation and (not reservation or any(preparation[k]!=reservation.get(k) for k in ('id','side'))):
            value.pop('marker_preparation',None)
            for session in value['sessions'].values():session.pop('marker_positions',None)
        if reservation and not value.get('active_side'):
            # Field reservation may have committed before the lesson draft.
            # Publish its side as blocked (no live access/session), then allow
            # Game to retry begin with the same durable operation identity.
            value.update(active_side=reservation.get('side'),active_id=reservation['id'],requires_activation=True)
        if value.get('active_side'):
            loaded=(reservation and reservation['id']==value.get('active_id') and reservation.get('side')==value['active_side']
                    and len(field.get('areas',[]))==6 and {a.get('marker') for a in field['areas']}==set(range(30,36)))
            value['display']={'contract':'hhh.playfield.display','version':1,'status':'ready' if loaded else 'unavailable',
                              'path':field['screen_path'] if loaded else None,
                              'error':None if loaded else 'Auto PP Cal 2 targets have not finished loading'}
    return value


def _prepare_calibration_markers(field):
    reservation=field.get('display_session') or {}
    if reservation.get('side') not in TEAMS or not isinstance(reservation.get('id'),str):
        raise ValueError('calibration target display unavailable')
    state=_lessons.snapshot()
    if state.get('active_side') and (state.get('active_id')!=reservation['id'] or state['active_side']!=reservation['side']):
        raise ValueError('calibration target display changed')
    areas=field.get('areas',[])
    if len(areas)!=6 or {a.get('marker') for a in areas}!=set(range(30,36)):
        raise ValueError('six calibration targets required')
    # Glows and hiding the two centre codes for the raised stage do not move
    # the board. Preserve the same six references through both capture stages.
    layout={'settings':{k:(field.get('settings') or {}).get(k) for k in ('cam','rot','fov')},
            'targets':sorted([[a.get(k) for k in ('marker','x','y','z','size')] for a in areas])}
    _lessons.prepare_markers(reservation['side'],reservation['id'],layout)
    return reservation


def _calibration_camera_observation():
    try:
        reservation=(_prepare_calibration_markers(_read_contract('playfield-areas','display_snapshot','hhh.playfield'))
                     if _lessons else None)
        raw = _read_contract('webcam','tag_snapshot','hhh.webcam.tags')
        corrected = _read_contract('camera-calibration','corrected_tag_snapshot','hhh.camera-correction',raw.get('tags') or [],raw.get('detections') or [])
        stamp=raw.get('frame_at')
        if not corrected.get('corrected') or not isinstance(corrected.get('calibration_revision'),str) or not corrected['calibration_revision']:
            raise ValueError('valid corrected camera required')
        if type(stamp) not in (int,float) or not math.isfinite(stamp) or not -1<=time.time()-stamp<=1.5:
            raise ValueError('fresh camera and arm feedback required')
        # An empty detector result means occlusion, not permission to resurrect
        # tracked/missing tags as newly observed marker positions.
        tags=corrected.get('detections') if 'detections' in corrected else corrected.get('tags',[])
        # Webcam's `missing` is elapsed poll time, not absence from its latest
        # detector frame. Use that frame's visible IDs, as Board does; held
        # positions from an empty frame must never seed a new cache.
        if 'visible_ids' in raw:
            visible=raw['visible_ids']
            if not isinstance(visible,list) or any(type(i) is not int for i in visible):
                raise ValueError('valid current camera marker IDs required')
            tags=[{**t,'missing':0} for t in tags or [] if t.get('id') in visible]
        # Match Auto PP Cal 2's one-second tracked-tag qualification. A tag
        # must also be detected in this frame: held tracker entries cannot
        # seed references while the arm covers the board.
        confirmed={t.get('id') for t in corrected.get('tags') or [] if type(t.get('id')) is int}
        tags=[t for t in tags or [] if t.get('id') in confirmed]
        points={}
        if reservation:
            context={'camera_revision':corrected['calibration_revision'],'camera_identity':raw.get('camera_identity'),
                     'size':[raw.get('width'),raw.get('height')]}
            points=_lessons.observe_markers(reservation['side'],reservation['id'],context,stamp,tags or [])
        return raw,corrected,points
    except Exception:
        if _lessons:_lessons.suspend_marker_observation()
        raise


def _fresh_calibration_measurement(side, marker=None):
    raw,corrected,points = _calibration_camera_observation()
    preparation=(_lessons.snapshot().get('marker_preparation') or {}) if _lessons else {}
    if preparation.get('movement_pending'):
        raise ValueError('Camera movement detected; waiting for stable calibration targets')
    if preparation and points!=preparation['marker_positions']:
        raise ValueError('Camera references changed; capture again')
    arms = _read_contract('dobot-mg400-relay','arms_snapshot','hhh.relay.arms')
    arm = arms['arms'][side]
    frame_at, feedback_at = raw.get('frame_at'), arm.get('feedback_at')
    for stamp in (frame_at, feedback_at):
        if type(stamp) not in (int,float) or not math.isfinite(stamp) or not -1 <= time.time()-stamp <= 1.5:
            raise ValueError('fresh camera and arm feedback required')
    pose = arm.get('pose')
    if not arm.get('connected') or not arm.get('enabled') or not isinstance(pose,list) or len(pose)!=4 or not all(type(v) in (int,float) and math.isfinite(v) for v in pose):
        raise ValueError('fresh enabled arm pose required')
    result = {'contract':'hhh.cal2.measurement','version':1,'status':'ready','pose':pose,'frame_at':frame_at,'feedback_at':feedback_at,'camera_revision':corrected.get('calibration_revision'),'pump':arm.get('pump_mode'),
              'tags':[t for t in (corrected.get('detections') or corrected.get('tags') or []) if t.get('missing',0)==0], 'arm':arm,'rig_identity':arm.get('device')}
    if preparation:
        result['reference_id']=preparation['reference_id']
    if marker is not None:
        if type(marker) is not int or marker not in range(30,36):
            raise ValueError('select a marker from 30 to 35')
        if len(points)!=6:
            missing=', '.join(str(i) for i in range(30,36) if str(i) not in points)
            raise ValueError(f'Preparing calibration: keep markers {missing} visible until all six camera positions are identified')
        point=points.get(str(marker)) if _lessons and _lessons.snapshot().get('active_side')==side else None
        if point:
            result.update(camera=point['camera'],marker_frame_at=point['frame_at'],camera_cached=point['frame_at']!=frame_at)
        else:
            raise ValueError('this calibration turn is not active')
    return result


def _disable_calibration_arm(side):
    result=_read_contract('dobot-mg400-relay','disable_side','hhh.relay.disabled',side)
    if result.get('inhibited') is not True or type(result.get('connected')) is not bool or (result['connected'] and result.get('disabled') is not True):
        raise ValueError('Waiting arm must be disabled before calibration')
    return result


def _sync_calibration_display(session):
    """Render durable lesson progress through the display owner's public API."""
    if not session:return
    if session['stage']=='perspective':
        visible=[31,35,33,34]
        highlighted=[m for m in visible if not session['draft']['parallax_points'].get(str(m))]
    else:
        visible=list(range(30,36))
        highlighted=[int(m) for m in session['captures']] if session['stage']=='points' else []
    _read_contract('playfield-areas','display_command','hhh.playfield',
                   {'action':'progress','id':session['id'],'visible':visible,'highlighted':highlighted})


def calibration_session_begin(value):
    if _lessons is None:
        raise ValueError('calibration owner unavailable')
    side = value.get('side')
    if side not in TEAMS:
        raise ValueError('valid calibration side required')
    cal = _calibration2_public()
    # Use the same commissioned target layout as Auto PP Cal 2. Its saved
    # templates deliberately have no Playfield runtime IDs; assign stable IDs
    # within this exclusive display session. Rotate the target positions for
    # the opposite player, just as the standalone Auto PP Cal 2 loader does.
    fixed = _fixed_cal2_playfield()
    areas = (fixed or {}).get('areas') or cal['playfield'].get('saved_areas')
    if (not isinstance(areas,list) or len(areas)!=6
            or any(not isinstance(a,dict) or type(a.get('marker')) is not int for a in areas)
            or {a['marker'] for a in areas}!=set(range(30,36))):
        raise ValueError('commission the six-marker playfield before the lesson')
    saved_view = (fixed.get('camera_view', 'normal') if fixed else
                  cal['playfield'].get('saved_camera_view', 'normal'))
    view = 'rot180' if side == 'purple' else 'normal'
    if saved_view not in ('normal', 'rot180'):
        raise ValueError('invalid calibration target orientation')
    session = _lessons.snapshot()['sessions'].get(value['id'])
    if session and session.get('captures') and session.get('display_camera_view', saved_view) != view:
        # Older lessons displayed the template unchanged for both sides. Never
        # reuse their measurements after moving the physical target layout.
        raise ValueError('Calibration target orientation changed; cancel and reopen calibration to capture all six points again')
    areas=copy.deepcopy(areas)
    for area in areas:
        if saved_view != view:
            area['x'], area['z'] = -float(area.get('x', 0)), -float(area.get('z', 0))
        area.update(id=f"cal2-{area['marker']}",color='#82baff',glow=.25,show_area=False,show_aruco=True,show_links=False)
    settings=copy.deepcopy((fixed or {}).get('settings') or cal['playfield'].get('saved_settings') or {})
    # Only the surround blooms. Playfield draws the marker/quiet border in its
    # separate sharp overlay pass, preserving camera detection contrast.
    settings['bloom']=max(.6,float(settings.get('bloom',0)))
    field=_read_contract('playfield-areas','display_snapshot','hhh.playfield')
    reservation=field.get('display_session') or {}
    if reservation.get('id')!=value['id'] or reservation.get('side')!=side:
        field=_read_contract('playfield-areas','display_command','hhh.playfield',
                             {'action':'begin','id':value['id'],'side':side,'areas':areas,'settings':settings})
    if session:
        _sync_calibration_display(session)
        field=_read_contract('playfield-areas','display_snapshot','hhh.playfield')
    _prepare_calibration_markers(field)
    _disable_calibration_arm('purple' if side=='green' else 'green')
    pending = calibration_session_snapshot()
    if pending['motion_blocked']:
        raise ValueError(pending['motion_error'])
    # Show the targets while commissioning feedback. The display reservation
    # blocks movement until fresh measurements allow a live lesson grant.
    _fresh_calibration_measurement(value['side'])
    cal['arms'][side]['camera_view'] = view
    result = _lessons.begin({**value, 'display_camera_view': view}, cal)
    session = result['sessions'][value['id']]
    _sync_calibration_display(session)
    return result


def calibration_session_command(side, value):
    if _lessons is None:
        raise ValueError('calibration owner unavailable')
    action = value.get('action')
    if action == 'heartbeat':
        maintained = calibration_session_maintain()
        if maintained.get('status') != 'ready':
            raise ValueError(maintained.get('error','calibration stop unavailable'))
        _fresh_calibration_measurement(side)
        return _lessons.heartbeat(side,value['id'])
    if action == 'capture':
        result = _lessons.capture(side,value,_fresh_calibration_measurement(side,value.get('marker')))
        _sync_calibration_display(result['sessions'][value['id']])
        return result
    if action == 'ground':
        return _lessons.parallax(side,value,_fresh_calibration_measurement(side,value.get('marker')))
    if action == 'raised':
        camera=value.get('camera')
        if not isinstance(camera,dict) or any(type(camera.get(k)) not in (int,float) or not math.isfinite(camera[k]) or not 0<=camera[k]<=1 for k in ('u','v')):
            raise ValueError('Tap the raised tag centre in the corrected camera')
        # The raised physical tag can obscure the ground code completely.
        # Match Auto PP Cal 2: explicit video selection in corrected-camera
        # coordinates, with live frame/arm and draft revision checks retained.
        measurement=_fresh_calibration_measurement(side)
        measurement['camera']={k:camera[k] for k in ('u','v')}
        result = _lessons.parallax(side,value,measurement)
        _sync_calibration_display(result['sessions'][value['id']])
        return result
    if action == 'height':
        raise ValueError('Pickup and transport heights are calculated from the six arm points; refresh the player page')
    if action == 'arrival':
        target = calibration_lesson_target(side,value['id'])
        return _lessons.arrival(side,value,_fresh_calibration_measurement(side)['pose'],target['pose'])
    if action != 'commit':
        raise ValueError('unsupported calibration action')
    return _commit_calibration_measurements(side,value.get('id'))


def _commit_calibration_measurements(side, session_id, *, offline=False):
    state = _lessons.derive_heights(side,session_id,offline=offline)
    session = state['sessions'].get(session_id)
    if not offline and (state['active_side'] != side or not session or session['side'] != side or session.get('epoch')!=state['epoch'] or session.get('paused') or session.get('access_until',0)<time.time()):
        raise PermissionError('calibration turn unavailable')
    if len(session['captures']) != 6 or set(session['draft']['parallax_points'])!={'31','35','33','34'} or any(not p for p in session['draft']['parallax_points'].values()):
        raise ValueError('six points and four raised-Atom samples required')
    measured = ({k:session.get(k) for k in ('camera_revision','rig_identity')} if offline else _fresh_calibration_measurement(side))
    _lessons.check_marker_reference(measured)
    # Observing the camera above can reset this draft. Never commit the stale
    # snapshot read before that observation.
    current=_lessons.snapshot()['sessions'].get(session_id)
    if current!=session:
        raise ValueError('Calibration measurements changed; review the current draft before saving')
    if not isinstance(measured.get('camera_revision'),str) or not measured['camera_revision']:
        raise ValueError('saved camera correction identity required')
    if session.get('camera_revision') != measured.get('camera_revision'):
        raise ValueError('camera correction changed; restart the draft')
    candidate = _calibration2_public()
    previous = copy.deepcopy(candidate)
    _remember_calibration_sources(candidate)
    candidate['camera_revision'] = measured.get('camera_revision')
    candidate['arms'][side] = session['draft']
    candidate['arms'][side]['camera_revision'] = measured.get('camera_revision')
    # New measurements belong to this camera correction; do not inherit an
    # older saved rig's explicit association with a different camera session.
    candidate['arms'][side].pop('camera_binding',None)
    candidate['arms'][side]['updated_at'] = time.time()
    candidate['arms'][side]['rig_identity'] = measured.get('rig_identity')
    if any(not WORKSPACE['z'][0] <= session[k] <= WORKSPACE['z'][1]
           for k in ('pickup_height','transport_height')):
        raise ValueError('Calculated pickup or transport height is outside the robot workspace; check the six arm points')
    model = CalibrationProjection(candidate).models[side]
    if isinstance(model,str):
        raise ValueError(model)
    if model[2] is None:
        raise ValueError('Four valid raised-tag samples required')
    # Retries reuse their revision; edits made during optional practice must
    # still be committed before the player completes the calibration turn.
    fingerprint=json.dumps({'id':session['id'],
        'draft':{k:session['draft'].get(k) for k in ('points','parallax_points','pickup_height','camera_view','stack_drop_offset')},
        'transport_height':session['transport_height'],
        'camera_revision':measured.get('camera_revision'),'rig_identity':measured.get('rig_identity')},
        sort_keys=True,allow_nan=False)
    expected_receipt=session['id']+':'+hashlib.sha256(fingerprint.encode()).hexdigest()
    receipt = candidate.get('lesson_receipt')
    if receipt != expected_receipt:
        _lessons.archive_rig(side,previous)
        candidate['revision'] = candidate.get('revision',1) + 1
        candidate['lesson_receipt'] = expected_receipt
        candidate['saved_selection'][side]={'policy':'latest','active_id':session['id']+':'+str(candidate['revision'])}
        atomic_json(CALIBRATION2_PATH,candidate)
        with _calibration_lock:
            global _calibration2
            _calibration2 = candidate
    _lessons.mark_committed(side,session['id'],candidate['revision'],offline=offline)
    return _lessons.snapshot()


def _current_camera_revision():
    corrected=_read_contract('camera-calibration','corrected_tag_snapshot','hhh.camera-correction',[],[])
    revision=corrected.get('calibration_revision')
    if not isinstance(revision,str) or not revision:
        raise ValueError('Current camera calibration identity unavailable')
    return revision


def _camera_compatibility(source_revision,current_revision):
    """Describe provenance only. A session mismatch never limits control tiers."""
    matched=bool(source_revision and source_revision==current_revision)
    warning=None if matched else (
        'Camera and arm calibrations are from different or unverified sessions. '
        'The saved arm calibration uses the current camera calibration, so '
        'positioning may be less precise. All control levels remain available.')
    return {'status':'matched' if matched else 'approximate',
            'source_camera_revision':source_revision,'current_camera_revision':current_revision,
            'warning':warning}


def _bound_camera_revision(arm,fallback=None):
    binding=arm.get('camera_binding')
    if binding is None:return arm.get('camera_revision',fallback)
    if (not isinstance(binding,dict) or not isinstance(binding.get('revision'),str)
            or not binding['revision'] or type(binding.get('applied_at')) not in (int,float)
            or not math.isfinite(binding['applied_at'])):
        raise ValueError('Applied camera calibration association is invalid; apply the saved calibration again')
    return binding['revision']


def calibration_history(side):
    """Read-only per-arm saved Cal 2 measurements; never grants lesson credit."""
    if side not in TEAMS or _lessons is None:
        return {'contract':'hhh.cal2.history','version':1,'status':'unavailable','error':'Calibration history unavailable','rows':[]}
    state=_lessons.snapshot()
    rows=[copy.deepcopy(row) for row in state.get('saved_calibrations',{}).values() if row.get('side')==side]
    archived={row['id'] for row in rows}
    for session in state['sessions'].values():
        if session.get('side')==side and session.get('calibration_revision') is not None and session.get('committed_at'):
            identity=session['id']+':'+str(session['calibration_revision'])
            if identity not in archived:
                rows.append({'id':identity,'side':side,'revision':session['calibration_revision'],
                             'saved_at':session['committed_at'],'practice':session.get('practice',False),
                             'draft':copy.deepcopy(session['draft']),'transport_height':session.get('transport_height'),
                             'camera_revision':session.get('camera_revision')})
    cal=_calibration2_public()
    arm=cal['arms'][side]
    selection=(cal.get('saved_selection',{}).get(side) or {})
    active_id=selection.get('active_id') or 'rig:'+side+':'+str(cal.get('revision',1))
    if active_id not in {row['id'] for row in rows} and any(p.get('pose',{}).get('set') for p in arm.get('points',{}).values()):
        rows.append({'id':active_id,'side':side,'label':'Current saved rig',
                     'revision':cal.get('revision',1),'saved_at':arm.get('updated_at'),
                     'draft':arm,'transport_height':arm.get('transport_height') if arm.get('transport_height') is not None else cal.get('shared_z',{}).get('transport_height'),
                     'camera_revision':arm.get('camera_revision',cal.get('camera_revision'))})
    rows.sort(key=lambda row:row.get('saved_at') or 0,reverse=True)
    try:current_camera=_current_camera_revision();camera_error=None
    except Exception as exc:current_camera=None;camera_error=str(exc)
    for row in rows:
        row['active']=row['id']==active_id
        try:_saved_calibration_candidate(cal,side,row);row.update(applicable=True,error=None)
        except (ValueError,KeyError,TypeError,OverflowError) as exc:row.update(applicable=False,error=str(exc))
        row['camera_compatibility']=(_camera_compatibility(row.get('camera_revision'),current_camera)
            if current_camera else {'status':'unavailable','warning':'Current camera calibration unavailable: '+camera_error})
    latest=next((row['id'] for row in rows if row['applicable']),None)
    return {'contract':'hhh.cal2.history','version':1,'status':'ready','rows':rows,
            'active_id':active_id,'latest_id':latest,'selection':selection.get('policy','latest'),
            'rig_revision':cal.get('revision',1)}


def _remember_calibration_sources(cal):
    selections=cal.setdefault('saved_selection',{})
    for side in TEAMS:
        selections.setdefault(side,{'policy':'latest','active_id':'rig:'+side+':'+str(cal.get('revision',1))})
        cal['arms'][side].setdefault('camera_revision',cal.get('camera_revision'))


def _saved_calibration_candidate(cal,side,row):
    if row.get('side')!=side:raise ValueError('Saved calibration belongs to the other arm')
    arm=copy.deepcopy(row['draft'])
    if not isinstance(arm,dict) or not isinstance(arm.get('points'),dict):
        raise ValueError('Saved calibration points unavailable')
    points=list(arm['points'].values())
    if len(points)!=6 or any(not isinstance(p,dict) for p in points) or {p.get('marker') for p in points}!=set(range(30,36)):
        raise ValueError('Six saved markers 30–35 required')
    for p in points:
        if not isinstance(p.get('pose'),dict) or not p['pose'].get('set'):raise ValueError('Six measured arm positions required')
        for axis in ('x','y','z','r'):
            value=p['pose'].get(axis)
            if type(value) not in (int,float) or not math.isfinite(value) or not WORKSPACE[axis][0]<=value<=WORKSPACE[axis][1]:
                raise ValueError('Saved arm positions must be finite and within the workspace')
        if not isinstance(p.get('camera'),dict):raise ValueError('Saved camera point required')
        if any(type(p['camera'].get(k)) not in (int,float) or not math.isfinite(p['camera'][k]) or not 0<=p['camera'][k]<=1 for k in ('u','v')):
            raise ValueError('Saved camera point is outside the image')
    if not isinstance(arm.get('parallax_points'),dict):raise ValueError('Four raised-tag samples required')
    for marker in (31,35,33,34):_clean_cal2_parallax_sample(marker,arm.get('parallax_points',{}).get(str(marker)))
    for height in (arm.get('pickup_height'),row.get('transport_height')):
        if type(height) not in (int,float) or not math.isfinite(height) or not WORKSPACE['z'][0]<=height<=WORKSPACE['z'][1]:
            raise ValueError('Saved pickup and transport heights required within the workspace')
    if arm.get('camera_view','normal') not in ('normal','rot180'):raise ValueError('Invalid saved camera orientation')
    candidate=copy.deepcopy(cal);_remember_calibration_sources(candidate)
    arm['camera_revision']=row.get('camera_revision',arm.get('camera_revision'))
    arm['updated_at']=row.get('saved_at')
    candidate['arms'][side]=arm
    if arm.get('transport_height') is not None:
        if arm['transport_height'] != row['transport_height']:
            raise ValueError('Saved arm transport height does not match its record')
    else:
        candidate['shared_z']['transport_height']=row['transport_height']
    model=CalibrationProjection(candidate).models[side]
    if isinstance(model,str):raise ValueError(model)
    if model[2] is None:raise ValueError('Four valid raised-tag samples required')
    return candidate


def calibration_saved_preview(value):
    """Resolve a saved, complete calibration; never changes the rig or display."""
    if not isinstance(value,dict) or value.get('side') not in TEAMS:raise ValueError('Select Green or Purple')
    side=value['side'];history=calibration_history(side)
    if history['status']!='ready':raise ValueError(history['error'])
    chosen=value.get('id','latest')
    if not isinstance(chosen,str):raise ValueError('Select a saved calibration')
    identity=history['latest_id'] if chosen=='latest' else chosen
    row=next((r for r in history['rows'] if r['id']==identity),None)
    if row is None:raise ValueError('Saved calibration is unavailable for this arm')
    if not row['applicable']:raise ValueError(row['error'])
    expected=value.get('expected_revision',history['rig_revision'])
    if type(expected) is not int or expected!=history['rig_revision']:
        raise ValueError('Calibration changed; refresh saved calibrations before applying')
    return {'contract':'hhh.cal2.saved','version':1,'status':'ready','side':side,'row':row,
            'selection':chosen,'rig_revision':history['rig_revision']}


def calibration_saved_apply(value):
    """Restore owned measurements after Game settles the lesson; revoke leases."""
    global _calibration2
    if _lessons is None:raise ValueError('Calibration owner unavailable')
    with _lessons.lock:
        preview=calibration_saved_preview(value);side=preview['side'];row=preview['row']
        scope=calibration_session_snapshot()
        if scope.get('active_side') or scope.get('motion_blocked'):
            raise ValueError('Finish returning to the game screen and confirm pending arm stops before applying')
        previous=_calibration2_public();candidate=_saved_calibration_candidate(previous,side,row)
        camera_revision=_current_camera_revision()
        # Keep the measured source revision and all original points. Reusing a
        # saved camera-to-arm fit with today's lens correction is approximate,
        # not a new measurement or a restoration of the old camera settings.
        compatibility=_camera_compatibility(candidate['arms'][side].get('camera_revision'),camera_revision)
        candidate['arms'][side]['camera_binding']={'revision':camera_revision,'applied_at':time.time()}
        relay=_read_contract('dobot-mg400-relay','arms_snapshot','hhh.relay.arms')
        observed=relay.get('observed_at')
        if type(observed) not in (int,float) or not -.25<=time.time()-observed<=1.5:
            raise ValueError('Fresh arm connection states are required before applying')
        arms=relay.get('arms',{})
        if any(not isinstance(arms.get(s),dict) or type(arms[s].get('connected')) is not bool for s in TEAMS):
            raise ValueError('Both arm connection states are required before applying')
        identity=row['draft'].get('rig_identity')
        if identity and arms[side].get('device')!=identity:raise ValueError('Saved calibration belongs to a different arm connection')
        operation='saved-calibration:'+uuid.uuid4().hex
        settled=[]
        try:
            # The existing durable stop gate blocks lease acquisition during
            # replacement. Maintenance cannot clear it while this lock is held.
            for s in TEAMS:_lessons.defer_stop(s,operation)
            for s in TEAMS:
                if arms[s]['connected']:
                    stopped=_read_contract('dobot-mg400-relay','stop_side','hhh.relay.stop',s)
                    if stopped.get('stopped') is not True:raise ValueError('Wait for '+s+' to stop before applying calibration')
                settled.append(s)
            if _current_camera_revision()!=camera_revision:
                raise ValueError('Camera calibration changed while applying; apply the saved arm calibration again')
            # Transport Z is shared; preserve both arms' original measurements
            # and height before replacing the selected rig.
            for s in TEAMS:_lessons.archive_rig(s,previous)
            candidate['saved_selection'][side]={'policy':preview['selection'],'active_id':row['id']}
            candidate['revision']=previous.get('revision',1)+1
            candidate['lesson_receipt']=None
            with _calibration_lock:
                atomic_json(CALIBRATION2_PATH,candidate)
                _calibration2=candidate
        finally:
            for s in settled:_lessons.confirm_stop(s,operation)
        return {**preview,'rig_revision':candidate['revision'],'applied':True,
                'camera_compatibility':compatibility}


def calibration_lesson_target(side, session_id):
    state = calibration_session_snapshot()
    session = state.get('sessions',{}).get(session_id)
    if not session or state.get('active_side') != side or session['stage'] != 'tutorial':
        raise ValueError('complete calibration before guided movement')
    model = CalibrationProjection(_calibration2_public()).models[side]
    if isinstance(model,str):
        raise ValueError(model)
    points = [p['camera'] for p in session['draft']['points'].values()]
    center = [sum(p[k] for p in points)/6 for k in ('u','v')]
    step = min(1,len(session['arrivals']))
    point = points[step]
    uv = [center[i]*.8 + point[k]*.2 for i,k in enumerate(('u','v'))]
    xy = model[0](*uv)
    return {'contract':'hhh.cal2.target','version':1,'status':'ready','camera':uv,
            'pose':[xy[0],xy[1],session['transport_height'],0], 'step':step}


def calibration_session_finish(value):
    return _lessons.finish(value['side'],value['id'],value['evidence_id'])


def calibration_session_complete(value):
    """Validate/install this lesson's measurements, then issue its completion receipt."""
    if _lessons is None:raise ValueError('Calibration owner unavailable')
    side,session_id=value.get('side'),value.get('id')
    scope=calibration_session_snapshot()
    session=scope.get('sessions',{}).get(session_id)
    if scope.get('active_side')!=side or scope.get('active_id')!=session_id or not session:
        raise PermissionError('wait for your calibration turn')
    if session['stage']!='complete':
        # Captures already contain validated feedback and camera/rig identity.
        # Finishing persists that evidence; it grants no movement or connection.
        _commit_calibration_measurements(side,session_id,offline=True)
    return _lessons.complete_measurements(side,session_id)


def calibration_session_release(value):
    state = calibration_session_snapshot()
    session = state.get('sessions',{}).get(value['id'])
    if session and session['side'] == value['side'] and state.get('active_side') is None:
        return state
    if state.get('active_id') != value['id'] or state.get('active_side') != value['side']:
        raise ValueError('calibration does not own this display reservation')
    if value.get('defer_stop') is True:
        # Projection can return to the game even with an offline arm. Keep a
        # durable, global motion inhibit until Relay confirms the old stop.
        if session:
            _lessons.defer_stop(value['side'],value['id'])
        _settle_deferred_stops()
    else:
        stopped = _read_contract('dobot-mg400-relay','stop_side','hhh.relay.stop',value['side'])
        if not stopped.get('stopped'):
            raise ValueError('wait for stopped motion before releasing the playfield')
    _read_contract('playfield-areas','display_command','hhh.playfield',{'action':'restore','id':value['id']})
    _lessons.clear_marker_cache()
    # A display-only reservation has no lesson or motion grant to release.
    return _lessons.release(value['side'],value['id']) if session else calibration_session_snapshot()


def _settle_deferred_stops():
    state=_lessons.snapshot()
    for side, session_id in state.get('pending_stops',{}).items():
        try:
            if state.get('sessions',{}).get(session_id,{}).get('completion_basis')=='measured-targets':
                _disable_calibration_arm(side)
            stopped = _read_contract('dobot-mg400-relay','stop_side','hhh.relay.stop',side)
            if stopped.get('stopped') is True:
                _lessons.confirm_stop(side,session_id)
        except Exception:
            # Snapshot exposes the durable motion inhibit; an unavailable arm
            # is never interpreted as stopped and does not freeze the screen.
            pass


def calibration_session_maintain():
    """Revoke expired access before asking Relay to hold; retain field ownership."""
    if _lessons is None:
        return calibration_session_snapshot()
    _settle_deferred_stops()
    state = calibration_session_snapshot()
    if state.get('active_side') in TEAMS:
        _sync_calibration_display(state.get('sessions',{}).get(state.get('active_id')))
        _disable_calibration_arm('purple' if state['active_side']=='green' else 'green')
    # Old stores could retain active_id after releasing active_side. Drafts are
    # historical evidence, not live turns; deferred stops have their own gate.
    session = (state.get('sessions',{}).get(state.get('active_id'))
               if state.get('active_side') in TEAMS and not state.get('requires_activation') else None)
    if session and session.get('access_until',0) < time.time():
        if not session.get('paused'):
            _lessons.pause(session['side'],session['id'])
        stopped = _read_contract('dobot-mg400-relay','stop_side','hhh.relay.stop',session['side'])
        if not stopped.get('stopped'):
            return {'contract':'hhh.cal2.session','version':1,'status':'unavailable','error':'expired calibration motion has not settled'}
    if state.get('active_side') in TEAMS and (not session or session.get('stage') in ('points','perspective')):
        # Game already calls maintenance every 250 ms. Learn all six camera
        # positions as soon as targets load, including before the arm connects.
        # A display reservation never grants capture or movement permission.
        try:_calibration_camera_observation()
        except Exception as exc:state['marker_cache_error']=str(exc)
    elif (session and not session.get('paused') and session.get('access_until',0)>=time.time()
          and session.get('stage')=='tutorial' and len(session.get('arrivals',[]))==2
          and not (session.get('pickup_evidence') or {}).get('lifted_at')):
        measurement=_fresh_calibration_measurement(session['side'])
        projection=tracking_projection(measurement['tags'],{session['side']:measurement['arm']})
        _lessons.observe_pickup(session['side'],session['id'],measurement,projection['arms'][session['side']])
    result=calibration_session_snapshot()
    if state.get('marker_cache_error'):result['marker_cache_error']=state['marker_cache_error']
    return result


def calibration_reach_snapshot():
    """Configured XY envelope, independent of camera fit or motion permission."""
    radius = RADIUS_MAX - CAL2_REACH_MARGIN_MM
    # A concave sector preserves the rear yaw exclusion; a convex hull would
    # silently fill it in. The inner base exclusion is checked separately.
    steps = math.ceil(2 * CAL2_YAW_LIMIT_DEG / 5)
    polygon = [[0.0, 0.0]] + [
        [radius * math.cos(math.radians(-CAL2_YAW_LIMIT_DEG + 2 * CAL2_YAW_LIMIT_DEG * i / steps)),
         radius * math.sin(math.radians(-CAL2_YAW_LIMIT_DEG + 2 * CAL2_YAW_LIMIT_DEG * i / steps))]
        for i in range(steps + 1)]
    return {'contract':'hhh.cal2.reach','version':1,'status':'ready',
            'physical_radius_max':RADIUS_MAX,'margin_mm':CAL2_REACH_MARGIN_MM,
            'guard':{'format':'auto-pp-calibration-2-v1','polygon':polygon,
                     'radius_min':max(RADIUS_MIN,220),'radius_max':radius,
                     'z_min':WORKSPACE['z'][0],'z_max':WORKSPACE['z'][1]}}


def calibration_safety_snapshot(side):
    try:
        cal = _calibration2_public()
        scope = calibration_session_snapshot()
        session = scope.get('sessions',{}).get(scope.get('active_id'),{})
        if (scope.get('active_side')==side and not scope.get('requires_activation')
                and not scope.get('motion_blocked') and session.get('epoch')==scope.get('epoch')
                and not session.get('paused') and session.get('access_until',0)>time.time()
                and session.get('stage') in ('points','perspective')):
            # Commissioning must work before a camera-to-robot fit exists.
            # Relay still validates the entire path, reach and floor from live
            # feedback; only the unfinished camera hull is inapplicable here.
            _fresh_calibration_measurement(side)
            x0,x1=WORKSPACE['x'];y0,y1=WORKSPACE['y']
            return {'contract':'hhh.cal2.safety','version':1,'status':'ready',
                    'revision':cal.get('revision',1),'session':scope,
                    'guard':{'format':cal['format'],'polygon':[[x0,y0],[x1,y0],[x1,y1],[x0,y1]],
                             'radius_min':max(RADIUS_MIN,220),'radius_max':RADIUS_MAX,
                             'z_min':WORKSPACE['z'][0],'z_max':WORKSPACE['z'][1]}}
        model = CalibrationProjection(cal).models[side]
        if isinstance(model,str):
            raise ValueError(model)
        arm=cal['arms'][side]
        camera_revision=_bound_camera_revision(arm,cal.get('camera_revision'))
        compatibility=None
        if camera_revision:
            current_camera=_current_camera_revision()
            if current_camera != camera_revision:
                raise ValueError(f'{side.title()} camera correction changed. Apply a saved {side.title()} calibration or run {side.title()} calibration in Laser Tag Y before moving.')
            compatibility=_camera_compatibility(arm.get('camera_revision',cal.get('camera_revision')),current_camera)
        identity = cal['arms'][side].get('rig_identity')
        if identity:
            arms = _read_contract('dobot-mg400-relay','arms_snapshot','hhh.relay.arms')
            if arms['arms'][side].get('device')!=identity:
                raise ValueError(f'{side.title()} arm connection changed. Restore the calibrated connection or run {side.title()} calibration in Laser Tag Y.')
        # The six samples validate/map the camera fit, not the physical reach.
        # Keep the fit/identity checks above while permitting the configured
        # workspace beyond those sample centres.
        guard = calibration_reach_snapshot()['guard']
        return {'contract':'hhh.cal2.safety','version':1,'status':'ready','revision':cal.get('revision',1),
                'guard':guard,'session':calibration_session_snapshot(),'camera_compatibility':compatibility}
    except Exception as exc:
        return {'contract':'hhh.cal2.safety','version':1,'status':'unavailable','error':str(exc)}


@bp.before_request
def calibration_reservation_guard():
    active = calibration_session_snapshot().get('active_side')
    if active and request.method == 'POST' and request.path.split('/api/')[-1].startswith(('calibration','direct')):
        return jsonify(ok=False,error='The game owns the calibration session. Use its lesson controls.'),409


def hub_stop():
    global _hub_ctx, _lessons
    if _lessons:
        active = _lessons.snapshot().get('active_side')
        if active:
            try:
                _read_contract('dobot-mg400-relay','stop_side','hhh.relay.stop',active)
            except Exception:
                logging.getLogger(__name__).exception('calibration shutdown stop failed')
    _hub_ctx = None
    _lessons = None


def tracking_projection(tags, arms):
    """hhh.cal2.projection v1: read-only, unrotated corrected-camera/mm mapping."""
    global _tracking_projection_cache
    calibration = _calibration2_public()
    key = json.dumps(calibration, sort_keys=True)
    with _tracking_projection_lock:
        if _tracking_projection_cache[0] != key:
            _tracking_projection_cache = (key, CalibrationProjection(calibration))
        return _tracking_projection_cache[1].project(tags, arms)


def tracking_intent_snapshot():
    """hhh.controller.intent v1: last player report, NOT observed board truth."""
    return _tracking_intents.snapshot()


def _roles():
    return request.environ.get("hhh.roles") or set()


@bp.route("/api/laser-intent", methods=["POST"])
def api_laser_intent():
    """Forward Green Auto PP X intentions to the active Laser Tag run."""
    if "green" not in _roles() and "gamemaster" not in _roles():
        return jsonify({"ok": False, "error": "green role required"}), 403
    data = request.get_json(silent=True) or {}
    kind = str(data.get("kind") or "")[:80]
    laser = _enabled_module("laser-tag")
    if laser is None or not hasattr(laser, "append_external_event"):
        return jsonify({"ok": False, "error": "Laser Tag logging unavailable"}), 503
    event, error = laser.append_external_event(
        "green_auto_pp_x", kind, data.get("detail"), category=data.get("category")
    )
    if error:
        status = 409 if error == "no active Laser Tag run" else 400
        return jsonify({"ok": False, "error": error}), status
    return jsonify({"ok": True, "event": event})


@bp.route("/api/laser-tag-x-intent", methods=["POST"])
def api_laser_tag_x_intent():
    """Forward the authenticated player's LTX intentions to Laser Tag X."""
    if not ({"green", "purple", "gamemaster"} & _roles()):
        return jsonify({"ok": False, "error": "player or gamemaster required"}), 403
    data = request.get_json(silent=True) or {}
    side = _requested_team(data)
    if side not in TEAMS:
        return jsonify({"ok": False, "error": "green or purple team required"}), 400
    kind = str(data.get("kind") or "")[:80]
    detail = dict(data.get("detail")) if isinstance(data.get("detail"), dict) else {}
    detail["team"] = side
    # Keep read-only intent available even without an active legacy X run.
    # The existing logging response and robot command path remain unchanged.
    _tracking_intents.record(side, kind, detail)
    laser = _enabled_module("laser-tag-x")
    if laser is None or not hasattr(laser, "append_external_event"):
        return jsonify({"ok": False, "error": "Laser Tag X logging unavailable"}), 503
    event, error = laser.append_external_event(
        f"{side}_ltx", kind, detail, category=data.get("category")
    )
    if error:
        status = 409 if error == "no active Laser Tag X run" else 400
        return jsonify({"ok": False, "error": error}), status
    return jsonify({"ok": True, "event": event})


@bp.route("/api/ltx-config")
def api_ltx_config():
    """Expose the gamemaster's Laser Tag X game mode to both players."""
    if not ({"green", "purple", "gamemaster"} & _roles()):
        return jsonify({"ok": False, "error": "player or gamemaster required"}), 403
    laser = _enabled_module("laser-tag-x")
    if laser is None or not hasattr(laser, "ltx_config_snapshot"):
        return jsonify({"ok": False, "error": "Laser Tag X configuration unavailable"}), 503
    return jsonify({"ok": True, **laser.ltx_config_snapshot()})


@bp.route("/api/ltx-state")
def api_ltx_state():
    """Expose read-only Laser Tag X timing/game state to both players."""
    if not ({"green", "purple", "gamemaster"} & _roles()):
        return jsonify({"ok": False, "error": "player or gamemaster required"}), 403
    laser = _enabled_module("laser-tag-x")
    if laser is None or not hasattr(laser, "ltx_player_state_snapshot"):
        return jsonify({"ok": False, "error": "Laser Tag X state unavailable"}), 503
    return jsonify({"ok": True, "state": laser.ltx_player_state_snapshot()})


@bp.route("/api/ltx-arms")
def api_ltx_arms():
    """Expose both compact live LTX arm poses to authenticated players."""
    if not ({"green", "purple", "gamemaster"} & _roles()):
        return jsonify({"ok": False, "error": "player or gamemaster required"}), 403
    laser = _enabled_module("laser-tag-x")
    if laser is None or not hasattr(laser, "ltx_player_arms_snapshot"):
        return jsonify({"ok": False, "error": "Laser Tag X arm tracking unavailable"}), 503
    return jsonify({"ok": True, **laser.ltx_player_arms_snapshot()})


def _is_operator():
    return "gamemaster" in _roles()


def _player_side():
    roles = _roles()
    if "green" in roles:
        return "green"
    if "purple" in roles:
        return "purple"
    return ""


def _referrer_side():
    ref = request.headers.get("Referer") or request.headers.get("Referrer") or ""
    for side in TEAMS:
        if f"/s/{side}/" in ref:
            return side
    return ""


def _requested_team(data):
    """The team the caller is allowed to act on: operator may name any team,
    a player only their own."""
    requested = data.get("team")
    if requested in TEAMS and (_is_operator() or requested in _roles()):
        return requested
    return _player_side()


def _read_log_rows():
    if not os.path.exists(LOG_PATH):
        return []
    rows = []
    try:
        with open(LOG_PATH, "r", encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                try:
                    row["elapsed_seconds"] = float(row.get("elapsed_seconds"))
                except (TypeError, ValueError):
                    continue
                rows.append(row)
    except OSError:
        return []
    return rows


def _row_logged_at(row):
    raw = row.get("logged_at")
    if not raw:
        return 0.0
    try:
        return _dt.datetime.fromisoformat(str(raw).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return 0.0


def _load_highscore_reset_at():
    try:
        with open(HIGHSCORE_RESET_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return float(data.get("reset_at", 0.0))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return 0.0


def _save_highscore_reset_at(reset_at):
    with open(HIGHSCORE_RESET_PATH, "w", encoding="utf-8") as fh:
        json.dump({"reset_at": reset_at}, fh, indent=2)


def _highscore_rows(rows=None):
    reset_at = float(_state.get("highscore_reset_at") or 0.0)
    source = _read_log_rows() if rows is None else rows
    if reset_at <= 0:
        return list(source)
    return [row for row in source if _row_logged_at(row) > reset_at]


def _seed_best_from_log():
    best = None
    best_player = ""
    best_team = ""
    for row in _highscore_rows():
        secs = row.get("elapsed_seconds")
        if best is None or secs < best:
            best = secs
            best_player = row.get("player") or ""
            best_team = row.get("team") or ""
    _state["best_seconds"] = best
    _state["best_player"] = best_player
    _state["best_team"] = best_team


def _top_score_rows(rows, limit=10):
    return sorted(
        rows,
        key=lambda row: (
            float(row.get("elapsed_seconds", float("inf"))),
            str(row.get("logged_at") or ""),
        ),
    )[:limit]


def _public_state_locked():
    out = dict(_state)
    out["teams"] = {t: dict(_state["teams"][t]) for t in TEAMS}
    out["server_time"] = time.time()
    return out


def _public_state():
    with _state_lock:
        return _public_state_locked()


def player_names_snapshot():
    """Return the registered player name for each shared player side."""
    with _state_lock:
        return {
            team: str(_state["teams"][team].get("player") or "")
            for team in TEAMS
        }


def _clean_pose(value):
    if not isinstance(value, dict):
        raise ValueError("pose required")
    try:
        return {
            "set": True,
            "x": round(float(value["x"]), 3),
            "y": round(float(value["y"]), 3),
            "z": round(float(value["z"]), 3),
            "r": round(float(value.get("r", 0.0)), 3),
        }
    except (KeyError, TypeError, ValueError):
        raise ValueError("pose must include numeric x, y, z, r")


def _clean_corner_map(value):
    if not isinstance(value, dict):
        raise ValueError("corner map required")
    out = {}
    used = set()
    for key in CORNER_KEYS:
        try:
            marker = int(value[key])
        except (KeyError, TypeError, ValueError):
            raise ValueError(f"{key.replace('_', ' ')} marker required")
        if marker not in CORNER_MARKERS:
            raise ValueError("corner markers must use the four displayed corner tag numbers")
        if marker in used:
            raise ValueError("each corner must use a different tag number")
        out[key] = marker
        used.add(marker)
    return out


def _clean_active_area(value):
    if not isinstance(value, dict):
        raise ValueError("active area required")
    try:
        s_min = float(value["sMin"])
        s_max = float(value["sMax"])
        t_min = float(value["tMin"])
        t_max = float(value["tMax"])
    except (KeyError, TypeError, ValueError):
        raise ValueError("active area requires numeric sMin, sMax, tMin, tMax")
    # Match the player calibration editor: permit one full calibrated-field
    # width of extrapolation while the UI marks unreachable cells separately.
    lo = -1.0
    hi = 2.0
    s_min = _clamp(s_min, lo, hi)
    s_max = _clamp(s_max, lo, hi)
    t_min = _clamp(t_min, lo, hi)
    t_max = _clamp(t_max, lo, hi)
    if s_max - s_min < 0.05 or t_max - t_min < 0.05:
        raise ValueError("active area is too small")
    return {
        "sMin": round(s_min, 4),
        "sMax": round(s_max, 4),
        "tMin": round(t_min, 4),
        "tMax": round(t_max, 4),
    }


def _clean_marker_cache(value):
    if not isinstance(value, dict):
        raise ValueError("marker cache required")
    tags = value.get("tags")
    if not isinstance(tags, dict):
        raise ValueError("marker cache requires tags")
    out_tags = {}
    for key in ("top_left", "top_right", "bottom_right", "bottom_left", "center"):
        tag = tags.get(key)
        if not isinstance(tag, dict):
            raise ValueError(f"{key.replace('_', ' ')} marker cache required")
        try:
            nx = _clamp(float(tag["nx"]), 0.0, 1.0)
            ny = _clamp(float(tag["ny"]), 0.0, 1.0)
            marker_id = int(tag.get("id", tag.get("marker", 0)))
        except (KeyError, TypeError, ValueError):
            raise ValueError(f"{key.replace('_', ' ')} marker cache requires numeric nx and ny")
        out_tags[key] = {
            "id": marker_id,
            "nx": round(nx, 6),
            "ny": round(ny, 6),
            "missing": 0.0,
        }
    captured_at = value.get("capturedAt", value.get("captured_at", value.get("captured_at_ms")))
    try:
        captured_at = int(float(captured_at))
    except (TypeError, ValueError):
        captured_at = int(time.time() * 1000)
    camera_view = str(value.get("cameraView") or value.get("camera_view") or "normal")
    if camera_view not in ("normal", "rot180"):
        camera_view = "normal"
    return {"tags": out_tags, "capturedAt": captured_at, "cameraView": camera_view}


def _calibration_side(data):
    data = data if isinstance(data, dict) else {}
    side = (
        data.get("side")
        or data.get("team")
        or request.values.get("side")
        or request.values.get("team")
        or request.headers.get("X-HHH-Team")
        or request.headers.get("X-Team")
    )
    side = str(side or "").strip().lower()
    player = _player_side()
    if side in TEAMS:
        if _is_operator() or player == side:
            return side
    if player in TEAMS and (not side or side == player):
        return player
    if _is_operator():
        hint = _referrer_side()
        if hint in TEAMS:
            return hint
    active = [team for team in TEAMS if _calibration_access.get(team, {}).get("enabled")]
    if len(active) == 1:
        return active[0]
    return None


def _ok(**kw):
    return jsonify({"ok": True, **kw})


def _fail(error, **kw):
    return jsonify({"ok": False, "error": error, **kw})


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _clamp_pose(x, y, z, r):
    z = _clamp(z, *WORKSPACE["z"])
    r = _clamp(r, *WORKSPACE["r"])
    radius = math.hypot(x, y)
    if radius == 0.0:
        x, y = RADIUS_MIN, 0.0
    elif radius > RADIUS_MAX:
        scale = RADIUS_MAX / radius
        x, y = x * scale, y * scale
    elif radius < RADIUS_MIN:
        scale = RADIUS_MIN / radius
        x, y = x * scale, y * scale
    return _clamp(x, *WORKSPACE["x"]), _clamp(y, *WORKSPACE["y"]), z, r


def _pump_mode(do_bits):
    suck = bool(do_bits & (1 << (SUCK_DO_INDEX - 1)))
    blow = bool(do_bits & (1 << (BLOW_DO_INDEX - 1)))
    if suck and blow:
        return "conflict"
    if suck:
        return "suck"
    if blow:
        return "blow"
    return "off"


def _calibration_from_saved(saved):
    base = _default_calibration()
    if not isinstance(saved, dict):
        return base
    saved_playfield = saved.get("playfield") if isinstance(saved.get("playfield"), dict) else {}
    saved_areas = saved_playfield.get("areas") if isinstance(saved_playfield.get("areas"), dict) else {}
    try:
        base["playfield"]["active_area"] = _clean_active_area(saved_playfield.get("active_area"))
    except ValueError:
        active_area = saved.get("active_area")
        if isinstance(active_area, dict):
            try:
                base["playfield"]["active_area"] = _clean_active_area(active_area)
            except ValueError:
                pass
    try:
        base["playfield"]["marker_cache"] = _clean_marker_cache(saved_playfield.get("marker_cache"))
    except ValueError:
        pass
    for key in base["playfield"]["areas"]:
        area = saved_areas.get(key)
        if isinstance(area, dict):
            base["playfield"]["areas"][key]["area_id"] = area.get("area_id")
    try:
        base["playfield"]["corner_map"] = _clean_corner_map(saved_playfield.get("corner_map"))
    except ValueError:
        pass
    global_corner_map = base["playfield"]["corner_map"]
    base["playfield"]["updated_at"] = saved_playfield.get("updated_at")
    saved_arms = saved.get("arms") if isinstance(saved.get("arms"), dict) else saved
    for side in TEAMS:
        src = saved_arms.get(side) if isinstance(saved_arms, dict) else None
        if not isinstance(src, dict):
            continue
        try:
            base["arms"][side]["corner_map"] = _clean_corner_map(src.get("corner_map"))
        except ValueError:
            base["arms"][side]["corner_map"] = dict(global_corner_map)
        try:
            base["arms"][side]["marker_cache"] = _clean_marker_cache(src.get("marker_cache"))
        except ValueError:
            pass
        for key in base["arms"][side]["points"]:
            pose = (((src.get("points") or {}).get(key) or {}).get("pose"))
            if isinstance(pose, dict) and pose.get("set"):
                try:
                    base["arms"][side]["points"][key]["pose"] = _clean_pose(pose)
                except ValueError:
                    pass
        for target in ("center",):
            pose = src.get(target)
            if isinstance(pose, dict) and pose.get("set"):
                try:
                    base["arms"][side][target] = _clean_pose(pose)
                except ValueError:
                    pass
        for target in ("pickup_height", "transport_height"):
            h = src.get(target)
            if isinstance(h, dict) and h.get("set"):
                try:
                    base["arms"][side][target] = {"set": True, "z": round(float(h["z"]), 3)}
                except (KeyError, TypeError, ValueError):
                    pass
        base["arms"][side]["updated_at"] = src.get("updated_at")
    return base


def _load_calibration():
    global _calibration
    try:
        with open(CALIBRATION_PATH, "r", encoding="utf-8") as fh:
            saved = json.load(fh)
    except (OSError, ValueError, TypeError):
        return
    base = _calibration_from_saved(saved)
    _calibration = base


def _save_calibration():
    atomic_json(CALIBRATION_PATH, _calibration)


def _calibration2_from_saved(saved):
    """Validate a saved Cal 2 document without changing live state."""
    base = _default_calibration2()
    if not isinstance(saved, dict):
        return base
    for key, target in ((saved.get("playfield") or {}).get("targets") or {}).items():
        if key in base["playfield"]["targets"] and isinstance(target, dict):
            base["playfield"]["targets"][key].update({
                field: target.get(field)
                for field in ("s", "t", "area_id") if target.get(field) is not None
            })
    fixed_snapshot = _fixed_cal2_playfield()
    if fixed_snapshot:
        canonical = _cal2_snapshot_coordinates(fixed_snapshot)
        for target in base["playfield"]["targets"].values():
            if target["marker"] in canonical:
                target.update(canonical[target["marker"]])
    saved_areas = (saved.get("playfield") or {}).get("saved_areas")
    if isinstance(saved_areas, list):
        base["playfield"]["saved_areas"] = json.loads(json.dumps(saved_areas))
    saved_settings = (saved.get("playfield") or {}).get("saved_settings")
    if isinstance(saved_settings, dict):
        base["playfield"]["saved_settings"] = json.loads(json.dumps(saved_settings))
    saved_view = (saved.get("playfield") or {}).get("saved_camera_view")
    if saved_view in ("normal", "rot180"):
        base["playfield"]["saved_camera_view"] = saved_view
    try:
        base["playfield"]["active_area"] = _clean_active_area(
            (saved.get("playfield") or {}).get("active_area"))
    except ValueError:
        pass
    for side in TEAMS:
        base["arms"][side]["rig_identity"]=(saved.get("arms",{}).get(side) or {}).get("rig_identity")
        arm = ((saved.get("arms") or {}).get(side) or {})
        if 'camera_revision' in arm:base['arms'][side]['camera_revision']=arm['camera_revision']
        if 'camera_binding' in arm:base['arms'][side]['camera_binding']=copy.deepcopy(arm['camera_binding'])
        if 'transport_height' in arm:
            height=arm['transport_height']
            if type(height) not in (int,float) or not math.isfinite(height) or not WORKSPACE['z'][0]<=height<=WORKSPACE['z'][1]:
                raise ValueError('Invalid saved arm transport height')
            base['arms'][side]['transport_height']=height
        if arm.get("camera_view") in ("normal", "rot180"):
            base["arms"][side]["camera_view"] = arm["camera_view"]
        for key, point in (arm.get("points") or {}).items():
            if key not in base["arms"][side]["points"] or not isinstance(point, dict):
                continue
            camera = point.get("camera")
            if isinstance(camera, dict):
                try:
                    base["arms"][side]["points"][key]["camera"] = {
                        "u": float(camera["u"]), "v": float(camera["v"])
                    }
                except (KeyError, TypeError, ValueError):
                    pass
            pose = point.get("pose")
            if isinstance(pose, dict) and pose.get("set"):
                try:
                    base["arms"][side]["points"][key]["pose"] = _clean_pose(pose)
                except ValueError:
                    pass
        for marker, sample in (arm.get("parallax_points") or {}).items():
            marker_key = str(marker)
            try:
                base["arms"][side]["parallax_points"][marker_key] = \
                    _clean_cal2_parallax_sample(marker, sample)
            except (KeyError, ValueError):
                pass
        base["arms"][side]["updated_at"] = arm.get("updated_at")
        try:
            stack_drop_offset = float(arm["stack_drop_offset"])
            if math.isfinite(stack_drop_offset) and 0 <= stack_drop_offset <= 100:
                base["arms"][side]["stack_drop_offset"] = stack_drop_offset
        except (KeyError, TypeError, ValueError):
            pass
    base["revision"] = saved.get("revision", 1) if type(saved.get("revision", 1)) is int else 1
    base["camera_revision"] = saved.get("camera_revision")
    base["lesson_receipt"] = saved.get("lesson_receipt")
    selections=saved.get('saved_selection',{})
    if isinstance(selections,dict):
        base['saved_selection']={side:copy.deepcopy(value) for side,value in selections.items() if side in TEAMS and isinstance(value,dict)
                                 and isinstance(value.get('policy'),str) and isinstance(value.get('active_id'),str)}
    shared_z = saved.get("shared_z") or {}
    try:
        base["shared_z"]["transport_height"] = float(shared_z["transport_height"])
    except (KeyError, TypeError, ValueError):
        pass
    # Older Cal 2 files stored one pickup Z for both robots. Copy that Cal 2
    # value to each arm on migration; the removed four-corner calibration is
    # deliberately not consulted.
    for side in TEAMS:
        arm = ((saved.get("arms") or {}).get(side) or {})
        candidates = [arm.get("pickup_height"), shared_z.get("pickup_height")]
        for candidate in candidates:
            try:
                value = float(candidate)
                if math.isfinite(value):
                    base["arms"][side]["pickup_height"] = value
                    break
            except (TypeError, ValueError):
                pass
    base["playfield"]["updated_at"] = (saved.get("playfield") or {}).get("updated_at")
    return base


def _load_calibration2():
    global _calibration2
    try:
        with open(CALIBRATION2_PATH, "r", encoding="utf-8") as fh:
            saved = json.load(fh)
    except (OSError, ValueError, TypeError):
        return
    if not isinstance(saved, dict):
        return
    base = _calibration2_from_saved(saved)
    _calibration2 = base


def _save_calibration2():
    atomic_json(CALIBRATION2_PATH, _calibration2)


def _calibration2_public():
    with _calibration_lock:
        value = json.loads(json.dumps(_calibration2))
    value['motion_envelope'] = calibration_reach_snapshot()
    return value


def _fixed_cal2_playfield():
    try:
        with open(FIXED_CAL2_PLAYFIELD_PATH, "r", encoding="utf-8") as fh:
            snapshot = json.load(fh)
    except (OSError, ValueError, TypeError):
        return None
    areas = snapshot.get("areas") if isinstance(snapshot, dict) else None
    if not isinstance(areas, list) or len(areas) != len(CAL2_MARKERS):
        return None
    try:
        if {int(area["marker"]) for area in areas} != set(CAL2_MARKERS):
            return None
    except (KeyError, TypeError, ValueError):
        return None
    return snapshot


def _cal2_snapshot_coordinates(snapshot):
    """Return immutable logical target coordinates from a saved field."""
    coordinates = {}
    for area in snapshot.get("areas") or ():
        try:
            marker = int(area["marker"])
            x, z = float(area["x"]), float(area["z"])
        except (KeyError, TypeError, ValueError):
            continue
        coordinates[marker] = {
            "s": round((1.0-x/CALIBRATION_TAG_SPAN_X)/2.0, 6),
            "t": round((1.0-z/CALIBRATION_TAG_SPAN_Z)/2.0, 6),
        }
    return coordinates


def _solve_linear_system(matrix, values):
    """Solve a small dense linear system with pivoted elimination."""
    size = len(values)
    rows = [list(map(float, matrix[i])) + [float(values[i])]
            for i in range(size)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(rows[row][column]))
        if abs(rows[pivot][column]) < 1e-10:
            return None
        rows[column], rows[pivot] = rows[pivot], rows[column]
        divisor = rows[column][column]
        rows[column] = [value/divisor for value in rows[column]]
        for row in range(size):
            if row == column:
                continue
            factor = rows[row][column]
            rows[row] = [
                value-factor*rows[column][index]
                for index, value in enumerate(rows[row])
            ]
    return [rows[index][-1] for index in range(size)]


def _cal2_robot_model(side):
    """Fit this arm's six Cal 2 poses in canonical field coordinates."""
    arm = _calibration2.get("arms", {}).get(side, {})
    points = arm.get("points") or {}
    targets = _calibration2.get("playfield", {}).get("targets") or {}
    samples = []
    for key in targets:
        point, target = points.get(key) or {}, targets[key]
        pose = point.get("pose") or {}
        try:
            if not pose.get("set"):
                return None
            s, t = float(target["s"]), float(target["t"])
            x, y = float(pose["x"]), float(pose["y"])
        except (KeyError, TypeError, ValueError):
            return None
        samples.append(([1.0, s, t, s*t], x, y))
    if len(samples) != len(CAL2_MARKERS):
        return None
    normal = [[0.0]*4 for _ in range(4)]
    rhs_x, rhs_y = [0.0]*4, [0.0]*4
    for features, x, y in samples:
        for row in range(4):
            rhs_x[row] += features[row]*x
            rhs_y[row] += features[row]*y
            for column in range(4):
                normal[row][column] += features[row]*features[column]
    coefficients_x = _solve_linear_system(normal, rhs_x)
    coefficients_y = _solve_linear_system(normal, rhs_y)
    if coefficients_x is None or coefficients_y is None:
        return None
    return coefficients_x, coefficients_y


def _cal2_robot_xy(side, s, t, model=None):
    """Map a canonical field point through this arm's own Cal 2 reach model."""
    model = model if model is not None else _cal2_robot_model(side)
    if model is None:
        return None
    features = (1.0, float(s), float(t), float(s)*float(t))
    return tuple(sum(value*coefficient for value, coefficient in zip(features, axis))
                 for axis in model)


def _cal2_axis_positions():
    area = _calibration2["playfield"].get("active_area") or {}
    s0, s1 = float(area.get("sMin", 0)), float(area.get("sMax", 1))
    t0, t1 = float(area.get("tMin", 0)), float(area.get("tMax", 1))
    # Convert the requested 20 mm robot-space inset to normalized field units.
    spans = []
    for side in TEAMS:
        model = _cal2_robot_model(side)
        a = _cal2_robot_xy(side, s0, (t0+t1)/2, model)
        b = _cal2_robot_xy(side, s1, (t0+t1)/2, model)
        c = _cal2_robot_xy(side, (s0+s1)/2, t0, model)
        d = _cal2_robot_xy(side, (s0+s1)/2, t1, model)
        if a and b:
            spans.append((abs(s1-s0) * 20.0 / max(1.0, math.dist(a, b)), "s"))
        if c and d:
            spans.append((abs(t1-t0) * 20.0 / max(1.0, math.dist(c, d)), "t"))
    inset_s = max([v for v, axis in spans if axis == "s"] or [abs(s1-s0)*0.05])
    inset_t = max([v for v, axis in spans if axis == "t"] or [abs(t1-t0)*0.05])
    inset_s = min(inset_s, abs(s1-s0)*0.22)
    inset_t = min(inset_t, abs(t1-t0)*0.22)
    return (
        [s0 + inset_s, (s0+s1)/2, s1 - inset_s],
        [t0 + inset_t, (t0+t1)/2, t1 - inset_t],
    )


def _cal2_safe_at(s, t, selected_side=None, models=None):
    sides = (selected_side,) if selected_side in TEAMS else TEAMS
    for side in sides:
        model = (models or {}).get(side) if models is not None else None
        xy = _cal2_robot_xy(side, s, t, model)
        if xy is None:
            continue
        radius = math.hypot(*xy)
        if radius < CAL2_RADIUS_MIN or radius > CAL2_RADIUS_MAX:
            return False
    return True


def _cal2_safe_at_view(s, t, selected_side=None, rotate_layout=False, models=None):
    """Test canonical reach; camera rotation affects only rendered coordinates."""
    return _cal2_safe_at(s, t, selected_side, models)


def _cal2_reachable_contour(side, rotate_layout=False):
    """Return three left/centre/right rows following this arm's usable contour.

    This samples the same per-arm six-point model used by the player's red
    reach overlay. Coordinates remain canonical; camera rotation is applied
    only when the physical marker areas are created.
    """
    ss, ts = _cal2_axis_positions()
    s_lo, s_hi = min(ss[0], ss[2]), max(ss[0], ss[2])
    t_lo, t_hi = min(ts[0], ts[2]), max(ts[0], ts[2])
    rows = []
    models = {side: _cal2_robot_model(side)}
    s_steps, t_steps = 320, 220
    for row_index in range(t_steps + 1):
        t = t_lo + (t_hi-t_lo) * row_index / t_steps
        runs, run = [], []
        for col_index in range(s_steps + 1):
            s = s_lo + (s_hi-s_lo) * col_index / s_steps
            if _cal2_safe_at_view(s, t, side, rotate_layout, models):
                run.append(s)
            elif run:
                runs.append(run)
                run = []
        if run:
            runs.append(run)
        if not runs:
            continue
        widest = max(runs, key=lambda values: values[-1]-values[0])
        rows.append({
            "t": t, "lo": widest[0], "hi": widest[-1],
            "width": widest[-1]-widest[0],
        })
    if not rows:
        return None
    max_width = max(row["width"] for row in rows)
    useful = [row for row in rows if row["width"] >= max_width * 0.30]
    if len(useful) < 3:
        useful = rows
    selected = [useful[0], useful[len(useful)//2], useful[-1]]
    result = []
    for row in selected:
        result.extend([
            (row["lo"], row["t"]),
            ((row["lo"]+row["hi"])/2.0, row["t"]),
            (row["hi"], row["t"]),
        ])
    return result


def _set_cal2_arm_view_locked(side, view):
    arm = _calibration2["arms"][side]
    if arm.get("camera_view") != view:
        # Raised/ground camera coordinates belong to the orientation in which
        # they were captured, so changing the authoritative view invalidates
        # only this player's parallax samples.
        arm["parallax_points"] = _empty_cal2_parallax_points()
    arm["camera_view"] = view
    arm["updated_at"] = time.time()


def _ensure_playfield_calibration2_areas(side=None, camera_view=None):
    playfield = _playfield_module()
    if playfield is None or not hasattr(playfield, "remove_area"):
        return False, "Playfield Areas prototype is not loaded"
    for area in list(playfield.list_areas()):
        area_id = area.get("id")
        if area_id:
            playfield.remove_area(area_id)
    fixed_snapshot = _fixed_cal2_playfield()
    saved_areas = (fixed_snapshot.get("areas") if fixed_snapshot else
                   _calibration2["playfield"].get("saved_areas"))
    # Laser Tag also uses the Cal 2 marker range. Older controller code accidentally
    # adopted whatever happened to be on the shared playfield on page load,
    # so reject that foreign snapshot and reconstruct the original Cal 2 field
    # from its already-captured robot calibration points.
    if isinstance(saved_areas, list) and any(
            str(area.get("name", "")).startswith("Laser Tag")
            for area in saved_areas if isinstance(area, dict)):
        with _calibration_lock:
            _calibration2["playfield"]["saved_areas"] = None
            _calibration2["playfield"]["saved_settings"] = None
            _save_calibration2()
        saved_areas = None
    if isinstance(saved_areas, list) and len(saved_areas) == len(CAL2_MARKERS):
        requested_view = camera_view if camera_view in ("normal", "rot180") else \
            (_calibration2["arms"][side].get("camera_view", "normal")
             if side in TEAMS else _calibration2["playfield"].get("saved_camera_view", "normal"))
        saved_view = (fixed_snapshot.get("camera_view", "normal")
                      if fixed_snapshot else
                      _calibration2["playfield"].get("saved_camera_view", "normal"))
        rotate_saved = requested_view != saved_view
        created = {}
        canonical = _cal2_snapshot_coordinates({"areas": saved_areas})
        for saved in saved_areas:
            fields = {
                key: saved[key]
                for key in (
                    "name", "x", "y", "z", "size", "color", "glow", "marker",
                    "show_area", "show_aruco", "show_links",
                )
                if key in saved
            }
            if rotate_saved:
                fields["x"] = -float(fields.get("x", 0.0))
                fields["z"] = -float(fields.get("z", 0.0))
            area = playfield.create_area(**fields)
            if area:
                created[int(area["marker"])] = area
        with _calibration_lock:
            if side in TEAMS:
                _set_cal2_arm_view_locked(side, requested_view)
            for target in _calibration2["playfield"]["targets"].values():
                area = created.get(target["marker"])
                logical = canonical.get(target["marker"])
                if not area or not logical:
                    continue
                target.update({
                    **logical,
                    "area_id": area.get("id"),
                })
            _calibration2["playfield"]["updated_at"] = time.time()
            _save_calibration2()
        saved_settings = (fixed_snapshot.get("settings") if fixed_snapshot else
                          _calibration2["playfield"].get("saved_settings"))
        if isinstance(saved_settings, dict) and hasattr(playfield, "set_view_settings"):
            playfield.set_view_settings(**saved_settings)
        else:
            _reset_playfield_camera(playfield)
        if hasattr(playfield, "save_areas_now"):
            playfield.save_areas_now()
        return True, None
    ss, ts = _cal2_axis_positions()
    view = camera_view if camera_view in ("normal", "rot180") else \
        (_calibration2["arms"][side].get("camera_view", "normal")
         if side in TEAMS else "normal")
    rotate_layout = side in TEAMS and view == "rot180"
    candidates = None
    if side in TEAMS:
        candidates = _cal2_reachable_contour(side, rotate_layout)
    if candidates is None:
        candidates = [(s, t) for t in ts for s in ss]
    # Pull an unsafe candidate toward the field centre until it is 20 mm
    # inside both robot reach rings.
    center_s, center_t = ss[1], ts[1]
    safe = []
    models = {side: _cal2_robot_model(side)} if side in TEAMS else None
    for s, t in candidates:
        for _ in range(20):
            if _cal2_safe_at_view(s, t, side, rotate_layout, models):
                break
            s = center_s + (s-center_s)*0.9
            t = center_t + (t-center_t)*0.9
        safe.append((s, t))
    with _calibration_lock:
        target_items = list(_calibration2["playfield"]["targets"].items())
        if side in TEAMS:
            _set_cal2_arm_view_locked(side, view)
        for (key, target), (s, t) in zip(target_items, safe):
            # Keep logical coordinates canonical. Only physical marker
            # placement follows the selected camera orientation.
            display_s, display_t = ((1.0-s, 1.0-t)
                                    if rotate_layout else (s, t))
            fields = {
                "name": f"Auto PP Cal 2 - {target['label']}",
                "x": CALIBRATION_TAG_SPAN_X * (1.0 - 2.0*display_s),
                "y": 0.02,
                "z": CALIBRATION_TAG_SPAN_Z * (1.0 - 2.0*display_t),
                "size": CALIBRATION_TAG_SIZE,
                "color": "#ffffff", "glow": 0.0,
                "marker": target["marker"],
                "show_area": False, "show_aruco": True, "show_links": False,
            }
            area = playfield.create_area(**fields)
            target.update({"s": round(s, 6), "t": round(t, 6),
                           "area_id": area.get("id") if area else None})
        _calibration2["playfield"]["updated_at"] = time.time()
        _save_calibration2()
    _reset_playfield_camera(playfield)
    if hasattr(playfield, "save_areas_now"):
        playfield.save_areas_now()
    return True, None


def _adopt_current_playfield_calibration2(side=None, camera_view=None):
    """Use the currently rendered marker objects without moving them."""
    playfield = _playfield_module()
    if playfield is None or not hasattr(playfield, "list_areas"):
        return False, "Playfield Areas prototype is not loaded"
    by_marker = {}
    for area in playfield.list_areas():
        try:
            marker = int(area.get("marker"))
        except (TypeError, ValueError):
            continue
        if marker in CAL2_MARKERS and area.get("show_aruco", True):
            by_marker[marker] = area
    missing = [marker for marker in CAL2_MARKERS if marker not in by_marker]
    if missing:
        return False, "current playfield is missing Cal 2 markers: " + \
            ", ".join(str(marker) for marker in missing)
    with _calibration_lock:
        saved_areas = []
        for target in _calibration2["playfield"]["targets"].values():
            area = by_marker[target["marker"]]
            try:
                x, z = float(area["x"]), float(area["z"])
            except (KeyError, TypeError, ValueError):
                return False, f"marker {target['marker']} has invalid playfield coordinates"
            target.update({
                "s": round((1.0-x/CALIBRATION_TAG_SPAN_X)/2.0, 6),
                "t": round((1.0-z/CALIBRATION_TAG_SPAN_Z)/2.0, 6),
                "area_id": area.get("id"),
            })
            saved_areas.append({
                key: area[key]
                for key in (
                    "name", "x", "y", "z", "size", "color", "glow", "marker",
                    "show_area", "show_aruco", "show_links",
                )
                if key in area
            })
        _calibration2["playfield"]["saved_areas"] = saved_areas
        if hasattr(playfield, "get_view_settings"):
            settings = playfield.get_view_settings()
            if isinstance(settings, dict):
                _calibration2["playfield"]["saved_settings"] = settings
        view = camera_view if camera_view in ("normal", "rot180") else \
            (_calibration2["arms"][side].get("camera_view", "normal")
             if side in TEAMS else "normal")
        if side in TEAMS:
            _set_cal2_arm_view_locked(side, view)
        _calibration2["playfield"]["saved_camera_view"] = view
        _calibration2["playfield"]["updated_at"] = time.time()
        _save_calibration2()
    return True, None


def _calibration_public():
    with _calibration_lock:
        return json.loads(json.dumps(_calibration))


def _calibration_access_public():
    return {
        "active_side": next((side for side in TEAMS if _calibration_access[side]["enabled"]), ""),
        "teams": {side: dict(_calibration_access[side]) for side in TEAMS},
    }


def _calibration_write_allowed(data=None):
    if _is_operator():
        return True, None
    side = _player_side()
    if side in TEAMS and _calibration_access[side]["enabled"]:
        return True, None
    return False, f"{side or 'player'} calibration is not enabled by the gamemaster"


def hub_init(ctx):
    global _hub_ctx
    _hub_ctx = ctx
    _load_calibration()
    _load_calibration2()
    _start_lessons()
    # Loading the prototype must be read-only. Calibration fields are shared
    # with other games, so only the explicit playfield endpoints below may
    # replace the currently active areas or camera settings.


def _playfield_module():
    return _enabled_module("playfield-areas")


def _relay_module():
    return _enabled_module("dobot-mg400-relay")


def _kick_relay_side(side):
    relay = _relay_module()
    if relay is None or not hasattr(relay, "kick_side"):
        return False
    return bool(relay.kick_side(side))


def _playfield_pose_for(key):
    # Calibration markers are mirrored around the center tag.
    return {
        "top_left": {"x": CALIBRATION_TAG_SPAN_X, "z": CALIBRATION_TAG_SPAN_Z},
        "top_right": {"x": -CALIBRATION_TAG_SPAN_X, "z": CALIBRATION_TAG_SPAN_Z},
        "bottom_right": {"x": -CALIBRATION_TAG_SPAN_X, "z": -CALIBRATION_TAG_SPAN_Z},
        "bottom_left": {"x": CALIBRATION_TAG_SPAN_X, "z": -CALIBRATION_TAG_SPAN_Z},
        "center": {"x": 0.0, "z": 0.0},
    }[key]


def _reset_playfield_camera(playfield):
    if not hasattr(playfield, "set_view_settings"):
        return
    playfield.set_view_settings(
        bloom=0.0,
        dof=0.0,
        fov=24.0,
        cam={"x": 0.0, "y": 18.0, "z": 0.0},
        rot={"x": -90.0, "y": 0.0, "z": 0.0},
    )


def _ensure_playfield_calibration_areas():
    playfield = _playfield_module()
    if playfield is None:
        return False, "Playfield Areas prototype is not loaded"
    if not hasattr(playfield, "remove_area"):
        return False, "Playfield Areas controller cannot delete areas"
    for area in list(playfield.list_areas()):
        area_id = area.get("id")
        if area_id:
            playfield.remove_area(area_id)
    with _calibration_lock:
        for key, area_ref in _calibration["playfield"]["areas"].items():
            label = area_ref["label"]
            name = f"Auto Pick Calibration - {label}"
            pos = _playfield_pose_for(key)
            fields = {
                "name": name,
                "x": pos["x"],
                "y": 0.02,
                "z": pos["z"],
                "size": CALIBRATION_TAG_SIZE,
                "color": "#ffffff",
                "glow": 0.0,
                "marker": area_ref["marker"],
                "show_area": False,
                "show_aruco": True,
                "show_links": False,
            }
            area = playfield.create_area(**fields)
            if area:
                area_ref["area_id"] = area["id"]
        _calibration["playfield"]["marker_cache"] = None
        _calibration["playfield"]["updated_at"] = time.time()
        _save_calibration()
    _reset_playfield_camera(playfield)
    if hasattr(playfield, "save_areas_now"):
        playfield.save_areas_now()
    return True, None


def _saved_playfield_payload(areas):
    return {
        "format": "auto-pick-and-place-playfield-v1",
        "saved_at": _dt.datetime.now(_dt.UTC).isoformat(),
        "areas": json.loads(json.dumps(areas)),
    }


def _sync_calibration_area_refs(areas):
    by_name = {area.get("name"): area.get("id") for area in areas if isinstance(area, dict)}
    with _calibration_lock:
        changed = False
        for key, area_ref in _calibration["playfield"]["areas"].items():
            name = f"Auto Pick Calibration - {area_ref['label']}"
            area_id = by_name.get(name)
            if area_id and area_ref.get("area_id") != area_id:
                area_ref["area_id"] = area_id
                changed = True
        if changed:
            _calibration["playfield"]["updated_at"] = time.time()
            _save_calibration()
        return json.loads(json.dumps(_calibration))


@bp.route("/")
@bp.route("/game")
def game():
    resp = send_from_directory(HERE, "game.html")
    resp.headers["Cache-Control"] = "no-store, max-age=0"
    return resp


@bp.route("/api/state")
def api_state():
    return jsonify(_public_state())


@bp.route("/api/events")
def api_events():
    return _live.stream(_public_state, interval=0.2)


@bp.route("/api/calibration")
def api_calibration():
    return jsonify({
        "ok": True,
        "calibration": _calibration_public(),
        "access": _calibration_access_public(),
    })


@bp.route("/api/calibration/access", methods=["GET", "POST"])
def api_calibration_access():
    if request.method == "GET":
        return jsonify({"ok": True, "access": _calibration_access_public()})
    if not _is_operator():
        return jsonify({"ok": False, "error": "gamemaster required"}), 403
    data = request.get_json(silent=True) or {}
    side = data.get("side") or data.get("team")
    if side not in TEAMS:
        return jsonify({"ok": False, "error": "team required"}), 400
    enabled = bool(data.get("enabled", True))
    now = time.time()
    kicked = []
    if enabled:
        for other in TEAMS:
            _calibration_access[other]["enabled"] = other == side
            _calibration_access[other]["updated_at"] = now
            if other != side and _kick_relay_side(other):
                kicked.append(other)
    else:
        _calibration_access[side]["enabled"] = False
        _calibration_access[side]["updated_at"] = now
    _live.bump()
    return jsonify({"ok": True, "access": _calibration_access_public(), "kicked": kicked})


@bp.route("/api/calibration/playfield", methods=["POST"])
def api_calibration_playfield():
    ok, err = _calibration_write_allowed()
    if not ok:
        return jsonify({"ok": False, "error": err}), 403
    ok, err = _ensure_playfield_calibration_areas()
    if not ok:
        return jsonify({"ok": False, "error": err}), 409
    return jsonify({"ok": True, "calibration": _calibration_public()})


@bp.route("/api/calibration2")
def api_calibration2():
    return jsonify({"ok": True, "calibration": _calibration2_public(),
                    "access": _calibration_access_public()})


@bp.route("/api/calibration2/export.zip", methods=["POST"])
def api_calibration2_export_zip():
    """Download Cal 2 state without activating or modifying it."""
    if not (_is_operator() or _player_side() in TEAMS):
        return jsonify({"ok": False, "error": "team or gamemaster required"}), 403
    side = _player_side() or "all"
    calibration = _calibration2_public()
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "auto-calibration-2.json",
            json.dumps(calibration, indent=2, sort_keys=True),
        )
        zf.writestr(
            "calibration-info.json",
            json.dumps({
                "format": "auto-pp-calibration-2-export-v1",
                "side": side,
                "exported_at": _dt.datetime.now(_dt.UTC).isoformat(),
                "active_area": calibration["playfield"]["active_area"],
            }, indent=2, sort_keys=True),
        )
    payload.seek(0)
    return Response(
        payload.getvalue(),
        mimetype="application/zip",
        headers={
            "Content-Disposition":
                f"attachment; filename=auto-pp-cal-2-{side}.zip"
        },
    )


@bp.route("/api/calibration2/import.zip", methods=["POST"])
def api_calibration2_import_zip():
    """Restore saved Cal 2 state only after an explicit, authorized upload."""
    global _calibration2
    player_side = _player_side()
    ok, err = _calibration_write_allowed()
    if not ok:
        return jsonify({"ok": False, "error": err}), 403
    upload = request.files.get("file")
    if upload is None:
        return jsonify({"ok": False, "error": "zip file required"}), 400
    try:
        raw = upload.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024:
            raise ValueError("calibration zip is larger than 2 MB")
        with zipfile.ZipFile(io.BytesIO(raw), "r") as zf:
            if "auto-calibration-2.json" not in zf.namelist():
                raise ValueError("auto-calibration-2.json missing from zip")
            info = zf.getinfo("auto-calibration-2.json")
            if info.file_size > 2 * 1024 * 1024:
                raise ValueError("calibration document is larger than 2 MB")
            saved = json.loads(
                zf.read("auto-calibration-2.json").decode("utf-8"))
    except (OSError, UnicodeDecodeError, zipfile.BadZipFile,
            json.JSONDecodeError, ValueError) as exc:
        return jsonify({
            "ok": False, "error": f"invalid Cal 2 calibration zip: {exc}"
        }), 400
    if not isinstance(saved, dict) or \
            saved.get("format") != "auto-pp-calibration-2-v1":
        return jsonify({
            "ok": False,
            "error": "uploaded file is not an Auto PP Cal 2 calibration",
        }), 400
    imported = _calibration2_from_saved(saved)
    with _calibration_lock:
        if _is_operator():
            _calibration2 = imported
        else:
            # A player restores only their arm plus the two intentionally shared
            # values. Do not replace the live playfield, target object IDs, or
            # the other player's calibration.
            _calibration2["arms"][player_side] = imported["arms"][player_side]
            _calibration2["shared_z"] = imported["shared_z"]
            _calibration2["playfield"]["active_area"] = \
                imported["playfield"]["active_area"]
            _calibration2["playfield"]["updated_at"] = time.time()
        _save_calibration2()
        out = json.loads(json.dumps(_calibration2))
    _live.bump()
    return jsonify({
        "ok": True,
        "calibration": out,
        "active_area": out["playfield"]["active_area"],
    })


@bp.route("/api/calibration2/playfield", methods=["POST"])
def api_calibration2_playfield():
    if not _is_operator():
        return jsonify({"ok": False, "error": "gamemaster required"}), 403
    data = request.get_json(silent=True) or {}
    side = data.get("side") or data.get("team")
    view = data.get("camera_view")
    if side not in TEAMS:
        side = None
    ok, err = _ensure_playfield_calibration2_areas(side, view)
    if not ok:
        return jsonify({"ok": False, "error": err}), 409
    return jsonify({"ok": True, "calibration": _calibration2_public(),
                    "access": _calibration_access_public()})


@bp.route("/api/calibration2/orientation", methods=["POST"])
def api_calibration2_orientation():
    if not _is_operator():
        return jsonify({"ok": False, "error": "gamemaster required"}), 403
    data = request.get_json(silent=True) or {}
    side = data.get("side") or data.get("team")
    view = data.get("camera_view")
    if side not in TEAMS:
        return jsonify({"ok": False, "error": "team required"}), 400
    if view not in ("normal", "rot180"):
        return jsonify({"ok": False, "error": "camera_view must be normal or rot180"}), 400
    ok, err = _ensure_playfield_calibration2_areas(side, view)
    if not ok:
        return jsonify({"ok": False, "error": err}), 409
    return jsonify({"ok": True, "side": side, "camera_view": view,
                    "calibration": _calibration2_public(),
                    "access": _calibration_access_public()})


@bp.route("/api/calibration2/use-current-playfield", methods=["POST"])
def api_calibration2_use_current_playfield():
    if not _is_operator():
        return jsonify({"ok": False, "error": "gamemaster required"}), 403
    data = request.get_json(silent=True) or {}
    side = data.get("side") or data.get("team")
    if side not in TEAMS:
        side = None
    ok, err = _adopt_current_playfield_calibration2(
        side, data.get("camera_view"))
    if not ok:
        return jsonify({"ok": False, "error": err}), 409
    return jsonify({
        "ok": True,
        "calibration": _calibration2_public(),
        "access": _calibration_access_public(),
    })


@bp.route("/api/calibration2/capture", methods=["POST"])
def api_calibration2_capture():
    data = request.get_json(silent=True) or {}
    side = _calibration_side(data)
    if side not in TEAMS:
        return jsonify({"ok": False, "error": "team required"}), 403
    if not _is_operator() and not _calibration_access[side]["enabled"]:
        return jsonify({"ok": False, "error": f"{side} calibration is not enabled by the gamemaster"}), 403
    key = data.get("target")
    if key not in _calibration2["arms"][side]["points"]:
        return jsonify({"ok": False, "error": "unknown calibration target"}), 400
    try:
        pose = _clean_pose(data.get("pose"))
        camera = data.get("camera") or {}
        camera = {"u": round(float(camera["u"]), 8),
                  "v": round(float(camera["v"]), 8)}
        if not all(math.isfinite(value) and 0 <= value <= 1 for value in camera.values()):
            raise ValueError('camera coordinates outside the corrected image')
    except (ValueError, KeyError, TypeError):
        return jsonify({"ok": False, "error": "numeric pose and camera coordinates required"}), 400
    with _calibration_lock:
        arm = _calibration2["arms"][side]
        for other_key, other in arm["points"].items():
            previous = other.get("pose") or {}
            if (other_key != key and previous.get("set")
                    and math.hypot(pose["x"]-previous["x"], pose["y"]-previous["y"]) < 2):
                return jsonify(ok=False, error=f"{side.title()} capture overlaps {other['label']}. "
                               f"Move the tool to {arm['points'][key]['label']} before capturing."), 400
        arm["points"][key]["pose"] = pose
        arm["points"][key]["camera"] = camera
        arm["updated_at"] = time.time()
        if data.get("pickup_height") is not None:
            arm["pickup_height"] = round(float(data["pickup_height"]), 3)
        if data.get("transport_height") is not None:
            _calibration2["shared_z"]["transport_height"] = \
                round(float(data["transport_height"]), 3)
            arm['transport_height'] = _calibration2['shared_z']['transport_height']
        _save_calibration2()
    return jsonify({"ok": True, "calibration": _calibration2_public()})


@bp.route("/api/calibration2/parallax", methods=["POST"])
def api_calibration2_parallax():
    data = request.get_json(silent=True) or {}
    side = _calibration_side(data)
    if side not in TEAMS:
        return jsonify({"ok": False, "error": "team required"}), 403
    if not _is_operator() and not _calibration_access[side]["enabled"]:
        return jsonify({"ok": False, "error": f"{side} calibration is not enabled by the gamemaster"}), 403
    try:
        marker = int(data.get("marker"))
        sample = _clean_cal2_parallax_sample(marker, data)
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "valid marker, ground and raised camera coordinates required"}), 400
    with _calibration_lock:
        _calibration2["arms"][side]["parallax_points"][str(marker)] = sample
        _calibration2["arms"][side]["updated_at"] = time.time()
        _save_calibration2()
    return jsonify({"ok": True, "calibration": _calibration2_public()})


@bp.route("/api/calibration2/parallax/reset", methods=["POST"])
def api_calibration2_parallax_reset():
    data = request.get_json(silent=True) or {}
    side = _calibration_side(data)
    if side not in TEAMS:
        return jsonify({"ok": False, "error": "team required"}), 403
    if not _is_operator() and not _calibration_access[side]["enabled"]:
        return jsonify({"ok": False, "error": f"{side} calibration is not enabled by the gamemaster"}), 403
    with _calibration_lock:
        _calibration2["arms"][side]["parallax_points"] = _empty_cal2_parallax_points()
        _calibration2["arms"][side]["updated_at"] = time.time()
        _save_calibration2()
    return jsonify({"ok": True, "calibration": _calibration2_public()})


@bp.route("/api/calibration2/z", methods=["POST"])
@bp.route("/api/calibration2/shared-z", methods=["POST"])
def api_calibration2_z():
    data = request.get_json(silent=True) or {}
    side = _calibration_side(data)
    if side not in TEAMS:
        return jsonify({"ok": False, "error": "team required"}), 403
    if not _is_operator() and not _calibration_access[side]["enabled"]:
        return jsonify({"ok": False, "error": f"{side} calibration is not enabled by the gamemaster"}), 403
    heights = {}
    accepted_heights = (
        "pickup_height", "transport_height", "stack_drop_offset")
    if any(key in data for key in accepted_heights):
        raw_heights = {
            key: data[key]
            for key in accepted_heights if key in data
        }
    else:
        height = str(data.get("height") or "")
        if height not in accepted_heights:
            return jsonify({
                "ok": False,
                "error": "height must be pickup_height, transport_height, or stack_drop_offset",
            }), 400
        raw_heights = {height: data.get("z")}
    try:
        for height, raw_value in raw_heights.items():
            value = round(float(raw_value), 3)
            if not math.isfinite(value):
                raise ValueError
            if height == "stack_drop_offset":
                if not 0 <= value <= 100:
                    raise ValueError
            elif not WORKSPACE["z"][0] <= value <= WORKSPACE["z"][1]:
                raise ValueError
            heights[height] = value
    except (TypeError, ValueError):
        return jsonify({
            "ok": False,
            "error": "Z values must be inside the robot workspace and the 100s stack drop offset must be 0-100 mm",
        }), 400
    with _calibration_lock:
        if "pickup_height" in heights:
            _calibration2["arms"][side]["pickup_height"] = \
                heights["pickup_height"]
            _calibration2["arms"][side]["updated_at"] = time.time()
        if "transport_height" in heights:
            _calibration2["shared_z"]["transport_height"] = \
                heights["transport_height"]
            _calibration2['arms'][side]['transport_height'] = heights['transport_height']
        if "stack_drop_offset" in heights:
            _calibration2["arms"][side]["stack_drop_offset"] = \
                heights["stack_drop_offset"]
            _calibration2["arms"][side]["updated_at"] = time.time()
        _save_calibration2()
    return jsonify({"ok": True, "calibration": _calibration2_public()})


@bp.route("/api/calibration2/active-area", methods=["POST"])
def api_calibration2_active_area():
    data = request.get_json(silent=True) or {}
    side = _calibration_side(data)
    if side not in TEAMS:
        return jsonify({"ok": False, "error": "team required"}), 403
    if not _is_operator() and not _calibration_access[side]["enabled"]:
        return jsonify({"ok": False, "error": f"{side} calibration is not enabled by the gamemaster"}), 403
    try:
        active_area = _clean_active_area(data.get("active_area"))
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    with _calibration_lock:
        _calibration2["playfield"]["active_area"] = active_area
        _calibration2["playfield"]["updated_at"] = time.time()
        _save_calibration2()
    return jsonify({"ok": True, "calibration": _calibration2_public(),
                    "active_area": active_area})


@bp.route("/api/calibration2/reset", methods=["POST"])
def api_calibration2_reset():
    data = request.get_json(silent=True) or {}
    side = _calibration_side(data)
    if side not in TEAMS:
        return jsonify({"ok": False, "error": "team required"}), 403
    if not _is_operator() and not _calibration_access[side]["enabled"]:
        return jsonify({"ok": False, "error": f"{side} calibration is not enabled by the gamemaster"}), 403
    with _calibration_lock:
        view = _calibration2["arms"][side].get("camera_view", "normal")
        pickup_height = _calibration2["arms"][side].get("pickup_height")
        stack_drop_offset = _calibration2["arms"][side].get(
            "stack_drop_offset", 31.5)
        _calibration2["arms"][side] = _default_calibration2()["arms"][side]
        _calibration2["arms"][side]["camera_view"] = view
        _calibration2["arms"][side]["pickup_height"] = pickup_height
        _calibration2["arms"][side]["stack_drop_offset"] = stack_drop_offset
        _save_calibration2()
    return jsonify({"ok": True, "calibration": _calibration2_public()})


@bp.route("/api/playfield/save", methods=["POST"])
def api_playfield_save():
    if not _is_operator():
        return jsonify({"ok": False, "error": "gamemaster required"}), 403
    playfield = _playfield_module()
    if playfield is None or not hasattr(playfield, "list_areas"):
        return jsonify({"ok": False, "error": "Playfield Areas prototype is not loaded"}), 409
    areas = playfield.list_areas()
    payload = _saved_playfield_payload(areas)
    try:
        with open(PLAYFIELD_SNAPSHOT_PATH, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
    except OSError as e:
        return jsonify({"ok": False, "error": f"could not save playfield: {e}"}), 500
    return jsonify({
        "ok": True,
        "count": len(payload["areas"]),
        "saved_at": payload["saved_at"],
    })


@bp.route("/api/playfield/load", methods=["POST"])
def api_playfield_load():
    if not _is_operator():
        return jsonify({"ok": False, "error": "gamemaster required"}), 403
    playfield = _playfield_module()
    if playfield is None or not hasattr(playfield, "replace_areas"):
        return jsonify({"ok": False, "error": "Playfield Areas controller cannot replace areas"}), 409
    try:
        with open(PLAYFIELD_SNAPSHOT_PATH, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
    except FileNotFoundError:
        return jsonify({"ok": False, "error": "no saved playfield yet"}), 404
    except (OSError, ValueError, TypeError) as e:
        return jsonify({"ok": False, "error": f"could not read saved playfield: {e}"}), 500
    areas = payload.get("areas")
    if not isinstance(areas, list):
        return jsonify({"ok": False, "error": "saved playfield is missing areas"}), 400
    try:
        loaded = playfield.replace_areas(areas)
    except (ValueError, KeyError, TypeError) as e:
        return jsonify({"ok": False, "error": f"could not load playfield: {e}"}), 400
    if hasattr(playfield, "save_areas_now"):
        playfield.save_areas_now()
    calibration = _sync_calibration_area_refs(loaded)
    _live.bump()
    return jsonify({
        "ok": True,
        "count": len(loaded),
        "saved_at": payload.get("saved_at"),
        "calibration": calibration,
    })


@bp.route("/api/calibration/corner-map", methods=["POST"])
def api_calibration_corner_map():
    ok, err = _calibration_write_allowed()
    if not ok:
        return jsonify({"ok": False, "error": err}), 403
    data = request.get_json(silent=True) or {}
    side = _calibration_side(data)
    try:
        corner_map = _clean_corner_map(data.get("corner_map"))
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    with _calibration_lock:
        if side in TEAMS:
            _calibration["arms"][side]["corner_map"] = corner_map
            _calibration["arms"][side]["marker_cache"] = None
            _calibration["arms"][side]["updated_at"] = time.time()
        else:
            _calibration["playfield"]["corner_map"] = corner_map
            _calibration["playfield"]["marker_cache"] = None
            _calibration["playfield"]["updated_at"] = time.time()
        _save_calibration()
        out = json.loads(json.dumps(_calibration))
    _live.bump()
    return jsonify({"ok": True, "calibration": out})


@bp.route("/api/calibration/active-area", methods=["POST"])
def api_calibration_active_area():
    ok, err = _calibration_write_allowed()
    if not ok:
        return jsonify({"ok": False, "error": err}), 403
    data = request.get_json(silent=True) or {}
    try:
        active_area = _clean_active_area(data.get("active_area"))
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    with _calibration_lock:
        _calibration["playfield"]["active_area"] = active_area
        _calibration["playfield"]["updated_at"] = time.time()
        _save_calibration()
        out = json.loads(json.dumps(_calibration))
    _live.bump()
    return jsonify({
        "ok": True,
        "calibration": out,
        "active_area": out["playfield"]["active_area"],
    })


@bp.route("/api/calibration/marker-cache", methods=["POST"])
def api_calibration_marker_cache():
    if not (_is_operator() or _player_side() in TEAMS):
        return jsonify({"ok": False, "error": "team or gamemaster required"}), 403
    data = request.get_json(silent=True) or {}
    side = _calibration_side(data)
    if side is None and not _is_operator():
        side = _player_side()
    try:
        marker_cache = _clean_marker_cache(data.get("marker_cache"))
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    with _calibration_lock:
        if side in TEAMS:
            _calibration["arms"][side]["marker_cache"] = marker_cache
            _calibration["arms"][side]["updated_at"] = time.time()
        else:
            _calibration["playfield"]["marker_cache"] = marker_cache
            _calibration["playfield"]["updated_at"] = time.time()
        _save_calibration()
        out = json.loads(json.dumps(_calibration))
    _live.bump()
    return jsonify({"ok": True, "calibration": out})


@bp.route("/api/calibration/export.zip", methods=["POST"])
def api_calibration_export_zip():
    if not (_is_operator() or _player_side() in TEAMS):
        return jsonify({"ok": False, "error": "team or gamemaster required"}), 403
    data = request.get_json(silent=True) or {}
    active_area = data.get("active_area") if isinstance(data.get("active_area"), dict) else _calibration_public().get("playfield", {}).get("active_area", {})
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "auto-calibration.json",
            json.dumps(_calibration_public(), indent=2, sort_keys=True),
        )
        zf.writestr(
            "active-area.json",
            json.dumps({
                "active_area": active_area,
                "exported_at": _dt.datetime.now(_dt.UTC).isoformat(),
                "format": "auto-pick-and-place-calibration-v1",
            }, indent=2, sort_keys=True),
        )
    payload.seek(0)
    return Response(
        payload.getvalue(),
        mimetype="application/zip",
        headers={"Content-Disposition": "attachment; filename=auto-pick-calibration.zip"},
    )


@bp.route("/api/calibration/import.zip", methods=["POST"])
def api_calibration_import_zip():
    global _calibration
    player_side = _player_side()
    ok, err = _calibration_write_allowed()
    if not ok:
        return jsonify({"ok": False, "error": err}), 403
    upload = request.files.get("file")
    if upload is None:
        return jsonify({"ok": False, "error": "zip file required"}), 400
    try:
        raw = upload.read()
        with zipfile.ZipFile(io.BytesIO(raw), "r") as zf:
            names = set(zf.namelist())
            if "auto-calibration.json" not in names:
                return jsonify({"ok": False, "error": "auto-calibration.json missing from zip"}), 400
            saved = json.loads(zf.read("auto-calibration.json").decode("utf-8"))
            active_area = None
            if "active-area.json" in names:
                active_payload = json.loads(zf.read("active-area.json").decode("utf-8"))
                active_area = active_payload.get("active_area") if isinstance(active_payload, dict) else None
    except (OSError, UnicodeDecodeError, zipfile.BadZipFile, json.JSONDecodeError) as e:
        return jsonify({"ok": False, "error": f"invalid calibration zip: {e}"}), 400
    with _calibration_lock:
        imported = _calibration_from_saved(saved)
        if _is_operator():
            _calibration = imported
        else:
            _calibration["playfield"] = imported["playfield"]
            _calibration["arms"][player_side] = imported["arms"][player_side]
        if active_area:
            try:
                _calibration["playfield"]["active_area"] = _clean_active_area(active_area)
            except ValueError:
                pass
        _save_calibration()
        out = json.loads(json.dumps(_calibration))
    _live.bump()
    return jsonify({"ok": True, "calibration": out, "active_area": active_area})


@bp.route("/api/calibration/capture", methods=["POST"])
def api_calibration_capture():
    data = request.get_json(silent=True) or {}
    side = _calibration_side(data)
    target = data.get("target")
    if side not in TEAMS:
        return jsonify({
            "ok": False,
            "error": "team required",
            "received_side": data.get("side") if isinstance(data, dict) else None,
            "received_team": data.get("team") if isinstance(data, dict) else None,
            "role_side": _player_side(),
            "referrer_side": _referrer_side(),
        }), 403
    if not _is_operator() and not _calibration_access[side]["enabled"]:
        return jsonify({"ok": False, "error": f"{side} calibration is not enabled by the gamemaster"}), 403
    if not isinstance(target, str):
        return jsonify({"ok": False, "error": "target required"}), 400
    now = time.time()
    with _calibration_lock:
        side_cal = _calibration["arms"][side]
        if target in side_cal["points"]:
            try:
                side_cal["points"][target]["pose"] = _clean_pose(data.get("pose"))
            except ValueError as e:
                return jsonify({"ok": False, "error": str(e)}), 400
        elif target == "center":
            try:
                side_cal["center"] = _clean_pose(data.get("pose"))
            except ValueError as e:
                return jsonify({"ok": False, "error": str(e)}), 400
        elif target in ("pickup_height", "transport_height"):
            pose = data.get("pose")
            try:
                z = float((pose or {}).get("z", data.get("z")))
            except (TypeError, ValueError):
                return jsonify({"ok": False, "error": "height requires numeric z"}), 400
            side_cal[target] = {"set": True, "z": round(z, 3)}
        else:
            return jsonify({"ok": False, "error": "unknown calibration target"}), 400
        side_cal["updated_at"] = now
        _save_calibration()
        out = json.loads(json.dumps(_calibration))
    _live.bump()
    return jsonify({"ok": True, "calibration": out})


@bp.route("/api/calibration/reset", methods=["POST"])
def api_calibration_reset():
    data = request.get_json(silent=True) or {}
    side = _calibration_side(data)
    if side not in TEAMS:
        return jsonify({"ok": False, "error": "team required"}), 403
    if not _is_operator() and not _calibration_access[side]["enabled"]:
        return jsonify({"ok": False, "error": f"{side} calibration is not enabled by the gamemaster"}), 403
    with _calibration_lock:
        _calibration["arms"][side] = _default_calibration()["arms"][side]
        _save_calibration()
        out = json.loads(json.dumps(_calibration))
    _live.bump()
    return jsonify({"ok": True, "calibration": out})


@bp.route("/api/direct/<action>", methods=["GET", "POST"])
def api_direct_retired(action):
    return jsonify(ok=False, error="Use the existing Dobot Relay controller; direct control has been retired."), 410


@bp.route("/api/player", methods=["POST"])
def api_player():
    data = request.get_json(silent=True) or {}
    team = _requested_team(data)
    if team not in TEAMS:
        return jsonify({"ok": False, "error": "player team required"}), 403
    name = str(data.get("name") or "").strip()[:32]
    if not name:
        return jsonify({"ok": False, "error": "name required"}), 400
    with _state_lock:
        _state["teams"][team] = _team_state()
        _state["teams"][team]["player"] = name
        _state["teams"][team]["phase"] = "ready"
        _state["updated_at"] = time.time()
        out = _public_state_locked()
    _live.bump()
    return jsonify(out)


@bp.route("/api/start", methods=["POST"])
def api_start():
    data = request.get_json(silent=True) or {}
    team = _requested_team(data)
    if team not in TEAMS:
        return jsonify({"ok": False, "error": "player team required"}), 403
    with _state_lock:
        ts = _state["teams"][team]
        if not ts["player"]:
            return jsonify({"ok": False, "error": "enter a name first"}), 409
        now = time.time()
        ts.update({
            "phase": "running", "started_at": now,
            "completed_at": None, "elapsed_seconds": None,
        })
        _state["updated_at"] = now
        out = _public_state_locked()
    _live.bump()
    return jsonify(out)


@bp.route("/api/finish", methods=["POST"])
def api_finish():
    if not _is_operator():
        return jsonify({"ok": False, "error": "gamemaster required"}), 403
    data = request.get_json(silent=True) or {}
    team = data.get("team")
    if team not in TEAMS:
        return jsonify({"ok": False, "error": "team required"}), 400
    with _state_lock:
        ts = _state["teams"][team]
        if ts["phase"] != "running" or not ts["started_at"]:
            return jsonify({"ok": False, "error": "no run in progress"}), 409
        now = time.time()
        elapsed = round(now - float(ts["started_at"]), 2)
        player = ts["player"]
        entry = {
            "logged_at": _dt.datetime.now(_dt.UTC).isoformat(),
            "player": player,
            "team": team,
            "elapsed_seconds": elapsed,
            "started_at": _dt.datetime.fromtimestamp(ts["started_at"], _dt.UTC).isoformat(),
            "completed_at": _dt.datetime.fromtimestamp(now, _dt.UTC).isoformat(),
        }
        need_header = not os.path.exists(LOG_PATH) or os.path.getsize(LOG_PATH) == 0
        with open(LOG_PATH, "a", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=LOG_FIELDS)
            if need_header:
                writer.writeheader()
            writer.writerow(entry)
        if _state["best_seconds"] is None or elapsed < _state["best_seconds"]:
            _state["best_seconds"] = elapsed
            _state["best_player"] = player
            _state["best_team"] = team
        ts.update({
            "phase": "done", "completed_at": now, "elapsed_seconds": elapsed,
        })
        _state["updated_at"] = now
        out = _public_state_locked()
    _live.bump()
    return jsonify(out)


@bp.route("/api/reset", methods=["POST"])
def api_reset():
    data = request.get_json(silent=True) or {}
    requested = data.get("team")
    with _state_lock:
        if requested in TEAMS and (_is_operator() or requested in _roles()):
            targets = [requested]
        elif _is_operator() and not requested:
            targets = list(TEAMS)            # operator: reset both
        else:
            side = _player_side()            # player: own team only
            targets = [side] if side in TEAMS else []
        if not targets:
            return jsonify({"ok": False, "error": "team required"}), 403
        for team in targets:
            _state["teams"][team] = _team_state()
        _state["updated_at"] = time.time()
        out = _public_state_locked()
    _live.bump()
    return jsonify(out)


@bp.route("/api/results")
def api_results():
    rows = _read_log_rows()
    top = _top_score_rows(_highscore_rows(rows))
    recent = list(rows)
    recent.reverse()
    with _state_lock:
        best = {
            "seconds": _state["best_seconds"],
            "player": _state["best_player"],
            "team": _state["best_team"],
        }
    return jsonify({
        "results": recent[:50],
        "top": top,
        "best": best,
        "count": len(rows),
        "highscore_reset_at": _state.get("highscore_reset_at") or 0.0,
    })


@bp.route("/api/results/reset-highscores", methods=["POST"])
def api_reset_highscores():
    if not _is_operator():
        return jsonify({"ok": False, "error": "gamemaster required"}), 403
    now = time.time()
    with _state_lock:
        _state["highscore_reset_at"] = now
        _state["best_seconds"] = None
        _state["best_player"] = ""
        _state["best_team"] = ""
        _state["updated_at"] = now
        _save_highscore_reset_at(now)
        out = _public_state_locked()
    _live.bump()
    return jsonify({"ok": True, "state": out})


@bp.route("/api/log.csv")
def api_log_csv():
    if os.path.exists(LOG_PATH):
        with open(LOG_PATH, "r", encoding="utf-8") as fh:
            body = fh.read()
    else:
        buf = io.StringIO()
        csv.DictWriter(buf, fieldnames=LOG_FIELDS).writeheader()
        body = buf.getvalue()
    return Response(
        body,
        mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=auto-pickup-log.csv"},
    )


_state["highscore_reset_at"] = _load_highscore_reset_at()
_seed_best_from_log()
