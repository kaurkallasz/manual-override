"""Photon Game: authoritative, presentation-free tower-defence simulation."""

from __future__ import annotations
from shared import delay_trace as trace
from shared.fixed_board import cue_layout

import json
import hashlib
import logging
import math
import os
import threading
import time
import uuid
from typing import Any
from pathlib import Path
from urllib.parse import unquote, urlsplit

from flask import Blueprint, current_app, jsonify, request, send_from_directory

import live
import post_match
from event_flow import starting_atoms

from photon_game_runtime import rewards
from photon_game_runtime import ContractLevelModel, DefenseEngine, SettingsStore
from photon_game_runtime.engine import orc_schedule
from photon_game_runtime import wave_timeline, starter_defenses
from photon_game_runtime.atom_buff import validated as _validated_occupancy, unavailable as _unavailable_occupancy
from photon_game_runtime.settings import validate_settings, PRESETS
from progress_link import ProgressLink
from journey import Journey
from presets import Presets

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")
SETTINGS_PATH = os.path.join(DATA_DIR, "settings.json")
LOG_PATH = os.path.join(DATA_DIR, "runs.jsonl")
CONTRACT = "photon.game"
VERSION = 2
LEVEL_CONTRACT = "photon.level.runtime"
LEVEL_VERSION = 2
LEVEL_VERSIONS = (1, 2)
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
_command_lock = threading.RLock()
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


def _check_enemy_renderer(settings):
    if settings.get('breaker_attack_mode') != 'ranged':
        return
    renderer = _module('laser-tag-y')
    reader = getattr(renderer, 'renderer_contract', None)
    contract = reader() if callable(reader) else None
    if (not isinstance(contract, dict) or contract.get('contract') != 'photon.renderer'
            or type(contract.get('version')) is not int or contract['version'] != 1
            or type(contract.get('enemy_combat_version')) is not int or contract['enemy_combat_version'] != 1):
        raise GameError('Breaker archers require the matching Laser Tag Y renderer; update and refresh displays before starting')


_journey = None
_presets = None


def _result_committed(attempt):
    if _journey:
        _journey.result(attempt)


def _journey_tick():
    # Progress invokes this outside its lock. Never wait behind an operator
    # command that may itself be waiting for a result to finish saving.
    if _clean_reset_pending(): return
    if _journey and _command_lock.acquire(blocking=False):
        try:
            if _clean_reset_pending(): return
            if _journey.snapshot().get('reset_stop_error'):
                if not _settle_reset_stops():return
            _journey.tick()
            _auto_start_next()
        finally:
            _command_lock.release()


_progress = ProgressLink(_module, lambda: _engine, _live.bump, Path(DATA_DIR) / 'pending-result.json', _result_committed, _journey_tick)


@trace.traced('game.journey_snapshot')
def journey_snapshot():
    value=_journey.snapshot() if _journey else {'contract':'photon.game.journey','version':1,'status':'unavailable','error':'not initialized'}
    if _module('auto-pickup-game'):
        try:
            owner=_module('auto-pickup-game')
            cal=owner.calibration_session_snapshot() if owner else {}
            if cal.get('contract')!='hhh.cal2.session' or type(cal.get('version')) is not int or cal['version']!=1 or cal.get('status')!='ready': raise ValueError('calibration display unavailable')
            if value.get('phase')=='calibration':
                value['calibration_display']=cal.get('display')
            value.update(motion_blocked=cal.get('motion_blocked',False),motion_error=cal.get('motion_error'))
        except Exception as exc:
            value['calibration_display']={'contract':'hhh.playfield.display','version':1,'status':'unavailable','error':str(exc)}
            value.update(motion_blocked=True,motion_error=str(exc))
    if value.get('reset_stop_error'):
        value.update(motion_blocked=True,motion_error=value['reset_stop_error'])
    if _saved_game_switch_error:
        value.update(motion_blocked=True, motion_error=_saved_game_switch_error)
    if _clean_reset_pending():
        value.update(motion_blocked=True, motion_error='Clean reset pending. Game Master must finish or retry it.')
    return value


def motion_policy(side):
    """Player and calibration scopes use the single guarded motion path."""
    state = journey_snapshot()
    with trace.locked(_lock, 'game.state_lock'):
        engine = _engine
    if engine is None:
        return {'contract':'photon.game.motion','version':1,'status':'unavailable',
                'blocked':True,'error':'Game controls are unavailable; wait for the level to load'}
    with trace.locked(engine.lock, 'game.engine_lock'):
        test, phase = engine.virtual_test_control, engine.phase
    active = state.get('active_side')
    if state.get('motion_blocked'):
        return {'contract':'photon.game.motion','version':1,'status':'ready','scope':'waiting','tier':0,
                'blocked':True,'error':state.get('motion_error') or 'Waiting for arm stop confirmation'}
    if active:
        owner = _module('auto-pickup-game')
        cal = owner.calibration_session_snapshot() if owner else {}
        if cal.get('contract')!='hhh.cal2.session' or type(cal.get('version')) is not int or cal['version']!=1 or cal.get('status')!='ready':
            return {'contract':'photon.game.motion','version':1,'status':'unavailable','error':'calibration owner unavailable'}
        session = cal.get('sessions',{}).get(state.get('session_id'),{})
        live = cal.get('active_side')==side and cal.get('active_id')==state.get('session_id') and session.get('epoch')==cal.get('epoch') and not session.get('paused') and session.get('access_until',0)>time.time()
        tier = 3 if session.get('stage') in ('tutorial','complete') else 2
        error = ('The other player is completing calibration' if side!=active else
                 'Calibration connection expired; reconnect to continue') if not live else None
        return {'contract':'photon.game.motion','version':1,'status':'ready','scope':'tutorial' if side==active else 'waiting',
                'tier':tier if side==active else 0,'blocked':not live,'error':error,'session_id':state.get('session_id')}
    error = None
    if state.get('phase')=='calibration':error='Waiting for the calibration turn'
    elif state.get('phase') in ('results','ready'):error=(state.get('auto_start') or {}).get('error') or 'Waiting for both players to continue and the next level to start'
    return {'contract':'photon.game.motion','version':1,'status':'ready','scope':'player','tier':None,
            'blocked':error is not None,'error':error}


def mobile_journey_command(side,value):
    with _command_lock:
        _require_player_access()
        result=_mobile_journey_command(side,value)
        if value.get('action') in ('ready','complete','finish'):
            _auto_start_next()
            result=_journey.snapshot()
            error=(result.get('auto_start') or {}).get('error')
            if error and value.get('action')=='ready':raise ValueError(error)
        return result


def _next_start_context(run_id,roster):
    saved=roster['saved_games']['active']
    return {'run_id':run_id,'event_id':roster['events']['active_id'],'game_id':saved['id'],'level':saved['level'],
            'players':{side:{'id':p['id'],'tier':p['selected_control'],'levels':_copy(p['levels'])}
                       for side,p in roster['roster'].items()}}


def _auto_start_next():
    """Both players authorized this continuation; all ordinary Start gates apply."""
    state=_journey.snapshot() if _journey else {}
    pending=state.get('auto_start')
    if not pending or pending.get('error') or state['phase']!='ready':return
    try:
        roster=_progress.roster()
        if _next_start_context(pending['run_id'],roster)!=pending:
            raise ValueError('Players, event or equipment changed; both players must press Ready again')
        _apply_command({'action':'start','event_id':pending['event_id']})
    except Exception as exc:
        # Do not repeatedly attempt a physical transition from the maintenance
        # loop. Both phones show the failure and either can explicitly retry.
        _journey.start_failed(f'Next level could not start: {exc}')


