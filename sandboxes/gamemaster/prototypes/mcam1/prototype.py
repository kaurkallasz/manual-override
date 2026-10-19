"""MCAM1 owns the XIAO preview, USB sensor controls and AI observations."""
import atexit
import math
from pathlib import Path
import threading
import time
from flask import Blueprint, Response, jsonify, request, send_from_directory
import live
from capture import Capture
from xiao_controls import XiaoControls
from mcam1_firmware import FirmwareManager, MAX_UPLOAD, devices

HERE = Path(__file__).parent
MANIFEST = {'name': 'MCAM1', 'group': 'Photon Engine',
            'description': 'XIAO USB Webcam LL Bulk · live preview, manual image controls and on-device AI.',
            'default_page': '', 'pages': [{'path': '', 'label': 'MCAM1', 'newtab': True}]}
bp = Blueprint('mcam1', __name__)
_live = live.LiveState()
_firmware_live = live.LiveState()
_flasher = None
_capture = _controls = _stop = _thread = None
_state_lock = threading.RLock()
_control_data = _ai_data = None
_control_ready = False


def hub_init(ctx):
    global _capture, _controls, _stop, _thread, _flasher
    _capture, _controls, _stop = Capture(), XiaoControls(), threading.Event()
    _flasher = FirmwareManager(HERE)
    _thread = threading.Thread(target=_observe, daemon=True, name='mcam1-ai')
    _thread.start()
    atexit.register(hub_stop)


def hub_stop():
    global _capture, _controls, _control_ready, _control_data, _ai_data, _flasher
    if _stop:
        _stop.set()
    if _thread and _thread is not threading.current_thread():
        _thread.join(timeout=5)
    if _capture:
        _capture.close()
    if _controls:
        _controls.close()
    if _flasher:
        _flasher.close()
        _flasher = None
    _capture = _controls = None
    _control_ready, _control_data, _ai_data = False, None, None


def _observe():
    global _ai_data
    while not _stop.wait(.25):
        with _state_lock:
            if not _control_ready or not _ai_data or _ai_data.get('transport_status') != 'ready':
                continue
            _ai_data = detection_snapshot()


def firmware_busy():
    return bool(_flasher and _flasher.busy())


def control_snapshot(action='get', name=None, value=None):
    with _state_lock:
        if firmware_busy():
            return dict(contract='hhh.camera.controls', version=1, status='unavailable', error='Firmware flashing in progress')
        return _control_snapshot(action, name, value)


def _control_snapshot(action='get', name=None, value=None):
    if _controls is None:
        return dict(contract='hhh.camera.controls', version=1, status='unavailable', error='MCAM1 is disabled')
    try:
        return {**_controls.request(action, name, value), 'contract':'hhh.camera.controls', 'version':1, 'status':'ready'}
    except ValueError:
        raise
    except Exception as exc:
        return dict(contract='hhh.camera.controls', version=1, status='unavailable', error=str(exc))


def detection_snapshot(action='get', name=None, value=None):
    with _state_lock:
        if firmware_busy():
            return dict(contract='hhh.camera.detections', version=1, status='unavailable', error='Firmware flashing in progress')
        return _detection_snapshot(action, name, value)


def _detection_snapshot(action='get', name=None, value=None):
    base = dict(contract='hhh.camera.detections', version=1)
    if _controls is None:
        return {**base, 'status':'unavailable', 'error':'MCAM1 is disabled'}
    try:
        started = time.monotonic()
        data = _controls.request_ai(action, name, value)
        data = {**data, **base, 'transport_status':'ready', 'received_at':time.time()}
        if data['age_ms'] >= 0:
            data['age_ms'] += math.ceil((time.monotonic()-started)*1000)
        usable = data['state']=='ready' and data['settings']['enabled']==1 and 0 <= data['age_ms'] <= data['settings']['stale_ms']
        data['status'] = 'ready' if usable else 'unavailable'
        if not usable:
            data['boxes'] = []
            if data['state']=='ready':
                data['state'] = 'waiting_for_detection'
        return data
    except ValueError:
        raise
    except Exception as exc:
        return {**base, 'status':'unavailable', 'error':str(exc)}


def still_snapshot():
    data = _capture.still() if _capture else dict(status='unavailable', error='MCAM1 is disabled', image=None)
    return {**data, 'contract':'hhh.camera.still', 'version':1, 'source':'camera', 'corrected':False, 'mime_type':'image/jpeg'}


def _snapshot():
    camera = _capture.snapshot(preview=True) if _capture else dict(status='unavailable', error='MCAM1 is disabled', preview=None)
    # Do not wait on USB round trips to deliver video.
    ai = dict(_ai_data) if _ai_data else None
    if ai and ai.get('transport_status') == 'ready' and ai['age_ms'] >= 0:
        ai['age_ms'] += max(0, math.ceil((time.time()-ai['received_at'])*1000))
        if ai['age_ms'] > ai['settings']['stale_ms']:
            ai['boxes'], ai['status'] = [], 'unavailable'
            if ai['state'] == 'ready':
                ai['state'] = 'waiting_for_detection'
    return dict(camera=camera, controls=_control_data, ai=ai, firmware_busy=firmware_busy())


@bp.before_request
def guard():
    if request.method == 'POST':
        origin = request.headers.get('Origin')
        if origin and origin.rstrip('/') != request.host_url.rstrip('/'):
            return jsonify(error='Same-origin request required'), 403
        limit = MAX_UPLOAD + 65536 if request.endpoint and request.endpoint.endswith('.firmware_upload') else 4096
        request.max_content_length = limit
        if request.content_length and request.content_length > limit:
            return jsonify(error='Request too large'), 413


@bp.route('/')
def index():
    return send_from_directory(HERE / 'web', 'index.html')


