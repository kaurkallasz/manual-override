"""Team-isolated mobile presentation facade over versioned game, art and progress outputs."""
import json
import time
import threading
import uuid
from flask import Blueprint, Response, abort, jsonify, request
from camera_view import registration
import live
MANIFEST = {'name':'Mobile LTZ API','description':'Authenticated Green and Purple mobile presentation adapter.','group':'Photon Engine'}
bp=Blueprint('mobile_ltz_api',__name__)
_live=live.LiveState()
_team_live={'green':_live,'purple':live.LiveState()}
_ctx=None
_delivery_lock=threading.Lock()
_delivery_epoch=uuid.uuid4().hex
_delivery_sequence=0
_delivery_at=None

def hub_init(ctx):
    global _ctx
    _ctx=ctx

def hub_stop():
    global _ctx
    _ctx=None

def _module(slug):
    return _ctx.get_prototype(slug) if _ctx and _ctx.is_prototype_enabled(slug) else None

def _game():
    module=_module('photon-game')
    if not module or not callable(getattr(module,'game_snapshot',None)):
        raise ValueError('Photon Game unavailable')
    try:
        value=module.game_snapshot()
    except Exception as exc:
        raise ValueError('Photon Game unavailable') from exc
    if not isinstance(value,dict) or value.get('contract')!='photon.game' or type(value.get('version')) is not int or value['version']!=2:
        raise ValueError('Photon Game contract mismatch')
    return module,value

def camera_view(game):
    try:
        board = _module('photon-board')
        camera = _module('camera-calibration')
        if not board or not camera:
            raise ValueError('Corrected camera view is unavailable.')
        descriptor = camera.preview_snapshot()
        if (descriptor.get('contract') != 'hhh.camera-preview' or type(descriptor.get('version')) is not int
                or descriptor['version'] != 1 or descriptor.get('status') != 'ready'
                or descriptor.get('coordinate_space') != 'corrected-camera-normalized'):
            raise ValueError('Corrected camera view is unavailable.')
        observation = board.runtime_observation()
        if game.get('journey',{}).get('phase')=='calibration':
            if observation.get('contract')!='photon.board.runtime' or type(observation.get('version')) is not int or observation['version']!=1 or observation.get('status')!='ready' or not observation.get('corrected') or not -1<=time.time()-observation.get('frame_at',0)<=1.5:
                raise ValueError('Fresh corrected camera required for calibration')
            matrix,markers=[1,0,0,0,1,0,0,0],[30,31,32,33,34,35]
        else:
            matrix, markers = registration(game['level'], observation)
        tags=[]
        if game.get('journey',{}).get('phase')=='calibration':
            for tag in observation.get('tags',[]):
                if (type(tag.get('id')) is int and not 40<=tag['id']<=59 and tag.get('missing',0)==0
                        and all(type(tag.get(k)) in (int,float) and 0<=tag[k]<=1 for k in ('nx','ny'))):
                    tags.append({'id':tag['id'],'u':tag['nx'],'v':tag['ny']})
        return {'status':'ready', 'matrix':matrix, 'markers':markers,'tags':tags,
                'width':observation['width'], 'height':observation['height'],
                'frame_at':observation['frame_at'], 'frame_path':'assets/mobile-camera.jpg'}
    except Exception as exc:
        return {'status':'unavailable', 'error':str(exc)}


