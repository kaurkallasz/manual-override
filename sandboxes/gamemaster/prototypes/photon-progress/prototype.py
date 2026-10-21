"""Photon Progress owns durable players, currency, mastery and result history."""
import json
import os
from pathlib import Path
import threading
import time

from flask import Blueprint, jsonify, request, send_from_directory
import live
from store import ProgressStore
from score_upload import UploadClient

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE / 'data'
CONTRACT = 'photon.progress'
VERSION = 2
MANIFEST = {'name': 'Photon Progress', 'group': 'Photon Engine',
            'description': 'Saved LTZ players, credits, event control unlocks and performance history.',
            'default_page': '', 'pages': [{'path': '', 'label': 'Player progress'}]}
bp = Blueprint('photon_progress', __name__)
_live = live.LiveState()
_uploader = None
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
        state = _ready().snapshot((query or {}).get('side'))
        score = state['scoreboard']
        if score['email_added'] and score['upload_state'] != 'submitted' and not (_uploader and _uploader.paired):
            score.update(upload_state='setup_required', message='Your email addresses are saved on this game, but online statistics are not connected yet. Ask the operator to finish setup; sign-in emails will send automatically afterward.')
        return _output(state)
    except Exception as exc:
        return {'contract': CONTRACT, 'version': VERSION, 'status': 'unavailable', 'ok': False, 'error': str(exc)}


def scoreboard_link_snapshot():
    """photon.scoreboard-link v1: non-blocking, credential-free operator notice.

    Configuration is atomically replaced by the uploader. Reading it directly
    through its validator avoids waiting on the network worker's upload lock.
    """
    result = {'contract': 'photon.scoreboard-link', 'version': 1, 'status': 'unavailable'}
    try:
        if _uploader is None:
            return result
        cfg = _uploader.read_config()
        pending = cfg.get('pairing_request', {})
        state = 'linked' if cfg.get('installation_id') else pending.get('status', 'unlinked')
        if state not in ('linked', 'unlinked', 'submitting', 'pending', 'cancelling',
                         'cancelled', 'rejected', 'expired', 'revoked'):
            return result
        return dict(result, status='ready', state=state,
                    upload_delayed=state == 'linked' and bool(_uploader.error))
    except Exception:
        return result


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


def attempt_snapshot(run_id):
    return _output({'attempt':_ready().attempt(run_id)})


def history_snapshot(query):
    return _output({'history': _ready().history(query.get('player_id'), query)})


def event_results_snapshot(query):
    """photon.progress v2: read-only data for a future scoreboard consumer."""
    return _output({'results': _ready().event_results(query.get('event_id'),
                    cursor=query.get('cursor',0),limit=query.get('limit',100))})


def player_command(side, value):
    """Owner-public mutation; caller must authenticate the supplied side."""
    if side not in ('green', 'purple') or not isinstance(value, dict):
        raise ValueError('valid player side and command required')
    if value.get('side', side) != side:
        raise PermissionError('wrong player side')
    action = value.get('action')
    if not value.get('event_id'):raise ValueError('Event identity required; refresh this client')
    if action == 'create':
        if type(value.get('select', False)) is not bool:
            raise ValueError('select must be true or false')
        result = _ready().create_player(value.get('name'), value.get('operation_id'), side=side if value.get('select') else None,event_id=value['event_id'],email=value.get('email'))
    elif action == 'scoreboard_email':
        _ready().score_set_contact(side,value.get('email'),value['event_id'])
        result = {}
    elif action == 'select':
        _ready().select_player(side, value.get('player_id'),value['event_id'])
        result = {}
    else:
        result = _ready().mutate_player(side, value)
    _live.bump()
    return _output({'result': result, **public_snapshot(side)})


def reserve_lesson_roster(value):
    result = _ready().reserve_lesson_roster(value['id'])
    _live.bump()
    return _output({'lesson_roster': result})


def reserve_roster(value):
    result = _ready().reserve_roster(value['id'],value.get('expected_players'))
    _live.bump()
    return _output({'reservation': result})


def release_start_reservation(value):
    _ready().release_start_reservation(value['id'])
    _live.bump()
    return _output()


def release_roster(value):
    _ready().release_roster(value['id'])
    _live.bump()
    return _output()


def complete_lesson(value):
    result = _ready().complete_lesson(value)
    _live.bump()
    return _output({'result': result})


def economy_snapshot():
    return _ready().economy_snapshot()

