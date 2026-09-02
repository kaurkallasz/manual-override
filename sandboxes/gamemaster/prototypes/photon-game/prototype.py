"""Photon Game: authoritative, presentation-free tower-defense simulation."""

import json
import math
import os
import threading
import time
import uuid

from flask import Blueprint, jsonify, request, send_from_directory

import live

HERE = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(HERE, "data", "runs.jsonl")
CONTRACT = "photon.game"
VERSION = 1
TOWER_TYPES = {
    100: {"type": "pulse", "team": "green", "range": 175.0, "damage": 24.0, "period": 0.55},
    101: {"type": "slow", "team": "green", "range": 145.0, "damage": 40.0, "period": 1.15},
    102: {"type": "mortar", "team": "purple", "range": 220.0, "damage": 64.0, "period": 1.7},
    103: {"type": "spark", "team": "purple", "range": 155.0, "damage": 20.0, "period": 0.42},
}

MANIFEST = {
    "name": "Photon Game",
    "description": "Input: Level, Board, and operator commands. Output: authoritative game snapshots and SSE.",
    "group": "Photon Engine",
    "default_page": "",
    "pages": [{"path": "", "label": "Game state"}],
}
bp = Blueprint("photon_game", __name__)
_hub_ctx = None
_lock = threading.RLock()
_live = live.LiveState()
_stop = threading.Event()
_worker = None


class GameError(ValueError):
    pass


def _new_state(level=None):
    return {
        "revision": 1, "phase": "setup", "message": "Ready",
        "run_id": None, "elapsed": 0.0, "core_hp": 100,
        "score": 0, "spawned": 0, "defeated": 0,
        "settings": {"enemy_count": 20, "spawn_interval": 1.25},
        "level": level, "towers": [], "enemies": [],
        "inputs": {
            "level": {"status": "unavailable", "error": "not read yet"},
            "board": {"status": "unavailable", "error": "not read yet"},
            "log": {"status": "ready", "error": None},
        },
        "_next_enemy": 1, "_spawn_wait": 0.0,
    }


_state = _new_state()


def _copy(value):
    return json.loads(json.dumps(value))


def _module(slug):
    if _hub_ctx is None or not _hub_ctx.is_prototype_enabled(slug):
        return None
    return _hub_ctx.get_prototype(slug)


def _level_input():
    module = _module("photon-level")
    if module is None or not callable(getattr(module, "level_snapshot", None)):
        return None, "Photon Level unavailable"
    try:
        value = module.level_snapshot()
    except Exception as exc:
        return None, f"Photon Level failed: {exc}"
    if (
        not isinstance(value, dict)
        or value.get("contract") != "photon.level"
        or value.get("version") not in {1, 2}
    ):
        return None, "Photon Level contract mismatch"
    if value.get("status") != "ready" or not isinstance(value.get("level"), dict):
        return None, str(value.get("error") or "Photon Level is not ready")
    return value, None


def _board_input():
    module = _module("photon-board")
    if module is None or not callable(getattr(module, "board_snapshot", None)):
        return None, "Photon Board unavailable"
    try:
        value = module.board_snapshot()
    except Exception as exc:
        return None, f"Photon Board failed: {exc}"
    if not isinstance(value, dict) or value.get("contract") != "photon.board" or value.get("version") != 1:
        return None, "Photon Board contract mismatch"
    if value.get("status") != "ready":
        return value, "; ".join(value.get("errors") or []) or "Photon Board is not ready"
    return value, None


def _public_state_locked():
    public = {key: value for key, value in _state.items() if not key.startswith("_")}
    return {
        "contract": CONTRACT, "version": VERSION, "status": "ready",
        "server_time": time.time(), **_copy(public),
    }


def game_snapshot():
    """Public read-only contract used by presentation modules."""
    with _lock:
        return _public_state_locked()


def game_events():
    """Public SSE response used by a presentation module."""
    return _live.stream(game_snapshot, interval=0.25)


def _touch_locked():
    _state["revision"] += 1


def _log(kind, detail=None):
    event = {
        "time": time.time(), "run_id": _state.get("run_id"),
        "event": kind, "detail": detail or {},
    }
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, separators=(",", ":")) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        _state["inputs"]["log"] = {"status": "ready", "error": None}
    except OSError as exc:
        _state["inputs"]["log"] = {"status": "unavailable", "error": str(exc)}


def _path_metrics(level):
    points = level["path"]
    lengths, total = [], 0.0
    for first, second in zip(points, points[1:]):
        length = math.hypot(second["x"] - first["x"], second["y"] - first["y"])
        lengths.append(length)
        total += length
    return lengths, total


def _path_position(level, distance):
    points, (lengths, total) = level["path"], _path_metrics(level)
    remaining = min(max(0.0, distance), total)
    for index, length in enumerate(lengths):
        if remaining <= length:
            ratio = remaining / length if length else 0.0
            first, second = points[index], points[index + 1]
            return {
                "x": round(first["x"] + (second["x"] - first["x"]) * ratio, 2),
                "y": round(first["y"] + (second["y"] - first["y"]) * ratio, 2),
            }
        remaining -= length
    return {"x": points[-1]["x"], "y": points[-1]["y"]}


