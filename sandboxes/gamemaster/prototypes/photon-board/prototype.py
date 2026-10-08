"""Photon Board: corrected physical observations, with an explicit simulator."""

import json
import math
import os
import tempfile
import threading
import time

from flask import Blueprint, jsonify, redirect, request, send_from_directory

import live
from cue_targets import CueTargets
from board_occupancy import OccupancyTracker
from marker_quality import marker_size as _marker_size, size_consistent_markers as _size_consistent_markers
from board_tracking import (
    BoardTracker, DEFAULT_SETTINGS, PhysicalPlacementTracker, SETTING_BOUNDS,
    STALE_S, fresh, validate_settings,
)

HERE = os.path.dirname(os.path.abspath(__file__))
SETTINGS_PATH = os.path.join(HERE, "data", "tracking-settings.json")
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
_simulation = {"enabled": False, "revision": 1, "tags": [], "arms": {}}
_live = live.LiveState()
_sample_lock = threading.RLock()
_tracker = BoardTracker()
_placement_tracker = PhysicalPlacementTracker()
_occupancy_tracker = OccupancyTracker()
_occupancy = {}
_cue_targets = CueTargets()
_cue_layouts = {}
_tracking = {}
_placement = {}
_runtime = {}
_thread = None
_stop = None
_settings = dict(DEFAULT_SETTINGS)
_settings_error = None


class BoardError(ValueError):
    pass


def settings_snapshot():
    with _lock:
        return {"contract": "photon.board.settings", "version": 1,
                "status": "unavailable" if _settings_error else "ready", "error": _settings_error,
                "settings": dict(_settings), "defaults": dict(DEFAULT_SETTINGS),
                "bounds": {key: {"min": bounds[0], "max": bounds[1]} for key, bounds in SETTING_BOUNDS.items()}}


def _load_settings():
    global _settings, _settings_error
    values, error = dict(DEFAULT_SETTINGS), None
    try:
        with open(SETTINGS_PATH, encoding="utf-8") as handle:
            document = json.load(handle)
        if not isinstance(document, dict) or type(document.get("version")) is not int or document["version"] != 1:
            raise ValueError("Expected tracking settings version 1")
        values = validate_settings(document.get("settings"))
    except FileNotFoundError:
        pass  # First use keeps the original defaults without writing a file.
    except (OSError, ValueError) as exc:
        error = f"Could not load tracking settings; using defaults: {exc}"
    with _lock:
        _settings, _settings_error = values, error


def update_settings(values):
    """Persist one validated replacement; never changes game or robot safety."""
    global _settings, _settings_error, _tracker
    clean = validate_settings(values)
    with _sample_lock:
        temporary = None
        try:
            folder = os.path.dirname(SETTINGS_PATH)
            os.makedirs(folder, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=folder, delete=False) as handle:
                temporary = handle.name
                json.dump({"version": 1, "settings": clean}, handle, indent=2, allow_nan=False)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, SETTINGS_PATH)
        except OSError as exc:
            with _lock:
                _settings_error = f"Could not save tracking settings; previous values remain active: {exc}"
            _live.bump()
            raise
        finally:
            if temporary is not None and os.path.exists(temporary):
                os.unlink(temporary)
        with _lock:
            _settings, _settings_error = clean, None
            _tracker = BoardTracker(clean)
            # Keep the raw observation cache, but never mix transport evidence
            # accumulated under different diagnostic thresholds.
            _tracking.update(status="unavailable", arms={}, tags=[], limits=dict(clean),
                             errors=["Settings applied; waiting for a fresh diagnostic sample"])
        _live.bump()
    return settings_snapshot()


def hub_init(ctx):
    global _hub_ctx, _thread, _stop, _tracker, _placement_tracker, _cue_targets, _cue_layouts, _occupancy_tracker
    hub_stop()
    _hub_ctx = ctx
    _load_settings()
    _tracker = BoardTracker(_settings)
    _placement_tracker = PhysicalPlacementTracker()
    _occupancy_tracker = OccupancyTracker()
    _cue_targets = CueTargets()
    _cue_layouts = {}
    _sample_tracking()
    _stop = threading.Event()
    _thread = threading.Thread(target=_tracking_loop, args=(_stop,), name="photon-board-tracking", daemon=True)
    _thread.start()