def _continue_players(side,value,roster):
    state=_journey.snapshot();run_id=value.get('run_id')
    choice=value.get('choice','continue')
    if choice not in ('continue','new','replay_level','replay_game'):raise ValueError('Choose a result action')
    if state.get('reset_operation')=='result-new:'+str(run_id):return state
    if state['phase']=='playing' and run_id and run_id==state.get('continued_from'):
        return state  # A delayed duplicate cannot start or reset a second game.
    if not state.get('run_id'):
        if run_id or choice!='continue':raise ValueError('Level result changed; refresh before pressing Continue / Ready')
        return _journey.ready(side)  # The first game still belongs to Game Master.
    if not run_id or run_id!=state.get('run_id'):
        raise ValueError('Level result changed; refresh before pressing Continue / Ready')
    pending=state.get('auto_start')
    if pending and state['phase']=='calibration':return state
    attempt=_progress._check(_module('photon-progress').attempt_snapshot(run_id))['attempt']
    context=_next_start_context(run_id,roster)
    if pending and {k:v for k,v in pending.items() if k!='error'}==context:
        _journey.queue_start(context)
        return _journey.snapshot()
    if attempt['event_id']!=context['event_id'] or attempt['game_id']!=context['game_id']:
        raise ValueError('This result belongs to another saved pair or event; refresh before continuing')
    # Restart recovery saves interrupted/aborted attempts without advancing the
    # level. They are settled results too, so both players can retry that level.
    if attempt['outcome'] not in ('won','overrun','operator_ended','interrupted','aborted'):
        raise ValueError('Wait for this pair’s level result to finish saving')
    if choice=='continue' and attempt['outcome']=='won' and attempt['metadata'].get('contract_control_tier')==4:
        raise ValueError('You Win! Game Over. Choose New game, Replay last level or Replay whole game.')
    state=_journey.ready(side,choice)
    teams={side:{**p,'tier':p['selected_control']} for side,p in roster['roster'].items()}
    if not Journey.readiness(state,teams)['all_ready']:return state
    if choice=='new':
        _reset_event_game({'event_id':context['event_id'],'operation_id':'result-new:'+run_id,
                           'reset_generation':state.get('reset_operation'),'run_id':_run_id,
                           'game_id':context['game_id']})
        return _journey.snapshot()
    if choice in ('replay_level','replay_game'):
        saved_game_command(side,{'action':choice,'event_id':context['event_id'],'run_id':run_id,
                                 'operation_id':'result-'+choice+':'+run_id})
        _journey.replay_result(run_id)
        _journey.queue_start(_next_start_context(run_id,_progress.roster()))
        return _journey.snapshot()
    if state['phase']=='results' or _engine.phase!='setup':
        _apply_command({'action':'next_match','event_id':context['event_id'],'run_id':run_id})
    _journey.queue_start(context)
    return _journey.snapshot()


def _mobile_journey_command(side,value):
    if side not in ('green','purple') or _journey is None:
        raise ValueError('game journey unavailable')
    if value.get('action')=='complete':
        return _journey.complete_calibration(side)
    if value.get('action')=='finish':
        board = _module('photon-board')
        if not board:
            raise ValueError('Board evidence unavailable')
        observation=board.runtime_observation()
        if observation.get('contract')!='photon.board.runtime' or type(observation.get('version')) is not int or observation['version']!=1 or observation.get('status')!='ready' or not -1<=time.time()-observation.get('frame_at',0)<=1.5:
            raise ValueError('fresh Board placement evidence required')
        return _journey.finish(side,observation)
    if value.get('action')=='ready':
        roster=_progress.roster()
        if not value.get('event_id') or value['event_id']!=roster['events']['active_id']:
            raise ValueError('Event changed; refresh before getting ready')
        return _continue_players(side,value,roster)
    if value.get('action')=='replay':
        if _engine and _engine.phase=='running':
            raise ValueError('finish the active game before replaying calibration')
        if _engine:
            _engine.set_virtual_play(False)
        return (_journey.resume_calibration() if _journey.snapshot().get('deferred_calibration')
                else _journey.manual({'side':side}))
    return _journey.lesson_command(side,value)


def _set_input(name, *, status, error=None, **detail):
    global _revision
    value = {"status": status, "error": error, **detail}
    with trace.locked(_lock, 'game.state_lock'):
        if _inputs[name] != value:
            _inputs[name] = value
            _revision += 1


@trace.traced('game.level_bundle')
def _level_bundle():
    module = _module("photon-level")
    if module is None or not callable(getattr(module, "runtime_bundle", None)):
        return None, "Photon Level is unavailable or disabled"
    try:
        # The versioned fast read keeps health/art current without copying
        # the entire immutable runtime for every display frame of state.
        status_reader = getattr(module, "runtime_status", None)
        with trace.locked(_lock, 'game.state_lock'):
            engine = _engine
        if engine is not None and callable(status_reader):
            status = trace.call('level.runtime_status', status_reader)
            if (
                not isinstance(status, dict)
                or status.get("contract") != LEVEL_CONTRACT
                or type(status.get("version")) is not int
                or status["version"] not in LEVEL_VERSIONS
                or type(status.get("revision")) is not int
                or status["revision"] < 1
                or status.get("status") not in ("ready", "unavailable")
            ):
                return None, "Photon Level runtime status is invalid"
            if status["status"] != "ready":
                return None, str(status.get("error") or "Photon Level is not ready")
            with trace.locked(engine.lock, 'game.engine_lock'):
                unchanged = (engine.level.layout_revision == status["revision"]
                             and engine.level.runtime_version == status['version'])
                frozen = engine.phase != "setup"
            if unchanged or frozen:
                return status, None
        value = trace.call('level.runtime_bundle', module.runtime_bundle)
    except Exception as exc:
        return None, f"Photon Level failed: {exc}"
    if (
        not isinstance(value, dict)
        or value.get("contract") != LEVEL_CONTRACT
        or type(value.get("version")) is not int or value.get("version") not in LEVEL_VERSIONS
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
    if value['runtime'].get('runtime_version', 1) != value['version']:
        return None, 'Photon Level runtime version does not match its envelope'
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
            **({'companion': _copy(raw['companion'])} if 'companion' in raw else {}),
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
        "atom_homes": _copy(runtime.get("atom_homes", [])),
        "core": _copy(raw_core),
        # Additive Level v1 fields stay optional so an older compatible Level
        # can still drive the game while a presentation uses its fallback map.
        "scene": _copy(visual_scene) if isinstance(visual_scene, dict) else None,
    }


@trace.traced('game.set_presentation')
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
    with trace.locked(_lock, 'game.state_lock'):
        _presentation = output
        _set_input("presentation", status=output["status"], error=output.get("error"), revision=output["revision"])


