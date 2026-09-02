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
RUNTIME_CONTRACT = "photon.board.runtime"
RUNTIME_VERSION = 1

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


def _clean_points(value, field, index):
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > 16:
        raise BoardError(f"tags[{index}].{field} must be a short point array")
    points = []
    for point in value:
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            raise BoardError(f"tags[{index}].{field} contains an invalid point")
        try:
            x, y = float(point[0]), float(point[1])
        except (TypeError, ValueError, OverflowError) as exc:
            raise BoardError(f"tags[{index}].{field} contains invalid numbers") from exc
        if not math.isfinite(x) or not math.isfinite(y):
            raise BoardError(f"tags[{index}].{field} must contain finite numbers")
        points.append([round(x, 6), round(y, 6)])
    return points


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
            missing = float(tag.get("missing", 0))
        except (TypeError, ValueError, OverflowError) as exc:
            raise BoardError(f"tags[{index}] has invalid numbers") from exc
        if tag_id < 0 or tag_id > 999 or tag_id in seen:
            raise BoardError(f"tags[{index}].id must be unique and between 0 and 999")
        if (
            not all(math.isfinite(v) for v in (nx, ny, rotation, missing))
            or not 0 <= nx <= 1 or not 0 <= ny <= 1 or missing < 0
        ):
            raise BoardError(f"tags[{index}] must use finite normalized coordinates")
        seen.add(tag_id)
        item = {
            "id": tag_id, "nx": round(nx, 5), "ny": round(ny, 5),
            "rotation": round(rotation, 2), "missing": round(missing, 3),
            "tracked": bool(tag.get("tracked", True)),
        }
        if tag.get("x") is not None or tag.get("y") is not None:
            try:
                x, y = float(tag.get("x")), float(tag.get("y"))
            except (TypeError, ValueError, OverflowError) as exc:
                raise BoardError(f"tags[{index}] has invalid pixel coordinates") from exc
            if not math.isfinite(x) or not math.isfinite(y):
                raise BoardError(f"tags[{index}] has non-finite pixel coordinates")
            item.update({"x": round(x, 3), "y": round(y, 3)})
        for field in ("corners", "ncorners"):
            if field in tag:
                item[field] = _clean_points(tag.get(field), field, index)
        clean.append(item)
    return sorted(clean, key=lambda item: item["id"])


def set_simulation(enabled, tags):
    with _lock:
        _simulation["enabled"] = bool(enabled)
        _simulation["tags"] = _clean_tags(tags) if enabled else []
        _simulation["revision"] += 1
    _live.bump()
    return board_snapshot()


def _clean_pose(value):
    if not isinstance(value, (list, tuple)) or len(value) < 3:
        return None
    try:
        pose = [float(item) for item in value[:4]]
    except (TypeError, ValueError, OverflowError):
        return None
    return [round(item, 4) for item in pose] if all(map(math.isfinite, pose)) else None


def _clean_arms(value):
    if not isinstance(value, dict):
        raise BoardError("relay arms must be an object")
    arms = {}
    for side in ("green", "purple"):
        raw = value.get(side) or {}
        if not isinstance(raw, dict):
            raise BoardError(f"relay arm {side} must be an object")
        pump_mode = str(raw.get("pump_mode") or "off")
        arms[side] = {
            "connected": bool(raw.get("connected")),
            "enabled": bool(raw.get("enabled")),
            "mode_name": str(raw.get("mode_name") or "")[:80],
            "pose": _clean_pose(raw.get("pose")),
            "target": _clean_pose(raw.get("target")),
            "pump_mode": pump_mode
            if pump_mode in {"suck", "blow", "off", "conflict"} else "off",
        }
    return arms


def _read_input(slug, function_name, contract, version, *args):
    module = _module(slug)
    if module is None:
        return None, f"{slug} unavailable or disabled"
    function = getattr(module, function_name, None)
    if not callable(function):
        return None, f"{slug} does not publish {function_name}()"
    try:
        value = function(*args)
    except Exception as exc:
        return None, f"{slug} failed: {exc}"
    if (
        not isinstance(value, dict)
        or value.get("contract") != contract
        or value.get("version") != version
    ):
        return None, f"{slug} contract mismatch (expected {contract} v{version})"
    if value.get("status") != "ready":
        return None, str(value.get("error") or f"{slug} is not ready")
    return value, None


def _input_state(value, error):
    return {
        "status": "ready" if value is not None else "unavailable",
        "error": error,
        "contract": value.get("contract") if value else None,
        "version": value.get("version") if value else None,
    }


