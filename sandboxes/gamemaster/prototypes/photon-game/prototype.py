"""Photon Game: authoritative, presentation-free tower-defence simulation."""

from __future__ import annotations

import json
import math
import os
import threading
import time
import uuid
from typing import Any

from flask import Blueprint, jsonify, request, send_from_directory

import live
from photon_game_runtime import ContractLevelModel, DefenseEngine, SettingsStore

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")
SETTINGS_PATH = os.path.join(DATA_DIR, "settings.json")
LOG_PATH = os.path.join(DATA_DIR, "runs.jsonl")
CONTRACT = "photon.game"
VERSION = 2
LEVEL_CONTRACT = "photon.level.runtime"
LEVEL_VERSION = 1
BOARD_CONTRACT = "photon.board.runtime"
BOARD_VERSION = 1

MANIFEST = {
    "name": "Photon Game",
    "description": (
        "Input: Level, Board, settings, and operator commands. Output: one "
        "authoritative game snapshot and one SSE stream."
    ),
    "group": "Photon Engine",
    "default_page": "",
    "pages": [{"path": "", "label": "Game state"}],
}

bp = Blueprint("photon_game", __name__)
_lock = threading.RLock()
_history_lock = threading.RLock()
_level_install_lock = threading.Lock()
_live = live.LiveState()
_hub_ctx = None
_engine: DefenseEngine | None = None
_settings = SettingsStore(SETTINGS_PATH)
_level_projection: dict[str, Any] | None = None
_revision = 1
_run_id: str | None = None
_history_sequence = 0
_inputs = {
    "level": {"status": "unavailable", "error": "not read yet"},
    "board": {"status": "unavailable", "error": "not read yet"},
}
_storage = {
    "settings": {"status": "ready", "error": None},
    "history": {"status": "ready", "error": None},
}


class GameError(ValueError):
    """A rejected operator command or unavailable required input."""


def _copy(value):
    return json.loads(json.dumps(value))


def _module(slug):
    if _hub_ctx is None or not _hub_ctx.is_prototype_enabled(slug):
        return None
    return _hub_ctx.get_prototype(slug)


def _set_input(name, *, status, error=None, **detail):
    global _revision
    value = {"status": status, "error": error, **detail}
    with _lock:
        if _inputs[name] != value:
            _inputs[name] = value
            _revision += 1


def _level_bundle():
    module = _module("photon-level")
    if module is None or not callable(getattr(module, "runtime_bundle", None)):
        return None, "Photon Level is unavailable or disabled"
    try:
        value = module.runtime_bundle()
    except Exception as exc:
        return None, f"Photon Level failed: {exc}"
    if (
        not isinstance(value, dict)
        or value.get("contract") != LEVEL_CONTRACT
        or value.get("version") != LEVEL_VERSION
    ):
        return None, f"Photon Level contract mismatch (expected {LEVEL_CONTRACT} v{LEVEL_VERSION})"
    if value.get("status") != "ready":
        return None, str(value.get("error") or "Photon Level is not ready")
    revision = value.get("revision")
    if (
        isinstance(revision, bool)
        or not isinstance(revision, int)
        or revision < 1
        or not isinstance(value.get("runtime"), dict)
        or not isinstance(value.get("waves"), list)
        or not value["waves"]
    ):
        return None, "Photon Level runtime payload is invalid"
    return value, None


def _simple_level(runtime):
    paths = {
        str(name): [list(map(float, point)) for point in points]
        for name, points in runtime["paths"].items()
    }
    first_path = next(iter(paths.values()), [])
    sockets = []
    for socket_id, raw in runtime["sockets"].items():
        size = float(raw.get("size", 0))
        sockets.append({
            "id": str(socket_id),
            "aruco_id": int(raw["aruco_id"]),
            "x": float(raw["x"]),
            "y": float(raw["y"]),
            "radius": size / 2.0,
        })
    sockets.sort(key=lambda item: item["aruco_id"])
    properties = runtime.get("map_properties") or {}
    return {
        "name": str(properties.get("level_id") or "photon-level"),
        "width": int(runtime["width"]),
        "height": int(runtime["height"]),
        "path": first_path,
        "paths": paths,
        "sockets": sockets,
    }


def _install_level(bundle):
    global _engine, _level_projection, _revision, _history_sequence
    revision = bundle["revision"]
    with _level_install_lock:
        with _lock:
            engine = _engine
        if engine is not None and engine.level.layout_revision == revision:
            _set_input("level", status="ready", revision=revision)
            return True
        if engine is not None:
            with engine.lock:
                active = engine.phase != "setup"
            if active:
                _set_input(
                    "level", status="ready", revision=engine.level.layout_revision,
                    pending_revision=revision,
                )
                return True

        next_level = ContractLevelModel(bundle["runtime"])
        projection = _simple_level(bundle["runtime"])
        start_engine = False
        if engine is None:
            engine = DefenseEngine(bundle["runtime"], bundle["waves"])
            engine.set_wake(_engine_changed)
            engine.set_physical_source(_physical_observation)
            with _lock:
                _engine = engine
                _history_sequence = 0
                start_engine = _hub_ctx is not None
        else:
            engine.reload_level(next_level, bundle["waves"])
        with _lock:
            _level_projection = projection
            _set_input("level", status="ready", revision=revision)
            _revision += 1
        if start_engine:
            engine.start_background()
    return True


