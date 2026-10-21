"""Laser Tag Y: a thin gamemaster presentation over Photon Game output."""

import base64
from shared.fixed_board import cue_layout
import json
import math
from shared.ltz_ui import ROOT as SCORE_UI_ROOT
import os
import time

from flask import Blueprint, Response, current_app, jsonify, redirect, request, send_from_directory

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
        markers = board.camera_markers_snapshot()
        if (not isinstance(markers, dict) or markers.get("contract") != "photon.board.camera-markers"
                or type(markers.get("version")) is not int or markers["version"] != 1):
            raise ValueError("Incompatible Photon Board camera markers")
        value["camera_markers"] = markers
        game = _module('photon-game')
        if game and callable(getattr(board, 'cue_targets_snapshot', None)):
            snapshot = game.game_snapshot()
            if (snapshot.get('contract') != GAME_CONTRACT or type(snapshot.get('version')) is not int
                    or snapshot['version'] != GAME_VERSION):
                raise ValueError('Photon Game contract mismatch')
            if snapshot.get('journey', {}).get('phase') != 'calibration' and not snapshot.get('virtual_play'):
                scope, ids = cue_layout(snapshot)
                fixed = board.cue_targets_snapshot(scope=scope, fixed_ids=ids)
                if (fixed.get('contract') != 'photon.board.cue-targets' or type(fixed.get('version')) is not int
                        or fixed['version'] != 2 or fixed.get('layout_scope') != scope
                        or fixed.get('fixed_ids') != sorted(ids)):
                    raise ValueError('Fixed board display contract mismatch')
                value['fixed_board'] = dict(fixed, scope=scope, server_time=time.time())
        json.dumps(value, allow_nan=False)
        return value
    except Exception as exc:
        return {"contract": "photon.board.tracking", "version": 1,
                "status": "unavailable", "source": "unknown", "tags": [],
                "errors": [str(exc)]}


def _camera_preview():
    """Read display pixels only through Board's public preview contract."""
    result = {"contract": "laser-tag-y.camera", "version": 1, "status": "unavailable"}
    try:
        board = _module("photon-board")
        if board is None or not callable(getattr(board, "preview_frame", None)):
            raise ValueError("Photon Board camera unavailable")
        value = board.preview_frame()
        if (not isinstance(value, dict) or value.get("contract") != "photon.board.preview"
                or type(value.get("version")) is not int or value["version"] != 1):
            raise ValueError("Incompatible Photon Board camera preview")
        if value.get("status") != "ready":
            raise ValueError(value.get("error") or "Waiting for a fresh corrected camera frame")
        stamp = value.get("frame_at")
        if (value.get("coordinate_space") != "corrected-camera-normalized"
                or type(stamp) not in (int, float) or not math.isfinite(stamp)
                or not -0.25 <= time.time() - stamp <= 2
                or any(type(value.get(k)) is not int or value[k] <= 0 for k in ("width", "height"))
                or not isinstance(value.get("jpeg"), bytes) or not value["jpeg"]):
            raise ValueError("Fresh corrected camera frame unavailable")
        return dict(result, status="ready", frame_at=stamp, width=value["width"], height=value["height"],
                    image="data:image/jpeg;base64," + base64.b64encode(value["jpeg"]).decode("ascii"))
    except Exception as exc:
        return dict(result, error=str(exc))


def _scoreboard_link():
    """Read only the Progress owner's public, credential-free link contract."""
    unavailable = {'contract': 'photon.scoreboard-link', 'version': 1, 'status': 'unavailable'}
    try:
        owner = _module('photon-progress')
        if owner is None or not callable(getattr(owner, 'scoreboard_link_snapshot', None)):
            return unavailable
        value = owner.scoreboard_link_snapshot()
        if (not isinstance(value, dict) or value.get('contract') != 'photon.scoreboard-link'
                or type(value.get('version')) is not int or value['version'] != 1
                or value.get('status') != 'ready'
                or value.get('state') not in ('linked', 'unlinked', 'submitting', 'pending',
                    'cancelling', 'cancelled', 'rejected', 'expired', 'revoked')
                or type(value.get('upload_delayed')) is not bool):
            return unavailable
        return {key: value[key] for key in ('contract', 'version', 'status', 'state', 'upload_delayed')}
    except Exception:
        return unavailable