def mobile_snapshot(side='green'):
    """Player-facing projection; no administrative settings/history/roster."""
    global _delivery_sequence, _delivery_at
    started=time.perf_counter()
    try:
        _, value = _game()
    except ValueError as exc:
        return {'status':'unavailable','error':str(exc)}
    if side not in ('green', 'purple'):
        raise ValueError('Unknown mobile team.')
    arms = value.pop('mobile_arms', {})
    value['mobile_arm'] = arms.get(side, value.get('mobile_arm') if side == 'green' else None)
    value['mobile_team'] = side
    value['mobile_camera'] = camera_view(value) if not value.get('virtual_play') else {'status':'unused'}
    for key in ('configuration', 'storage', 'inputs', 'progress', 'level_presets'):
        value.pop(key, None)
    # Movement packets retain authoritative health/effects and short guides,
    # not internal lane bookkeeping or unnecessary float precision.
    fields=('id','enemy_type','x','y','vx','vy','facing_x','facing_y','hp','max_hp',
            'attacking','burn_until','electrocuted_until','electrocution_depth',
            'electrocution_intensity','motion')
    value['enemies']=[{key:round(enemy[key],3) if isinstance(enemy[key],float) else enemy[key]
                       for key in fields if key in enemy} for enemy in value.get('enemies',[])]
    progress = _module('photon-progress')
    if progress and callable(getattr(progress, 'progress_snapshot', None)):
        try:
            profile = progress.public_snapshot(side)
            if not isinstance(profile,dict) or profile.get('contract') != 'photon.progress' or type(profile.get('version')) is not int or profile['version']!=2 or profile.get('status')!='ready':
                raise ValueError('Photon Progress v2 unavailable')
            value['mobile_progress'] = profile
        except Exception as exc:
            value['mobile_progress']={'contract':'photon.progress','version':2,'status':'unavailable','error':str(exc),'player':None,'players':[]}
    journey = value.get('journey') or {}
    owner = _module('auto-pickup-game')
    value['mobile_calibration'] = None
    value['mobile_calibration_preparation'] = None
    value['mobile_calibration_ready'] = False
    value['mobile_calibration_connect'] = False
    if owner and callable(getattr(owner,'calibration_session_snapshot',None)):
        try:
            cal = owner.calibration_session_snapshot()
            if not isinstance(cal,dict) or cal.get('contract')!='hhh.cal2.session' or type(cal.get('version')) is not int or cal['version']!=1 or cal.get('status')!='ready':
                raise ValueError('Auto PP Cal 2 session v1 unavailable')
            value['mobile_rig_revision']=cal.get('rig_revision')
            value['mobile_calibration_connect'] = bool(journey.get('phase')=='calibration'
                and (journey.get('calibration_side')==side or side in cal.get('pending_stops',{})))
            if journey.get('phase')=='calibration' and journey.get('calibration_side')==side:
                session_id = journey['id']+':'+side
                session = cal.get('sessions',{}).get(session_id)
                preparation=cal.get('marker_preparation') or {}
                if preparation.get('id')==session_id and preparation.get('side')==side:
                    value['mobile_calibration_preparation']=preparation
                positions=(value['mobile_calibration_preparation'] or {}).get('marker_positions',{})
                if session and session.get('side')==side:
                    value['mobile_calibration'] = session
                    positions=positions or session.get('marker_positions',{})
                    value['mobile_calibration_ready'] = bool(
                        journey.get('active_side')==side and journey.get('session_id')==session_id
                        and cal.get('active_side')==side and cal.get('active_id')==session_id
                        and not cal.get('requires_activation') and not cal.get('motion_blocked')
                        and session.get('epoch')==cal.get('epoch') and not session.get('paused')
                        and session.get('access_until',0)>time.time())
                camera=value.get('mobile_camera') or {}
                if camera.get('status')=='ready':
                    tags=camera.setdefault('tags',[])
                    visible={t['id'] for t in tags}
                    for marker,point in positions.items():
                        uv=point.get('camera') or {}
                        if marker in {str(i) for i in range(30,36)} and int(marker) not in visible and all(type(uv.get(k)) in (int,float) and 0<=uv[k]<=1 for k in ('u','v')):
                            tags.append({'id':int(marker),'u':uv['u'],'v':uv['v'],'cached':True})
                if value['mobile_calibration_ready'] and session['stage']=='tutorial':
                    target=owner.calibration_lesson_target(side,session['id'])
                    if not isinstance(target,dict) or target.get('contract')!='hhh.cal2.target' or type(target.get('version')) is not int or target['version']!=1 or target.get('status')!='ready':
                        raise ValueError('Guided calibration target v1 unavailable')
                    value['mobile_calibration_target']=target
        except Exception as exc:
            value['mobile_calibration_connect']=False
            value['mobile_calibration_ready']=False
            value['mobile_calibration_error']=str(exc)
    elif journey.get('phase')=='calibration':
        value['mobile_calibration_error']='Auto PP Cal 2 unavailable'
    now=time.perf_counter()
    with _delivery_lock:
        _delivery_sequence+=1
        value['delivery']={'contract':'photon.delivery','version':1,'epoch':_delivery_epoch,
                           'sequence':_delivery_sequence,'prepared_at':time.time(),
                           'source_gap_ms':round((now-_delivery_at)*1000,2) if _delivery_at is not None else None,
                           'build_ms':round((now-started)*1000,2)}
        _delivery_at=now
    return value


