"""Photon Game: authoritative, presentation-free tower-defence simulation."""

from __future__ import annotations

import json
import math
import os
import threading
import time
import uuid
from typing import Any
from urllib.parse import unquote, urlsplit

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
    "pages": [{"path": "", "label": "Game settings"}],
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
_presentation: dict[str, Any] = {}
_revision = 1
_run_id: str | None = None
_history_sequence = 0
_inputs = {
    "level": {"status": "unavailable", "error": "not read yet"},
    "board": {"status": "unavailable", "error": "not read yet"},
    "presentation": {"status": "unavailable", "error": "not read yet"},
}
_storage = {
    "settings": {"status": "ready", "error": None},
    "history": {"status": "ready", "error": None},
}


class GameError(ValueError):
    """A rejected operator command or unavailable required input."""

    def __init__(self, message, *, fields=None):
        super().__init__(message)
        self.fields = dict(fields or {})


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
        x = float(raw["x"])
        y = float(raw["y"])
        marker_size = float(raw.get("marker_size", runtime.get("aruco", {}).get("size", size)))
        sockets.append({
            "id": str(socket_id),
            "socket_id": str(socket_id),
            "owner": str(raw.get("owner") or ""),
            "aruco_id": int(raw["aruco_id"]),
            "x": x,
            "y": y,
            "size": size,
            "radius": size / 2.0,
            "marker_x": float(raw.get("marker_x", x)),
            "marker_y": float(raw.get("marker_y", y)),
            "marker_size": marker_size,
        })
    sockets.sort(key=lambda item: item["aruco_id"])
    properties = runtime.get("map_properties") or {}
    raw_core = runtime.get("core_visual")
    if not isinstance(raw_core, dict):
        raw_core = runtime.get("core") or {}
        core_x = float(raw_core.get("x", runtime["width"] / 2))
        core_y = float(raw_core.get("y", runtime["height"] / 2))
        raw_core = {
            "x": core_x,
            "y": core_y,
            "marker_x": core_x,
            "marker_y": core_y,
            "marker_size": float(runtime.get("aruco", {}).get("core_size", 116)),
        }
    visual_scene = runtime.get("visual_scene")
    return {
        "name": str(properties.get("level_id") or "photon-level"),
        "width": int(runtime["width"]),
        "height": int(runtime["height"]),
        "path": first_path,
        "paths": paths,
        "sockets": sockets,
        "core": _copy(raw_core),
        # Additive Level v1 fields stay optional so an older compatible Level
        # can still drive the game while a presentation uses its fallback map.
        "scene": _copy(visual_scene) if isinstance(visual_scene, dict) else None,
    }


def _set_presentation(value, error=None):
    """Validate Level's optional descriptor, then forward it without resolving art."""
    global _presentation
    if not error:
        if not isinstance(value, dict):
            error = "Photon Level supplied no presentation assets"
        elif value.get("contract") != "photon.level.assets" or type(value.get("version")) is not int or value["version"] != 1:
            error = "Photon Level presentation contract mismatch"
        elif value.get("status") not in ("ready", "unavailable"):
            error = "Photon Level presentation status is invalid"
        else:
            base, assets = value.get("base"), value.get("assets")
            def safe_path(path, *, absolute=False):
                if not isinstance(path, str) or not path:
                    return False
                try:
                    parsed = urlsplit(path)
                except ValueError:
                    return False
                decoded = unquote(parsed.path)
                return (
                    not parsed.scheme and not parsed.netloc and not parsed.fragment
                    and "\\" not in decoded and ".." not in decoded.split("/")
                    and decoded.startswith("/") == absolute
                    and not decoded.startswith("//")
                )
            if (
                not isinstance(value.get("revision"), str) or not value["revision"]
                or not safe_path(base, absolute=True) or "?" in base
                or not isinstance(assets, dict)
                or any(not isinstance(key, str) or not safe_path(path) for key, path in assets.items())
            ):
                error = "Photon Level presentation payload is invalid"
    output = (
        {"contract": "photon.level.assets", "version": 1, "status": "unavailable",
         "error": error, "revision": "unavailable", "base": "", "assets": {}}
        if error else _copy(value)
    )
    with _lock:
        _presentation = output
        _set_input("presentation", status=output["status"], error=output.get("error"), revision=output["revision"])


def _install_level(bundle):
    global _engine, _level_projection, _revision, _history_sequence
    revision = bundle["revision"]
    with _level_install_lock:
        with _lock:
            engine = _engine
        if engine is not None and engine.level.layout_revision == revision:
            _set_presentation(bundle.get("presentation"))
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

        _set_presentation(bundle.get("presentation"))
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
        _set_presentation(None, error)
        return False
    try:
        return _install_level(bundle)
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        _set_input("level", status="unavailable", error=f"Photon Level output rejected: {exc}")
        _set_presentation(None, f"Photon Level output rejected: {exc}")
        return False


