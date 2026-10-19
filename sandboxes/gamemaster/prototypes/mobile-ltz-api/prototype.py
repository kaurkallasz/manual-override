"""Team-isolated mobile presentation facade over versioned game, art and progress outputs."""
import json
import time
import threading
import uuid
import logging
from pathlib import Path
from shared.ltz_ui import manifest as shop_assets, asset_response as shop_asset_response
from flask import Blueprint, Response, abort, current_app, g, jsonify, request, send_from_directory
from camera_view import registration
import mcam1_view
from delivery_diagnostics import DeliveryDiagnostics
import live
import connection_log
import delay_analysis
from shared import delay_trace as trace
from shared.fixed_board import cue_layout
MANIFEST = {'name':'Mobile LTZ API','description':'Player payloads, delivery statistics and API diagnostics.',
            'group':'Photon Engine','default_page':'','pages':[{'path':'','label':'Delivery diagnostics'}, {'path':'delay-analysis','label':'Delay Analysis'}]}
bp=Blueprint('mobile_ltz_api',__name__)
_live=live.LiveState()
_team_live={'green':_live,'purple':live.LiveState()}
_ctx=None
_delivery_lock=threading.Lock()
_delivery_epoch=uuid.uuid4().hex
_delivery_sequence=0
_delivery_at=None
_diagnostics=DeliveryDiagnostics()
_diagnostic_errors=0
_diagnostic_error_logged_at=0.0
_cue_scope_lock = threading.Lock()
_cue_scope = None
_cue_scope_since = 0.0

def hub_init(ctx):
    global _ctx, _diagnostics, _diagnostic_errors, _cue_scope, _cue_scope_since
    _ctx=ctx
    delay_analysis.start(Path(__file__).parent / 'data' / 'delay-analysis')
    _diagnostics=DeliveryDiagnostics()
    _diagnostic_errors=0
    _cue_scope, _cue_scope_since = None, 0.0

def hub_stop():
    global _ctx
    delay_analysis.stop()
    _ctx=None


@trace.traced('mobile.observe')
def _observe(method, *args, **kwargs):
    """Observability must never interrupt player delivery."""
    global _diagnostic_errors, _diagnostic_error_logged_at
    try:
        getattr(_diagnostics, method)(*args, **kwargs)
    except Exception:
        _diagnostic_errors += 1
        if time.monotonic() - _diagnostic_error_logged_at > 60:
            _diagnostic_error_logged_at = time.monotonic()
            logging.getLogger(__name__).exception('Mobile delivery diagnostics failed')


def _operator_guard():
    if 'gamemaster' not in (request.environ.get('hhh.roles') or ()):
        abort(403)


@bp.route('/')
def index():
    _operator_guard()
    return send_from_directory(Path(__file__).parent, 'index.html')


@bp.route('/monitor.js')
@bp.route('/monitor.css')
def monitor_asset():
    _operator_guard()
    return send_from_directory(Path(__file__).parent, request.path.rsplit('/', 1)[-1])


@bp.route('/api/monitor')
def delivery_monitor_api():
    _operator_guard()
    side = request.args.get('side')
    channel = request.args.get('channel')
    if side not in (None, 'green', 'purple') or channel not in (None, 'generated', 'sse', 'http'):
        abort(400)
    result = _diagnostics.snapshot(side=side, payloads=request.args.get('payloads') == '1', channel=channel)
    result['observer_errors'] = _diagnostic_errors
    response = jsonify(result)
    response.headers['Cache-Control'] = 'no-store'
    return response


@bp.before_request
def begin_measurement():
    g.mobile_request_started = time.perf_counter()


@bp.after_request
@trace.traced('mobile.record_response')
def record_response(response):
    if '/api/delay' in request.path or '/delay-analysis' in request.path:
        return response
    started = getattr(g, 'mobile_request_started', None)
    if started is None:
        # Hub authentication may return before this blueprint's before_request.
        return response
    endpoint = (request.endpoint or '').rsplit('.', 1)[-1]
    if endpoint in {'index', 'monitor_asset', 'delivery_monitor_api', 'connection_diagnostics_api'}:
        return response
    if endpoint == 'mobile_events_api' and response.mimetype == 'text/event-stream':
        return response
    side = request.args.get('side', 'green')
    if side not in ('green', 'purple'):
        return response
    value = response.get_json(silent=True) if response.is_json and not response.is_streamed else None
    route = request.method + ' ' + (request.url_rule.rule if request.url_rule else request.path)
    _observe('http_response', side, route, response.status_code, response.content_length or 0,
             response.mimetype, (time.perf_counter() - started) * 1000,
             value=value, action=getattr(g, 'mobile_action', None))
    return response