def _place_locked(socket_id, atom_tag_id, source):
    if _state["level"] is None:
        raise GameError("no level is available")
    try:
        atom_tag_id = int(atom_tag_id)
    except (TypeError, ValueError) as exc:
        raise GameError("atom_tag_id must be 100, 101, 102, or 103") from exc
    tower_rule = TOWER_TYPES.get(atom_tag_id)
    if tower_rule is None:
        raise GameError("atom_tag_id must be 100, 101, 102, or 103")
    socket = next((item for item in _state["level"]["sockets"] if item["id"] == str(socket_id)), None)
    if socket is None:
        raise GameError("unknown socket_id")
    existing = next((item for item in _state["towers"] if item["socket_id"] == socket["id"]), None)
    tower = {
        "socket_id": socket["id"], "atom_tag_id": atom_tag_id,
        "type": tower_rule["type"], "team": tower_rule["team"],
        "x": socket["x"], "y": socket["y"], "health": 100,
        "cooldown": 0.0, "source": source,
    }
    if existing:
        if all(existing.get(key) == tower[key] for key in ("atom_tag_id", "type", "team", "source")) and existing.get("health") == 100:
            return False
        _state["towers"][_state["towers"].index(existing)] = tower
    else:
        _state["towers"].append(tower)
    _log("tower_placed", {"socket_id": socket["id"], "atom_tag_id": atom_tag_id, "source": source})
    return True


def _apply_board_locked(board):
    if not board or board.get("status") != "ready" or _state["level"] is None:
        return False
    changed = False
    width, height = _state["level"]["width"], _state["level"]["height"]
    arms = board.get("arms") or {}
    for tag in board.get("tags") or []:
        if tag.get("id") not in TOWER_TYPES:
            continue
        rule = TOWER_TYPES[tag["id"]]
        if board.get("source") != "simulation":
            arm = arms.get(rule["team"]) or {}
            if not (arm.get("connected") and arm.get("enabled") and arm.get("pump_mode") == "off"):
                continue
        x, y = float(tag["nx"]) * width, float(tag["ny"]) * height
        sockets = sorted(
            _state["level"]["sockets"],
            key=lambda item: math.hypot(item["x"] - x, item["y"] - y),
        )
        if sockets and math.hypot(sockets[0]["x"] - x, sockets[0]["y"] - y) <= sockets[0]["radius"]:
            changed = _place_locked(sockets[0]["id"], tag["id"], board.get("source")) or changed
    return changed


def _start_locked(level):
    settings = _copy(_state["settings"])
    inputs = _copy(_state["inputs"])
    _state.clear()
    _state.update(_new_state(_copy(level)))
    _state["settings"] = settings
    _state["inputs"] = inputs
    _state.update({
        "phase": "running", "message": "Defend the learning core",
        "run_id": uuid.uuid4().hex, "revision": 1,
    })
    _log("run_started", {"settings": settings})


def apply_command(data):
    """Public validated command input for presentation modules."""
    if not isinstance(data, dict):
        raise GameError("command must be an object")
    action = str(data.get("action") or "")
    level_value = None
    if action in {"start", "reset"}:
        snapshot, error = _level_input()
        level_value = snapshot.get("level") if snapshot else None
        with _lock:
            _state["inputs"]["level"] = {
                "status": "ready" if snapshot else "unavailable", "error": error,
                "revision": snapshot.get("revision") if snapshot else None,
            }
        if action == "start" and level_value is None:
            raise GameError(error)
    with _lock:
        if action == "start":
            _start_locked(level_value)
        elif action == "reset":
            settings = _copy(_state["settings"])
            inputs = _copy(_state["inputs"])
            _state.clear()
            _state.update(_new_state(_copy(level_value) if level_value else None))
            _state["settings"], _state["inputs"] = settings, inputs
            _log("reset")
        elif action == "pause":
            if _state["phase"] != "running":
                raise GameError(f"cannot pause from {_state['phase']}")
            _state["phase"], _state["message"] = "paused", "Paused"
            _log("paused")
        elif action == "resume":
            if _state["phase"] != "paused":
                raise GameError(f"cannot resume from {_state['phase']}")
            _state["phase"], _state["message"] = "running", "Defend the learning core"
            _log("resumed")
        elif action == "place":
            _place_locked(data.get("socket_id"), data.get("atom_tag_id"), "operator")
        elif action == "configure":
            if _state["phase"] != "setup":
                raise GameError("settings can only change during setup")
            try:
                enemy_count = int(data.get("enemy_count"))
                spawn_interval = float(data.get("spawn_interval"))
            except (TypeError, ValueError, OverflowError) as exc:
                raise GameError("enemy_count and spawn_interval must be numbers") from exc
            if not 1 <= enemy_count <= 200 or not 0.2 <= spawn_interval <= 10:
                raise GameError("enemy_count must be 1–200 and spawn_interval 0.2–10")
            _state["settings"] = {"enemy_count": enemy_count, "spawn_interval": spawn_interval}
        else:
            raise GameError("unknown action")
        _touch_locked()
        output = _public_state_locked()
    _live.bump()
    return output