def _board_input_report(value):
    """Bounded diagnostics from the existing Board read, never physical evidence."""
    def stamp(item):
        try:
            return item if type(item) in (int, float) and math.isfinite(item) else None
        except OverflowError:
            return None

    def message(item):
        return item[:500] if isinstance(item, str) else None

    def reports(items):
        if not isinstance(items, dict):
            return {}
        result = {}
        for name, item in list(items.items())[:32]:
            if not isinstance(name, str) or not isinstance(item, dict):
                continue
            result[name[:64]] = {
                "status": item.get("status") if item.get("status") in ("ready", "unavailable", "simulated") else "unavailable",
                "error": message(item.get("error")), "contract": message(item.get("contract")),
                "version": item.get("version") if type(item.get("version")) is int else None,
            }
        return result

    tracking = value.get("tracking")
    if not isinstance(tracking, dict) or tracking.get("contract") != "photon.board.tracking" or type(tracking.get("version")) is not int or tracking["version"] != 1:
        tracking = {}
    placement = value.get("placement")
    if not isinstance(placement, dict) or placement.get("contract") != "photon.board.placement" or type(placement.get("version")) is not int or placement["version"] != 1:
        placement = {}
    return {
        "reported_at": time.time(), "observed_at": stamp(value.get("observed_at")),
        "frame_at": stamp(value.get("frame_at")), "source": message(value.get("source")),
        "inputs": reports(value.get("inputs")),
        "tracking": {"status": message(tracking.get("status")),
                     "sampled_at": stamp(tracking.get("sampled_at")),
                     "inputs": reports(tracking.get("inputs"))},
        "placement": {"status": message(placement.get("status")),
                      "sampled_at": stamp(placement.get("sampled_at")),
                      "error": message(placement.get("error"))},
    }


def _unavailable_placement(error):
    return {
        "contract": "photon.board.placement", "version": 1,
        "status": "unavailable", "error": str(error)[:500],
        "relations": [],
    }


def _board_observation(diagnostics=None):
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
        or type(value.get("version")) is not int or value.get("version") != BOARD_VERSION
    ):
        return None, f"Photon Board contract mismatch (expected {BOARD_CONTRACT} v{BOARD_VERSION})"
    if diagnostics is not None:
        diagnostics.update(_board_input_report(value))
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
    placement = value.get("placement")
    if (
        not isinstance(placement, dict)
        or placement.get("contract") != "photon.board.placement"
        or type(placement.get("version")) is not int
        or placement.get("version") != 1
    ):
        return None, "Photon Board placement contract mismatch (expected photon.board.placement v1)"
    if placement.get("status") != "ready":
        return None, str(placement.get("error") or "Photon Board placement evidence is unavailable")
    try:
        sampled_at = float(placement["sampled_at"])
        source_epoch = placement["source_epoch"]
        placement_revision = placement["revision"]
        relations = placement["relations"]
        if (
            not math.isfinite(sampled_at)
            or time.time() - sampled_at < -1.0
            or time.time() - sampled_at > 2.0
            or not isinstance(source_epoch, str)
            or not 1 <= len(source_epoch) <= 160
            or type(placement_revision) is not int
            or placement_revision < 0
            or not isinstance(relations, list)
            or len(relations) > 512
        ):
            raise ValueError
        clean_relations = []
        identities = set()
        ranks = set()
        targets = set()
        for relation in relations:
            if not isinstance(relation, dict):
                raise ValueError
            relation_id = relation["relation_id"]
            movable_id = relation["movable_id"]
            marker_id = relation["marker_id"]
            arm = relation["arm"]
            rank = relation["rank"]
            stable = relation["stable"]
            distance = float(relation["distance"])
            observed_since = float(relation["observed_since"])
            stable_at = float(relation["stable_at"])
            marker_seen_at = float(relation["marker_seen_at"])
            if (
                not isinstance(relation_id, str) or not 1 <= len(relation_id) <= 240
                or type(movable_id) is not int or not 100 <= movable_id <= 999
                or type(marker_id) is not int or not 0 <= marker_id < 100
                or arm not in {"green", "purple"}
                or type(rank) is not int or not 0 <= rank < 100
                or type(stable) is not bool
                or not all(math.isfinite(item) for item in (
                    distance, observed_since, stable_at, marker_seen_at,
                ))
                or not 0 <= distance <= 1
                or observed_since > stable_at
                or marker_seen_at > sampled_at + 1.0
                or stable and stable_at > sampled_at + 0.01
                or relation_id in identities
                or (arm, movable_id, rank) in ranks
                or (arm, movable_id, marker_id) in targets
            ):
                raise ValueError
            identities.add(relation_id)
            ranks.add((arm, movable_id, rank))
            targets.add((arm, movable_id, marker_id))
            clean_relations.append({
                "relation_id": relation_id, "movable_id": movable_id,
                "marker_id": marker_id, "arm": arm, "rank": rank,
                "distance": distance, "observed_since": observed_since,
                "stable_at": stable_at, "stable": stable,
                "marker_seen_at": marker_seen_at,
            })
    except (KeyError, TypeError, ValueError, OverflowError):
        return None, "Photon Board placement payload is invalid"
    return {
        "contract": "photon.board.placement", "version": 1,
        "status": "ready", "error": None,
        "revision": placement_revision,
        "board_revision": revision,
        "source": str(value.get("source") or "unknown")[:80],
        "source_epoch": source_epoch, "sampled_at": sampled_at,
        "relations": clean_relations,
    }, None