def hub_stop():
    global _hub_ctx, _thread, _stop, _tracking, _placement, _runtime, _occupancy
    if _stop is not None:
        _stop.set()
    if _thread is not None:
        _thread.join(timeout=2)
        if _thread.is_alive():
            raise RuntimeError("Previous Photon Board sampler has not stopped; refusing a second sampler")
    _hub_ctx = None
    _thread = _stop = None
    with _lock:
        _tracking = {}
        _placement = {}
        _runtime = {}
        _occupancy = {}


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


def set_simulation(enabled, tags, arms=None):
    clean_tags = _clean_tags(tags) if enabled else []
    clean_arms = _clean_arms(arms or {}) if enabled and arms else {}
    with _sample_lock:
        with _lock:
            _simulation.update(enabled=bool(enabled), tags=clean_tags, arms=clean_arms)
            _simulation["revision"] += 1
        _sample_tracking()
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
        pump_mode = str(raw.get("pump_mode") or "unknown")
        arms[side] = {
            "connected": bool(raw.get("connected")),
            "enabled": bool(raw.get("enabled")),
            "mode_name": str(raw.get("mode_name") or "")[:80],
            "pose": _clean_pose(raw.get("pose")),
            "target": _clean_pose(raw.get("target")),
            "control_mode": raw.get("control_mode") if raw.get("control_mode") in {"cartesian", "joint"} else None,
            "feedback_at": raw.get("feedback_at") if isinstance(raw.get("feedback_at"), (int, float)) and math.isfinite(raw["feedback_at"]) else None,
            "pump_mode": pump_mode
            if pump_mode in {"suck", "blow", "off", "conflict"} else "unknown",
        }
    return arms


def _read_input(slug, function_name, contract, version, *args):
    try:
        module = _module(slug)
    except Exception as exc:
        return None, f"{slug} discovery failed: {exc}"
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
        or type(value.get("version")) is not int or value.get("version") != version
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


def _validate_tracking_inputs(projection, intents):
    def vector(value, field, optional=False):
        if optional and value is None:
            return
        if not isinstance(value, (list, tuple)) or len(value) != 2 or any(
            type(v) not in (int, float) or not math.isfinite(v) for v in value
        ):
            raise BoardError(f"{field} must be a finite two-coordinate array")

    if projection is not None:
        if projection.get("coordinate_space") != "corrected-camera-normalized" or projection.get("units") != "mm":
            raise BoardError("Cal 2 projection coordinate space or units mismatch")
        if not isinstance(projection.get("arms"), dict):
            raise BoardError("Cal 2 projection arms must be an object")
        for side, arm in projection["arms"].items():
            if side not in {"green", "purple"} or not isinstance(arm, dict):
                raise BoardError("Invalid Cal 2 arm")
            if arm.get("status") != "ready":
                continue
            for field in ("base_camera", "tcp_camera", "target_camera"):
                vector(arm.get(field), field, optional=field != "base_camera")
            if not isinstance(arm.get("tags"), list) or len(arm["tags"]) > 1000:
                raise BoardError("Invalid Cal 2 tag array")
            seen = set()
            for tag in arm["tags"]:
                if not isinstance(tag, dict) or type(tag.get("id")) is not int or tag["id"] in seen:
                    raise BoardError("Cal 2 tag IDs must be unique integers")
                seen.add(tag["id"])
                if tag.get("status") != "ready":
                    continue
                vector(tag.get("robot_xy"), "robot_xy")
                vector(tag.get("ground_camera"), "ground_camera")
                for field in ("pickup_z", "drop_z"):
                    value = tag.get(field)
                    if value is not None and (type(value) not in (int, float) or not math.isfinite(value)):
                        raise BoardError(f"{field} must be finite or null")
    if intents is not None:
        if not isinstance(intents.get("arms"), dict):
            raise BoardError("Controller intent arms must be an object")
        for side, report in intents["arms"].items():
            if side not in {"green", "purple"} or not isinstance(report, dict) or not isinstance(report.get("stage"), str):
                raise BoardError("Invalid controller stage report")
        json.dumps(intents, allow_nan=False)