def _tick_locked(dt):
    if _state["phase"] != "running" or _state["level"] is None:
        return False
    _state["elapsed"] = round(_state["elapsed"] + dt, 3)
    _state["_spawn_wait"] -= dt
    if _state["spawned"] < _state["settings"]["enemy_count"] and _state["_spawn_wait"] <= 0:
        enemy_id = _state["_next_enemy"]
        _state["_next_enemy"] += 1
        _state["spawned"] += 1
        _state["_spawn_wait"] += _state["settings"]["spawn_interval"]
        position = _path_position(_state["level"], 0)
        _state["enemies"].append({
            "id": enemy_id, "distance": 0.0, "x": position["x"], "y": position["y"],
            "health": 100.0, "max_health": 100.0,
        })
    _, path_length = _path_metrics(_state["level"])
    escaped = []
    for enemy in _state["enemies"]:
        enemy["distance"] += 48.0 * dt
        enemy.update(_path_position(_state["level"], enemy["distance"]))
        if enemy["distance"] >= path_length:
            escaped.append(enemy)
    for enemy in escaped:
        _state["enemies"].remove(enemy)
        _state["core_hp"] = max(0, _state["core_hp"] - 10)

    for tower in _state["towers"]:
        tower["cooldown"] = max(0.0, tower["cooldown"] - dt)
        rule = TOWER_TYPES[tower["atom_tag_id"]]
        targets = [
            enemy for enemy in _state["enemies"]
            if math.hypot(enemy["x"] - tower["x"], enemy["y"] - tower["y"]) <= rule["range"]
        ]
        if tower["cooldown"] <= 0 and targets:
            target = max(targets, key=lambda item: item["distance"])
            target["health"] -= rule["damage"]
            tower["cooldown"] = rule["period"]
    defeated = [enemy for enemy in _state["enemies"] if enemy["health"] <= 0]
    for enemy in defeated:
        _state["enemies"].remove(enemy)
        _state["defeated"] += 1
        _state["score"] += 100

    finished = _state["spawned"] >= _state["settings"]["enemy_count"] and not _state["enemies"]
    if _state["core_hp"] <= 0:
        _state["phase"], _state["message"] = "lost", "The learning core was overrun"
        _log("run_finished", {"result": "lost", "score": _state["score"]})
    elif finished:
        _state["phase"], _state["message"] = "won", "Learning core secured"
        _log("run_finished", {"result": "won", "score": _state["score"]})
    return True


def _loop():
    last = time.monotonic()
    next_inputs = 0.0
    while not _stop.wait(0.05):
        now = time.monotonic()
        dt, last = min(0.1, now - last), now
        level_snapshot = board_snapshot = None
        level_error = board_error = None
        if now >= next_inputs:
            level_snapshot, level_error = _level_input()
            board_snapshot, board_error = _board_input()
            next_inputs = now + 0.25
        with _lock:
            changed = False
            if level_snapshot is not None:
                previous_revision = _state["inputs"]["level"].get("revision")
                level_input = {
                    "status": "ready", "error": None, "revision": level_snapshot["revision"],
                }
                changed = level_input != _state["inputs"]["level"] or changed
                _state["inputs"]["level"] = level_input
                if _state["phase"] == "setup" and (
                    _state["level"] is None
                    or previous_revision != level_snapshot["revision"]
                ):
                    _state["level"] = _copy(level_snapshot["level"])
                    changed = True
            elif level_error is not None:
                level_input = {"status": "unavailable", "error": level_error}
                changed = level_input != _state["inputs"]["level"] or changed
                _state["inputs"]["level"] = level_input
            if board_snapshot is not None:
                board_input = {
                    "status": board_snapshot.get("status"), "error": board_error,
                    "source": board_snapshot.get("source"),
                }
                changed = board_input != _state["inputs"]["board"] or changed
                _state["inputs"]["board"] = board_input
                changed = _apply_board_locked(board_snapshot) or changed
            elif board_error is not None:
                board_input = {"status": "unavailable", "error": board_error}
                changed = board_input != _state["inputs"]["board"] or changed
                _state["inputs"]["board"] = board_input
            changed = _tick_locked(dt) or changed
            if changed:
                _touch_locked()
        if changed:
            _live.bump()


def hub_init(ctx):
    global _hub_ctx, _worker
    _hub_ctx = ctx
    _stop.clear()
    if _worker is None or not _worker.is_alive():
        _worker = threading.Thread(target=_loop, name="photon-game", daemon=True)
        _worker.start()


def hub_stop():
    global _hub_ctx, _worker
    _stop.set()
    if _worker is not None and _worker is not threading.current_thread():
        _worker.join(timeout=1.0)
    _worker = None
    _hub_ctx = None


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