def _mobile_guard(*, mutation=False):
    side = request.args.get('side', 'green')
    if side not in ('green', 'purple'):
        abort(400)
    if not set(request.environ.get('hhh.roles') or ()) & {side, 'gamemaster'}:
        abort(403)
    if mutation:
        origin = request.headers.get('Origin')
        if origin and origin.rstrip('/') != request.host_url.rstrip('/'):
            abort(403)
        if not request.is_json:
            abort(415)
    return side


@bp.route('/api/state')
def mobile_state_api():
    side = _mobile_guard()
    return jsonify(mobile_snapshot(side))


def _purple_mobile_snapshot():
    return mobile_snapshot('purple')


@bp.route('/api/events')
def mobile_events_api():
    side = _mobile_guard()
    return _team_live[side].stream(mobile_snapshot if side == 'green' else _purple_mobile_snapshot, interval=.15, shared=True,
                        # Start/reset must deliver a complete scene to every
                        # team, even when the map itself has not changed.
                        identity_fields=('run_id', 'level_revision'), envelope=True,
                        static_fields=('level', 'presentation', 'settings', 'loadout',
                                       'force_field_blockers', 'row_barrier_geometry', 'mobile_progress'))


@bp.route('/api/command', methods=['POST'])
def mobile_command_api():
    side = _mobile_guard(mutation=True)
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or len(json.dumps(data)) > 2048:
        return jsonify(ok=False, error='Invalid mobile command.'), 400
    if data.get('side', side) != side:
        abort(403)
    data = {**data, 'side':side}
    try:
        game, snapshot = _game()
        if data.get('action') == 'turret_aim':
            if not callable(getattr(game, 'mobile_turret_aim', None)):
                raise ValueError('Player turret aiming is unavailable.')
            if not snapshot.get('virtual_play') and camera_view(snapshot).get('status') != 'ready':
                raise ValueError('Camera alignment is unavailable. Wait for tracking to return.')
            result = game.mobile_turret_aim(data)
            for stream in _team_live.values():
                stream.bump()
            return jsonify(ok=True, tower=result, server_time=time.time())
        result = game.mobile_command(data)
        for stream in _team_live.values():
            stream.bump()
        return jsonify(ok=True, arm=result, server_time=time.time())
    except (ValueError, PermissionError) as exc:
        return jsonify(ok=False, error=str(exc)), 400


def _progress_owner():
    owner = _module('photon-progress')
    if owner is None:
        raise ValueError('Progress unavailable')
    value=owner.progress_snapshot()
    if value.get('contract')!='photon.progress' or type(value.get('version')) is not int or value['version']!=2 or value.get('status')!='ready':
        raise ValueError('Progress v2 unavailable')
    return owner