def economy_command(value):
    result=_ready().save_prices(value)
    _live.bump()
    return {**economy_snapshot(),'result':result}

def event_snapshot():
    return progress_snapshot()


def event_preview(value):
    _ready().event_preview(value)
    return _output()


def event_command(value):
    result=_ready().event_command(value);_live.bump()
    return _output({'result':result,**_ready().snapshot()})


def bind_game_atoms(value):
    result=_ready().bind_atoms(value);_live.bump()
    return _output({'game':result})


def advance_level(value):
    result=_ready().advance_level(value);_live.bump()
    return _output({'attempt':result})


def control_policy(side):
    """Read-only server capability contract; never accepts browser claims."""
    return _output(_ready().control_policy(side))


def saved_game_command(value):
    """Game serializes this between-match operation with Start and transitions."""
    result = _ready().game_command(value)
    _live.bump()
    return _output({'result': result})


def saved_game_preview(value):
    _ready().game_preview(value)
    return _output()


def prepare_game():
    _ready().prepare_game()
    _live.bump()
    return progress_snapshot()


def hub_init(ctx):
    global _store, _error, _uploader
    if _uploader: _uploader.stop()
    with _lock:
        try:
            candidate = ProgressStore(DATA_DIR / 'progress.sqlite3')
            candidate.initialize()
            _store, _error = candidate, None
            _uploader = UploadClient(candidate, DATA_DIR / 'scoreboard', _live.bump)
            try:
                config = _uploader.read_config()
                if config.get('installation_id') or config.get('pairing_request'): _uploader.start()
            except Exception:
                _uploader.error = 'Installation configuration unavailable; saved game progress remains available'
        except Exception as exc:
            _store, _error = None, str(exc)
    _live.bump()


def hub_stop():
    global _store, _error, _uploader
    if _uploader: _uploader.stop()
    _uploader = None
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
    return {'player_id': player_id, 'combined': request.args.get('combined') == '1', **{k: v for k, v in request.args.items() if k in ('tier','side_at_run', 'level', 'from', 'to', 'cohort', 'cursor', 'limit', 'dataset')}}


def public_snapshot(side):
    state = progress_snapshot({'side': side})
    if state['status'] == 'ready':
        # Only the chosen side's full profile is exposed; public roster is names/tiers.
        state['roster'] = {team: {k: p[k] for k in ('id', 'name', 'selected_control', 'is_test')} for team, p in state['roster'].items()}
        state['active_attempts'] = [{**a, 'participants': [{k: p[k] for k in ('player_id', 'name', 'side', 'control_tier')} for p in a['participants']]} for a in state['active_attempts']]
    return state


_public = public_snapshot


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
    return jsonify(player_command(side, data))


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


@bp.route('/api/event-results')
def event_results_api():
    # Prepared data only. Public web access is a separate, future feature.
    _admin()
    return jsonify(event_results_snapshot(request.args))


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


def _scoreboard_admin():
    _admin()
    if request.method == 'POST':
        origin = request.headers.get('Origin')
        if origin and origin.rstrip('/') != request.host_url.rstrip('/'):
            raise PermissionError('Same-origin request required')
        if not request.is_json:
            raise ValueError('JSON request required')
    if _uploader is None:
        raise ValueError('Scoreboard uploader unavailable')


@bp.route('/api/scoreboard', methods=['GET','POST'])
def scoreboard_api():
    _scoreboard_admin()
    if request.method == 'POST':
        data=request.get_json()
        if data.get('action') == 'request_pairing':
            return jsonify(_output({'scoreboard':_uploader.request_pairing(data.get('name'),data.get('contact_email'))}))
        if data.get('action') == 'cancel_request':
            return jsonify(_output({'scoreboard':_uploader.cancel_request()}))
        if data.get('action') == 'pair':
            result=_uploader.pair(data.get('code'),data.get('name'))
            _uploader.start()
            return jsonify(_output({'scoreboard':result}))
        if data.get('action') == 'disconnect':
            _uploader.disconnect()
        elif data.get('action') == 'retry':
            with _ready().transaction(write=True) as db:
                db.execute('UPDATE score_outbox SET next_at=0')
            _uploader.pair_next = 0
            _uploader.start()
            _uploader.wake.set()
        else:
            raise ValueError('Unknown scoreboard action')
    return jsonify(_output({'scoreboard':_uploader.status()}))


@bp.route('/scoreboard-admin.js')
def scoreboard_admin_script():
    _admin()
    return send_from_directory(HERE, 'scoreboard-admin.js')
