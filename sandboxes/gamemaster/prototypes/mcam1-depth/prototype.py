"""Gamemaster motion-depth observations; no motion or camera control path."""
from pathlib import Path
import cv2
from flask import Blueprint, jsonify, request, send_from_directory
import live
from depth_config import number
from depth_service import DepthService

HERE = Path(__file__).parent
MANIFEST = dict(name='MCAM1 Depth', group='Photon Engine',
                description='Motion depth and Atom clearance from MCAM1 and measured arm feedback.',
                default_page='', pages=[dict(path='', label='MCAM1 Depth', newtab=True)])
bp = Blueprint('mcam1_depth', __name__)
_live = live.LiveState()
_service = None


def hub_init(ctx):
    global _service
    _service = DepthService(ctx, HERE/'calibration.json', _live.bump)
    _service.start_worker()


def hub_stop():
    global _service
    if _service:
        _service.close()
        _service = None


def depth_snapshot():
    if not _service:
        return dict(contract='hhh.mcam1.depth', version=1, status='unavailable', error='Module is not running')
    return _service.snapshot()


@bp.before_request
def guard():
    if request.method == 'POST':
        origin = request.headers.get('Origin')
        if origin and origin.rstrip('/') != request.host_url.rstrip('/'):
            return jsonify(error='Same-origin request required'), 403
        request.max_content_length = 16384
        if request.content_length and request.content_length > 16384:
            return jsonify(error='Request too large'), 413
        if _service is None:
            return jsonify(error='Module is not running'), 503


@bp.get('/')
def index():
    return send_from_directory(HERE/'web', 'index.html')


@bp.get('/<name>')
def asset(name):
    if name not in ('app.js', 'style.css', 'checkerboard.svg'):
        return jsonify(error='Not found'), 404
    return send_from_directory(HERE/'web', name)


@bp.get('/api/state')
def state():
    return jsonify(depth_snapshot())


@bp.get('/api/events')
def events():
    return _live.stream(depth_snapshot, interval=.1, shared=True)


@bp.post('/api/config')
def configure():
    try:
        return jsonify(config=_service.configure(request.get_json(silent=True)))
    except (ValueError, TypeError, KeyError, cv2.error) as exc:
        return jsonify(error=str(exc)), 400
    except OSError as exc:
        return jsonify(error=f'Could not save calibration: {exc}'), 503


@bp.post('/api/analysis')
def analysis():
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or set(data) != {'running'} or type(data['running']) is not bool:
        return jsonify(error='Expected running: true or false'), 400
    _service.set_running(data['running'])
    return jsonify(depth_snapshot())


@bp.post('/api/lens')
def lens():
    data = request.get_json(silent=True)
    try:
        if not isinstance(data, dict) or set(data)-{'action', 'columns', 'rows', 'square_mm'}:
            raise ValueError('Invalid lens calibration request')
        columns, rows = data.get('columns', 9), data.get('rows', 6)
        if type(columns) is not int or type(rows) is not int or not 4 <= columns <= 12 or not 4 <= rows <= 10:
            raise ValueError('Checkerboard inner corners must be 4–12 columns and 4–10 rows')
        square = number(data.get('square_mm', 10), 1, 100)
        _service.calibration(data.get('action'), columns, rows, square)
        return jsonify(depth_snapshot())
    except (ValueError, TypeError, KeyError, cv2.error) as exc:
        return jsonify(error=str(exc)), 400
    except OSError as exc:
        return jsonify(error=f'Could not save calibration: {exc}'), 503