@bp.route('/api/player',methods=['POST'])
def player_api():
    side=_mobile_guard(mutation=True)
    data=request.get_json(silent=True)
    try:
        if not isinstance(data,dict) or len(json.dumps(data))>2048:
            raise ValueError('invalid player command')
        _,game=_game()
        if data.get('action') in ('create','select') and game.get('journey',{}).get('phase') not in ('lobby','ready'):
            raise ValueError('finish the shared player journey before changing profiles')
        result=_progress_owner().player_command(side,data)
        for stream in _team_live.values():stream.bump()
        return jsonify(result)
    except (ValueError,PermissionError) as exc:
        return jsonify(ok=False,error=str(exc)),400


@bp.route('/api/history')
def history_api():
    side=_mobile_guard()
    try:
        owner=_progress_owner()
        player=owner.progress_snapshot({'side':side}).get('player')
        query={k:v for k,v in request.args.items() if k in ('dataset','tier','side_at_run','level','from','to','cursor','limit','cohort')}
        query.update(player_id=player['id'] if player else None,combined=request.args.get('combined')=='1')
        return jsonify(owner.history_snapshot(query))
    except (ValueError,PermissionError) as exc:
        return jsonify(ok=False,error=str(exc)),400


@bp.route('/api/journey',methods=['POST'])
def journey_api():
    side=_mobile_guard(mutation=True)
    try:
        data=request.get_json(silent=True)
        if not isinstance(data,dict) or len(json.dumps(data))>2048:
            raise ValueError('invalid journey command')
        game,_=_game()
        result=game.mobile_journey_command(side,data)
        for stream in _team_live.values():stream.bump()
        return jsonify(ok=True,journey=result)
    except (ValueError,PermissionError) as exc:
        return jsonify(ok=False,error=str(exc)),400


@bp.route('/api/calibrations')
def calibration_history_api():
    side=_mobile_guard()
    try:
        owner=_module('auto-pickup-game')
        if owner is None or not callable(getattr(owner,'calibration_history',None)):
            raise ValueError('Saved calibrations unavailable')
        value=owner.calibration_history(side)
        if not isinstance(value,dict) or value.get('contract')!='hhh.cal2.history' or type(value.get('version')) is not int or value['version']!=1 or value.get('status')!='ready' or not isinstance(value.get('rows'),list):
            raise ValueError('Saved calibration contract unavailable')
        return jsonify(value)
    except Exception as exc:
        return jsonify(ok=False,error=str(exc)),503


@bp.route('/api/renderer.js')
def mobile_renderer_api():
    _mobile_guard()
    module = _module('laser-tag-y')
    if not module or not callable(getattr(module, 'renderer_contract', None)):
        abort(503)
    contract = module.renderer_contract()
    if contract.get('contract') != 'photon.renderer' or type(contract.get('version')) is not int or contract['version'] != 1:
        abort(503)
    return module.renderer_response()


@bp.route('/api/assets/<path:filename>')
def mobile_asset_api(filename):
    _mobile_guard()
    if filename == 'mobile-camera.jpg':
        camera = _module('camera-calibration')
        if not camera or not callable(getattr(camera, 'preview_frame', None)):
            abort(503)
        frame = camera.preview_frame()
        if (frame.get('contract') != 'hhh.camera-frame' or type(frame.get('version')) is not int
                or frame['version'] != 1 or frame.get('status') != 'ready'
                or frame.get('coordinate_space') != 'corrected-camera-normalized'
                or not isinstance(frame.get('jpeg'), bytes)
                or not -1 <= time.time()-frame.get('frame_at', 0) <= 2):
            abort(503)
        return Response(frame['jpeg'], mimetype='image/jpeg', headers={'Cache-Control':'no-store'})
    module = _module('photon-level')
    if not module or not callable(getattr(module, 'presentation_asset_response', None)):
        abort(503)
    descriptor = module.presentation_assets()
    if descriptor.get('contract') != 'photon.level.assets' or type(descriptor.get('version')) is not int or descriptor['version'] != 1:
        abort(503)
    return module.presentation_asset_response(filename)
