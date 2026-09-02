"""Laser Tag Y: a thin gamemaster presentation over Photon Game output."""

import json
import os

from flask import Blueprint, Response, jsonify, request, send_from_directory

HERE = os.path.dirname(os.path.abspath(__file__))

MANIFEST = {
    "name": "Laser Tag Y",
    "description": "Presentation only: draws Photon Game output and forwards validated gamemaster commands.",
    "group": "Games",
    "default_page": "game",
    "pages": [
        {"path": "game", "label": "Game master"},
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
    if not isinstance(snapshot, dict) or snapshot.get("contract") != "photon.game" or snapshot.get("version") != 1:
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
@bp.route("/screen")
def page():
    return send_from_directory(HERE, "index.html")


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
    return game.game_events()


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
        return jsonify({"ok": False, "error": str(exc)}), 400


@bp.route("/api/art")
def art_api():
    art = _module("photon-art")
    if art is None or not callable(getattr(art, "art_snapshot", None)):
        return jsonify({"status": "unavailable", "error": "Photon Art unavailable"}), 503
    try:
        output = art.art_snapshot()
    except Exception as exc:
        return jsonify({"status": "unavailable", "error": f"Photon Art failed: {exc}"}), 503
    if not isinstance(output, dict) or output.get("contract") != "photon.art" or output.get("version") != 1:
        return jsonify({"status": "unavailable", "error": "Photon Art contract mismatch"}), 503
    output = dict(output)
    output["base"] = request.script_root + "/p/photon-art/"
    return jsonify(output)
