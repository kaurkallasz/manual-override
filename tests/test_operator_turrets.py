"""Run: PYTHONPATH=tests .venv/bin/python -m unittest test_operator_turrets"""
import copy
import tempfile
import time
import unittest
from unittest import mock

from test_photon_framework import load
from virtual_upgrades_fixture import fixture_app


class OperatorTurretTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.game = load('photon-game')
        cls.bundle = load('photon-level').runtime_bundle()

    def setUp(self):
        self.e = self.game.DefenseEngine(self.bundle['runtime'], self.bundle['waves'])

    def select(self, tag=100, sid='socket_01'):
        self.e.operator_turret_command('operator_atom', sid, tag)

    def activate(self, team='green', sid='socket_01'):
        self.e.operator_turret_command('operator_turret', sid, team)

    def state(self, sid='socket_01'):
        return next(s for s in self.e.snapshot()['turret_controls']['sockets'] if s['socket_id'] == sid)

    def physical(self, tag=102, sid='socket_01', state='present', *, activation=False):
        now = time.time()
        marker = self.e.level.sockets[sid]['aruco_id']
        relation = dict(movable_id=tag, marker_id=marker, relation_id=f'{tag}:{marker}',
                        state=state, departed_at=now if state == 'departed' else None)
        placement = dict(status='unavailable', error='No arm',
                         occupancy=dict(status='ready', sampled_at=now, relations=[relation]))
        if activation:
            placement.update(status='ready', sampled_at=now, relations=[dict(
                movable_id=tag, marker_id=marker, arm=self.e.atom_owners[tag],
                distance=0, stable=True, relation_id=f'{tag}:{marker}',
                observed_since=now-2, stable_at=now-1)])
        self.e.ingest_physical(placement)

    def test_initial_selection_and_last_team_are_separate_from_weapon_owner(self):
        self.assertTrue(all(s['activation'] == 'initial' and s['atom_id'] is None
                            for s in self.e.snapshot()['turret_controls']['sockets']))
        with self.assertRaisesRegex(ValueError, 'Select or detect'):
            self.activate()
        self.select(101)
        tower = self.e.placements['socket_01']
        self.assertEqual((tower['owner'], tower['tower_type']), ('green', 'flamethrower'))
        self.activate('purple')
        self.assertEqual(self.state()['activation'], 'purple')
        self.assertEqual((tower['owner'], tower['tower_type']), ('green', 'flamethrower'))
        tower['hp'] *= .5
        hp = tower['hp']
        self.activate('purple')
        self.assertEqual(tower['hp'], hp)  # Same command is idempotent.

    def test_number_during_running_game_installs_and_replenishes_without_boost(self):
        self.e.start(reward_enabled=True)
        self.select(100)
        tower = self.e.placements['socket_01']
        self.assertEqual((tower['owner'], tower['tower_type']), ('green', 'machine_gun'))
        self.assertEqual(tower['source'], 'operator')
        self.assertNotEqual(tower['atom_buff_state'], 'active')
        self.assertIsNone(tower['occupying_atom_id'])
        self.assertEqual(tower['atom_damage_multiplier'], 1)
        self.assertEqual(tower['atom_health_multiplier'], 1)
        self.assertEqual(tower['max_hp'], tower['normal_max_hp'])
        self.assertFalse(self.e.manual_atom_presence)
        self.assertFalse(self.e.atom_presence)
        self.assertTrue(self.e.atom_visits[100]['departed'])
        tower['hp'] *= .5
        self.select(100)
        self.assertEqual(tower['hp'], tower['max_hp'])  # Each click is a fresh activation.
        self.select(101)
        self.assertEqual(tower['hp'], tower['max_hp'])
        self.assertIsNone(tower['occupying_atom_id'])
        self.assertEqual(tower['tower_type'], 'machine_gun')
        self.select(None)
        self.assertEqual(tower['atom_damage_multiplier'], 1)
        self.assertIsNone(tower['occupying_atom_id'])
        self.assertFalse(tower['destroyed'])
        self.select(102)
        self.assertEqual(self.state()['activation'], 'purple')
        self.assertEqual((tower['owner'], tower['tower_type']), ('green', 'machine_gun'))

    def test_same_number_after_x_rebuilds_and_keeps_weapon(self):
        self.e.start(reward_enabled=False)
        self.select(101)
        self.activate('deactivated')
        self.assertTrue(self.e.placements['socket_01']['destroyed'])
        self.select(101)
        tower = self.e.placements['socket_01']
        self.assertFalse(tower['destroyed'])
        self.assertEqual((tower['owner'], tower['tower_type']), ('green', 'flamethrower'))
        self.assertNotEqual(tower['atom_buff_state'], 'active')
        self.assertEqual(tower['atom_damage_multiplier'], 1)
        self.assertEqual(tower['max_hp'], tower['normal_max_hp'])
        self.assertEqual(tower['hp'], tower['max_hp'])
        self.assertGreater(tower['activation_complete_at'], self.e.runtime_time)

    def test_locked_weapon_rejects_selection_before_occupancy_changes(self):
        levels = {key: 1 for key in ('damage-machine-gun', 'damage-flamethrower',
                                    'damage-mortar', 'damage-tesla-coil', 'forcefield')}
        levels['damage-flamethrower'] = 0
        self.e.set_virtual_test_loadout(levels)
        self.select(100)
        before = copy.deepcopy((self.e.manual_atom_presence, self.e.atom_presence, self.e.atom_visits))
        with self.assertRaisesRegex(ValueError, 'locked'):
            self.select(101, 'socket_03')
        self.assertEqual((self.e.manual_atom_presence, self.e.atom_presence, self.e.atom_visits), before)
        self.assertNotIn('socket_03', self.e.placements)

    def test_physical_priority_consumes_overrides_and_removal_does_not_restore(self):
        self.select(100)
        self.select(102, 'socket_03')
        self.physical(102)
        self.assertEqual((self.state()['atom_id'], self.state()['atom_source']), (102, 'physical'))
        self.assertIsNone(self.state('socket_03')['atom_id'])
        self.assertFalse(self.e.manual_atom_presence)
        for tag, sid in [(100, 'socket_01'), (102, 'socket_03'), (None, 'socket_01')]:
            with self.assertRaisesRegex(ValueError, 'Physical Atom'):
                self.select(tag, sid)
        self.physical(102, state='departed')
        self.assertIsNone(self.state()['atom_id'])
        self.select(101)
        self.assertIsNone(self.state()['atom_id'])
        self.assertEqual(self.state()['activation'], 'green')

    def test_reusing_number_on_another_target_leaves_neither_occupied(self):
        self.select(100)
        self.select(100, 'socket_03')
        self.assertIsNone(self.state()['atom_id'])
        self.select(101, 'socket_03')
        self.assertFalse(self.e.atom_presence)
        self.assertFalse(self.e.manual_atom_presence)
        self.assertTrue(all(t['atom_damage_multiplier'] == 1 for t in self.e.placements.values()))
        self.select(None, 'socket_03')
        self.assertFalse(self.e.atom_presence)

    def test_camera_unavailable_does_not_resurrect_a_superseded_choice(self):
        self.select(100)
        self.physical(103)
        self.e.ingest_physical({'status': 'unavailable'})
        self.assertIsNone(self.state()['atom_id'])
        self.assertEqual(self.state()['occupancy_status'], 'unavailable')
        self.physical(103)
        self.assertEqual(self.state()['atom_id'], 103)

    def test_real_atom_boosts_manual_turret_and_removal_ends_boost(self):
        levels = {key: 4 for key in ('damage-machine-gun', 'damage-flamethrower',
                                    'damage-mortar', 'damage-tesla-coil', 'forcefield')}
        self.e.set_virtual_test_loadout(levels)
        self.e.settings['l4_turrets_per_socket'] = 2
        self.e.start(reward_enabled=False)
        self.e.run_started_at = time.time() - 10
        sid = next(sid for sid, socket in self.e.level.sockets.items() if socket.get('companion'))
        self.select(100, sid)
        def units():
            snapshot = self.e.snapshot()
            return [t for t in snapshot['towers'] + snapshot['companions'] if t['socket_id'] == sid]
        self.assertEqual(len(units()), 2)
        self.assertTrue(all(t['atom_damage_multiplier'] == t['atom_health_multiplier'] == 1 for t in units()))
        self.physical(100, sid, activation=True)
        self.assertTrue(all(t['atom_buff_state'] == 'active' and t['atom_damage_multiplier'] == 2 for t in units()))
        self.physical(100, sid, state='departed')
        self.assertTrue(all(t['atom_buff_state'] == 'inactive' and t['atom_damage_multiplier'] == 1 for t in units()))
        self.e.ingest_physical({'status': 'unavailable'})
        self.assertTrue(all(t['atom_damage_multiplier'] == 1 for t in units()))

    def test_physical_repeat_cannot_undo_x_but_departure_return_can(self):
        self.e.start(reward_enabled=False)
        self.e.run_started_at = time.time()-10
        self.physical(100, activation=True)
        tower = self.e.placements['socket_01']
        self.activate('deactivated')
        self.physical(100, activation=True)
        self.e.ingest_physical({'status': 'unavailable'})
        self.physical(100, activation=True)
        self.assertTrue(tower['destroyed'])
        self.assertEqual(tower['hp'], 0)
        self.assertFalse(tower['deactivated'])
        self.assertFalse(self.e.snapshot()['towers'][0]['operational'])
        self.physical(100, state='departed')
        self.physical(100, activation=True)
        tower = self.e.placements['socket_01']
        self.assertFalse(tower['destroyed'])
        self.assertEqual(self.state()['activation'], 'green')
        tower['hp'] *= .5
        hp = tower['hp']
        self.physical(100, activation=True)
        self.assertEqual(tower['hp'], hp)
        self.physical(100, state='departed')
        self.physical(102, activation=True)
        self.assertEqual(self.state()['activation'], 'purple')
        self.assertEqual(tower['tower_type'], 'machine_gun')

    def test_x_destroys_primary_companion_and_breaks_row(self):
        levels = {key: 4 for key in ('damage-machine-gun', 'damage-flamethrower',
                                    'damage-mortar', 'damage-tesla-coil', 'forcefield')}
        self.e.set_virtual_test_loadout(levels)
        row = self.e.level.row_barriers[0]
        for sid in row['socket_ids']:
            self.select(100, sid)
            self.activate('green', sid)
        self.e.runtime_time = 10
        self.assertTrue(self.e.snapshot()['row_barriers'][0]['powered'])
        sid = next(sid for sid in row['socket_ids'] if self.e.placements[sid].get('companion'))
        tower = self.e.placements[sid]
        self.activate('deactivated', sid)
        snapshot = self.e.snapshot()
        self.assertTrue(tower['destroyed'])
        self.assertEqual(tower['hp'], 0)
        self.assertFalse(tower['deactivated'])
        self.assertTrue(all(t['destroyed'] and t['hp'] == 0 for t in snapshot['towers'] + snapshot['companions'] if t['socket_id'] == sid))
        destroyed_at = tower['destroyed_at']
        self.e.sim_time += 1
        self.activate('deactivated', sid)
        self.assertEqual(tower['destroyed_at'], destroyed_at)
        self.assertEqual(sum(e['kind'] == 'tower_destroyed' and e['socket_id'] == sid for e in self.e.events), 1)
        self.assertFalse(snapshot['row_barriers'][0]['powered'])
        self.assertTrue(all(not t['operational'] for t in snapshot['towers'] + snapshot['companions'] if t['socket_id'] == sid))
        self.assertTrue(all(not self.e._field_operational(f) for f in self.e.force_fields.values()
                            if sid in (f['from_socket'], f['to_socket'])))
        before = tower['hp']
        self.e._apply_tower_damage(tower, 10000)
        self.assertEqual(tower['hp'], before)
        # Put a target directly in this weapon's range; no primary/companion fires.
        with mock.patch.object(self.e, '_tower_targeting', side_effect=AssertionError('Inactive weapon targeted')):
            for other in self.e.placements.values():
                other['deactivated'] = True
            self.e._sync_companions()
            self.e._fire_towers([{'id': 999}], set())

    def test_reactivation_preserves_destroyed_weapon_and_reset_clears_everything(self):
        self.select(101)
        self.activate()
        tower = self.e.placements['socket_01']
        self.e._apply_tower_damage(tower, 100000)
        self.assertEqual(self.state()['activation'], 'deactivated')
        self.select(103)
        self.assertEqual(self.e.placements['socket_01']['tower_type'], 'flamethrower')
        self.assertEqual(self.e.placements['socket_01']['owner'], 'green')
        self.assertFalse(self.e.placements['socket_01']['destroyed'])
        self.e.start(reward_enabled=False)
        self.assertEqual(self.state()['activation'], 'purple')
        self.assertIsNone(self.state()['atom_id'])
        self.assertEqual(self.e.placements['socket_01']['atom_damage_multiplier'], 1)
        self.e.reset()
        self.assertEqual(self.state()['activation'], 'initial')
        self.assertIsNone(self.state()['atom_id'])
        self.activate('deactivated')
        self.assertEqual(self.state()['activation'], 'deactivated')

    def test_invalid_commands_do_not_change_game(self):
        before = copy.deepcopy(self.e.atom_presence)
        for tag in (True, '100', 999, 100.0):
            with self.assertRaises(ValueError):
                self.select(tag)
        for sid in ('unknown', None, 40):
            with self.assertRaises(ValueError):
                self.select(100, sid)
        with self.assertRaises(ValueError):
            self.activate('red')
        self.assertEqual(self.e.atom_presence, before)
        self.assertFalse(self.e.placements)