def _sync_level():
    bundle, error = _level_bundle()
    if error:
        _set_input("level", status="unavailable", error=error)
        return False
    try:
        return _install_level(bundle)
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        _set_input("level", status="unavailable", error=f"Photon Level output rejected: {exc}")
        return False


def _board_observation():
    module = _module("photon-board")
    if module is None or not callable(getattr(module, "runtime_observation", None)):
        return None, "Photon Board is unavailable or disabled"
    try:
        value = module.runtime_observation()
    except Exception as exc:
        return None, f"Photon Board failed: {exc}"
    if (
        not isinstance(value, dict)
        or value.get("contract") != BOARD_CONTRACT
        or value.get("version") != BOARD_VERSION
    ):
        return None, f"Photon Board contract mismatch (expected {BOARD_CONTRACT} v{BOARD_VERSION})"
    if value.get("status") != "ready":
        errors = value.get("errors")
        detail = "; ".join(str(item) for item in errors) if isinstance(errors, list) else ""
        return None, str(value.get("error") or detail or "Photon Board is not ready")
    try:
        revision = int(value["revision"])
        observed_at = float(value["observed_at"])
    except (KeyError, TypeError, ValueError, OverflowError):
        return None, "Photon Board observation metadata is invalid"
    age = time.time() - observed_at
    if revision < 0 or not math.isfinite(observed_at) or age < -1.0 or age > 2.0:
        return None, "Photon Board observation is stale or invalid"
    if not isinstance(value.get("tags"), list) or not isinstance(value.get("arms"), dict):
        return None, "Photon Board observation payload is invalid"
    if len(value["tags"]) > 128:
        return None, "Photon Board observation contains too many tags"
    try:
        seen = set()
        for tag in value["tags"]:
            if not isinstance(tag, dict):
                raise ValueError
            tag_id = int(tag["id"])
            nx, ny = float(tag["nx"]), float(tag["ny"])
            missing = float(tag.get("missing", 0))
            if (
                tag_id in seen
                or not 0 <= tag_id <= 999
                or not all(math.isfinite(item) for item in (nx, ny, missing))
                or not 0 <= nx <= 1
                or not 0 <= ny <= 1
                or missing < 0
            ):
                raise ValueError
            seen.add(tag_id)
        for side, arm in value["arms"].items():
            if side not in {"green", "purple"} or not isinstance(arm, dict):
                raise ValueError
            if str(arm.get("pump_mode") or "off") not in {"suck", "blow", "off", "conflict"}:
                raise ValueError
    except (KeyError, TypeError, ValueError, OverflowError):
        return None, "Photon Board observation payload is invalid"
    return value, None


def _physical_observation():
    observation, error = _board_observation()
    if error:
        _set_input("board", status="unavailable", error=error)
        return [], {}
    _set_input(
        "board", status="ready", revision=int(observation["revision"]),
        source=str(observation.get("source") or "unknown"),
    )
    return _copy(observation["tags"]), _copy(observation["arms"])


def _append_history(kind, detail=None):
    with _history_lock:
        with _lock:
            run_id = _run_id
        entry = {
            "recorded_at": time.time(),
            "run_id": run_id,
            "kind": str(kind),
            "detail": _copy(detail or {}),
        }
        try:
            os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
            with open(LOG_PATH, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, separators=(",", ":")) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            with _lock:
                _storage["history"] = {"status": "ready", "error": None}
        except OSError as exc:
            with _lock:
                _storage["history"] = {"status": "unavailable", "error": str(exc)}


def _persist_engine_events():
    global _history_sequence
    with _lock:
        engine = _engine
    if engine is None:
        return
    with engine.lock:
        events = _copy(engine.events)
    with _history_lock:
        for event in events:
            sequence = int(event.get("sequence", 0))
            if sequence <= _history_sequence:
                continue
            _append_history("game_event", event)
            _history_sequence = sequence


def _engine_changed():
    global _revision
    with _lock:
        _revision += 1
    _persist_engine_events()
    _live.bump()


def _public_snapshot(*, compact_enemies=False):
    _sync_level()
    with _lock:
        engine = _engine
        inputs = _copy(_inputs)
        storage = _copy(_storage)
        level = _copy(_level_projection)
        revision = _revision
        run_id = _run_id
    if engine is None:
        return {
            "contract": CONTRACT,
            "version": VERSION,
            "status": "unavailable",
            "error": inputs["level"].get("error") or "Photon Level is unavailable",
            "revision": revision,
            "run_id": run_id,
            "phase": "setup",
            "paused": False,
            "virtual_play": False,
            "level": None,
            "enemies": [],
            "towers": [],
            "inputs": inputs,
            "storage": storage,
            "server_time": time.time(),
        }
    simulation = engine.snapshot(compact_enemies=compact_enemies)
    return {
        "contract": CONTRACT,
        "version": VERSION,
        "status": "ready",
        "error": None,
        "revision": revision,
        "run_id": run_id,
        "level": level,
        "inputs": inputs,
        "storage": storage,
        **simulation,
    }


