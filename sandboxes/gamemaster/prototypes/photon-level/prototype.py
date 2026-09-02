"""Photon Level: owner of authored playfield geometry and wave definitions."""

from __future__ import annotations

import copy
import json
import math
import os
import threading

from flask import Blueprint, jsonify, request, send_from_directory, url_for

import live
from level_contract import parse_tiled_level, simple_level
from level_layout import SocketLayoutError, update_socket_layout_file

HERE = os.path.dirname(os.path.abspath(__file__))
ASSET_ROOT = os.path.join(HERE, "assets")
MAP_PATH = os.path.join(ASSET_ROOT, "tiled", "levels", "z-pixel-first-map.tmj")
WAVE_PATH = os.path.join(
    ASSET_ROOT, "tiled", "levels", "z-pixel-first-map.waves.json"
)
CONTRACT = "photon.level"
VERSION = 2
RUNTIME_CONTRACT = "photon.level.runtime"
RUNTIME_VERSION = 1

MANIFEST = {
    "name": "Photon Level",
    "description": (
        "Input: one validated socket layout. Output: versioned TMJ geometry, "
        "routes, waves, and a generic level projection."
    ),
    "group": "Photon Engine",
    "default_page": "",
    "pages": [{"path": "", "label": "Level"}],
}
bp = Blueprint("photon_level", __name__)
_lock = threading.RLock()
_live = live.LiveState()
_raw_map: dict = {}
_runtime: dict = {}
_waves: dict = {}
_load_error: str | None = None


class LevelError(ValueError):
    """A rejected authored-level input or invalid level source."""


def _validate_waves(value, lane_names):
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise LevelError("wave file must use schema_version 1")
    waves = value.get("waves")
    if not isinstance(waves, list) or not waves:
        raise LevelError("wave file must contain at least one wave")
    for expected, wave in enumerate(waves, 1):
        if not isinstance(wave, dict) or wave.get("wave") != expected:
            raise LevelError("waves must be numbered consecutively from 1")
        groups = wave.get("groups")
        if not isinstance(groups, list) or not groups:
            raise LevelError(f"wave {expected} must contain groups")
        for group in groups:
            if (
                not isinstance(group, dict)
                or not isinstance(group.get("enemy"), str)
                or isinstance(group.get("count"), bool)
                or not isinstance(group.get("count"), int)
                or group["count"] <= 0
                or isinstance(group.get("duration_s"), bool)
                or not isinstance(group.get("duration_s"), (int, float))
                or not math.isfinite(float(group["duration_s"]))
                or group["duration_s"] <= 0
                or not isinstance(group.get("lane_weights"), dict)
                or not group["lane_weights"]
            ):
                raise LevelError(f"wave {expected} contains an invalid group")
            lane_weights = group["lane_weights"]
            if set(lane_weights) - set(lane_names) or any(
                isinstance(weight, bool)
                or not isinstance(weight, (int, float))
                or not math.isfinite(float(weight))
                or weight < 0
                for weight in lane_weights.values()
            ) or not any(weight > 0 for weight in lane_weights.values()):
                raise LevelError(f"wave {expected} contains invalid lane weights")
    return value


def _load_source():
    with open(MAP_PATH, encoding="utf-8") as handle:
        raw_map = json.load(handle)
    runtime = parse_tiled_level(MAP_PATH)
    with open(WAVE_PATH, encoding="utf-8") as handle:
        waves = _validate_waves(json.load(handle), runtime["paths"])
    if waves.get("level_id") != runtime["map_properties"].get("level_id"):
        raise LevelError("map and wave level_id values do not match")
    return raw_map, runtime, waves


def _reload_source():
    global _raw_map, _runtime, _waves, _load_error
    try:
        raw_map, runtime, waves = _load_source()
    except (OSError, json.JSONDecodeError, TypeError, KeyError, ValueError) as exc:
        _load_error = str(exc)
        return False
    _raw_map, _runtime, _waves = raw_map, runtime, waves
    _load_error = None
    return True


with _lock:
    _reload_source()


