"""Photon Board: corrected physical observations, with an explicit simulator."""

import json
import math
import os
import threading
import time

from flask import Blueprint, jsonify, request, send_from_directory

import live

HERE = os.path.dirname(os.path.abspath(__file__))
CONTRACT = "photon.board"
VERSION = 1

MANIFEST = {
    "name": "Photon Board",
    "description": "Input: camera/calibration evidence or simulated tags. Output: one normalized board observation.",
    "group": "Photon Engine",
    "default_page": "",
    "pages": [{"path": "", "label": "Board"}],
}
bp = Blueprint("photon_board", __name__)
_hub_ctx = None
_lock = threading.RLock()
_simulation = {"enabled": False, "revision": 1, "tags": []}
_live = live.LiveState()


class BoardError(ValueError):
    pass


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


def _clean_tags(value):
    if not isinstance(value, list) or len(value) > 128:
        raise BoardError("tags must be an array of at most 128 observations")
    clean, seen = [], set()
    for index, tag in enumerate(value):
        if not isinstance(tag, dict):
            raise BoardError(f"tags[{index}] must be an object")
        try:
            tag_id = int(tag.get("id"))
            nx, ny = float(tag.get("nx")), float(tag.get("ny"))
            rotation = float(tag.get("rotation", 0))
        except (TypeError, ValueError, OverflowError) as exc:
            raise BoardError(f"tags[{index}] has invalid numbers") from exc
        if tag_id < 0 or tag_id > 999 or tag_id in seen:
            raise BoardError(f"tags[{index}].id must be unique and between 0 and 999")
        if not all(math.isfinite(v) for v in (nx, ny, rotation)) or not 0 <= nx <= 1 or not 0 <= ny <= 1:
            raise BoardError(f"tags[{index}] must use finite normalized coordinates")
        seen.add(tag_id)
        clean.append({
            "id": tag_id, "nx": round(nx, 5), "ny": round(ny, 5),
            "rotation": round(rotation, 2), "tracked": True,
        })
    return sorted(clean, key=lambda item: item["id"])


def set_simulation(enabled, tags):
    with _lock:
        _simulation["enabled"] = bool(enabled)
        _simulation["tags"] = _clean_tags(tags) if enabled else []
        _simulation["revision"] += 1
    _live.bump()
    return board_snapshot()


def _arm_snapshot(relay):
    arms = {}
    if relay is None or not callable(getattr(relay, "arm_state", None)):
        return arms
    for side in ("green", "purple"):
        try:
            raw = relay.arm_state(side) or {}
            arms[side] = {
                "connected": bool(raw.get("connected")),
                "enabled": bool(raw.get("enabled")),
                "pump_mode": str(raw.get("pump_mode") or "off"),
                "updated_at": raw.get("updated_at"),
            }
        except (TypeError, ValueError, RuntimeError) as exc:
            arms[side] = {"connected": False, "error": str(exc)}
    return arms


def board_snapshot():
    """Public read-only contract. Bad hardware evidence always yields no tags."""
    with _lock:
        simulated = json.loads(json.dumps(_simulation))
    now = time.time()
    if simulated["enabled"]:
        return {
            "contract": CONTRACT, "version": VERSION,
            "revision": simulated["revision"], "status": "ready",
            "source": "simulation", "corrected": True,
            "observed_at": now, "tags": simulated["tags"], "arms": {}, "errors": [],
        }

    errors = []
    webcam = _module("webcam")
    calibration = _module("camera-calibration")
    relay = _module("dobot-mg400-relay")
    if webcam is None or not callable(getattr(webcam, "get_tags", None)):
        errors.append("webcam unavailable")
    if calibration is None or not callable(getattr(calibration, "correct_tag_sets", None)):
        errors.append("camera calibration unavailable")
    tags, corrected = [], False
    if not errors:
        try:
            raw = webcam.get_tags()
            raw, _, corrected = calibration.correct_tag_sets(raw, [])
            if corrected:
                tags = _clean_tags([
                    tag for tag in raw
                    if bool(tag.get("tracked", True)) and float(tag.get("missing", 0)) <= 0.5
                ])
            else:
                errors.append("camera correction is not valid")
        except (AttributeError, KeyError, TypeError, ValueError, RuntimeError) as exc:
            errors.append(f"camera read failed: {exc}")
            tags = []
    return {
        "contract": CONTRACT, "version": VERSION, "revision": 0,
        "status": "ready" if corrected else "unavailable",
        "source": "camera", "corrected": bool(corrected),
        "observed_at": now, "tags": tags if corrected else [],
        "arms": _arm_snapshot(relay), "errors": errors,
    }


def _operator_only():
    if "gamemaster" not in (request.environ.get("hhh.roles") or set()):
        return jsonify({"ok": False, "error": "gamemaster required"}), 403
    return None


@bp.route("/")
def index():
    return send_from_directory(HERE, "index.html")


@bp.route("/api/board")
def board_api():
    snapshot = board_snapshot()
    return jsonify(snapshot), 200 if snapshot["status"] == "ready" else 503


@bp.route("/api/events")
def events_api():
    return _live.stream(board_snapshot, interval=0.2)


@bp.route("/api/simulation", methods=["POST"])
def simulation_api():
    denied = _operator_only()
    if denied:
        return denied
    data = request.get_json(silent=True) or {}
    try:
        return jsonify({
            "ok": True,
            "output": set_simulation(bool(data.get("enabled")), data.get("tags") or []),
        })
    except BoardError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