def _with_markers(response, *, preview=False, scoreboard=False):
    """Multiplex display diagnostics/pixels onto the existing Game SSE connection."""
    def stream():
        next_sample, previous = 0, None
        next_score, previous_score, score_sent = 0, None, 0
        try:
            for chunk in response.iter_encoded():
                yield chunk
                now = time.monotonic()
                if scoreboard and now >= next_score:
                    next_score = now + 2
                    payload = json.dumps(_scoreboard_link(), allow_nan=False, separators=(",", ":"))
                    if payload != previous_score or now - score_sent >= 10:
                        previous_score, score_sent = payload, now
                        yield ("event: scoreboard\ndata: " + payload + "\n\n").encode()
                if now < next_sample:
                    continue
                next_sample = now + 0.2
                payload = json.dumps(_marker_diagnostics(), allow_nan=False,
                                     separators=(",", ":"))
                if payload != previous:
                    previous = payload
                    yield ("event: markers\ndata: " + payload + "\n\n").encode()
                if preview:
                    yield ("event: camera\ndata: " + json.dumps(_camera_preview(),
                           allow_nan=False, separators=(",", ":")) + "\n\n").encode()
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
    return _renderer_bundle()


def _renderer_bundle():
    # Same owner supplies one bundle to Y, authenticated Mobile and the exporter.
    with open(os.path.join(HERE, "breaker-renderer.js"), encoding="utf-8") as helper:
        prefix = helper.read()
    with open(os.path.join(HERE, "tower-defence-view.js"), encoding="utf-8") as renderer:
        return Response(prefix + "\n" + renderer.read(), mimetype="application/javascript",
                        headers={"Cache-Control": "no-cache"})


def renderer_contract():
    return {"contract": "photon.renderer", "version": 1, "enemy_combat_version": 1}


def renderer_response():
    """Owned renderer shared with authenticated player presentations."""
    return _renderer_bundle()


@bp.route("/scoreboard-notice.js")
@bp.route("/player-join.js")
@bp.route("/player-join.css")
@bp.route("/calibration-display.js")
@bp.route("/calibration-display.css")
@bp.route("/calibration-history.js")
@bp.route("/player-admin.js")
@bp.route("/turret-controls.js")
@bp.route("/turret-controls.css")
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
    scoreboard = request.args.get('scoreboard') == '1'
    if scoreboard:
        denied = _operator_only()
        if denied:
            return denied
    game, error = _game()
    if game is None or not callable(getattr(game, "game_events", None)):
        return Response(
            "data: " + json.dumps(_unavailable(error or "Photon Game SSE unavailable")) + "\n\n",
            status=503, mimetype="text/event-stream",
        )
    response = game.game_events(incremental=True)
    return _with_markers(response, preview=request.args.get("preview") == "1", scoreboard=scoreboard) if request.args.get("markers") == "1" or scoreboard else response


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
    except Exception:
        current_app.logger.exception('Unexpected Photon Game command failure')
        return jsonify(ok=False, error='Server error while processing the command. Check the live game status and server log before retrying.'), 500

@bp.route('/score-feedback.js')
@bp.route('/shop.css')
@bp.route('/shop.js')
@bp.route('/marker-presence.js')
@bp.route('/wave-timeline.js')
@bp.route('/wave-timeline.css')
def score_ui():
    return send_from_directory(SCORE_UI_ROOT,request.path.rsplit('/',1)[-1],max_age=0)


@bp.route('/operation-id.js')
def operation_id_asset():
    return send_from_directory(os.path.join(HERE,'../../../../shared/mobile_ltz'),'operation-id.js',max_age=0)