def _runtime_input():
    """Complete validated observation for production game adapters."""
    with _lock:
        simulated = json.loads(json.dumps(_simulation))
    now = time.time()
    if simulated["enabled"]:
        for arm in simulated["arms"].values():
            arm["feedback_at"] = now
        return {
            "contract": RUNTIME_CONTRACT, "version": RUNTIME_VERSION,
            "revision": simulated["revision"], "status": "ready",
            "source": "simulation", "corrected": True,
            "observed_at": now, "frame_at": now, "tags": simulated["tags"],
            "detections": simulated["tags"],
            "visible_ids": [tag["id"] for tag in simulated["tags"] if tag.get("missing", 0) == 0],
            "width": 0, "height": 0, "arms": simulated["arms"], "errors": [],
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
    frame_at = (webcam or {}).get("frame_at")
    camera_tags, camera_detections = tags, detections
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
    result = {
        "contract": RUNTIME_CONTRACT, "version": RUNTIME_VERSION,
        "revision": revision,
        "status": "ready" if ready else "unavailable",
        "source": "camera", "corrected": bool(corrected),
        "camera_identity": (webcam or {}).get("camera_identity"),
        "camera_revision": (correction or {}).get("calibration_revision"),
        "observed_at": observed_at,
        "frame_at": frame_at,
        "tags": tags, "detections": detections,
        "visible_ids": visible_ids,
        "width": width, "height": height, "arms": arms,
        "errors": errors, "inputs": inputs,
        "_source_stamps": {name: value.get("observed_at") for name, value in (("webcam", webcam), ("relay", relay)) if value is not None},
        "_has_frame_time": webcam is not None and "frame_at" in webcam,
    }
    # An independent camera projection for occupancy; legacy placement/raw
    # observations continue to require the relay. Never expose this private input.
    result['_occupancy_camera'] = {
        **{key: result[key] for key in ('source', 'corrected', 'camera_identity',
           'camera_revision', 'width', 'height', 'frame_at', 'visible_ids')},
        'status': 'ready' if corrected and fresh((webcam or {}).get('observed_at'), now) else 'unavailable',
        'tags': camera_tags, 'detections': camera_detections,
    }
    return result


def _fresh_runtime(raw, now, stale_s):
    """Two projections of one read: configurable diagnostics, fixed game gate."""
    output = json.loads(json.dumps(raw))
    output.pop('_occupancy_camera', None)
    stamps = output.pop("_source_stamps", {})
    has_frame_time = output.pop("_has_frame_time", False)
    for name, stamp in stamps.items():
        if not fresh(stamp, now, stale_s):
            error = f"{name} snapshot stale or missing timestamp"
            output["errors"].append(error)
            output["inputs"][name] = _input_state(None, error)
            output["status"] = "unavailable"
            if name == "relay":
                output["arms"] = {}
    if has_frame_time and not fresh(output.get("frame_at"), now, stale_s):
        output["errors"].append("camera processed frame stale")
        output["inputs"]["webcam"] = _input_state(None, "camera processed frame stale")
        output.update(status="unavailable", frame_at=None)
    if output["status"] != "ready":
        output.update(tags=[], detections=[], visible_ids=[])
    return output


def _sample_tracking():
    global _tracking, _placement, _runtime, _occupancy
    with _sample_lock:
        now = time.time()
        raw = _runtime_input()
        try:
            occupancy = _occupancy_tracker.update(raw.get('_occupancy_camera', raw), now)
            json.dumps(occupancy, allow_nan=False)
        except (ValueError, TypeError, KeyError, IndexError, AttributeError, OverflowError) as exc:
            occupancy = _occupancy_tracker.unavailable(f'Occupancy input rejected: {exc}', now)
        base_runtime = _fresh_runtime(raw, now, STALE_S)
        _cue_targets.update(base_runtime, now)
        for targets in _cue_layouts.values():
            targets.update(base_runtime, now)
        try:
            placement = _placement_tracker.update(base_runtime, now)
            json.dumps(placement, allow_nan=False)
        except (ValueError, TypeError, KeyError, IndexError, AttributeError, OverflowError) as exc:
            _placement_tracker.reset_evidence()
            placement = _placement_tracker.unavailable(
                f"Physical placement input rejected: {exc}",
                revision=_placement_tracker.revision,
                source=str(base_runtime.get("source") or "unknown"),
                source_epoch=_placement_tracker.source_epoch,
                sampled_at=now,
            )
        runtime = _fresh_runtime(raw, now, _tracker.settings["stale_s"])
        remembered = {tag_id: rec["tag"] for tag_id, rec in _tracker.records.items()
                      if now - rec["last_seen"] <= 15}
        remembered.update({tag["id"]: tag for tag in runtime["detections"]})
        projection, projection_error = _read_input(
            "auto-pickup-game", "tracking_projection", "hhh.cal2.projection", 1,
            list(remembered.values()), runtime["arms"])
        intents, intent_error = (None, "Simulation does not read live controller intent")
        if runtime["source"] != "simulation":
            intents, intent_error = _read_input("auto-pickup-game", "tracking_intent_snapshot", "hhh.controller.intent", 1)
        runtime["inputs"]["cal2_projection"] = _input_state(projection, projection_error)
        runtime["inputs"]["controller_intent"] = _input_state(intents, intent_error)
        try:
            _validate_tracking_inputs(projection, intents)
            output = _tracker.update(runtime, projection, intents, now)
            json.dumps(output, allow_nan=False)
        except (ValueError, TypeError, KeyError, IndexError, AttributeError, OverflowError) as exc:
            _tracker.reset_evidence()
            runtime.update(status="unavailable", errors=[f"Tracking input rejected: {exc}"])
            output = _tracker.update(runtime, None, None, now)
        with _lock:
            _tracking = output
            _placement = placement
            _runtime = base_runtime
            _occupancy = occupancy
        _live.bump()


def _tracking_loop(stop):
    global _placement, _runtime, _occupancy
    while not stop.wait(0.2):
        try:
            _sample_tracking()
        except Exception as exc:
            # A failing sibling must not kill the sampler or preserve old truth.
            with _lock:
                _tracking.update(status="unavailable", sampled_at=time.time(), arms={}, tags=[], errors=[f"Tracking sampler failed: {exc}"])
                _placement = _placement_tracker.unavailable(
                    f"Board sampler failed: {exc}",
                    revision=_placement_tracker.revision,
                    source=_placement_tracker.source or "unknown",
                    source_epoch=_placement_tracker.source_epoch,
                    sampled_at=time.time(),
                )
                _runtime = {}
                _occupancy = _occupancy_tracker.unavailable(f'Board sampler failed: {exc}', time.time())
            _tracker.reset_evidence()
            _placement_tracker.reset_evidence()
            _live.bump()


def occupancy_snapshot():
    """photon.board.occupancy v1; cached camera authority, independent of arms."""
    with _lock:
        output = json.loads(json.dumps(_occupancy))
    now = time.time()
    if (not output or not fresh(output.get('sampled_at'), now)
            or not fresh(output.get('frame_at'), now)):
        return {'contract': 'photon.board.occupancy', 'version': 1,
                'status': 'unavailable', 'error': 'Occupancy sampler or camera stale',
                'relations': []}
    # Short per-tag grace is stricter than the general camera freshness gate.
    for relation in output.get('relations', []):
        if relation['state'] == 'present' and now - relation['evidence_at'] > .35:
            relation['state'] = 'unavailable'
    return output


def tracking_snapshot():
    """photon.board.tracking v1. Reading never advances transport state."""
    with _lock:
        output = json.loads(json.dumps(_tracking))
        game_placement = json.loads(json.dumps(_placement))
        configuration = settings_snapshot()
    stale_s = configuration["settings"]["stale_s"]
    if not output or not fresh(output.get("sampled_at"), time.time()):
        return {"contract": "photon.board.tracking", "version": 1, "status": "unavailable",
                "source": "unknown", "arms": {}, "tags": [], "errors": ["Board sampler stopped or stale"],
                "limits": dict(configuration["settings"]), "configuration": configuration,
                "game_placement": _placement_tracker.unavailable(
                    "Board sampler stopped or stale",
                    revision=int(game_placement.get("revision", 0)) if isinstance(game_placement, dict) else 0,
                    source=str(game_placement.get("source") or "unknown") if isinstance(game_placement, dict) else "unknown",
                    source_epoch=str(game_placement.get("source_epoch") or "unknown") if isinstance(game_placement, dict) else "unknown",
                )}
    output["configuration"] = configuration
    if not fresh(output.get("frame_at"), time.time(), stale_s):
        output.update(status="unavailable", arms={})
        for tag in output["tags"]:
            tag.update(visible=False, stage="unknown", arm=None, target_id=None,
                       confidence="unknown", evidence="Camera frame stale")
        game_placement = _placement_tracker.unavailable(
            "Camera frame stale",
            revision=int(game_placement.get("revision", 0)) if isinstance(game_placement, dict) else 0,
            source=str(output.get("source") or "unknown"),
            source_epoch=str(game_placement.get("source_epoch") or "unknown") if isinstance(game_placement, dict) else "unknown",
            sampled_at=game_placement.get("sampled_at") if isinstance(game_placement, dict) else None,
        )
    output["game_placement"] = game_placement
    return output


def runtime_observation():
    """Cached source observation. HTTP/SSE readers never sample hardware."""
    with _lock:
        output = json.loads(json.dumps(_runtime))
        sampled_at = _tracking.get("sampled_at")
        placement = json.loads(json.dumps(_placement))
    if not output or not fresh(sampled_at, time.time()):
        output = {"contract": RUNTIME_CONTRACT, "version": RUNTIME_VERSION,
                  "revision": 0, "status": "unavailable", "source": "unknown",
                  "observed_at": None, "frame_at": None, "corrected": False,
                  "tags": [], "detections": [], "visible_ids": [], "arms": {},
                  "width": 0, "height": 0, "inputs": {}, "errors": ["Board sampler stopped or stale"]}
        placement = _placement_tracker.unavailable(
            "Board sampler stopped or stale", source="unknown",
            source_epoch=_placement_tracker.source_epoch,
        )
    stale_arms = set()
    for side, arm in output["arms"].items():
        if arm.get("connected") and not fresh(arm.get("feedback_at"), time.time()):
            # Keep last pose for diagnostics but remove all authority to place.
            arm.update(connected=False, enabled=False, pump_mode="unknown")
            output["errors"].append(f"{side} arm feedback stale or missing")
            stale_arms.add(side)
    if output.get("frame_at") is not None and not fresh(output["frame_at"], time.time()):
        output.update(status="unavailable", tags=[], detections=[], visible_ids=[])
        output["errors"].append("Camera frame stale")
    if (
        not placement
        or placement.get("contract") != "photon.board.placement"
        or not fresh(placement.get("sampled_at"), time.time())
        or output.get("status") != "ready"
    ):
        placement = _placement_tracker.unavailable(
            "Physical placement evidence is stale or unavailable",
            revision=int(placement.get("revision", 0)) if isinstance(placement, dict) else 0,
            source=str(output.get("source") or "unknown"),
            source_epoch=(placement.get("source_epoch") if isinstance(placement, dict) else _placement_tracker.source_epoch),
            sampled_at=placement.get("sampled_at") if isinstance(placement, dict) else None,
        )
    elif stale_arms:
        placement["relations"] = [
            relation for relation in placement.get("relations", [])
            if relation.get("arm") not in stale_arms
        ]
    output["placement"] = placement
    output['occupancy'] = occupancy_snapshot()
    output["tracking"] = tracking_snapshot()
    return output


def cue_targets_snapshot(*, scope=None, fixed_ids=None):
    """Camera evidence, optionally limited to the consumer's active layout.

    Registering a layout never samples hardware or seeds from another map.
    The existing sampler learns its tags from subsequent camera observations.
    """
    if scope is not None or fixed_ids is not None:
        if (not isinstance(scope, str) or not 1 <= len(scope) <= 128
                or not isinstance(fixed_ids, list) or not 1 <= len(fixed_ids) <= 30
                or any(type(i) is not int or not 30 <= i <= 59 for i in fixed_ids)
                or len(set(fixed_ids)) != len(fixed_ids)):
            raise ValueError('Cue layout requires a scope and unique fixed marker IDs 30–59.')
        key = (scope, tuple(sorted(fixed_ids)))
    else:
        key = None
    with _sample_lock:
        targets = _cue_targets
        if key is not None:
            targets = _cue_layouts.pop(key, None)
            if targets is None:
                targets = CueTargets(fixed_ids=key[1])
            _cue_layouts[key] = targets
            # Both teams share the same game layout; retain recent calibration
            # layouts too, without an unbounded cache of old games.
            while len(_cue_layouts) > 4:
                del _cue_layouts[next(iter(_cue_layouts))]
        value = targets.snapshot(time.time())
        if key is not None:
            value.update(layout_scope=scope, fixed_ids=list(key[1]))
        if runtime_observation().get('status') != 'ready':
            value.update(status='unavailable', tags=[], error='Board observations unavailable.')
        return value


@bp.route('/api/cue-targets')
def cue_targets_api():
    response = jsonify(cue_targets_snapshot())
    response.headers['Cache-Control'] = 'no-store'
    return response


def camera_markers_snapshot():
    """photon.board.camera-markers v1: current corrected detections, never memory."""
    runtime = runtime_observation()
    value = {"contract": "photon.board.camera-markers", "version": 1,
             "status": "unavailable", "source": runtime.get("source"),
             "coordinate_space": "corrected-camera-normalized",
             "frame_at": runtime.get("frame_at"), "max_age_s": STALE_S,
             "width": runtime.get("width", 0), "height": runtime.get("height", 0),
             "tags": [], "error": "Fresh corrected camera markers unavailable."}
    if (runtime.get("status") != "ready" or runtime.get("source") != "camera"
            or not runtime.get("corrected") or not fresh(runtime.get("frame_at"), time.time())
            or not value["width"] or not value["height"]):
        return value
    visible = set(runtime.get("visible_ids", []))
    candidates = [tag for tag in runtime.get("detections", [])
                  if tag["id"] in visible and 0 <= tag.get("missing", float("inf")) <= STALE_S]
    accepted, value["size_filter"] = _size_consistent_markers(candidates, value["width"], value["height"])
    for tag in accepted:
        value["tags"].append({"id": tag["id"], "camera": [tag["nx"], tag["ny"]],
                              "corners": tag.get("ncorners"), "last_seen": runtime["frame_at"]})
    value.update(status="ready", error=None)
    return value


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
        "placement": runtime["placement"],
        "tracking": runtime["tracking"],
    }