def _physical_observation():
    upstream = {}
    observation, error = _board_observation(upstream)
    if error:
        _set_input("board", status="unavailable", error=error, upstream=upstream)
        return _unavailable_placement(error)
    _set_input(
        "board", status="ready", revision=int(observation["board_revision"]),
        source=str(observation.get("source") or "unknown"),
        placement_revision=int(observation["revision"]),
        upstream=upstream,
    )
    return _copy(observation)


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


def _configuration_snapshot(engine):
    output = _settings.response()
    output.pop("ok", None)
    output.update({
        "contract": "photon.game.settings",
        "version": 1,
        "authored_wave_enemy_counts": [],
    })
    with _lock:
        _storage["settings"] = {
            "status": output["status"], "error": output.get("error"),
        }
    if engine is not None:
        with engine.lock:
            output["authored_wave_enemy_counts"] = [
                sum(max(0, int(group.get("count", 0))) for group in wave.get("groups", []))
                for wave in engine.wave_source
            ]
    return output


def _public_snapshot(*, compact_enemies=False):
    _sync_level()
    with _lock:
        engine = _engine
    configuration = _configuration_snapshot(engine)
    with _lock:
        inputs = _copy(_inputs)
        storage = _copy(_storage)
        level = _copy(_level_projection)
        presentation = _copy(_presentation)
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
            "presentation": presentation,
            "enemies": [],
            "towers": [],
            "inputs": inputs,
            "storage": storage,
            "configuration": configuration,
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
        "presentation": presentation,
        "inputs": inputs,
        "storage": storage,
        "configuration": configuration,
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
    engine = None
    level_ready = False
    if action not in {"configure", "reset_settings"}:
        engine, level_ready = _require_engine()
    try:
        if action == "start":
            if not level_ready:
                raise GameError(_inputs["level"].get("error") or "Photon Level is unavailable")
            virtual_play = (
                bool(data["virtual_play"])
                if "virtual_play" in data
                else bool(engine.snapshot()["virtual_play"])
            )
            if not virtual_play:
                _physical_observation()
                with _lock:
                    board_error = _inputs["board"].get("error")
                    board_ready = _inputs["board"].get("status") == "ready"
                if not board_ready:
                    raise GameError(board_error or "Photon Board is unavailable")
            engine.set_virtual_play(virtual_play)
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
            if "virtual_play" in data:
                engine.set_virtual_play(bool(data["virtual_play"]))
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
                raise GameError(
                    "settings validation failed",
                    fields=errors,
                )
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
    except OSError as exc:
        with _lock:
            _storage["settings"] = {
                "status": "unavailable", "error": str(_settings.error or exc),
            }
            _revision += 1
        raise GameError(f"settings were not saved: {exc}") from exc
    if action not in {"configure", "reset_settings"}:
        _append_history("operator_command", {"action": action})
    return game_snapshot()


def hub_init(ctx):
    global _hub_ctx
    _hub_ctx = ctx
    with _lock:
        _storage["settings"] = {
            "status": "unavailable" if _settings.error else "ready",
            "error": _settings.error,
        }
    _sync_level()
    with _lock:
        engine = _engine
    if engine is not None:
        engine.set_wake(_engine_changed)
        engine.set_physical_source(_physical_observation)
        engine.start_background()


def hub_stop():
    global _hub_ctx, _engine, _level_projection, _presentation
    with _lock:
        engine = _engine
    if engine is not None:
        engine.stop_background()
        engine.set_physical_source(None)
    with _lock:
        _engine = None
        _level_projection = None
        _presentation = {}
        _hub_ctx = None
        _inputs["level"] = {"status": "unavailable", "error": "not read yet"}
        _inputs["board"] = {"status": "unavailable", "error": "not read yet"}
        _inputs["presentation"] = {"status": "unavailable", "error": "not read yet"}


def _operator_only():
    if "gamemaster" not in (request.environ.get("hhh.roles") or set()):
        return jsonify({"ok": False, "error": "gamemaster required"}), 403
    return None


@bp.route("/")
@bp.route("/settings")
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
        return jsonify({"ok": False, "error": str(exc), "errors": exc.fields}), 400