def game_snapshot():
    """The sole read-only Photon Game output consumed by presentations."""
    return _public_snapshot()


def game_events():
    """The sole Photon Game SSE output, carrying compact game snapshots."""
    return _live.stream(lambda: _public_snapshot(compact_enemies=True), interval=0.25)


def _require_engine():
    _sync_level()
    with _lock:
        engine = _engine
        level_ready = _inputs["level"].get("status") == "ready"
    if engine is None:
        raise GameError("Photon Level is unavailable")
    return engine, level_ready


def apply_command(data):
    """Apply one validated operator input and return the authoritative snapshot."""
    global _run_id, _history_sequence, _revision
    if not isinstance(data, dict):
        raise GameError("command must be an object")
    action = str(data.get("action") or "")
    engine, level_ready = _require_engine()
    try:
        if action == "start":
            if not level_ready:
                raise GameError(_inputs["level"].get("error") or "Photon Level is unavailable")
            if "virtual_play" in data:
                engine.set_virtual_play(bool(data["virtual_play"]))
            with _lock:
                _run_id = uuid.uuid4().hex
                _history_sequence = 0
            engine.start(_settings.snapshot())
        elif action == "pause":
            if engine.snapshot()["phase"] != "running":
                raise GameError("game is not running")
            engine.pause(True)
        elif action == "resume":
            if engine.snapshot()["phase"] != "running":
                raise GameError("game is not running")
            engine.pause(False)
        elif action == "reset":
            engine.reset()
            with _lock:
                _run_id = None
                _history_sequence = 0
                _revision += 1
            _sync_level()
            _live.bump()
        elif action == "set_virtual":
            engine.set_virtual_play(bool(data.get("virtual_play")))
        elif action == "place":
            socket_id = data.get("socket_id")
            engine.place(
                int(data["atom_tag_id"]),
                str(socket_id) if socket_id not in (None, "") else None,
                data.get("tower_type"),
                source="virtual",
                team=data.get("team"),
            )
        elif action == "activate_core":
            engine.activate_core_tag(
                int(data["atom_tag_id"]), source="virtual", team=data.get("team")
            )
        elif action == "loadout":
            engine.set_loadout(int(data["atom_tag_id"]), str(data["tower_type"]))
        elif action == "aim":
            engine.set_tower_aim(
                int(data["atom_tag_id"]),
                float(data["angle_degrees"]),
                float(data["spread"]),
                socket_id=data.get("socket_id"),
            )
        elif action == "configure":
            response, errors = _settings.update(
                data.get("settings") or {}, data.get("preset")
            )
            if errors:
                raise GameError("settings validation failed: " + "; ".join(
                    f"{key} {value}" for key, value in sorted(errors.items())
                ))
            with _lock:
                _storage["settings"] = {"status": "ready", "error": None}
                _revision += 1
            _append_history("settings_saved", {
                "revision": response["revision"], "preset": response["preset"]
            })
        elif action == "reset_settings":
            response = _settings.reset_defaults()
            with _lock:
                _storage["settings"] = {"status": "ready", "error": None}
                _revision += 1
            _append_history("settings_reset", {"revision": response["revision"]})
        else:
            raise GameError("unknown action")
    except KeyError as exc:
        raise GameError(f"{exc.args[0]} is required") from exc
    except (PermissionError, TypeError, ValueError, OverflowError) as exc:
        if isinstance(exc, GameError):
            raise
        raise GameError(str(exc)) from exc
    if action not in {"configure", "reset_settings"}:
        _append_history("operator_command", {"action": action})
    return game_snapshot()


def hub_init(ctx):
    global _hub_ctx
    _hub_ctx = ctx
    _sync_level()
    with _lock:
        engine = _engine
    if engine is not None:
        engine.set_wake(_engine_changed)
        engine.set_physical_source(_physical_observation)
        engine.start_background()


def hub_stop():
    global _hub_ctx, _engine, _level_projection
    with _lock:
        engine = _engine
    if engine is not None:
        engine.stop_background()
        engine.set_physical_source(None)
    with _lock:
        _engine = None
        _level_projection = None
        _hub_ctx = None
        _inputs["level"] = {"status": "unavailable", "error": "not read yet"}
        _inputs["board"] = {"status": "unavailable", "error": "not read yet"}


def _operator_only():
    if "gamemaster" not in (request.environ.get("hhh.roles") or set()):
        return jsonify({"ok": False, "error": "gamemaster required"}), 403
    return None


@bp.route("/")
def index():
    return send_from_directory(HERE, "index.html")


@bp.route("/api/state")
def state_api():
    return jsonify(game_snapshot())


@bp.route("/api/events")
def events_api():
    return game_events()


@bp.route("/api/command", methods=["POST"])
def command_api():
    denied = _operator_only()
    if denied:
        return denied
    try:
        return jsonify({"ok": True, "output": apply_command(request.get_json(silent=True))})
    except GameError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