def _operator_only():
    if "gamemaster" not in (request.environ.get("hhh.roles") or set()):
        return jsonify({"ok": False, "error": "gamemaster required"}), 403
    return None


@bp.route("/")
def index():
    return send_from_directory(HERE, "index.html")


@bp.route("/board-diagnostics.js")
def diagnostics_script():
    return send_from_directory(HERE, "board-diagnostics.js")


@bp.route("/api/diagnostics")
def diagnostics_api():
    output = tracking_snapshot()
    return jsonify(output), 200 if output["status"] == "ready" else 503


@bp.route("/api/settings", methods=["GET", "POST"])
def settings_api():
    if request.method == "GET":
        return jsonify(settings_snapshot())
    denied = _operator_only()
    if denied:
        return denied
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or set(data) != {"settings"}:
        return jsonify({"ok": False, "error": "Object containing settings required"}), 400
    try:
        return jsonify({"ok": True, "output": update_settings(data["settings"])})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except OSError as exc:
        return jsonify({"ok": False, "error": f"Settings were not saved: {exc}"}), 503


@bp.route("/api/preview")
def preview_api():
    with _lock:
        simulated = _simulation["enabled"]
    if simulated:
        return jsonify({"error": "Simulation never displays live camera evidence"}), 409
    preview, error = _read_input("camera-calibration", "preview_snapshot", "hhh.camera-preview", 1)
    if preview is None or preview.get("stream_path") != "/api/corrected-stream":
        return jsonify({"error": error or "Invalid corrected camera preview path"}), 503
    return redirect(request.script_root + "/p/camera-calibration" + preview["stream_path"])


