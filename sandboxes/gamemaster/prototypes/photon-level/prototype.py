"""Photon Level: owner of authored geometry, waves, and static artwork."""

from __future__ import annotations

import copy
import json
import math
import os
import threading
from pathlib import Path

from flask import Blueprint, jsonify, request, send_from_directory, url_for

import live
from level_contract import _tileset_catalog, parse_tiled_level, properties, simple_level
from level_layout import SocketLayoutError, update_socket_layout_file
from level_assets import asset_snapshot

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
        "routes, waves, static artwork, and a generic level projection."
    ),
    "group": "Photon Engine",
    "default_page": "",
    "pages": [{"path": "", "label": "Level"}, {"path": "art", "label": "Artwork"}],
}
bp = Blueprint("photon_level", __name__)
_lock = threading.RLock()
_live = live.LiveState()
_raw_map: dict = {}
_runtime: dict = {}
_waves: dict = {}
_map_asset_paths: dict = {}
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


def _scene_asset_paths(raw_map, runtime):
    """Resolve authored scene IDs once, inside their owning package."""
    _, catalog = _tileset_catalog(Path(MAP_PATH), raw_map)
    used = {
        item["asset_id"] for layer in runtime["visual_scene"]["layers"]
        for item in layer["items"] if item["kind"] == "sprite"
    }
    root = Path(ASSET_ROOT).resolve()
    assets = {}
    for item in catalog.values():
        if item["asset_id"] not in used:
            continue
        path = item["image_path"]
        if not path.is_relative_to(root):
            raise LevelError(f"preview asset unavailable (outside content package): {item['asset_id']}")
        relative = path.relative_to(root).as_posix()
        previous = assets.setdefault(item["asset_id"], relative)
        if previous != relative:
            raise LevelError(f"ambiguous preview asset: {item['asset_id']}")
    if used - assets.keys():
        raise LevelError("preview scene contains unresolved artwork")
    return assets


def _reload_source():
    global _raw_map, _runtime, _waves, _load_error, _map_asset_paths
    try:
        raw_map, runtime, waves = _load_source()
        map_assets = _scene_asset_paths(raw_map, runtime)
    except (OSError, json.JSONDecodeError, TypeError, KeyError, ValueError) as exc:
        _load_error = str(exc)
        return False
    _raw_map, _runtime, _waves = raw_map, runtime, waves
    _map_asset_paths = map_assets
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
            "presentation": presentation_assets(),
        }


def presentation_assets():
    """Static content descriptor embedded in the runtime bundle."""
    with _lock:
        output = asset_snapshot(ASSET_ROOT, _map_asset_paths)
        if _load_error:
            output.update(status="unavailable", error=_load_error)
        return output


def editor_snapshot():
    """One-revision authoring view using only this module's local assets."""
    with _lock:
        if _load_error is not None:
            raise LevelError(_load_error)
        level = simple_level(_runtime)
        asset_root = Path(ASSET_ROOT).resolve()
        assets = _scene_asset_paths(_raw_map, _runtime)
        for asset_id, relative in assets.items():
            if not (asset_root / relative).is_file():
                raise LevelError(f"preview asset unavailable: {asset_id}")

        # Publish an affine display transform, not a second copy of the rules.
        # Resizing changes only the marker's optical offset, not its footprint.
        sockets = {socket["socket_id"]: socket for socket in level["sockets"]}
        for layer in _raw_map["layers"]:
            for obj in layer.get("objects", []):
                props = properties(obj)
                socket = sockets.get(props.get("socket_id"))
                if socket is None:
                    continue
                slope = float(props["aruco_optical_center_v"]) - 0.5
                angle = math.radians(float(obj.get("rotation", 0)))
                socket["marker_resize_x"] = -slope * math.sin(angle)
                socket["marker_resize_y"] = slope * math.cos(angle)

        for marker_id in (38, *range(40, 56)):
            relative = f"aruco/{marker_id}.png"
            if not (asset_root / relative).is_file():
                raise LevelError(f"preview marker unavailable: {marker_id}")
            assets[f"marker/{marker_id}"] = relative
        return {
            "contract": "photon.level.editor", "version": 1,
            "status": "ready", "revision": _runtime["layout_revision"],
            "level": level, "assets": assets,
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


@bp.route("/level-editor.js")
def editor_script():
    return send_from_directory(HERE, "level-editor.js")


@bp.route("/api/editor")
def editor_api():
    try:
        output = editor_snapshot()
        output["assets"] = {
            key: url_for(".level_asset", filename=filename)
            for key, filename in output["assets"].items()
        }
        response = jsonify(output)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        response = jsonify({
            "contract": "photon.level.editor", "version": 1,
            "status": "unavailable", "error": str(exc),
        })
        response.status_code = 503
    response.headers["Cache-Control"] = "no-store"
    return response


@bp.route("/assets/<path:filename>")
def level_asset(filename):
    response = send_from_directory(ASSET_ROOT, filename)
    response.headers["Cache-Control"] = "no-cache"
    return response


@bp.route("/api/assets")
def assets_api():
    response = jsonify(presentation_assets())
    response.headers["Cache-Control"] = "no-store"
    return response


@bp.route("/art")
def art_page():
    return send_from_directory(HERE, "art.html")


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