@trace.traced('game.install_level')
def _install_level(bundle):
    global _engine, _level_projection, _revision, _history_sequence
    revision = bundle["revision"]
    with trace.locked(_level_install_lock, 'game.level_install_lock'):
        with trace.locked(_lock, 'game.state_lock'):
            engine = _engine
        if (engine is not None and engine.level.layout_revision == revision
                and engine.level.runtime_version == bundle['version']):
            _set_presentation(bundle.get("presentation"))
            _set_input("level", status="ready", revision=revision)
            return True
        if engine is not None:
            with trace.locked(engine.lock, 'game.engine_lock'):
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
            engine.set_movement_source(_movement_observation)
            with trace.locked(_lock, 'game.state_lock'):
                _engine = engine
                _history_sequence = 0
                start_engine = _hub_ctx is not None
        else:
            engine.reload_level(next_level, bundle["waves"])
        with trace.locked(_lock, 'game.state_lock'):
            _level_projection = projection
            _set_input("level", status="ready", revision=revision)
            _revision += 1
        engine.configure_piece_codes(_settings.snapshot())
        if start_engine:
            engine.start_background()
    return True


@trace.traced('game.sync_level')
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


def _validated_stacking(value, sampled_at, source_epoch):
    """Validate the optional camera-only cover contract independently of arms."""
    if value is None:
        return None
    if (
        not isinstance(value, dict)
        or value.get("contract") != "photon.board.stacking"
        or type(value.get("version")) is not int or value["version"] != 1
        or value.get("status") != "ready"
        or value.get("sampled_at") != sampled_at
        or value.get("source_epoch") != source_epoch
        or not isinstance(value.get("relations"), list)
        or len(value["relations"]) > 512
    ):
        raise ValueError("Invalid stacking contract")
    clean, lowers, uppers, identities = [], set(), set(), set()
    for relation in value["relations"]:
        if not isinstance(relation, dict):
            raise ValueError("Invalid cover")
        lower, upper = relation.get("lower_id"), relation.get("upper_id")
        identity, stable = relation.get("relation_id"), relation.get("stable")
        numbers = [relation.get(key) for key in (
            "distance", "lower_seen_at", "observed_since", "stable_at",
        )]
        if (
            type(lower) is not int or not 100 <= lower <= 999
            or type(upper) is not int or not 100 <= upper <= 999 or upper == lower
            or lower in lowers or upper in uppers
            or not isinstance(identity, str) or not 1 <= len(identity) <= 240
            or identity in identities or type(stable) is not bool
            or any(type(number) not in (int, float) or not math.isfinite(number) for number in numbers)
        ):
            raise ValueError("Invalid cover identity or evidence")
        distance, seen_at, since, stable_at = numbers
        if (not 0 <= distance <= 1 or not seen_at <= since < stable_at
            or since > sampled_at or stable and stable_at > sampled_at + 0.01):
            raise ValueError("Invalid cover timestamps or distance")
        lowers.add(lower)
        uppers.add(upper)
        identities.add(identity)
        clean.append({key: relation[key] for key in (
            "relation_id", "lower_id", "upper_id", "distance", "lower_seen_at",
            "observed_since", "stable_at", "stable",
        )})
    return {**value, "relations": clean}


@trace.traced('game.board_observation')
def _board_observation(diagnostics=None):
    module = _module("photon-board")
    if module is None or not callable(getattr(module, "runtime_observation", None)):
        return None, "Photon Board is unavailable or disabled"
    with trace.locked(_lock, 'game.state_lock'):
        layout = ({key: _level_projection.get(key) for key in
                   ('id', 'layout_revision', 'width', 'height', 'sockets', 'core')}
                  if _level_projection else None)
        run_id = _run_id
    scope, fixed_ids = cue_layout({'level': layout, 'run_id': run_id}) if layout else (None, [])
    if diagnostics is not None and scope is not None:
        diagnostics['_layout_scope'] = scope
    try:
        if scope is not None:
            reader = getattr(module, 'game_observation', None)
            if not callable(reader):
                return None, 'Photon Board contract mismatch: game map API unavailable'
            value = reader(scope=scope, fixed_ids=fixed_ids)
        else:
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
    if scope is not None and (value.get('layout_scope') != scope or value.get('fixed_ids') != sorted(fixed_ids)):
        return None, 'Photon Board game map scope mismatch; waiting for a matching sample'
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
        stacking = _validated_stacking(placement.get("stacking"), sampled_at, source_epoch)
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
        "stacking": stacking,
    }, None


def _physical_observation():
    upstream = {}
    observation, error = _board_observation(upstream)
    scope = upstream.pop('_layout_scope', None)
    occupancy_supported = False
    try:
        module = _module('photon-board')
        reader = getattr(module, 'occupancy_snapshot', None)
        occupancy_supported = callable(reader)
        occupancy = (_validated_occupancy(reader(scope=scope) if scope is not None else reader())
                     if callable(reader) else _unavailable_occupancy('Board occupancy unavailable'))
    except Exception as exc:
        occupancy = _unavailable_occupancy(f'Board occupancy failed: {exc}')
    if occupancy_supported:
        upstream['occupancy'] = {'status': occupancy['status'], 'error': occupancy.get('error')}
    if error:
        _set_input("board", status="unavailable", error=error, upstream=upstream)
        return {**_unavailable_placement(error), 'occupancy': occupancy}
    _set_input(
        "board", status="ready", revision=int(observation["board_revision"]),
        source=str(observation.get("source") or "unknown"),
        placement_revision=int(observation["revision"]),
        upstream=upstream,
    )
    return {**_copy(observation), 'occupancy': occupancy}


@trace.traced('game.append_history')
def _append_history(kind, detail=None):
    with trace.locked(_history_lock, 'game.history_lock'):
        with trace.locked(_lock, 'game.state_lock'):
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
                trace.call('logging.history_fsync', os.fsync, handle.fileno())
            with trace.locked(_lock, 'game.state_lock'):
                _storage["history"] = {"status": "ready", "error": None}
        except OSError as exc:
            with trace.locked(_lock, 'game.state_lock'):
                _storage["history"] = {"status": "unavailable", "error": str(exc)}


@trace.traced('game.persist_engine_events')
def _persist_engine_events():
    global _history_sequence
    with trace.locked(_lock, 'game.state_lock'):
        engine = _engine
    if engine is None:
        return
    with trace.locked(engine.lock, 'game.engine_lock'):
        events = _copy(engine.events)
    with trace.locked(_history_lock, 'game.history_lock'):
        for event in events:
            sequence = int(event.get("sequence", 0))
            if sequence <= _history_sequence:
                continue
            _append_history("game_event", event)
            _history_sequence = sequence


def _engine_changed():
    global _revision
    with trace.locked(_lock, 'game.state_lock'):
        _revision += 1
    _persist_engine_events()
    _live.bump()


@trace.traced('game.configuration_snapshot')
def _configuration_snapshot(engine):
    output = _settings.response()
    output.pop("ok", None)
    output.update({
        "contract": "photon.game.settings",
        "version": 1,
        "authored_wave_enemy_counts": [],
    })
    with trace.locked(_lock, 'game.state_lock'):
        _storage["settings"] = {
            "status": output["status"], "error": output.get("error"),
        }
    if engine is not None:
        with trace.locked(engine.lock, 'game.engine_lock'):
            output["authored_wave_enemy_counts"] = [
                sum(max(0, int(group.get("count", 0))) for group in wave.get("groups", []))
                for wave in engine.wave_source
            ]
            output['orc_previews'] = [orc_schedule(output['settings'], engine.wave_source, tier) for tier in range(1, 5)]
    return output


