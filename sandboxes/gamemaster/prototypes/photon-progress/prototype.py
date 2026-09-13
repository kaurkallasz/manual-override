"""Photon Progress owns durable players, currency, mastery and result history."""
import json
import os
from pathlib import Path
import threading
import time

from flask import Blueprint, jsonify, request, send_from_directory
import live
from store import ProgressStore

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE / 'data'
CONTRACT = 'photon.progress'
VERSION = 1
MANIFEST = {'name': 'Photon Progress', 'group': 'Photon Engine',
            'description': 'Saved LTZ players, credits, three-win control unlocks and performance history.',
            'default_page': '', 'pages': [{'path': '', 'label': 'Player progress'}]}
bp = Blueprint('photon_progress', __name__)
_live = live.LiveState()
_store = None
_error = 'not initialized'
_lock = threading.RLock()


def _ready():
    if _store is None:
        raise ValueError(_error or 'Photon Progress unavailable')
    return _store


def _output(value=None):
    return {'contract': CONTRACT, 'version': VERSION, 'status': 'ready', 'ok': True, **(value or {})}


def progress_snapshot(query=None):
    try:
        return _output(_ready().snapshot((query or {}).get('side')))
    except Exception as exc:
        return {'contract': CONTRACT, 'version': VERSION, 'status': 'unavailable', 'ok': False, 'error': str(exc)}


def begin_attempt(value):
    result = _ready().begin(value)
    _live.bump()
    return _output({'attempt': result})


def checkpoint_attempt(value):
    result = _ready().record(value)
    _live.bump()
    return _output({'attempt': result})


def finalize_attempt(value):
    result = _ready().record(value, final=True)
    _live.bump()
    return _output({'attempt': result})


def recover_attempts():
    _ready().recover()
    _live.bump()
    return _output()


def history_snapshot(query):
    return _output({'history': _ready().history(query['player_id'], query)})


def control_policy(side):
    """Read-only server capability contract; never accepts browser claims."""
    return _output(_ready().control_policy(side))


def hub_init(ctx):
    global _store, _error
    with _lock:
        try:
            candidate = ProgressStore(DATA_DIR / 'progress.sqlite3')
            candidate.initialize()
            _store, _error = candidate, None
        except Exception as exc:
            _store, _error = None, str(exc)
    _live.bump()


def hub_stop():
    global _store, _error
    with _lock:
        _store, _error = None, 'stopped'
    _live.bump()


def _side():
    roles = request.environ.get('hhh.roles') or set()
    requested = request.args.get('side') or (request.get_json(silent=True) or {}).get('side')
    if requested not in ('green', 'purple'):
        raise PermissionError('a Green or Purple side is required')
    if requested not in roles and 'gamemaster' not in roles:
        raise PermissionError('this side is not authorized')
    return requested


def _admin():
    if 'gamemaster' not in (request.environ.get('hhh.roles') or set()):
        raise PermissionError('Gamemaster required')


def _player_query():
    side = _side()
    state = _ready().snapshot(side)
    player_id = state['player']['id'] if state['player'] else None
    if 'gamemaster' in (request.environ.get('hhh.roles') or set()) and request.args.get('player_id'):
        player_id = request.args['player_id']
    if not player_id:
        raise ValueError('select a player first')
    return {'player_id': player_id, **{k: v for k, v in request.args.items() if k in ('tier', 'level', 'from', 'to', 'cohort', 'cursor', 'limit', 'dataset')}}


def _public(side):
    state = progress_snapshot({'side': side})
    if state['status'] == 'ready':
        # Only the chosen side's full profile is exposed; public roster is names/tiers.
        state['roster'] = {team: {k: p[k] for k in ('id', 'name', 'selected_control')} for team, p in state['roster'].items()}
        state['active_attempts'] = [{**a, 'participants': [{k: p[k] for k in ('player_id', 'name', 'side', 'control_tier')} for p in a['participants']]} for a in state['active_attempts']]
    return state


@bp.errorhandler(Exception)
def failed(exc):
    status = 403 if isinstance(exc, PermissionError) else 400 if isinstance(exc, (ValueError, KeyError, TypeError)) else 503
    return jsonify({'ok': False, 'status': 'unavailable', 'error': str(exc)}), status


@bp.route('/')
def index():
    return send_from_directory(HERE, 'index.html')


@bp.route('/api/state')
def state_api():
    return jsonify(_public(_side()))


@bp.route('/api/events')
def events_api():
    side = _side()
    return _live.stream(lambda: _public(side))


@bp.route('/api/player', methods=['POST'])
def player_api():
    side = _side()
    data = request.get_json(silent=True) or {}
    action = data.get('action')
    if action == 'create':
        result = _ready().create_player(data.get('name'), data.get('operation_id'))
    elif action == 'select':
        _ready().select_player(side, data.get('player_id'))
        result = {}
    else:
        result = _ready().mutate_player(side, data)
    _live.bump()
    return jsonify(_output({'result': result, **_public(side)}))


@bp.route('/api/history')
def history_api():
    return jsonify(history_snapshot(_player_query()))


@bp.route('/api/backup')
def export_api():
    _admin()
    backup = _ready().export()
    if any(json.loads(row['data'])['outcome'] == 'running' for row in backup['tables']['attempts']):
        raise ValueError('finish active attempts before exporting a portable backup')
    response = jsonify(backup)
    response.headers['Content-Disposition'] = 'attachment; filename=ltz-player-progress.json'
    return response


@bp.route('/api/backup', methods=['POST'])
def import_api():
    _admin()
    if request.content_length is None or request.content_length > 20000000:
        raise ValueError('backup must be at most 20 MB')
    data = request.get_json(silent=True) or {}
    preview = data.get('preview') is not False
    with _lock, _ready().lock:
        result = _ready().import_backup(data.get('backup'), preview=True)
        if not preview:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            path = DATA_DIR / f'backup-before-import-{time.time_ns()}.json'
            temp = path.with_suffix('.tmp')
            with temp.open('w') as handle:
                json.dump(_ready().export(), handle)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, path)
            result = _ready().import_backup(data['backup'])
    if not preview:
        _live.bump()
    return jsonify(_output({'preview': preview, **result}))
