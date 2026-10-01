"""LTX player tab: an isolated route using the shared Auto PP X controller."""

import os

from flask import Blueprint, send_from_directory

SHARED_PLAYER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'shared', 'robot_controls'))
CAL2_DIR = SHARED_PLAYER_DIR
CRANE_CONTROLS_DIR = os.path.join(SHARED_PLAYER_DIR,'assets','crane-controls')

MANIFEST = {
    "name": "LTX",
    "description": "Laser Tag X player cue builder and Cartesian arm controller.",
    "default_page": "?ltz=1",
    "pages": [{"path": "", "label": "Laser Tag X controls"},
              {"path": "?ltz=1", "label": "LTZ player controls"}],
}
bp = Blueprint("purple_player_ltx", __name__)


@bp.route("/")
def index():
    response = send_from_directory(SHARED_PLAYER_DIR, "controller.html")
    response.headers["Cache-Control"] = "no-store, max-age=0"
    return response


@bp.route("/assets/crane-controls/<path:filename>")
def crane_control_asset(filename):
    response = send_from_directory(CRANE_CONTROLS_DIR, filename)
    response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return response


@bp.route("/calibrate")
def calibrate():
    response = send_from_directory(CAL2_DIR, "calibrate2.html")
    response.headers["Cache-Control"] = "no-store, max-age=0"
    return response

_ctx = None


def hub_init(ctx):
    global _ctx
    _ctx = ctx


def hub_stop():
    global _ctx
    _ctx = None


def controller_contract():
    """Public presentation entry point; commands stay with the existing controller."""
    ready = bool(_ctx and all(_ctx.is_prototype_enabled(slug) for slug in
                             ('cartesian-xyz-test', 'auto-pickup-game', 'auto-pp-cal-2')))
    return {'contract': 'purple.robot-controller', 'version': 1,
            'status': 'ready' if ready else 'unavailable',
            'path': '/s/purple/p/ltx/?ltz=1&mobile=1&bridge=1',
            'error': None if ready else 'Enable Purple LTX, Cartesian XYZ Test, Auto Pick and Place, and Auto PP Cal 2.'}


@bp.route('/mobile-bridge.js')
def mobile_bridge():
    response = send_from_directory(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'shared', 'mobile_ltz')), 'arm-bridge.js')
    response.headers['Cache-Control'] = 'no-store'
    return response


@bp.route('/joint-rig.js')
@bp.route('/live-game.js')
def shared_control_library():
    from flask import request
    directory = os.path.abspath(os.path.join(SHARED_PLAYER_DIR, '..', 'mobile_ltz'))
    response = send_from_directory(directory, request.path.rsplit('/', 1)[-1])
    response.headers['Cache-Control'] = 'no-store'
    return response