@bp.route('/<name>')
def asset(name):
    if name not in ('style.css', 'app.js', 'camera-client.js', 'ai-overlay.js', 'firmware.js'):
        return jsonify(error='Not found'), 404
    return send_from_directory(HERE / 'web', name)


@bp.route('/api/events')
def events():
    return _live.stream(_snapshot, interval=1/30, shared=True)


@bp.route('/api/capture', methods=['POST'])
def capture_api():
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or set(data)-{'action','mode'} or data.get('action') not in ('start','stop'):
        return jsonify(error='Expected start/stop and a supported mode'), 400
    if _capture is None:
        return jsonify(error='MCAM1 is disabled'), 503
    try:
        with _state_lock:
            if firmware_busy():
                return jsonify(error='Firmware flashing in progress'), 409
            if data['action']=='start':
                # Identify the board via its USB serial identity before starting video.
                _controls.available_port()
                _capture.start(data.get('mode', '480,320,30'))
            else:
                _capture.stop()
    except (ValueError, TypeError) as exc:
        return jsonify(error=str(exc)), 400
    except Exception as exc:
        return jsonify(error=str(exc)), 503
    _live.bump()
    return jsonify(_capture.snapshot())


def _command(namespace):
    global _control_data, _control_ready, _ai_data
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or set(data)-{'action','name','value'}:
        return jsonify(error='Expected a JSON control request'), 400
    try:
        with _state_lock:
            if firmware_busy():
                return jsonify(error='Firmware flashing in progress'), 409
            fn = control_snapshot if namespace=='ctrl' else detection_snapshot
            result = fn(data.get('action','get'), data.get('name'), data.get('value'))
            if namespace=='ctrl':
                _control_data = result
                _control_ready = result['status']=='ready'
            else:
                _ai_data = result
    except (ValueError, TypeError) as exc:
        return jsonify(error=str(exc)), 400
    _live.bump()
    return jsonify(result), 200 if result.get('transport_status', result['status'])=='ready' else 503


@bp.route('/api/controls', methods=['POST'])
def controls_api():
    return _command('ctrl')


@bp.route('/api/ai', methods=['POST'])
def ai_api():
    return _command('ai')


@bp.route('/api/disconnect', methods=['POST'])
def disconnect_api():
    global _control_ready, _control_data, _ai_data
    with _state_lock:
        _control_ready, _control_data, _ai_data = False, None, None
        if _controls:
            _controls.close()
    _live.bump()
    return jsonify(ok=True)


def _release_camera():
    global _control_ready, _control_data, _ai_data
    # Caller owns _state_lock, so no observer or control command can reopen USB.
    _control_ready, _control_data, _ai_data = False, None, None
    if _capture:
        _capture.stop()
    if _controls:
        _controls.close()


@bp.route('/api/firmware/state')
def firmware_state():
    if not _flasher:
        return jsonify(error='Firmware utility unavailable'), 503
    return jsonify(_flasher.snapshot())


@bp.route('/api/firmware/events')
def firmware_events():
    return _firmware_live.stream(lambda: _flasher.snapshot() if _flasher else dict(error='MCAM1 disabled'), interval=.5, shared=True)


@bp.route('/api/firmware/devices')
def firmware_devices():
    try:
        return jsonify(devices=devices())
    except Exception as exc:
        return jsonify(error=str(exc), devices=[]), 503


@bp.route('/api/firmware/builtin')
def firmware_builtin():
    return send_from_directory(HERE / 'firmware', 'xiao-ai-v1-bulk.zip', as_attachment=True)


@bp.route('/api/firmware/upload', methods=['POST'])
def firmware_upload():
    if not _flasher:
        return jsonify(error='Firmware utility unavailable'), 503
    files = request.files.getlist('bundle')
    if len(files) != 1 or set(request.files) != {'bundle'}:
        return jsonify(error='Upload one firmware ZIP in the bundle field'), 400
    try:
        result = _flasher.stage(files[0].stream)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    except RuntimeError as exc:
        return jsonify(error=str(exc)), 409
    except Exception as exc:
        return jsonify(error=f'Could not validate bundle: {exc}'), 400
    _firmware_live.bump()
    return jsonify(result)


@bp.route('/api/firmware/flash', methods=['POST'])
def firmware_flash():
    if not _flasher:
        return jsonify(error='Firmware utility unavailable'), 503
    data = request.get_json(silent=True)
    if (not isinstance(data, dict) or set(data) != {'bundle_id','device_token','confirmation'}
            or any(not isinstance(v, str) or len(v) > 150 for v in data.values())):
        return jsonify(error='Expected bundle_id, device_token and target confirmation'), 400
    try:
        with _state_lock:
            result = _flasher.start(data['bundle_id'], data['device_token'], data['confirmation'], _release_camera)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    except RuntimeError as exc:
        return jsonify(error=str(exc)), 409
    _live.bump()
    _firmware_live.bump()
    return jsonify(result), 202


@bp.route('/api/frame')
def frame_api():
    frame = still_snapshot()
    return jsonify({k:v for k,v in frame.items() if k != 'image'}), 200 if frame['status']=='ready' else 503


@bp.route('/api/still')
def still_api():
    frame = still_snapshot()
    if frame['status']!='ready':
        return jsonify({k:v for k,v in frame.items() if k != 'image'}), 503
    return Response(frame['image'], mimetype='image/jpeg', headers={
        'Cache-Control':'no-store', 'X-Camera-Contract':'hhh.camera.still', 'X-Camera-Version':'1',
        'X-Camera-Width':str(frame['width']), 'X-Camera-Height':str(frame['height']),
        'X-Camera-Captured-At':str(frame['captured_at']), 'X-Camera-Frame-Id':str(frame['frame_id'])})
