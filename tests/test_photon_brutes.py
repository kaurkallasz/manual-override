"""Brute tuning, wave introduction, persistence, and presentation smoke tests."""

import copy
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from test_photon_framework import load


BRUTE_KEYS = {
    "brute_first_wave", "brute_size_multiplier", "brute_health", "brute_damage_per_s",
}


class PhotonBruteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.game = load("photon-game")
        cls.bundle = load("photon-level").runtime_bundle()

    def engine(self, settings=None, waves=None):
        if waves is not None:
            waves = copy.deepcopy(waves)
            for number, wave in enumerate(waves, 1):
                wave.setdefault('wave', number)
                for group in wave['groups']:
                    group.setdefault('lane_weights', {'top_outer': 1, 'bottom_outer': 1})
        engine = self.game.DefenseEngine(self.bundle["runtime"], waves or self.bundle["waves"])
        engine.set_virtual_play(True)
        engine.start(settings)
        return engine

    def test_default_and_custom_stats_compose_with_global_tuning(self):
        for settings, expected in (
            ({}, (960, 64, 64)),
            ({"brute_health": 500, "brute_damage_per_s": 20,
              "enemy_health_multiplier": 2, "enemy_core_damage_multiplier": 3,
              "enemy_tower_damage_multiplier": 4}, (1000, 60, 80)),
        ):
            with self.subTest(settings=settings):
                engine = self.engine(settings)
                self.assertTrue(engine._spawn_enemy("brute", {}))
                brute = engine.enemies[1]
                self.assertEqual((brute["hp"], brute["core_dps"], brute["tower_dps"]), expected)
                self.assertEqual(brute["hp"], brute["max_hp"])
                self.assertEqual(brute["collision_radius"], 2.8)
                self.assertTrue(engine._spawn_enemy("grunt", {}))
                self.assertEqual(engine.enemies[2]["hp"], 70 * settings.get("enemy_health_multiplier", 1))
                for compact in (True, False):
                    self.assertEqual(engine.snapshot(compact_enemies=compact)["settings"]["brute_size_multiplier"], 2)

    def test_brute_melee_deals_four_times_previous_damage(self):
        engine = self.engine()
        engine._spawn_enemy("brute", {})
        brute = engine.enemies[1]
        tower = {"x": brute["x"], "y": brute["y"], "hp": 1000}
        engine.placements["test"] = tower
        engine._damage_towers([brute], 0.5)
        self.assertEqual(tower["hp"], 968)

    def test_default_waves_mix_one_brute_after_every_forty_regular_orcs(self):
        engine = self.engine()
        for number, authored in enumerate(self.bundle["waves"], 1):
            if number > 1:
                engine._launch_wave(number)
            engine.sim_time += max(group["duration_s"] for group in authored["groups"])
            spawned = []
            with mock.patch.object(engine, "_spawn_enemy", side_effect=lambda role, *_: spawned.append(role) or True):
                engine._spawn_due()
            count = sum(group["count"] for group in authored["groups"])
            base_role = authored["groups"][0]["enemy"]
            regular = "grunt" if base_role == "brute" else base_role
            self.assertEqual(len(spawned), count)
            if number < 4:
                self.assertEqual(spawned, [regular] * count)
            else:
                expected = ([regular] * 40 + ["brute"]) * (count // 41) + [regular] * (count % 41)
                self.assertEqual(spawned, expected)
            if number == 4:
                self.assertEqual((spawned.count("grunt"), spawned.count("brute")), (256, 6))
        self.assertEqual(engine.wave_source, self.bundle["waves"])

    def test_changed_first_wave_preserves_counts_timing_and_lanes(self):
        for first in (1, 2, 6, 12):
            with self.subTest(first=first):
                engine = self.engine({"brute_first_wave": first})
                for wave in range(2, 13):
                    engine._launch_wave(wave)
                for wave, authored in zip(engine.launched_waves, self.bundle["waves"]):
                    for group, source in zip(wave["groups"], authored["groups"]):
                        self.assertNotEqual(group["enemy"], "brute")
                        self.assertEqual(group["brute_interval"], 41 if wave["wave"] >= first else 0)
                        for key in ("count", "duration_s", "lane_weights"):
                            self.assertEqual(group[key], source[key])
                self.assertEqual(engine.wave_source, self.bundle["waves"])

    def test_brutes_spawn_from_fourth_wave_but_not_in_shorter_run(self):
        engine = self.engine({"wave_count": 4})
        for wave in range(2, 5):
            engine._launch_wave(wave)
        engine.sim_time += 34
        roles = []
        with mock.patch.object(engine, "_spawn_enemy", side_effect=lambda role, *_: roles.append(role) or True):
            engine._spawn_due()
        self.assertEqual(roles.count("brute"), 6)
        shorter = self.engine({"wave_count": 3})
        for wave in range(2, 5):
            shorter._launch_wave(wave)
        shorter._spawn_due()
        self.assertNotIn("brute", {enemy["enemy_type"] for enemy in shorter.enemies.values()})

    def test_ratio_spans_groups_and_respects_scaled_totals_and_remainders(self):
        for multiplier, total in ((0.5, 41), (1, 82), (2, 164)):
            engine = self.engine({"brute_first_wave": 1, "wave_count": 1,
                                  "enemy_count_multiplier": multiplier}, waves=[{"groups": [
                {"enemy": "runner", "count": 20, "duration_s": 10},
                {"enemy": "brute", "count": 62, "duration_s": 10},
            ]}])
            engine.sim_time = 10
            spawned = []
            with mock.patch.object(engine, "_spawn_enemy", side_effect=lambda role, *_: spawned.append(role) or True):
                engine._spawn_due()
            self.assertEqual(len(spawned), total)
            self.assertEqual(spawned.count("brute"), total // 41)
            self.assertEqual(spawned[:int(20 * multiplier)], ["runner"] * int(20 * multiplier))
            self.assertEqual([i + 1 for i, role in enumerate(spawned) if role == "brute"],
                             list(range(41, total + 1, 41)))
        for count in (1, 40, 41, 42):
            engine = self.engine({"brute_first_wave": 1, "wave_count": 1}, waves=[{"groups": [
                {"enemy": "brute", "count": count, "duration_s": 10},
            ]}])
            engine.sim_time = 10
            spawned = []
            with mock.patch.object(engine, "_spawn_enemy", side_effect=lambda role, *_: spawned.append(role) or True):
                engine._spawn_due()
            self.assertEqual(spawned.count("brute"), count // 41)
            self.assertEqual(len(spawned), count)

    def test_pressure_queue_retains_brute_positions_after_blocked_spawn_and_cap(self):
        engine = self.engine({"brute_first_wave": 1, "wave_count": 1, "max_active_enemies": 1},
                             waves=[{"groups": [{"enemy": "brute", "count": 83, "duration_s": 10}]}])
        engine.sim_time = 10
        spawned = []

        def block_after_seventeen(role, *_):
            if len(spawned) == 17:
                return False
            spawned.append(role)
            return True

        with mock.patch.object(engine, "_spawn_enemy", side_effect=block_after_seventeen):
            engine._spawn_due()
        self.assertEqual(engine.pressure_bank, 66)
        self.assertEqual(engine.pressure_queue[0]["spawn_index"], 17)
        while engine.pressure_queue:
            engine._spawn_due()
            self.assertEqual(len(engine.enemies), 1)
            enemy = next(iter(engine.enemies.values()))
            spawned.append(enemy["enemy_type"])
            self.assertEqual(enemy["hp"], 960 if enemy["enemy_type"] == "brute" else 70)
            # A full playfield leaves the remaining sequence untouched.
            pending_before = copy.deepcopy(engine.pressure_queue)
            engine._spawn_due()
            self.assertEqual(engine.pressure_queue, pending_before)
            engine.enemies.clear()
        self.assertEqual(spawned, (["grunt"] * 40 + ["brute"]) * 2 + ["grunt"])
        self.assertEqual(engine.pressure_bank, 0)

    def test_settings_persist_and_only_apply_to_next_start(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "settings.json"
            store = self.game.SettingsStore(path)
            engine = self.engine(store.snapshot())
            before = copy.deepcopy(engine.snapshot()["settings"])
            changed = dict(store.snapshot(), brute_first_wave=2, brute_size_multiplier=2.5,
                           brute_health=1500, brute_damage_per_s=90)
            result, errors = store.update(changed)
            self.assertEqual(errors, {})
            self.assertEqual(result["settings"], changed)
            self.assertEqual(engine.snapshot()["settings"], before)
            reloaded = self.game.SettingsStore(path)
            self.assertEqual(reloaded.snapshot(), changed)
            engine.start(reloaded.snapshot())
            engine._spawn_enemy("brute", {})
            self.assertEqual(engine.enemies[1]["hp"], 1500)
            self.assertEqual(engine.enemies[1]["tower_dps"], 90)
            self.assertEqual(engine.snapshot()["settings"]["brute_size_multiplier"], 2.5)

    def test_validation_rejects_invalid_brute_parameters_without_saving(self):
        with tempfile.TemporaryDirectory() as folder:
            store = self.game.SettingsStore(Path(folder) / "settings.json")
            before = store.snapshot()
            invalid = {"brute_first_wave": (0, 13, 3.5),
                       "brute_size_multiplier": (0, 11, "nan"),
                       "brute_health": (0, 100001, "inf"),
                       "brute_damage_per_s": (-1, 10001, "oops")}
            for key, values in invalid.items():
                for value in values:
                    with self.subTest(key=key, value=value):
                        result, errors = store.update(dict(before, **{key: value}))
                        self.assertIsNone(result)
                        self.assertIn(key, errors)
                        self.assertEqual(store.snapshot(), before)

    def test_legacy_saved_settings_keep_tuning_and_gain_brute_defaults(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "settings.json"
            defaults = self.game.SettingsStore(path).snapshot()
            legacy = {key: value for key, value in defaults.items() if key not in BRUTE_KEYS}
            legacy.update(wave_count=6, enemy_health_multiplier=1.5)
            payload = {"schema_version": 1, "revision": 7, "preset": "custom", "settings": legacy}
            path.write_text(json.dumps(payload))
            store = self.game.SettingsStore(path)
            self.assertIsNone(store.error)
            self.assertEqual(store.revision, 7)
            self.assertEqual(store.snapshot(), {**defaults, **legacy})
            for broken in ({**legacy, "unknown": 1}, {key: value for key, value in legacy.items() if key != "wave_count"}):
                path.write_text(json.dumps({**payload, "settings": broken}))
                self.assertIsNotNone(self.game.SettingsStore(path).error)

    @unittest.skipUnless(shutil.which("node"), "Node.js required for renderer checks")
    def test_renderer_scales_brutes_and_updates_cached_art_between_runs(self):
        result = subprocess.run([shutil.which("node"), str(Path(__file__).with_name("photon_brute_renderer.cjs"))],
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
