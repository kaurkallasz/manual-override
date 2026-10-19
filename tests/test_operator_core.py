"""Run: PYTHONPATH=tests .venv/bin/python -m unittest test_operator_core."""
import tempfile
import unittest
from unittest import mock

from test_photon_framework import load
from virtual_upgrades_fixture import fixture_app
from operator_turret_fixture import start_core_ring


class OperatorCoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.game = load('photon-game')
        cls.bundle = load('photon-level').runtime_bundle()

    def setUp(self):
        self.e = self.game.DefenseEngine(self.bundle['runtime'], self.bundle['waves'])
        start_core_ring(self.e)

    def select(self, tag):
        self.e.operator_turret_command('operator_core', None, tag)

    def test_opposing_teams_in_either_order_use_normal_completion(self):
        for first, second in ((100, 103), (102, 101)):
            with self.subTest(first=first):
                self.setUp()
                self.select(first)
                self.assertEqual(self.e.core_stage, 'first_tag')
                self.assertEqual(self.e.core_first_tag, first)
                self.assertEqual(self.e.core_first_source, 'operator')
                self.select(second)
                self.assertEqual(self.e.core_stage, 'detonating')
                self.assertEqual(self.e.phase, 'running')
                for _ in range(30):
                    self.e.step(.1)
                self.assertEqual(self.e.phase, 'won')
                state = self.e.snapshot()['core_sequence']
                self.assertEqual(state['second_atom_tag_id'], second)
                self.assertEqual(state['second_source'], 'operator')
                self.assertEqual(sum(e['kind'] == 'run_won' for e in self.e.events), 1)
                with self.assertRaises(ValueError):
                    self.select(None)  # X cannot undo a completed run.

    def test_same_team_and_same_atom_do_not_complete_or_replace_first(self):
        for first, same_team in ((100, 101), (102, 103)):
            with self.subTest(first=first):
                self.setUp()
                self.select(first)
                for second in (first, same_team):
                    with self.assertRaisesRegex(ValueError, 'opposing team'):
                        self.select(second)
                    self.assertEqual(self.e.core_stage, 'first_tag')
                    self.assertEqual(self.e.core_first_tag, first)
                    self.assertIsNone(self.e.core_second_tag)

    def test_x_clears_pending_layer_and_does_not_damage_core_or_award_win(self):
        self.select(100)
        hp = self.e.core_hp
        self.select(None)
        self.assertEqual(self.e.core_stage, 'ring_ready')
        self.assertIsNone(self.e.core_first_tag)
        self.assertIsNone(self.e.core_first_source)
        self.assertEqual(self.e.core_hp, hp)
        self.assertEqual(self.e.phase, 'running')
        self.select(103)
        self.assertEqual(self.e.core_first_tag, 103)
        self.select(100)
        with self.assertRaisesRegex(ValueError, 'already complete'):
            self.select(None)

    def test_requires_running_game_ring_and_strict_atom_id(self):
        for tag in (True, '100', 100.0, 999):
            with self.assertRaises(ValueError):
                self.select(tag)
        self.e.ring_completed_at = None
        with self.assertRaisesRegex(ValueError, 'force-field ring'):
            self.select(100)
        self.e.phase = 'setup'
        with self.assertRaisesRegex(ValueError, 'Start the run'):
            self.select(100)
        self.assertIsNone(self.e.core_first_tag)

    def test_moving_manual_atom_to_core_removes_turret_buff(self):
        self.e.operator_turret_command('operator_atom', 'socket_01', 100)
        self.select(100)
        self.assertNotIn(100, self.e.manual_atom_presence)
        self.assertNotIn(100, self.e.atom_presence)
        self.assertEqual(self.e.placements['socket_01']['atom_damage_multiplier'], 1)

    def test_atom_physically_on_turret_cannot_be_selected_at_core(self):
        self.e.physical_atom_presence[100] = 'socket_01'
        with self.assertRaisesRegex(ValueError, 'Physical Atom'):
            self.select(100)
        self.assertEqual(self.e.core_stage, 'ring_ready')


class OperatorCoreApiTests(unittest.TestCase):
    def test_authorized_scored_input_same_team_rejection_clear_and_reconnect(self):
        with tempfile.TemporaryDirectory() as folder:
            app, game, view = fixture_app(folder)
            game._engine.stop_background()
            client = app.test_client()
            url = '/s/gamemaster/p/laser-tag-y/api/command'
            def select(tag):
                return client.post(url, json={'action': 'operator_core', 'atom_tag_id': tag})
            try:
                start_core_ring(game._engine)
                with mock.patch.object(game._progress, 'snapshot', return_value={'reward_enabled': True}):
                    self.assertEqual(select(100).status_code, 200)
                    bad = select(101)
                    self.assertEqual(bad.status_code, 400)
                    self.assertIn('opposing team', bad.get_json()['error'])
                    snapshot = client.get('/s/gamemaster/p/laser-tag-y/api/state').get_json()
                    self.assertEqual(snapshot['core_sequence']['first_atom_tag_id'], 100)
                    self.assertTrue(snapshot['turret_controls']['core']['can_clear'])
                    self.assertEqual(select(None).status_code, 200)
                    self.assertEqual(select(102).status_code, 200)
                    self.assertEqual(select(100).status_code, 200)
                    self.assertEqual(game._engine.core_stage, 'detonating')
                app.before_request_funcs[None].clear()
                self.assertEqual(select(None).status_code, 403)
            finally:
                view.hub_stop()
                game.hub_stop()


if __name__ == '__main__':
    unittest.main()
