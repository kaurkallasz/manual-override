"""Laser Tag Y: a thin gamemaster presentation over Photon Game output."""

import json
import os

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
        or snapshot.get("version") != GAME_VERSION
    ):
        return None, "Photon Game contract mismatch"
    return module, None


def _unavailable(error):
    return {
        "contract": "laser-tag-y.presentation", "version": 1,
        "status": "unavailable", "error": error,
    }


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
    return game.game_events(incremental=True)


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
