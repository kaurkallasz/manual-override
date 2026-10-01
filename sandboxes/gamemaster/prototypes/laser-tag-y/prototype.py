"""Laser Tag Y: a thin gamemaster presentation over Photon Game output."""

import json
import os
import time

from flask import Blueprint, Response, jsonify, redirect, request, send_from_directory

HERE = os.path.dirname(os.path.abspath(__file__))
GAME_CONTRACT = "photon.game"
GAME_VERSION = 2

MANIFEST = {
    "name": "Laser Tag Y",
    "description": "Presentation only: draws Photon Game output and forwards validated gamemaster commands.",
    "group": "Games",
    "default_page": "game",
    "pages": [
        {"path": "game", "label": "Game master"},
        {"path": "settings", "label": "Photon Game settings"},
        {"path": "screen", "label": "External screen", "newtab": True},
    ],
}
bp = Blueprint("laser_tag_y", __name__)
_hub_ctx = None


def hub_init(ctx):
    global _hub_ctx
    _hub_ctx = ctx


def hub_stop():
    global _hub_ctx
    _hub_ctx = None


def _module(slug):
    if _hub_ctx is None or not _hub_ctx.is_prototype_enabled(slug):
        return None
    return _hub_ctx.get_prototype(slug)


def _game():
    module = _module("photon-game")
    if module is None or not callable(getattr(module, "game_snapshot", None)):
        return None, "Photon Game unavailable"
    try:
        snapshot = module.game_snapshot()
    except Exception as exc:
        return None, f"Photon Game failed: {exc}"
    if (
        not isinstance(snapshot, dict)
        or snapshot.get("contract") != GAME_CONTRACT
        or type(snapshot.get("version")) is not int or snapshot["version"] != GAME_VERSION
    ):
        return None, "Photon Game contract mismatch"
    return module, None


def _unavailable(error):
    return {
        "contract": "laser-tag-y.presentation", "version": 1,
        "status": "unavailable", "error": error,
    }


def _marker_diagnostics():
    """Read Board's cached display projection; never sample or control hardware."""
    try:
        board = _module("photon-board")
        if board is None or not callable(getattr(board, "tracking_snapshot", None)):
            raise ValueError("Photon Board marker diagnostics unavailable")
        value = board.tracking_snapshot()
        if (not isinstance(value, dict) or value.get("contract") != "photon.board.tracking"
                or type(value.get("version")) is not int or value["version"] != 1):
            raise ValueError("Incompatible Photon Board marker diagnostics")
        value = {key: value[key] for key in (
            "contract", "version", "status", "source", "coordinate_space",
            "width", "height", "sampled_at", "frame_at", "limits", "tags", "errors",
        ) if key in value}
        json.dumps(value, allow_nan=False)
        return value
    except Exception as exc:
        return {"contract": "photon.board.tracking", "version": 1,
                "status": "unavailable", "source": "unknown", "tags": [],
                "errors": [str(exc)]}


def _with_markers(response):
    """Multiplex display diagnostics onto the existing Game SSE connection."""
    def stream():
        next_sample, previous = 0, None
        try:
            for chunk in response.iter_encoded():
                yield chunk
                now = time.monotonic()
                if now < next_sample:
                    continue
                next_sample = now + 0.2
                payload = json.dumps(_marker_diagnostics(), allow_nan=False,
                                     separators=(",", ":"))
                if payload != previous:
                    previous = payload
                    yield ("event: markers\ndata: " + payload + "\n\n").encode()
        finally:
            response.close()
    return Response(stream(), mimetype="text/event-stream", headers={
        "Cache-Control": "no-cache", "X-Accel-Buffering": "no",
    })


def _operator_only():
    if "gamemaster" not in (request.environ.get("hhh.roles") or set()):
        return jsonify({"ok": False, "error": "gamemaster required"}), 403
    return None


@bp.route("/")
@bp.route("/game")
def page():
    return send_from_directory(HERE, "index.html")


@bp.route("/screen")
def screen():
    return send_from_directory(HERE, "screen.html")


@bp.route("/settings")
def settings():
    # Compatibility shortcut only: Game owns the form as well as its settings.
    game, error = _game()
    if game is None:
        return jsonify(_unavailable(error)), 503
    return redirect(request.script_root + "/p/photon-game/settings")


@bp.route("/tower-defence-view.js")
def renderer():
    return send_from_directory(HERE, "tower-defence-view.js")


def renderer_contract():
    return {"contract": "photon.renderer", "version": 1}


def renderer_response():
    """Owned renderer shared with authenticated player presentations."""
    return send_from_directory(HERE, "tower-defence-view.js")


@bp.route("/calibration-display.js")
@bp.route("/calibration-display.css")
@bp.route("/calibration-history.js")
@bp.route("/calibration-history.css")
def calibration_display_asset():
    return send_from_directory(HERE, request.path.rsplit('/', 1)[-1])


@bp.route('/api/calibrations')
def saved_calibrations_api():
    denied=_operator_only()
    if denied:return denied
    owner=_module('auto-pickup-game')
    if not owner or not callable(getattr(owner,'calibration_history',None)):
        return jsonify(ok=False,error='Calibration history unavailable'),503
    try:
        value=owner.calibration_history(request.args.get('side','green'))
        if not isinstance(value,dict) or value.get('contract')!='hhh.cal2.history' or type(value.get('version')) is not int or value['version']!=1 or value.get('status')!='ready':
            raise ValueError('Calibration history v1 unavailable')
        return jsonify(value)
    except Exception as exc:
        return jsonify(ok=False,error=str(exc)),503


@bp.route("/data-flow.js")
def data_flow_script():
    return send_from_directory(HERE, "data-flow.js")


@bp.route("/data-flow.css")
def data_flow_style():
    return send_from_directory(HERE, "data-flow.css")


@bp.route("/api/state")
def state_api():
    game, error = _game()
    if game is None:
        return jsonify(_unavailable(error)), 503
    return jsonify(game.game_snapshot())


@bp.route("/api/events")
def events_api():
    game, error = _game()
    if game is None or not callable(getattr(game, "game_events", None)):
        return Response(
            "data: " + json.dumps(_unavailable(error or "Photon Game SSE unavailable")) + "\n\n",
            status=503, mimetype="text/event-stream",
        )
    response = game.game_events(incremental=True)
    return _with_markers(response) if request.args.get("markers") == "1" else response


@bp.route("/api/command", methods=["POST"])
def command_api():
    denied = _operator_only()
    if denied:
        return denied
    game, error = _game()
    if game is None or not callable(getattr(game, "apply_command", None)):
        return jsonify({"ok": False, "error": error or "Photon Game command input unavailable"}), 503
    try:
        return jsonify({"ok": True, "output": game.apply_command(request.get_json(silent=True))})
    except (TypeError, ValueError) as exc:
        return jsonify({
            "ok": False,
            "error": str(exc),
            "errors": getattr(exc, "fields", {}),
        }), 400
