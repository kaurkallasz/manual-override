"""Validated module-local Photon Game settings and built-in presets."""

from __future__ import annotations

import json
import math
import os
import threading
from pathlib import Path
from typing import Any

from .engine import DEFAULT_SETTINGS, CONTROL_ORC_KEYS, PIECE_KEYS


RULES = {
    **{key: (int, 0, 999) for key in PIECE_KEYS},
    "wave_count": (int, 1, 12),
    "wave_interval_s": (float, 2.0, 600.0),
    "release_rate_multiplier": (float, 0.05, 20.0),
    "enemy_count_multiplier": (float, 0.1, 5.0),
    **{key: (float, 0.1, 5.0) for key in CONTROL_ORC_KEYS},
    "enemy_health_multiplier": (float, 0.1, 10.0),
    "enemy_speed_multiplier": (float, 0.1, 5.0),
    "enemy_core_damage_multiplier": (float, 0.0, 10.0),
    "enemy_tower_damage_multiplier": (float, 0.0, 10.0),
    "brute_first_wave": (int, 1, 12),
    "brute_size_multiplier": (float, 0.5, 10.0),
    "brute_health": (float, 1.0, 100000.0),
    "brute_damage_per_s": (float, 0.0, 10000.0),
    "force_field_damage_per_s": (float, 0.0, 500.0),
    "force_field_slow": (float, 0.05, 1.0),
    "force_field_hit_capacity": (int, 1, 10000),
    "ring_field_immunity_s": (float, 0.0, 600.0),
    "machine_gun_damage": (float, 0.0, 1000.0),
    "flamethrower_damage": (float, 0.0, 1000.0),
    "flamethrower_burn_damage_per_s": (float, 0.0, 500.0),
    "flamethrower_burn_duration_s": (float, 0.0, 30.0),
    "mortar_damage": (float, 0.0, 5000.0),
    "mortar_far_damage_multiplier": (float, 0.05, 1.0),
    "tesla_damage": (float, 0.0, 5000.0),
    "tesla_link_distance": (float, 1.0, 500.0),
    "tesla_max_links": (int, 1, 50),
    "defense_unit_health_percent": (float, 1.0, 100.0),
    "tower_link_start_multiplier": (float, 0.1, 5.0),
    "tower_link_step": (float, 0.0, 1.0),
    "core_hp": (float, 100.0, 100000.0),
    "max_active_enemies": (int, 1, 1000),
}

DEFAULTS = {key: DEFAULT_SETTINGS[key] for key in RULES}
# Accept the complete pre-Brute settings shape without losing saved tuning.
BRUTE_SETTING_KEYS = {
    "brute_first_wave", "brute_size_multiplier", "brute_health", "brute_damage_per_s",
}
PRESETS = {
    "balanced": dict(DEFAULTS),
    "training": {
        **DEFAULTS,
        "wave_count": 6,
        "wave_interval_s": 60.0,
        "release_rate_multiplier": 0.65,
        "enemy_count_multiplier": 0.5,
        "enemy_health_multiplier": 0.75,
        "enemy_speed_multiplier": 0.75,
        "enemy_core_damage_multiplier": 0.5,
        "enemy_tower_damage_multiplier": 0.5,
        "core_hp": 15000.0,
    },
    "onslaught": {
        **DEFAULTS,
        "wave_interval_s": 28.0,
        "release_rate_multiplier": 1.8,
        "enemy_count_multiplier": 1.35,
        "enemy_health_multiplier": 1.25,
        "enemy_speed_multiplier": 1.15,
        "enemy_core_damage_multiplier": 1.4,
        "enemy_tower_damage_multiplier": 1.4,
    },
}