@trace.traced('game.public_snapshot')
def _public_snapshot(*, compact_enemies=False):
    _sync_level()
    with trace.locked(_lock, 'game.state_lock'):
        engine = _engine
    configuration = _configuration_snapshot(engine)
    with trace.locked(_lock, 'game.state_lock'):
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
            "progress": trace.call('game.progress', _progress.snapshot),
            "level_presets": _presets.snapshot() if _presets else {'status':'unavailable'},
            "server_time": time.time(), "journey":journey_snapshot(),
        }
    simulation = engine.snapshot(compact_enemies=compact_enemies)
    progress = trace.call('game.progress', _progress.snapshot)
    next_match = trace.call('game.post_match_preview', post_match.preview, _presets,engine,(level or {}).get('name','photon-level'),_settings.snapshot())
    next_loadouts = trace.call('game.post_match_loadouts', post_match.loadouts, _module,simulation['phase'])
    journey = journey_snapshot()
    journey['readiness'] = (Journey.readiness(journey,next_loadouts['teams']) if next_loadouts.get('status')=='ready'
                            else {'status':'unavailable','error':next_loadouts.get('error','Player status unavailable')})
    if simulation['phase'] == 'setup':
        with trace.locked(engine.lock, 'game.engine_lock'):
            saved = (next_loadouts.get('saved_games') or {}).get('active')
            simulation.update(starter_defenses.preview(engine, saved, next_loadouts.get('teams')))
        tier = simulation['virtual_test_control'] or max((p['tier'] for p in (next_loadouts or {}).get('teams',{}).values()), default=1)
        selected = next((p for p in next_match.get('tiers',[]) if p['tier'] == tier), None)
        if selected:
            simulation['wave_timeline'] = wave_timeline.preview(selected['timings'])
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
        "progress": trace.call('game.progress', _progress.snapshot),
        "journey": journey,
        "level_presets": _presets.snapshot() if _presets else None,
        **simulation,
        "next_match":next_match,
        "result_save":post_match.save_state(progress,run_id,simulation["phase"]),
        "next_loadouts":next_loadouts,
    }


def game_snapshot():
    """The sole read-only Photon Game output consumed by presentations."""
    return _public_snapshot()


def _mobile_saved_control(side='green'):
    """Read the required tier; missing player state grants no ordinary movement."""
    module = _module('photon-progress')
    if not module or not callable(getattr(module, 'progress_snapshot', None)):
        return 0
    try:
        profile = module.progress_snapshot({'side': side})
        if not isinstance(profile, dict) or profile.get('status') != 'ready' or profile.get('contract') != 'photon.progress' or type(profile.get('version')) is not int or profile['version'] != 2:
            return 0
        player = profile.get('player') or {}
        level = player.get('current_control_tier', 0)
        if player.get('progression_stage') != 'playing':
            return 0
        return level if type(level) is int and 1 <= level <= 4 else 0
    except Exception:
        logging.getLogger(__name__).exception('%s mobile progression unavailable', side)
        return 0


def mobile_command(data):
    """Virtual robot gameplay was removed; physical controls use the guarded relay."""
    raise ValueError('Virtual gameplay is unavailable; use the physical arm controls')


def mobile_turret_aim(data):
    """Photon Game v2 player aim intent; independent of virtual robot sessions."""
    if not isinstance(data, dict) or data.get('side', 'green') not in ('green', 'purple'):
        raise ValueError('A valid mobile team is required.')
    side = data.get('side', 'green')
    with _command_lock:
        engine, ready = _require_engine()
        if not ready:
            raise ValueError('Level unavailable.')
        with trace.locked(engine.lock, 'game.engine_lock'):
            if engine.paused or engine.phase not in ('setup', 'running'):
                raise ValueError('Turret adjustment is unavailable while the game is paused or ended.')
            if data.get('run_id') != _run_id:
                raise ValueError('Game changed. Select the turret again.')
            sid = data.get('socket_id')
            tower = engine.combat_tower(sid) if isinstance(sid, str) else None
            if not tower or tower.get('owner') != side:
                raise ValueError('Select a placed '+side.title()+' turret.')
            if (not isinstance(data.get('aim_instance'), str) or data['aim_instance'] != tower['aim_instance']
                    or type(data.get('atom_tag_id')) is not int or data['atom_tag_id'] != tower['atom_tag_id']
                    or data.get('activation_started_at') != tower['activation_started_at']
                    or type(data.get('aim_revision')) is not int or data['aim_revision'] != tower['aim_revision']):
                raise ValueError('Turret changed. Select it again.')
            if any(type(data.get(k)) not in (int, float) or not math.isfinite(data[k])
                   for k in ('angle_degrees', 'spread')):
                raise ValueError('Finite direction and range are required.')
            result = engine.set_tower_aim(data['atom_tag_id'], data['angle_degrees'],
                                          data['spread'], socket_id=sid)
    _live.bump()
    return result


def _event_snapshot():
    return _public_snapshot(compact_enemies=True)


def game_events(*, incremental=False):
    """The sole Photon Game SSE output, carrying compact game snapshots."""
    return _live.stream(
        _event_snapshot, interval=0.25, shared=True,
        static_fields=(
            "level", "presentation", "configuration", "settings", "loadout",
            "force_field_blockers", "row_barrier_geometry",
        ) if incremental else (),
    )


def _require_engine():
    _sync_level()
    with trace.locked(_lock, 'game.state_lock'):
        engine = _engine
        level_ready = _inputs["level"].get("status") == "ready"
    if engine is None:
        raise GameError("Photon Level is unavailable")
    if engine.phase == "setup":
        engine.configure_piece_codes(_settings.snapshot())
    return engine, level_ready


def apply_command(data):
    with _command_lock:
        _require_player_access()
        return _apply_command(data)


def _clean_reset_pending():
    access = getattr(_hub_ctx, 'player_sessions', None)
    return bool(access and access.blocked)


def _require_player_access():
    if _clean_reset_pending():
        raise GameError('Clean reset pending. Finish or retry it from the player panel.')


def player_connections():
    """Hub player-management v1 projection; identities belong to the Hub."""
    access = _hub_ctx.player_sessions
    names, controlling, error = {}, [], None
    try:
        roster = _progress.roster()['roster']
        names = {side: player.get('name') for side, player in roster.items()}
        owner = _module('dobot-mg400-relay')
        state = owner.player_control_sessions()
        if (state.get('contract') != 'hhh.relay.player-sessions'
                or type(state.get('version')) is not int or state['version'] != 1
                or state.get('status') != 'ready'):
            raise ValueError('Player control ownership unavailable')
        controlling = list(state['sessions'].values())
    except Exception as exc:
        error = str(exc)
    return {**access.snapshot(names, controlling), 'error': error}