def _record_action(data):
    # Use only a body the authenticated route already parsed. Never consume a
    # rejected or streaming request body just to add diagnostics.
    if isinstance(data, dict) and isinstance(data.get('action'), str):
        g.mobile_action = data['action'][:80]

def _module(slug):
    return _ctx.get_prototype(slug) if _ctx and _ctx.is_prototype_enabled(slug) else None

@trace.traced('mobile.game')
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

@trace.traced('mobile.camera_view')
def camera_view(game):
    alignment = None
    tracking = None
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
        if game.get('journey',{}).get('phase')=='calibration':
            observation = board.runtime_observation()
            if observation.get('contract')!='photon.board.runtime' or type(observation.get('version')) is not int or observation['version']!=1 or observation.get('status')!='ready' or not observation.get('corrected') or not -1<=time.time()-observation.get('frame_at',0)<=1.5:
                raise ValueError('Fresh corrected camera required for calibration')
            matrix,markers=[1,0,0,0,1,0,0,0],[30,31,32,33,34,35]
        else:
            alignment = {'status':'unavailable'}
            observation = board.camera_markers_snapshot()
            # Current detections are presentation evidence even while alignment
            # or the independent cue map is held. Never use them as cue targets.
            tracking = {**observation, 'server_time':time.time()}
            matrix, markers = registration(game['level'], observation, diagnostics=alignment)
            alignment['status'] = 'ready'
        tags=[]
        if game.get('journey',{}).get('phase')=='calibration':
            for tag in observation.get('tags',[]):
                if (type(tag.get('id')) is int and not 40<=tag['id']<=59 and tag.get('missing',0)==0
                        and all(type(tag.get(k)) in (int,float) and 0<=tag[k]<=1 for k in ('nx','ny'))):
                    tags.append({'id':tag['id'],'u':tag['nx'],'v':tag['ny']})
        return {'status':'ready', 'matrix':matrix, 'markers':markers,'tags':tags,
                'width':observation['width'], 'height':observation['height'],
                'frame_at':observation['frame_at'], 'frame_path':'assets/mobile-camera.jpg',
                'alignment':alignment, 'tracking':tracking}
    except Exception as exc:
        return {'status':'unavailable', 'error':str(exc), 'alignment':alignment, 'tracking':tracking}


@trace.traced('mobile.motion_safety')
def _motion_safety(side):
    """Read the same owner as Relay, without exposing guards or other sessions."""
    try:
        owner = _module('auto-pickup-game')
        if owner is None or not callable(getattr(owner,'calibration_safety_snapshot',None)):
            raise ValueError('Cal 2 safety owner unavailable')
        value = owner.calibration_safety_snapshot(side)
        if not isinstance(value,dict) or value.get('contract')!='hhh.cal2.safety' or type(value.get('version')) is not int or value['version']!=1:
            raise ValueError('Cal 2 safety contract unavailable')
        if value.get('status')!='ready':
            reason=value.get('error')
            raise ValueError(reason if isinstance(reason,str) and reason else 'Validated Cal 2 safety limits unavailable')
        result = {'status':'ready','revision':value.get('revision')}
        if (value.get('camera_compatibility') or {}).get('manual_only'):
            result['camera_compatibility'] = value['camera_compatibility']
        return result
    except Exception as exc:
        return {'status':'unavailable','error':str(exc)}


@trace.traced('mobile.motion_policy')
def _motion_policy(game, side):
    """Project Game's transition decision, also enforced by the physical relay."""
    try:
        policy = game.motion_policy(side)
        if (not isinstance(policy,dict) or policy.get('contract')!='photon.game.motion'
                or type(policy.get('version')) is not int or policy['version']!=1
                or policy.get('status')!='ready' or type(policy.get('blocked')) is not bool
                or policy.get('scope') not in ('player','tutorial','waiting')):
            raise ValueError('Game control policy unavailable')
        return policy
    except Exception as exc:
        return {'contract':'photon.game.motion','version':1,'status':'unavailable',
                'blocked':True,'error':str(exc)}


