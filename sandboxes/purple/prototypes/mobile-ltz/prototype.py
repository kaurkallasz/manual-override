"""Purple's touch-first mobile LTZ presentation; gameplay lives in Photon Game."""
from pathlib import Path
import re
import uuid
from flask import Blueprint, Response, abort, jsonify, request

HERE = Path(__file__).resolve().parents[4] / 'shared/mobile_ltz'
TEAM = 'purple'
MANIFEST = {'name': 'mobile ltz', 'description': 'Touch controller and live virtual battlefield.',
            'default_page': '', 'pages': [{'path': '', 'label': 'mobile ltz'}]}
bp = Blueprint('purple_mobile_ltz', __name__)
CLIENT_FILES = ('index.html', 'mobile.css', 'mobile.js', 'viewport.js', 'live-game.js', 'network.js')
_client = None
_ctx = None


def hub_init(ctx):
    global _client, _ctx
    _ctx = ctx
    # Freeze one complete UI per launch. A refresh cannot mix generations.
    files = {name: (HERE / name).read_text() for name in CLIENT_FILES}
    # Keep the established hosted file contract: deployed PHP relays may only
    # allow these six filenames. New helpers travel inside mobile.js.
    files['mobile.js'] = (HERE / 'operation-id.js').read_text() + '\n' + (HERE / 'journey.js').read_text() + '\n' + (HERE / 'joint-rig.js').read_text() + '\n' + (HERE / 'turret-overlay.js').read_text() + '\n' + (HERE / 'physical-arm.js').read_text() + '\n' + files['mobile.js']
    files['mobile.js'] = (HERE / 'connection-log.js').read_text() + '\n' + files['mobile.js']
    _client = {'build': uuid.uuid4().hex, 'files': files}


def hub_stop():
    global _client, _ctx
    _client = None
    _ctx = None


def client_contract():
    return {'contract': 'mobile.client', 'version': 1,
            'status': 'ready' if _client else 'unavailable',
            'build': _client['build'] if _client else None}


def client_response(filename, *, hosted=False):
    if filename not in CLIENT_FILES:
        abort(404)
    if not _client:
        abort(503)
    build = _client['build']
    content = _client['files'][filename]
    if filename == 'index.html':
        content = content.replace('mobile ltz · Green', 'mobile ltz · '+TEAM.title())
        content = content.replace('<html lang="en">', f'<html lang="en" data-mobile-build="{build}" data-mobile-team="{TEAM}">')
        for name in CLIENT_FILES[1:]:
            url = f'api.php?path=client/{build}/{name}' if hosted else f'{name}?v={build}'
            content = re.sub(r'(?<=")' + re.escape(name) + r'(?:\?[^"]*)?(?=")', url, content)
    mime = 'text/html' if filename.endswith('.html') else 'text/css' if filename.endswith('.css') else 'application/javascript'
    response = Response(content, content_type=mime + '; charset=utf-8')
    response.headers['Cache-Control'] = 'no-store, max-age=0'
    response.headers['X-Mobile-Build'] = build
    return response


@bp.route('/api/client/manifest')
def client_manifest():
    response = jsonify(client_contract())
    response.headers['Cache-Control'] = 'no-store'
    return response


@bp.route('/api/client/<build>/<filename>')
def published_client(build, filename):
    if not _client:
        abort(503)
    if build != _client['build'] and not (build == 'latest' and filename == 'index.html'):
        abort(409, 'Game server restarted. Refresh to load the current mobile page.')
    return client_response(filename, hosted=True)


@bp.route('/')
def index():
    return client_response('index.html')


@bp.route('/<filename>')
def static_file(filename):
    if filename == 'index.html':
        abort(404)
    if _client and request.args.get('v') and request.args['v'] != _client['build']:
        abort(409, 'Game server restarted. Refresh the mobile page.')
    return client_response(filename)


@bp.route('/api/physical-controller')
def physical_controller():
    try:
        if not _ctx or not _ctx.is_prototype_enabled('ltx'):
            raise ValueError(TEAM.title()+' LTX robot controller is disabled.')
        module = _ctx.get_prototype('ltx')
        value = module.controller_contract()
        if (value.get('contract') != TEAM+'.robot-controller' or type(value.get('version')) is not int
                or value['version'] != 1 or value.get('status') != 'ready'
                or value.get('path') != f'/s/{TEAM}/p/ltx/?ltz=1&mobile=1&bridge=1'):
            raise ValueError(value.get('error') or TEAM.title()+' robot controller contract unavailable.')
        return jsonify(value)
    except Exception as exc:
        return jsonify(status='unavailable', error=str(exc)), 503