def validate_settings(incoming: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    incoming = incoming if isinstance(incoming, dict) else {}
    clean: dict[str, Any] = {}
    errors: dict[str, str] = {}
    for key, (kind, lower, upper) in RULES.items():
        raw = incoming.get(key, DEFAULTS[key])
        try:
            if isinstance(raw, bool):
                raise ValueError
            if kind is int:
                numeric = float(raw)
                if not numeric.is_integer():
                    raise ValueError
                value: int | float = int(numeric)
            else:
                value = float(raw)
            if not math.isfinite(float(value)) or value < lower or value > upper:
                raise ValueError
        except (TypeError, ValueError, OverflowError):
            errors[key] = f"must be between {lower:g} and {upper:g}"
            continue
        clean[key] = value
    for previous, current in zip(CONTROL_ORC_KEYS, CONTROL_ORC_KEYS[1:]):
        if previous in clean and current in clean and clean[current] <= clean[previous]:
            errors[current] = 'must be greater than the preceding control method'
    codes = [clean.get(key) for key in PIECE_KEYS]
    if len(set(codes)) != len(codes):
        for key in PIECE_KEYS:
            errors[key] = "movable piece codes must be unique across both teams"
    return clean, errors


class SettingsStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.lock = threading.RLock()
        self.revision = 1
        self.draft = dict(DEFAULTS)
        self.preset = "balanced"
        self.error: str | None = None
        self._load()

    def _load(self) -> None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("settings document must be an object")
            if type(data.get("schema_version")) is not int or data["schema_version"] != 1:
                raise ValueError("expected settings schema version 1")
            incoming = data.get("settings")
            legacy = set(incoming) - set(PIECE_KEYS) if isinstance(incoming, dict) else set()
            if not isinstance(incoming, dict) or set(incoming) - set(RULES) or legacy not in (
                set(RULES) - set(PIECE_KEYS), set(RULES) - set(PIECE_KEYS) - BRUTE_SETTING_KEYS,
                set(RULES) - set(PIECE_KEYS) - set(CONTROL_ORC_KEYS),
                set(RULES) - set(PIECE_KEYS) - BRUTE_SETTING_KEYS - set(CONTROL_ORC_KEYS),
            ):
                raise ValueError("settings document must contain every known setting and no unknown settings")
            clean, errors = validate_settings(incoming)
            if errors:
                raise ValueError("persisted settings failed validation")
            revision = data.get("revision", 1)
            preset = data.get("preset", "custom")
            if type(revision) is not int or revision < 1 or not isinstance(preset, str):
                raise ValueError("settings revision or preset is invalid")
            self.draft = clean
            self.preset = (preset or "custom")[:40]
            self.revision = revision
            self.error = None
        except FileNotFoundError:
            self.error = None
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            self.error = f"Could not load settings; defaults remain active: {exc}"

    def _save_locked(self, draft, preset, revision) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(self.path.suffix + ".tmp")
        payload = {
            "schema_version": 1,
            "revision": revision,
            "preset": preset,
            "settings": draft,
        }
        try:
            with temp.open("w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, self.path)
        finally:
            try:
                temp.unlink()
            except FileNotFoundError:
                pass

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return dict(self.draft)

    def response(self) -> dict[str, Any]:
        with self.lock:
            return {
                "ok": True,
                "status": "unavailable" if self.error else "ready",
                "error": self.error,
                "revision": self.revision,
                "preset": self.preset,
                "settings": dict(self.draft),
                "defaults": dict(DEFAULTS),
                "presets": {key: dict(value) for key, value in PRESETS.items()},
                "limits": {
                    key: {"min": lower, "max": upper, "integer": kind is int}
                    for key, (kind, lower, upper) in RULES.items()
                },
            }

    def update(self, incoming: dict[str, Any], preset: str | None = None) -> tuple[dict[str, Any] | None, dict[str, str]]:
        candidate = PRESETS.get(preset) if preset in PRESETS else incoming
        clean, errors = validate_settings(candidate or {})
        if errors:
            return None, errors
        with self.lock:
            next_preset = str(preset or "custom")[:40]
            next_revision = self.revision + 1
            try:
                self._save_locked(clean, next_preset, next_revision)
            except OSError as exc:
                self.error = f"Could not save settings; previous values remain active: {exc}"
                raise
            self.draft = clean
            self.preset = next_preset
            self.revision = next_revision
            self.error = None
            return self.response(), {}

    def reset_defaults(self) -> dict[str, Any]:
        response, errors = self.update(dict(DEFAULTS), "balanced")
        if errors or response is None:
            raise RuntimeError("default settings failed validation")
        return response