def clean_reset_players(data):
    """Revoke access before resetting Game; failed resets remain closed on disk.

    The operation ID belongs to the Hub recovery record. Repeating a completed
    operation cannot reset a later game or disconnect players who joined later.
    """
    access = _hub_ctx.player_sessions
    operation = data['operation_id']
    with access.transition:
        if not access.begin_reset(operation, None):
            return {'ok': True, 'operation_id': operation, 'already_completed': True}
        _hub_ctx.invalidate_player_links()
        try:
            # Never hold the Game command lock while waiting for a player HTTP
            # request that may itself be waiting to enter the Game owner.
            access.drain()
            with _command_lock, _journey.operation_lock:
                _require_engine()
                relay = _module('dobot-mg400-relay')
                ownership = relay.player_control_sessions()
                if (ownership.get('contract') != 'hhh.relay.player-sessions'
                        or type(ownership.get('version')) is not int or ownership['version'] != 1
                        or ownership.get('status') != 'ready'
                        or not isinstance(ownership.get('leased_sides'), list)
                        or any(side not in ('green', 'purple') for side in ownership['leased_sides'])):
                    raise GameError('Player control ownership unavailable')
                scope = sorted(set(_reset_stop_scope()) | set(ownership['leased_sides']))
                _journey.reset_stop('Clean reset requested; waiting for arm stop confirmation', sides=scope)
                result = relay.revoke_player_controls()
                if (result.get('contract') != 'hhh.relay.player-sessions'
                        or type(result.get('version')) is not int or result['version'] != 1
                        or result.get('status') != 'ready' or result.get('released') is not True):
                    raise GameError('Could not release player controls')
                roster = _progress.roster()
                _reset_event_game({'event_id': roster['events']['active_id'],
                    'game_id': roster['saved_games']['active_id'], 'run_id': _run_id,
                    'reset_generation': _journey.snapshot().get('reset_operation'),
                    'operation_id': operation}, allow_no_event=True)
                if _journey.snapshot().get('reset_stop_error') and not _settle_reset_stops():
                    raise GameError(_journey.snapshot()['reset_stop_error'])
                # QR encoding/availability is part of completion; a failed code
                # render must not reopen admission with missing or stale links.
                with access.lock:
                    _hub_ctx.refresh_player_links()
                    access.finish_reset(operation)
                _live.bump()
            return {'ok': True, 'operation_id': operation}
        except Exception as exc:
            _hub_ctx.invalidate_player_links()
            access.reset_failed(str(exc))
            _live.bump()
            raise


_saved_game_switch_error = None


def _arms_before_game_switch():
    owner = _module('dobot-mg400-relay')
    if owner is None or not callable(getattr(owner, 'arms_snapshot', None)):
        raise ValueError('Arm connection status unavailable before changing games')
    state = owner.arms_snapshot()
    if (state.get('contract') != 'hhh.relay.arms' or type(state.get('version')) is not int
            or state['version'] != 1 or state.get('status') != 'ready'
            or type(state.get('observed_at')) not in (float, int)
            or not -.25 <= time.time()-state['observed_at'] <= 1.5):
        raise ValueError('Fresh arm connection status required before changing games')
    for side in ('green', 'purple'):
        arm = state.get('arms', {}).get(side, {})
        if type(arm.get('connected')) is not bool:
            raise ValueError('Both arm connection states are required')
    return owner,state


def _stop_for_saved_game(sides=None):
    owner,state=_arms_before_game_switch()
    for side in ('green','purple'):
        required=side in sides if sides is not None else state['arms'][side]['connected']
        if required:
            stopped = owner.stop_side(side)
            if (stopped.get('contract') != 'hhh.relay.stop' or type(stopped.get('version')) is not int
                    or stopped['version'] != 1 or stopped.get('status') != 'ready' or stopped.get('stopped') is not True):
                raise ValueError(f'Waiting for {side} to confirm the Reset stop' if sides is not None
                                 else f'Waiting for {side} to stop before changing games')


def _reset_stop_scope():
    """Track actual motion obligations, not every disconnected controller."""
    previous=_journey.snapshot()
    recorded=previous.get('reset_stop_sides')
    # [] is an explicit absence of stop obligations. Only old records with no
    # scope (None) require the conservative both-arms fallback.
    sides=set(recorded if recorded is not None else ('green','purple')) if previous.get('reset_stop_error') else set()
    if _engine.phase=='running':sides.update(('green','purple'))
    try:
        _,arms=_arms_before_game_switch()
        sides.update(s for s,arm in arms['arms'].items() if arm['connected'])
        if _module('auto-pickup-game'):
            cal=_journey.call('auto-pickup-game','calibration_session_snapshot','hhh.cal2.session',1)
            sides.update(cal.get('pending_stops',{}))
            if cal.get('active_side'):sides.add(cal['active_side'])
    except Exception:
        # Unknown hardware state cannot erase a possible outstanding stop.
        sides.update(('green','purple'))
    return sorted(sides)


def _settle_reset_stops():
    state=_journey.snapshot()
    # Older records did not identify the arms involved. Keep that obligation
    # conservative until an explicit, evidenced recovery or successful stop.
    sides=state.get('reset_stop_sides')
    pending=list(sides if sides is not None else ('green','purple'))
    error=None
    for side in list(pending):
        try:_stop_for_saved_game(sides=[side])
        except Exception as exc:error=error or str(exc)
        else:
            pending.remove(side)
            _journey.reset_stop(state['reset_stop_error'] if pending else None,sides=pending)
    _journey.reset_stop(error if pending else None,sides=pending)
    return not pending


def saved_game_command(side, value):
    """Authenticated player entrypoint, serialized with every game Start."""
    global _run_id, _saved_game_switch_error
    if side not in ('green', 'purple') or not isinstance(value, dict):
        raise ValueError('valid side and saved game command required')
    if not value.get('event_id'):raise ValueError('Event identity required; refresh this client')
    with _command_lock, _journey.operation_lock:
        _require_player_access()
        engine, _ = _require_engine()
        if engine.phase == 'running':
            raise ValueError('finish the current match before saving or loading a game')
        if _journey.snapshot()['phase'] == 'calibration':
            raise ValueError('finish calibration before saving or loading a game')
        _progress.flush()
        owner = _module('photon-progress')
        if owner is None or not callable(getattr(owner, 'saved_game_command', None)):
            raise ValueError('Saved games unavailable')
        _progress._check(owner.progress_snapshot())
        # Validate the complete request before clearing a ready roster or shop UI.
        _progress._check(owner.saved_game_preview(value))
        if value['action'] in ('new', 'load', 'replay_level', 'replay_game'):
            _saved_game_switch_error = 'Changing game. Waiting for arm stop confirmation.'
            _live.bump()
            try:
                if not engine.virtual_play: _stop_for_saved_game()
            except Exception as exc:
                _saved_game_switch_error = str(exc)
                raise
            _journey.cancel()
        try: result = _progress._check(owner.saved_game_command(value))
        except Exception:
            _saved_game_switch_error = None
            raise
        if value['action'] in ('new', 'load', 'replay_level', 'replay_game'):
            virtual = engine.virtual_play
            engine.reset()
            engine.set_virtual_play(virtual)
            engine.set_virtual_test_loadout(None, None)
            _run_id = None
            _progress.clear_finished()
            _journey.reset_lobby()
            if value['action']=='load':
                _journey.restore_game_calibration(_progress.roster())
            _saved_game_switch_error = None
        _live.bump()
        return result


def event_command(value):
    global _run_id,_saved_game_switch_error
    with _command_lock,_journey.operation_lock:
        _require_player_access()
        engine,_=_require_engine()
        if engine.phase=='running' or _journey.snapshot()['phase']=='calibration':raise ValueError('Finish the match and calibration before changing events')
        _progress.flush()
        owner=_module('photon-progress')
        _progress._check(owner.event_preview(value))
        _saved_game_switch_error='Changing event; waiting for arms to stop'
        _live.bump()
        try:
            if not engine.virtual_play:_stop_for_saved_game()
            _journey.cancel()
            result=_progress._check(owner.event_command(value))
            engine.reset();_run_id=None;_progress.clear_finished();_journey.reset_lobby()
        except Exception as exc:
            _saved_game_switch_error=str(exc);raise
        _saved_game_switch_error=None;_live.bump()
        return result