class OperatorTurretApiTests(unittest.TestCase):
    def test_roles_running_scored_controls_and_reconnect_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            app, game, view = fixture_app(folder)
            game._engine.stop_background()
            client = app.test_client()
            url = '/s/gamemaster/p/laser-tag-y/api/command'
            try:
                for data in [dict(action='operator_atom', socket_id='socket_01', atom_tag_id=100),
                             dict(action='operator_turret', socket_id='socket_01', activation='green')]:
                    response = client.post(url, json=data)
                    self.assertEqual(response.status_code, 200, response.get_json())
                state = client.get('/s/gamemaster/p/laser-tag-y/api/state').get_json()
                self.assertEqual(state['turret_controls']['sockets'][0]['activation'], 'green')
                with client.get('/s/gamemaster/p/laser-tag-y/api/events', buffered=False) as stream:
                    self.assertIn(b'turret_controls', next(iter(stream.response)))
                game._engine.phase = 'running'
                with mock.patch.object(game._progress, 'snapshot', return_value={'reward_enabled': True}):
                    for action, key, value in [('operator_atom', 'atom_tag_id', 101), ('operator_turret', 'activation', 'deactivated')]:
                        response = client.post(url, json={'action': action, 'socket_id': 'socket_01', key: value})
                        self.assertEqual(response.status_code, 200, response.get_json())
                    self.assertTrue(game._engine.placements['socket_01']['destroyed'])
                    response = client.post(url, json=dict(action='operator_atom', socket_id='socket_01', atom_tag_id=101))
                    self.assertEqual(response.status_code, 200, response.get_json())
                    self.assertFalse(game._engine.placements['socket_01']['destroyed'])
                    self.assertIsNone(game._engine.placements['socket_01']['occupying_atom_id'])
                    self.assertEqual(game._engine.placements['socket_01']['atom_damage_multiplier'], 1)
                    # Unrelated virtual-placement/loadout restrictions remain in force.
                    response = client.post(url, json=dict(action='place', socket_id='socket_03', atom_tag_id=101))
                    self.assertEqual(response.status_code, 400)
                    self.assertIn('scored', response.get_json()['error'])
                app.before_request_funcs[None].clear()
                response = client.post(url, json=dict(action='operator_atom', socket_id='socket_01', atom_tag_id=100))
                self.assertEqual(response.status_code, 403)
            finally:
                view.hub_stop()
                game.hub_stop()


if __name__ == '__main__':
    unittest.main()