def preview_frame():
    """photon.board.preview v1: fresh corrected display pixels, never game input."""
    empty = {"contract": "photon.board.preview", "version": 1,
             "status": "unavailable", "coordinate_space": "corrected-camera-normalized",
             "frame_at": None, "width": 0, "height": 0, "jpeg": None}
    with _lock:
        if _simulation["enabled"]:
            return dict(empty, error="Simulation never displays live camera evidence")
    value, error = _read_input("camera-calibration", "preview_frame", "hhh.camera-frame", 1)
    if value is None:
        return dict(empty, error=error)
    stamp = value.get("frame_at")
    if (value.get("coordinate_space") != empty["coordinate_space"]
            or type(stamp) not in (int, float) or not math.isfinite(stamp)
            or not -0.25 <= time.time() - stamp <= 2
            or any(type(value.get(k)) is not int or value[k] <= 0 for k in ("width", "height"))
            or not isinstance(value.get("jpeg"), bytes) or not value["jpeg"]):
        return dict(empty, error="Fresh corrected camera frame unavailable")
    return dict(empty, status="ready", error=None,
                **{key: value[key] for key in ("frame_at", "width", "height", "jpeg")})


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
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or type(data.get("enabled")) is not bool:
        return jsonify({"ok": False, "error": "object with boolean enabled required"}), 400
    try:
        return jsonify({
            "ok": True,
            "output": set_simulation(bool(data.get("enabled")), data.get("tags") or [], data.get("arms")),
        })
    except BoardError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