def _reset_event_game(data, *, allow_no_event=False):
    """Return the current event to player selection, preserving its stored progress."""
    global _run_id, _history_sequence, _revision, _saved_game_switch_error
    roster=_progress.roster()
    event_id=roster['events']['active_id']
    if (not event_id and not allow_no_event) or data.get('event_id')!=event_id:
        raise GameError('Select the active event and refresh before Reset')
    operation=data.get('operation_id')
    if not isinstance(operation,str) or not 1<=len(operation)<=160 or not all(c.isalnum() or c in '-_:.' for c in operation):
        raise GameError('Reset operation ID required; refresh Game Master')
    previous_reset=_journey.snapshot().get('reset_operation')
    if previous_reset==operation:return
    if ('reset_generation' not in data or data['reset_generation']!=previous_reset
            or 'run_id' not in data or data['run_id']!=_run_id or 'game_id' not in data
            or data['game_id']!=roster['saved_games']['active_id']):
        raise GameError('Game changed; refresh before Reset')
    owner=_module('photon-progress')
    if not callable(getattr(owner,'event_command',None)):
        raise GameError('Event player selection unavailable')
    _saved_game_switch_error='Resetting game; waiting for arms to stop'
    _live.bump()
    try:
        # Reset the UI even when hardware is offline; retain a durable motion
        # inhibit until the normal stop path can confirm both arms are safe.
        _journey.checkpoint_calibration(roster)
        _journey.reset_stop('Reset requested; waiting for arm stop confirmation',sides=_reset_stop_scope())
        _settle_reset_stops()
        if _engine.phase=='running':_engine.pause(True)
        # Abandon unfinished play without a forced turret purchase or level unlock.
        # A result that already finished keeps its actual outcome and settlement.
        _progress.flush(outcome='aborted')
        _journey.cancel(defer_stop=True)
        # Reselecting the same event atomically clears both selected players and
        # its active pair, through Progress's existing public owner contract.
        if event_id:
            _progress._check(owner.event_command({'action':'select','event_id':event_id,'operation_id':operation}))
        _engine.reset()
        _engine.set_virtual_test_loadout(None,None)
        _engine.configure_piece_codes(_settings.snapshot())
        _progress.clear_finished()
        _journey.reset_lobby(reset_operation=operation)
        with trace.locked(_lock,'game.state_lock'):
            _run_id=None;_history_sequence=0;_revision+=1
        _sync_level()
    except Exception as exc:
        _saved_game_switch_error=str(exc)
        _live.bump()
        raise
    _saved_game_switch_error=None
    _live.bump()


def _bind_starting_atoms(engine,roster,observation,requested):
    saved=roster['saved_games']['active']
    if not isinstance(requested,dict):
        raise ValueError('Invalid starting Atom selection')
    defaults={h['owner']:h['atom_tag_id'] for h in starter_defenses.platforms(engine,saved) if h['slot']==0}
    atoms=starting_atoms(engine,saved,observation,{**defaults,**engine.setup_starting_atoms,**requested})
    result=_progress._check(_module('photon-progress').bind_game_atoms({
        'event_id':roster['events']['active_id'],'game_id':saved['id'],'atoms':atoms}))
    return result['game']


