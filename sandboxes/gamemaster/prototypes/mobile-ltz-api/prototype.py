"""Green mobile presentation facade over versioned game, art and progress outputs."""
import json
import time
import threading
import uuid
from flask import Blueprint, Response, abort, jsonify, request
from camera_view import registration
import live
MANIFEST = {'name':'Mobile LTZ API','description':'Authenticated Green mobile presentation adapter.','group':'Photon Engine'}
bp=Blueprint('mobile_ltz_api',__name__)
_live=live.LiveState()
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
        matrix, markers = registration(game['level'], observation)
        return {'status':'ready', 'matrix':matrix, 'markers':markers,
                'width':observation['width'], 'height':observation['height'],
                'frame_at':observation['frame_at'], 'frame_path':'assets/mobile-camera.jpg'}
    except Exception as exc:
        return {'status':'unavailable', 'error':str(exc)}


def mobile_snapshot():
    """Player-facing projection; no administrative settings/history/roster."""
    global _delivery_sequence, _delivery_at
    started=time.perf_counter()
    try:
        _, value = _game()
    except ValueError as exc:
        return {'status':'unavailable','error':str(exc)}
    value['mobile_camera'] = camera_view(value) if not value.get('virtual_play') else {'status':'unused'}
    for key in ('configuration', 'storage', 'inputs', 'progress'):
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
        profile = progress.progress_snapshot({'side': 'green'})
        if profile.get('contract') == 'photon.progress' and type(profile.get('version')) is int and profile['version'] == 1:
            value['mobile_progress'] = {key: profile.get(key) for key in ('status', 'player', 'error')}
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
    if not set(request.environ.get('hhh.roles') or ()) & {'green', 'gamemaster'}:
        abort(403)
    if mutation:
        origin = request.headers.get('Origin')
        if origin and origin.rstrip('/') != request.host_url.rstrip('/'):
            abort(403)
        if not request.is_json:
            abort(415)


@bp.route('/api/state')
def mobile_state_api():
    _mobile_guard()
    return jsonify(mobile_snapshot())


@bp.route('/api/events')
def mobile_events_api():
    _mobile_guard()
    return _live.stream(mobile_snapshot, interval=.15, shared=True,
                        # Start/reset must deliver a complete scene to every
                        # team, even when the map itself has not changed.
                        identity_fields=('run_id', 'level_revision'), envelope=True,
                        static_fields=('level', 'presentation', 'settings', 'loadout',
                                       'force_field_blockers', 'row_barrier_geometry', 'mobile_progress'))


@bp.route('/api/command', methods=['POST'])
def mobile_command_api():
    _mobile_guard(mutation=True)
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or len(json.dumps(data)) > 2048:
        return jsonify(ok=False, error='Invalid mobile command.'), 400
    if data.get('side', 'green') != 'green':
        abort(403)
    try:
        game, snapshot = _game()
        if data.get('action') == 'turret_aim':
            if not callable(getattr(game, 'mobile_turret_aim', None)):
                raise ValueError('Player turret aiming is unavailable.')
            if not snapshot.get('virtual_play') and camera_view(snapshot).get('status') != 'ready':
                raise ValueError('Camera alignment is unavailable. Wait for tracking to return.')
            result = game.mobile_turret_aim(data)
            _live.bump()
            return jsonify(ok=True, tower=result, server_time=time.time())
        result = game.mobile_command(data)
        _live.bump()
        return jsonify(ok=True, arm=result, server_time=time.time())
    except (ValueError, PermissionError) as exc:
        return jsonify(ok=False, error=str(exc)), 400


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