def runtime_observation():
    """Complete validated observation for production game adapters."""
    with _lock:
        simulated = json.loads(json.dumps(_simulation))
    now = time.time()
    if simulated["enabled"]:
        return {
            "contract": RUNTIME_CONTRACT, "version": RUNTIME_VERSION,
            "revision": simulated["revision"], "status": "ready",
            "source": "simulation", "corrected": True,
            "observed_at": now, "tags": simulated["tags"],
            "detections": simulated["tags"],
            "visible_ids": [tag["id"] for tag in simulated["tags"]],
            "width": 0, "height": 0, "arms": {}, "errors": [],
            "inputs": {
                name: {"status": "simulated", "error": None}
                for name in ("webcam", "camera_calibration", "relay")
            },
        }

    webcam, webcam_error = _read_input(
        "webcam", "tag_snapshot", "hhh.webcam.tags", 1
    )
    correction, correction_error = (None, "not read")
    if webcam is not None:
        correction, correction_error = _read_input(
            "camera-calibration", "corrected_tag_snapshot",
            "hhh.camera-correction", 1,
            webcam.get("tags") or [], webcam.get("detections") or [],
        )
    relay, relay_error = _read_input(
        "dobot-mg400-relay", "arms_snapshot", "hhh.relay.arms", 1
    )

    inputs = {
        "webcam": _input_state(webcam, webcam_error),
        "camera_calibration": _input_state(correction, correction_error),
        "relay": _input_state(relay, relay_error),
    }
    errors = [error for error in (webcam_error, correction_error, relay_error) if error]
    corrected = correction is not None and bool(correction.get("corrected"))
    tags, detections, arms = [], [], {}
    if corrected:
        try:
            tags = _clean_tags(correction.get("tags") or [])
            detections = _clean_tags(correction.get("detections") or [])
        except BoardError as exc:
            errors.append(f"corrected tag output rejected: {exc}")
            corrected = False
    if relay is not None:
        try:
            arms = _clean_arms(relay.get("arms"))
        except BoardError as exc:
            errors.append(f"relay output rejected: {exc}")
            inputs["relay"] = _input_state(None, str(exc))
            arms = {}
    ready = corrected and inputs["relay"]["status"] == "ready"
    if not ready:
        tags, detections = [], []
    metadata = correction or webcam or {}
    try:
        width = int(metadata.get("width") or 0)
        height = int(metadata.get("height") or 0)
        revision = int((webcam or {}).get("revision") or 0)
        observed_at = float(metadata.get("observed_at") or now)
        visible_ids = sorted({
            int(tag_id) for tag_id in (webcam or {}).get("visible_ids", [])
            if isinstance(tag_id, (int, float))
            and math.isfinite(float(tag_id))
            and 0 <= int(tag_id) <= 999
        })
        if width < 0 or height < 0 or revision < 0 or not math.isfinite(observed_at):
            raise ValueError("metadata values are out of range")
    except (TypeError, ValueError, OverflowError) as exc:
        errors.append(f"camera metadata rejected: {exc}")
        corrected, ready, tags, detections = False, False, [], []
        width = height = revision = 0
        observed_at, visible_ids = now, []
    return {
        "contract": RUNTIME_CONTRACT, "version": RUNTIME_VERSION,
        "revision": revision,
        "status": "ready" if ready else "unavailable",
        "source": "camera", "corrected": bool(corrected),
        "observed_at": observed_at,
        "tags": tags, "detections": detections,
        "visible_ids": visible_ids,
        "width": width, "height": height, "arms": arms,
        "errors": errors, "inputs": inputs,
    }


def board_snapshot():
    """Small public projection. Bad camera evidence always yields no tags."""
    runtime = runtime_observation()
    tags = [
        {
            key: tag[key]
            for key in ("id", "nx", "ny", "rotation", "missing", "tracked")
        }
        for tag in runtime["tags"]
        if tag.get("tracked", True) and float(tag.get("missing", 0)) <= 0.5
    ]
    return {
        "contract": CONTRACT, "version": VERSION,
        "revision": runtime["revision"], "status": runtime["status"],
        "source": runtime["source"], "corrected": runtime["corrected"],
        "observed_at": runtime["observed_at"], "tags": tags,
        "arms": runtime["arms"], "errors": runtime["errors"],
        "inputs": runtime["inputs"],
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


@bp.route("/api/runtime")
def runtime_api():
    snapshot = runtime_observation()
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