def _apply_command(data):
    """Apply one validated operator input and return the authoritative snapshot."""
    global _run_id, _history_sequence, _revision
    if not isinstance(data, dict):
        raise GameError("command must be an object")
    action = str(data.get("action") or "")
    engine = None
    level_ready = False
    if action not in {"configure", "reset_settings", 'level_preset'}:
        engine, level_ready = _require_engine()
    try:
        if action in ('place', 'activate_core', 'loadout', 'aim', 'virtual_test_loadout','calibration_test') and engine is not None and engine.phase == 'running' and trace.call('game.progress', _progress.snapshot).get('reward_enabled'):
            raise GameError('end the scored attempt before operator placement or loadout intervention')
        if action == "starting_atom":
            if engine.phase != 'setup':
                raise GameError('Starting Atoms can only be selected before a match')
            side, tag = data.get('side'), data.get('atom_tag_id')
            if side not in ('green', 'purple') or tag is not None and (type(tag) is not int or engine.atom_owners.get(tag) != side):
                raise GameError('Choose a configured Atom for this team')
            saved = (_progress.roster().get('saved_games') or {}).get('active')
            if (saved or {}).get('atoms'):
                raise GameError('Starting Atoms are fixed in this save')
            with trace.locked(engine.lock, 'game.engine_lock'):
                engine.setup_starting_atoms[side] = tag
        elif action == "start":
            if engine.phase != 'setup':
                raise GameError('reset the finished game before starting another attempt')
            if not level_ready:
                raise GameError(_inputs["level"].get("error") or "Photon Level is unavailable")
            virtual_play = (
                bool(data["virtual_play"])
                if "virtual_play" in data
                else bool(engine.snapshot()["virtual_play"])
            )
            if not virtual_play:
                journey = journey_snapshot()
                if journey.get('motion_blocked'):
                    raise GameError(journey.get('motion_error') or 'Waiting for arm stop confirmation')
                _physical_observation()
                with trace.locked(_lock, 'game.state_lock'):
                    board_error = _inputs["board"].get("error")
                    board_ready = _inputs["board"].get("status") == "ready"
                if not board_ready:
                    raise GameError(board_error or "Photon Board is unavailable")
            if data.get('reward_enabled',True) is not True or virtual_play:
                raise GameError('Practice and virtual gameplay have been removed')
            reward_enabled=True
            roster=_progress.roster()
            if not data.get('event_id') or data['event_id']!=roster['events']['active_id']:
                raise GameError('Select an event and refresh before Start')
            if _journey:
                _journey.release_start()  # Recover this journey's unconsumed Start lock before rebinding.
            if not roster['saved_games']['active_id']:
                roster=_progress._check(_module('photon-progress').prepare_game())
            if _inputs['board'].get('upstream',{}).get('source')=='simulation':
                raise GameError('Event matches require physical camera input')
            saved_game=roster['saved_games']['active']
            engine.set_virtual_test_loadout(None,None)
            settings = _settings.snapshot()
            participants = [dict(player_id=p['id'], name=p['name'], side=side,
                                 control_tier=p['selected_control'], levels=p['levels'])
                            for side, p in sorted((roster or {}).get('roster', {}).items())]
            tier = saved_game['level']
            settings,preset = _presets.for_run((_level_projection or {}).get('name','photon-level'),tier,settings) if _presets else (settings,None)
            engine.configure_piece_codes(settings)
            saved_game=_bind_starting_atoms(engine,roster,_physical_observation(),data.get('starting_atoms',{}))
            _check_enemy_renderer(settings)
            previews = [orc_schedule(settings, engine.wave_source, i) for i in range(1, 5)]
            if reward_enabled and any(b['total'] <= a['total'] for a, b in zip(previews, previews[1:])):
                raise GameError('increase control-method percentages so each tier schedules more orcs')
            if reward_enabled and _presets:
                family=_presets.family_for_map((_level_projection or {}).get('name','photon-level'),_settings.snapshot())
                schedules=[orc_schedule(base,engine.wave_source,i+1) for i,(base,_) in enumerate(family)]
                if any((p or {}).get('family') not in ('progression','breaker-archer','ltz-horde-v1','event-progression-v1') for _,p in family) or any(b['total']<=a['total'] or b['wave_interval_s']>=a['wave_interval_s'] or b['release_rate_multiplier']<=a['release_rate_multiplier'] for a,b in zip(schedules,schedules[1:])):
                    raise GameError('scored presets require more orcs, shorter wave gaps and faster release at each tier')
            if reward_enabled and _settings.response()['preset'] == 'training':
                raise GameError('Select an event level preset')
            run_id = uuid.uuid4().hex
            reservation_id = None
            if roster is not None:
                metadata = {'campaign_id': 'ltz', 'level_id': (_level_projection or {}).get('name', 'photon-level'),
                            'level_revision': engine.level.layout_revision,
                            'settings_revision': _settings.revision,
                            'settings_hash': hashlib.sha256(json.dumps(settings, sort_keys=True).encode()).hexdigest(),
                            'settings': settings, 'contract_control_tier': tier,
                            'orc_schedule': previews[tier - 1], 'scoring_version': 1,
                            'enemy_combat_version': 1,
                            'reward_rules': rewards.rules(settings,engine.wave_source,previews[tier-1]),
                            'companion_policy': {**engine.snapshot()['companion_policy'], 'l4_turrets_per_socket': settings['l4_turrets_per_socket']}}
                metadata['level_preset']=preset
                metadata['starter_defense_policy']={'version':1,'per_player':2 if tier==4 else 1,'rebuildable':False,'topology':False}
                metadata['core_rule_version']=2  # Ring plus opposing-team stack; no kill gate.
                metadata['event_id']=roster['events']['active_id']
                try:
                    reservation_id = _journey.start(reward_enabled) if _journey else None
                    attempt = _progress.begin({'run_id': run_id, 'event_id':roster['events']['active_id'], 'reward_enabled': reward_enabled,
                                               'metadata': metadata, 'expected_roster': participants, 'reservation_id':reservation_id,
                                               'expected_game_id': (roster.get('saved_games') or {}).get('active_id')})
                except Exception:
                    if _journey and reservation_id:
                        _journey.release_start(reservation_id)
                    raise
                reward_enabled = attempt['reward_enabled']
            engine.set_virtual_play(virtual_play)
            with trace.locked(_lock, 'game.state_lock'):
                _run_id = run_id
                _history_sequence = 0
            try:
                engine.start(settings, progression={p['side']: p for p in participants},reward_enabled=True,preset=preset,countdown_s=5.0,event_game=saved_game)
                if _journey:
                    _journey.started(run_id if roster is not None else None, reward_enabled)
            except Exception:
                _progress.flush(outcome='aborted')
                raise
        elif action in ('end_match','unlock_next_level','next_match'):
            roster=_progress.roster()
            if not data.get('event_id') or data['event_id']!=roster['events']['active_id']:raise GameError('Event changed; refresh first')
            requested=data.get('run_id')
            if not isinstance(requested,str):raise GameError('Match ID required')
            owner=_module('photon-progress')
            a=_progress._check(owner.attempt_snapshot(requested))['attempt']
            if a['event_id']!=data['event_id'] or a['game_id']!=roster['saved_games']['active_id']:raise GameError('This match belongs to another saved pair or event')
            if action=='end_match':
                if a['outcome']=='operator_ended':return game_snapshot()
                if requested==_run_id and engine.phase=='operator_ended':
                    _progress.flush(outcome='operator_ended')
                    return game_snapshot()
                if requested!=_run_id or engine.phase!='running':raise GameError('The match has already ended')
                _stop_for_saved_game()
                engine.end_match()
                _progress.flush(outcome='operator_ended')
            elif action=='unlock_next_level':
                if engine.phase=='running':raise GameError('End the match before advancing')
                result=_progress._check(owner.advance_level(data))['attempt']
                with _progress.lock:_progress._set(result=result)
                if engine.phase=='setup':_journey.prepare_next()
                _live.bump()
            else:
                if a['outcome']=='won' and a['metadata'].get('contract_control_tier')==4:
                    raise GameError('You Win! Game Over. Choose a replay or New game from the results.')
                if engine.phase=='running':raise GameError('End the match first')
                if _journey.snapshot()['phase']=='calibration':raise GameError('Finish calibration first')
                _stop_for_saved_game()
                engine.reset();_run_id=None
                _journey.prepare_next()
        elif action == 'level_preset':
            return _presets.command({**data,'action':data.get('preset_action','save'),'settings':PRESETS['balanced'] if data.get('preset_action')=='defaults' else data.get('settings')})
        elif action == 'journey_cancel':
            if engine.phase=='running': raise GameError('end the active attempt before cancelling the transition')
            return _journey.cancel(defer_stop=True)
        elif action == 'show_game':
            return _journey.show_game()
        elif action == 'calibration_resume':
            if engine.phase == 'running':
                raise GameError('end the current game before resuming calibration')
            engine.set_virtual_play(False)
            return _journey.resume_calibration()
        elif action == 'calibration_apply':
            if engine.phase=='running':raise GameError('End the current game before applying a saved calibration')
            return _journey.apply_saved_calibration(data)
        elif action == 'calibration_setup':
            if engine.phase == 'running':
                raise GameError('end the current match before calibration setup')
            engine.set_virtual_play(False)
            return _journey.manual(data)
        elif action == "pause":
            if engine.snapshot()["phase"] != "running":
                raise GameError("game is not running")
            engine.pause(True)
        elif action == "resume":
            if engine.snapshot()["phase"] != "running":
                raise GameError("game is not running")
            engine.pause(False)
        elif action == "reset":
            _reset_event_game(data)
        elif action in ('virtual_test_loadout','set_virtual','test_end_match','test_next_level','next_level','calibration_test','place','activate_core','loadout'):
            raise GameError('This legacy practice command has been removed; refresh the client')
        elif action in ('operator_atom', 'operator_turret', 'operator_core'):
            if action in ('operator_atom', 'operator_core') and 'atom_tag_id' not in data:
                raise GameError('Atom selection is required; use null to clear it')
            saved=(_progress.roster().get('saved_games') or {}).get('active')
            if saved and saved.get('atoms'):engine.event_game=saved
            if _journey and _journey.snapshot().get('phase') == 'calibration':
                raise GameError('Finish calibration before changing turret controls')
            if not engine.virtual_play:
                # Refresh cached Board evidence before validating manual priority.
                engine.ingest_physical(_physical_observation())
            engine.operator_turret_command(action, data.get('socket_id'),
                data.get('atom_tag_id') if action in ('operator_atom', 'operator_core') else data.get('activation'))
        elif action == "aim":
            engine.set_tower_aim(
                int(data["atom_tag_id"]),
                float(data["angle_degrees"]),
                float(data["spread"]),
                socket_id=data.get("socket_id"),
            )
        elif action == "configure":
            candidate, validation = validate_settings(PRESETS.get(data.get('preset'), data.get('settings') or {}))
            if validation:
                raise GameError('settings validation failed', fields=validation)
            if _engine is not None:
                _engine.validate_piece_codes(candidate)
            response, errors = _settings.update(
                data.get("settings") or {}, data.get("preset")
            )
            if errors:
                raise GameError(
                    "settings validation failed",
                    fields=errors,
                )
            with trace.locked(_lock, 'game.state_lock'):
                _storage["settings"] = {"status": "ready", "error": None}
                _revision += 1
            if _engine is not None and _engine.phase == "setup":
                _engine.configure_piece_codes(response["settings"])
            _append_history("settings_saved", {
                "revision": response["revision"], "preset": response["preset"]
            })
        elif action == "reset_settings":
            response = _settings.reset_defaults()
            with trace.locked(_lock, 'game.state_lock'):
                _storage["settings"] = {"status": "ready", "error": None}
                _revision += 1
            if _engine is not None and _engine.phase == "setup":
                _engine.configure_piece_codes(response["settings"])
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
        with trace.locked(_lock, 'game.state_lock'):
            _storage["settings"] = {
                "status": "unavailable", "error": str(_settings.error or exc),
            }
            _revision += 1
        raise GameError(f"settings were not saved: {exc}") from exc
    if action not in {"configure", "reset_settings"}:
        _append_history("operator_command", {"action": action})
    return game_snapshot()