def level_snapshot():
    """Public, JSON-serializable framework output for sibling modules."""
    with _lock:
        ready = _load_error is None
        return {
            "contract": CONTRACT,
            "version": VERSION,
            "revision": _runtime.get("layout_revision", 0),
            "status": "ready" if ready else "unavailable",
            "error": _load_error,
            "level": simple_level(_runtime) if ready else None,
            "map": {"format": "tmj", "endpoint": "api/tiled-map"},
            "waves": {
                "schema_version": _waves.get("schema_version"),
                "count": len(_waves.get("waves", [])),
                "endpoint": "api/waves",
            },
        }


def runtime_bundle():
    """Public rich output consumed by a game runtime, never a source-file path."""
    with _lock:
        ready = _load_error is None
        return {
            "contract": RUNTIME_CONTRACT,
            "version": RUNTIME_VERSION,
            "revision": _runtime.get("layout_revision", 0),
            "status": "ready" if ready else "unavailable",
            "error": _load_error,
            "runtime": copy.deepcopy(_runtime) if ready else None,
            "waves": copy.deepcopy(_waves.get("waves")) if ready else None,
        }


def tiled_map_snapshot(asset_base: str):
    """Return TMJ with its external tilesets rewritten to this module's assets."""
    if not isinstance(asset_base, str) or not asset_base.endswith("/"):
        raise LevelError("asset_base must be an absolute URL path ending in /")
    with _lock:
        if _load_error is not None:
            raise LevelError(_load_error)
        output = copy.deepcopy(_raw_map)
    for reference in output.get("tilesets", []):
        if reference.get("source"):
            reference["source"] = asset_base + "tiled/tilesets/" + os.path.basename(
                reference["source"]
            )
    return output


def waves_document():
    """Return the authored wave document for presenters and compatibility APIs."""
    with _lock:
        if _load_error is not None:
            raise LevelError(_load_error)
        return copy.deepcopy(_waves)


def update_layout(sockets, *, expected_revision=None):
    """Validate and atomically publish all sixteen authored socket positions."""
    with _lock:
        if _load_error is not None:
            raise LevelError(_load_error)
        current = int(_runtime["layout_revision"])
        if expected_revision is not None:
            try:
                expected_revision = int(expected_revision)
            except (TypeError, ValueError) as exc:
                raise LevelError("expected_revision must be an integer") from exc
            if expected_revision != current:
                raise LevelError(
                    f"level revision changed: expected {expected_revision}, found {current}"
                )
        update_socket_layout_file(
            MAP_PATH, sockets, validate_candidate=parse_tiled_level
        )
        if not _reload_source():
            raise LevelError(_load_error or "updated level could not be reloaded")
        output = level_snapshot()
    _live.bump()
    return output


def _operator_only():
    if "gamemaster" not in (request.environ.get("hhh.roles") or set()):
        return jsonify({"ok": False, "error": "gamemaster required"}), 403
    return None


@bp.route("/")
def index():
    return send_from_directory(HERE, "index.html")


@bp.route("/assets/<path:filename>")
def level_asset(filename):
    response = send_from_directory(ASSET_ROOT, filename)
    response.headers["Cache-Control"] = "no-cache"
    return response


@bp.route("/api/level")
def level_api():
    return jsonify(level_snapshot())


@bp.route("/api/runtime")
def runtime_api():
    return jsonify(runtime_bundle())


@bp.route("/api/tiled-map")
def tiled_map_api():
    try:
        base = url_for(".level_asset", filename="")
        response = jsonify(tiled_map_snapshot(base))
    except LevelError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 503
    response.headers["Cache-Control"] = "no-store, max-age=0"
    response.headers["X-Level-Revision"] = str(_runtime["layout_revision"])
    return response


@bp.route("/api/waves")
def waves_api():
    try:
        response = jsonify(waves_document())
    except LevelError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 503
    response.headers["Cache-Control"] = "no-store, max-age=0"
    return response


@bp.route("/api/layout", methods=["POST"])
def layout_api():
    denied = _operator_only()
    if denied:
        return denied
    value = request.get_json(silent=True) or {}
    try:
        output = update_layout(
            value.get("sockets"), expected_revision=value.get("expected_revision")
        )
    except (LevelError, SocketLayoutError, TypeError, ValueError) as exc:
        status = 409 if "revision changed" in str(exc) else 400
        return jsonify({"ok": False, "error": str(exc)}), status
    return jsonify({"ok": True, "output": output})


@bp.route("/api/events")
def events_api():
    return _live.stream(level_snapshot, interval=1.0)