@trace.traced('mobile.snapshot', side='argument')
def mobile_snapshot(side='green'):
    """Player-facing projection; no administrative settings/history/roster."""
    global _delivery_sequence, _delivery_at
    started=time.perf_counter()
    try:
        game, value = _game()
    except ValueError as exc:
        value = {'status':'unavailable','error':str(exc)}
        if side in ('green', 'purple'):
            _observe('generated', side, value, (time.perf_counter()-started)*1000)
        return value
    if side not in ('green', 'purple'):
        raise ValueError('Unknown mobile team.')
    trace.annotate(side=side, run_id=value.get('run_id'))
    value['delay_analysis'] = trace.config(side)
    arms = value.pop('mobile_arms', {})
    value['mobile_arm'] = arms.get(side, value.get('mobile_arm') if side == 'green' else None)
    value['mobile_team'] = side
    value['mobile_motion_policy'] = _motion_policy(game, side)
    value['mobile_mcam1'] = trace.call('mobile.mcam1', mcam1_view.snapshot, _module)[0]
    if value.get('presentation'):
        value['presentation']={**value['presentation'],'assets':{**value['presentation'].get('assets',{}),**trace.call('mobile.shop_assets', shop_assets)}}
    value['mobile_camera'] = camera_view(value) if not value.get('virtual_play') else {'status':'unused'}
    value['mobile_safety'] = _motion_safety(side) if not value.get('virtual_play') else {'status':'unused'}
    value['mobile_cue_targets'] = _cue_targets_projection(value) if not value.get('virtual_play') else {'status':'unused'}
    for key in ('configuration', 'storage', 'inputs', 'progress', 'level_presets','next_loadouts'):
        value.pop(key, None)
    # Movement packets retain authoritative health/effects and short guides,
    # not internal lane bookkeeping or unnecessary float precision.
    fields=('id','enemy_type','x','y','vx','vy','facing_x','facing_y','hp','max_hp',
            'attacking','burn_until','electrocuted_until','electrocution_depth',
            'electrocution_intensity','motion','combat')
    value['enemies']=[{key:round(enemy[key],3) if isinstance(enemy[key],float) else enemy[key]
                       for key in fields if key in enemy} for enemy in value.get('enemies',[])]
    progress = _module('photon-progress')
    if progress and callable(getattr(progress, 'progress_snapshot', None)):
        try:
            profile = trace.call('mobile.progress', progress.public_snapshot, side)
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
            cal = trace.call('mobile.calibration', owner.calibration_session_snapshot)
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
                    if session and session.get('stage')=='perspective':
                        # Hidden centre targets must not return as cached labels.
                        camera['tags']=[tag for tag in tags if tag['id'] not in (30,32)]
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
    trace.annotate(sequence=_delivery_sequence)
    trace.measure('mobile.source_gap', value['delivery']['source_gap_ms'] or 0, side=side, sequence=_delivery_sequence)
    _observe('generated', side, value, (now-started)*1000)
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


@trace.traced('mobile.cue_targets_projection')
def _cue_targets_projection(game):
    """Read cached evidence for SSE and commands, scoped to this run/layout."""
    global _cue_scope, _cue_scope_since
    try:
        board = _module('photon-board')
        if not board or not callable(getattr(board, 'cue_targets_snapshot', None)):
            raise ValueError('Cue target mapping unavailable.')
        field = None
        if game.get('journey', {}).get('phase') == 'calibration':
            field = _module('playfield-areas')
            field = field.display_snapshot() if field else {}
        scope, fixed_ids = cue_layout(game, field)
        with _cue_scope_lock:
            if scope != _cue_scope:
                _cue_scope, _cue_scope_since = scope, time.time()
            since = _cue_scope_since
        # Filter at the camera owner BEFORE learning/conflict detection. Merely
        # hiding unrelated tags here leaves their global hold/epoch in effect.
        value = board.cue_targets_snapshot(scope=scope, fixed_ids=fixed_ids)
        if (value.get('contract') != 'photon.board.cue-targets' or type(value.get('version')) is not int
                or value['version'] != 2 or value.get('layout_scope') != scope
                or value.get('fixed_ids') != sorted(fixed_ids)):
            raise ValueError('Cue target mapping contract mismatch.')
        value.update(scope=scope, scope_since=since, server_time=time.time())
        # The owner acknowledges a run/layout-specific map. A later reader
        # must not discard fixed targets already learned by another display.
        return value
    except Exception as exc:
        return dict(contract='photon.board.cue-targets', version=2, status='unavailable', tags=[], error=str(exc))