def _movement_observation():
    """Read-only inputs for the simulation-owned movement recorder."""
    outputs = {}
    for key, slug, function in (
        ('relay','dobot-mg400-relay','arms_snapshot'),
        ('calibration','auto-pickup-game','movement_calibration_snapshot'),
        ('camera','photon-board','camera_markers_snapshot'),
    ):
        owner = _module(slug)
        reader = getattr(owner, function, None)
        if not callable(reader):
            raise ValueError(f'{slug} movement evidence unavailable')
        outputs[key] = reader()
    return outputs


def hub_init(ctx):
    global _hub_ctx, _journey, _presets, _saved_game_switch_error
    _saved_game_switch_error = None
    _hub_ctx = ctx
    _journey = Journey(Path(LOG_PATH).parent/'journey.json',_module,_live.bump,lambda side:[code for code,owner in (_engine.atom_owners if _engine else {}).items() if owner==side])
    _presets = Presets(Path(LOG_PATH).parent/'level-presets.json')
    with trace.locked(_lock, 'game.state_lock'):
        _storage["settings"] = {
            "status": "unavailable" if _settings.error else "ready",
            "error": _settings.error,
        }
    _progress.start()
    _sync_level()
    register = getattr(ctx, 'register_player_management', None)
    if register:
        register({'contract': 'photon.player-management', 'version': 1,
                  'snapshot': player_connections, 'clean_reset': clean_reset_players})
    if _level_projection:
        _presets.ensure_map(_level_projection.get('name','photon-level'),_settings.snapshot())
    with trace.locked(_lock, 'game.state_lock'):
        engine = _engine
    if engine is not None:
        engine.set_wake(_engine_changed)
        engine.set_physical_source(_physical_observation)
        engine.set_movement_source(_movement_observation)
        engine.start_background()


def hub_stop():
    global _hub_ctx, _engine, _level_projection, _presentation, _journey, _presets
    with trace.locked(_lock, 'game.state_lock'):
        engine = _engine
    if engine is not None:
        engine.stop_background()
        engine.set_physical_source(None)
        try:
            _progress.flush(outcome='interrupted')
        except ValueError:
            # The durable outbox is replayed before recovery on the next start.
            pass
    _progress.stop()
    with trace.locked(_lock, 'game.state_lock'):
        _engine = None
        _level_projection = None
        _presentation = {}
        _hub_ctx = None
        _journey = None
        _presets = None
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
    if request.args.get('view') == 'configuration':
        return _orc_events()
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
    except Exception:
        current_app.logger.exception('Unexpected Photon Game command failure')
        return jsonify(ok=False, error='Server error while processing the command. Check the live game status and server log before retrying.'), 500


@bp.route('/api/saved-game', methods=['POST'])
def saved_game_api():
    side = request.args.get('side')
    roles = request.environ.get('hhh.roles') or set()
    if side not in ('green', 'purple') or not ({side, 'gamemaster'} & set(roles)):
        return jsonify(ok=False, error='Player side required'), 403
    origin = request.headers.get('Origin')
    if origin and origin.rstrip('/') != request.host_url.rstrip('/'):
        return jsonify(ok=False, error='Same-origin request required'), 403
    try: return jsonify(saved_game_command(side, request.get_json(silent=True)))
    except (ValueError, TypeError, KeyError) as exc: return jsonify(ok=False, error=str(exc)), 400


@bp.route('/api/economy', methods=['GET','POST'])
def economy_api():
    denied=_operator_only()
    if denied:return denied
    try:return jsonify(post_match.economy(_module,request.get_json(silent=True) if request.method=='POST' else None))
    except (ValueError,KeyError,TypeError) as exc:return jsonify({'ok':False,'error':str(exc)}),400

@bp.route('/api/event',methods=['GET','POST'])
def event_api():
    denied=_operator_only()
    if denied:return denied
    try:return jsonify(event_command(request.get_json(silent=True)) if request.method=='POST' else _progress.roster())
    except (ValueError,TypeError,KeyError) as exc:return jsonify(ok=False,error=str(exc)),400


@bp.route('/economy-settings.js')
def economy_settings_script():
    return send_from_directory(HERE,'economy-settings.js')


@bp.route('/api/orc-preview', methods=['POST'])
def orc_preview_api():
    # Read-only draft calculations; no settings are saved by this endpoint.
    if not (set(request.environ.get('hhh.roles') or ()) & {'green', 'purple', 'gamemaster'}):
        return jsonify({'ok': False, 'error': 'authentication required'}), 403
    incoming = request.get_json(silent=True) or {}
    if incoming.get('settings') is not None and 'gamemaster' not in (request.environ.get('hhh.roles') or ()):
        return jsonify({'ok': False, 'error': 'Gamemaster required for draft settings'}), 403
    settings, errors = validate_settings(incoming.get('settings') or _settings.snapshot())
    if errors:
        return jsonify({'ok': False, 'errors': errors, 'error': 'settings validation failed'}), 400
    engine, ready = _require_engine()
    with trace.locked(engine.lock, 'game.engine_lock'):
        previews = [orc_schedule(settings, engine.wave_source, tier) for tier in range(1, 5)]
    return jsonify({'ok': True, 'previews': previews})


def _orc_events():
    def snapshot():
        with trace.locked(_lock, 'game.state_lock'):
            engine,run_id = _engine,_run_id
        if engine is None:
            return {'contract':'photon.game.preview','version':1,'status':'unavailable','ok': False, 'error': 'Photon Level unavailable', 'previews': [],'virtual_test_control':None}
        progress = _progress.snapshot()
        with trace.locked(engine.lock, 'game.engine_lock'):
            terminal = None
            if engine.phase in ('won','overrun','operator_ended'):
                terminal = {'run_id':run_id,'phase':engine.phase,'contract_control_tier':engine.contract_control_tier,
                            'kills':engine.kills,'sim_time':engine.sim_time,'match_score':engine.rewards.snapshot(),
                            'kill_heatmap':engine.rewards.heatmap.snapshot(),
                            'robot_movement':engine.robot_movement.snapshot(engine.sim_time),
                            'result_save':post_match.save_state(progress,run_id,engine.phase)}
            return {'contract':'photon.game.preview','version':1,'status':'ready','ok': True,
                    'virtual_test_control':engine.virtual_test_control,'journey':_journey.snapshot() if _journey else None,
                    'terminal_result':terminal,
                    'previews': trace.call('game.post_match_preview', post_match.preview, _presets,engine,(_level_projection or {}).get('name','photon-level'),_settings.snapshot()).get('tiers',[])}
    return _live.stream(snapshot, interval=15)
