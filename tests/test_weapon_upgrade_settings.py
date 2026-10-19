"""Run: PYTHONPATH=tests .venv/bin/python -m unittest test_weapon_upgrade_settings"""
import json
from pathlib import Path
import tempfile
import unittest

from test_photon_framework import load
from virtual_upgrades_fixture import fixture_app

TRACKS = ('damage-machine-gun', 'damage-flamethrower', 'damage-mortar', 'damage-tesla-coil', 'forcefield')


class WeaponUpgradeSettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.game = load('photon-game')
        cls.bundle = load('photon-level').runtime_bundle()

    def engine(self, level, settings=None):
        engine = self.game.DefenseEngine(self.bundle['runtime'], self.bundle['waves'])
        engine.set_virtual_play(True)
        engine.set_virtual_test_loadout(dict.fromkeys(TRACKS, level))
        engine.place(100, 'socket_01', source='virtual')
        if settings is not None:
            engine.start(settings)
        return engine

    def test_default_bonuses_apply_to_placement_start_and_live_upgrade(self):
        for level, multiplier in ((1, 1), (2, 1.3), (3, 1.4), (4, 1.5)):
            for atom in range(100, 104):
                with self.subTest(level=level, atom=atom):
                    engine = self.engine(level)
                    engine.place(atom, 'socket_02', source='virtual')
                    for start in (False, True):
                        if start:
                            engine.start()
                        tower = engine.placements['socket_02']
                        self.assertAlmostEqual(tower['upgrade_multiplier'], multiplier)
                        self.assertAlmostEqual(tower['base_max_hp'], engine._tower_max_hp() * multiplier)
                    engine.pause(True)
                    tower['hp'] *= .4
                    engine.set_virtual_test_loadout(dict.fromkeys(TRACKS, 4))
                    self.assertAlmostEqual(tower['upgrade_multiplier'], 1.5)
                    self.assertAlmostEqual(tower['hp'] / tower['max_hp'], .4)

    def test_configured_bonus_changes_actual_shot_damage(self):
        damage = []
        for level in (1, 2):
            engine = self.engine(level, {'weapon_upgrade_l2_percent': 75})
            engine.remove_atom(100, source='virtual')
            engine.sim_time = engine.runtime_time = 10
            tower = engine.placements['socket_01']
            tower.update(aim_angle=0, aim_spread=.5, cooldown=0)
            enemy = {'id': 1, 'x': tower['x'] + 25, 'y': tower['y'], 'hp': 10000, 'progress': 1}
            engine.enemies = {1: enemy}
            engine._fire_towers(.01, set())
            damage.append(10000 - enemy['hp'])
        self.assertGreater(damage[0], 0)
        self.assertAlmostEqual(damage[1] / damage[0], 1.75)

    def test_double_turrets_toggle_and_custom_l4_bonus(self):
        for count in (1, 2):
            engine = self.engine(4, {'l4_turrets_per_socket': count, 'weapon_upgrade_l4_percent': 85})
            for sid in engine.level.sockets:
                engine.place(100, sid, source='virtual')
            state = engine.snapshot()
            self.assertEqual(len(state['towers']), 16)
            self.assertEqual(len(state['companions']), 12 if count == 2 else 0)
            for tower in state['towers'] + state['companions']:
                self.assertAlmostEqual(tower['upgrade_multiplier'], 1.85)
            self.assertEqual(state['companion_policy']['l4_turrets_per_socket'], count)

    def test_legacy_settings_load_validation_and_atomic_persistence(self):
        from photon_game_runtime import upgrades
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'settings.json'
            store = self.game.SettingsStore(path)
            store.update(store.snapshot())
            legacy = json.loads(path.read_text())
            for key in upgrades.DEFAULTS:
                legacy['settings'].pop(key)
            legacy['settings']['machine_gun_damage'] = 27
            path.write_text(json.dumps(legacy))
            store = self.game.SettingsStore(path)
            self.assertIsNone(store.error)
            self.assertEqual(store.snapshot()['machine_gun_damage'], 27)
            self.assertEqual({key: store.snapshot()[key] for key in upgrades.DEFAULTS}, upgrades.DEFAULTS)
            tuned = {**store.snapshot(), 'weapon_upgrade_l2_percent': 35, 'l4_turrets_per_socket': 1}
            self.assertFalse(store.update(tuned)[1])
            self.assertEqual(self.game.SettingsStore(path).snapshot(), tuned)
            for patch in ({'weapon_upgrade_l3_percent': 30}, {'weapon_upgrade_l4_percent': float('nan')},
                          {'weapon_upgrade_l2_percent': -1}, {'l4_turrets_per_socket': 3},
                          {'l4_turrets_per_socket': 1.5}, {'l4_turrets_per_socket': True}):
                before = path.read_bytes()
                self.assertTrue(store.update({**tuned, **patch})[1])
                self.assertEqual(path.read_bytes(), before)

    def test_api_preset_preview_and_run_use_saved_tuning(self):
        with tempfile.TemporaryDirectory() as folder:
            app, game, view = fixture_app(folder)
            try:
                with app.test_client() as client:
                    url = '/s/gamemaster/p/photon-game/api/command'
                    settings = {**game._settings.snapshot(), 'weapon_upgrade_l2_percent': 35,
                                'weapon_upgrade_l3_percent': 45, 'weapon_upgrade_l4_percent': 65,
                                'l4_turrets_per_socket': 1}
                    self.assertEqual(client.post(url, json={'action': 'configure', 'settings': settings}).status_code, 200)
                    self.assertEqual(game.SettingsStore(Path(folder) / 'settings.json').snapshot(), settings)
                    state = game.game_snapshot()
                    saved = client.post(url, json={'action': 'level_preset', 'preset_action': 'save',
                        'map_id': state['level']['name'], 'tier': 1, 'name': 'Upgrade playtest',
                        'revision': state['level_presets']['revision'], 'settings': settings})
                    self.assertEqual(saved.status_code, 200, saved.json)
                    preview = game.game_snapshot()['next_match']['tiers'][0]['weapon_upgrades']
                    self.assertEqual(preview['bonus_percent'], {'2': 35, '3': 45, '4': 65})
                    self.assertEqual(preview['l4_turrets_per_socket'], 1)
                    game.apply_command({'action': 'virtual_test_loadout', 'levels': dict.fromkeys(TRACKS, 4), 'enabled': True})
                    game._engine.place(100, 'socket_01', source='virtual')
                    game.apply_command({'action': 'start'})
                    self.assertEqual(game.game_snapshot()['settings'], settings)
                    self.assertAlmostEqual(game.game_snapshot()['towers'][0]['upgrade_multiplier'], 1.65)
                    self.assertEqual(game.game_snapshot()['companions'], [])
                    game.apply_command({'action': 'configure', 'settings': {**settings, 'weapon_upgrade_l4_percent': 95}})
                    self.assertEqual(game.game_snapshot()['settings'], settings)
            finally:
                view.hub_stop()
                game.hub_stop()


if __name__ == '__main__':
    unittest.main()