@bp.route('/api/cue-targets')
def cue_targets_api():
    _mobile_guard()
    try:
        _, game = _game()
        value = _cue_targets_projection(game)
    except ValueError as exc:
        value = dict(contract='photon.board.cue-targets', version=2, status='unavailable', tags=[], error=str(exc))
    response = jsonify(value)
    response.headers['Cache-Control'] = 'no-store'
    return response


@bp.route('/api/diagnostics', methods=['POST', 'GET'])
def connection_diagnostics_api():
    side = _mobile_guard(mutation=request.method == 'POST')
    if request.method == 'GET' and 'gamemaster' not in (request.environ.get('hhh.roles') or ()):
        abort(403)
    try:
        if request.method == 'GET':
            return Response(connection_log.export(), mimetype='application/x-ndjson', headers={
                'Content-Disposition': 'attachment; filename=mobile-connection-events.jsonl',
                'Cache-Control': 'no-store'})
        # Bound reads even if Content-Length is omitted.
        raw = request.stream.read(65537)
        if len(raw) > 65536:
            abort(413)
        value = json.loads(raw)
        if isinstance(value, dict) and value.get('contract') == trace.CONTRACT:
            return jsonify(delay_analysis.client_batch(side, value))
        if len(raw) > (12288 if trace.enabled() else 4096):
            abort(413)
        if not trace.call('logging.connection_event', connection_log.append, side, value):
            return jsonify(ok=False, error='Diagnostic rate limit.'), 429
        return jsonify(ok=True)
    except (ValueError, UnicodeDecodeError) as exc:
        return jsonify(ok=False, error=str(exc)), 400
    except OSError:
        current_app.logger.exception('Could not persist mobile connection diagnostics')
        return jsonify(ok=False, error='Connection log storage unavailable.'), 503


def _purple_mobile_snapshot():
    return mobile_snapshot('purple')


@bp.route('/api/events')
def mobile_events_api():
    side = _mobile_guard()
    response = _team_live[side].stream(mobile_snapshot if side == 'green' else _purple_mobile_snapshot, interval=.15, shared=True,
                        # Start/reset must deliver a complete scene to every
                        # team, even when the map itself has not changed.
                        identity_fields=('run_id', 'level_revision'), envelope=True,
                        # Progress contains shop.server_time and remains dynamic;
                        # otherwise its clock forces full scene resends each tick.
                        static_fields=('level', 'presentation', 'settings', 'loadout',
                                       'force_field_blockers', 'row_barrier_geometry'))
    original = response.response
    def measured_stream():
        failed = False
        _observe('stream_open', side)
        try:
            for chunk in original:
                _observe('emitted', side, chunk)
                yield chunk
        except GeneratorExit:
            raise
        except Exception:
            failed = True
            raise
        finally:
            try:
                if callable(getattr(original, 'close', None)):
                    original.close()
            finally:
                _observe('stream_close', side, failed=failed)
    response.response = measured_stream()
    return response


@bp.route('/api/command', methods=['POST'])
def mobile_command_api():
    side = _mobile_guard(mutation=True)
    data = request.get_json(silent=True)
    _record_action(data)
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
    _record_action(data)
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


@bp.route('/api/saved-game', methods=['POST'])
def saved_game_api():
    side = _mobile_guard(mutation=True)
    try:
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or len(json.dumps(data)) > 2048:
            raise ValueError('invalid saved game command')
        owner, _ = _game()
        result = owner.saved_game_command(side, data)
        if (result.get('contract') != 'photon.progress' or type(result.get('version')) is not int
                or result['version'] != 2 or result.get('status') != 'ready'):
            raise ValueError('Saved game contract unavailable')
        for stream in _team_live.values(): stream.bump()
        return jsonify(result)
    except (ValueError, PermissionError, TypeError) as exc:
        return jsonify(ok=False, error=str(exc)), 400


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
        _record_action(data)
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
    if filename == 'mcam1.jpg':
        descriptor, image = mcam1_view.snapshot(_module)
        if image is None:
            return jsonify(descriptor), 503
        return Response(image, mimetype='image/jpeg', headers={'Cache-Control':'no-store'})
    if filename.startswith('ui/ltz/'):
        return shop_asset_response(filename.removeprefix('ui/ltz/'))
    if filename == 'mobile-camera.jpg':
        camera = _module('camera-calibration')
        if not camera or not callable(getattr(camera, 'preview_frame', None)):
            abort(503)
        frame = camera.preview_frame(mobile=True)
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


delay_analysis.register(bp, _operator_guard, _mobile_guard)
