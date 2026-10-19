"""Authoritative start sequence; PYTHONPATH=tests .venv/bin/python -m unittest test_mission_countdown"""
import tempfile
import unittest
from test_photon_framework import load
from virtual_upgrades_fixture import fixture_app


class MissionCountdownTests(unittest.TestCase):
    def setUp(self):
        game, level = load('photon-game'), load('photon-level')
        bundle = level.runtime_bundle()
        self.engine = game.DefenseEngine(bundle['runtime'], bundle['waves'])
        self.engine.set_virtual_play(True)

    def step(self, seconds):
        for _ in range(round(seconds * 20)):
            self.engine.step(.05)

    def test_five_seconds_hold_combat_then_go(self):
        e = self.engine
        e.start({'first_wave_delay_s': 0}, countdown_s=5)
        for remaining in (5, 4, 3, 2, 1):
            value = e.snapshot()
            self.assertEqual(value['start_countdown']['remaining_s'], remaining)
            self.assertEqual(value['sim_time'], 0)
            self.assertEqual(value['wave'], 0)
            self.assertEqual(value['active_enemies'], 0)
            self.assertEqual(value['core_hp'], value['core_max_hp'])
            self.step(1)
        self.assertEqual(e.snapshot()['start_countdown']['remaining_s'], 0)
        self.assertEqual(e.sim_time, 0)
        self.assertEqual(e.current_wave, 1)
        self.step(.1)
        self.assertGreater(e.sim_time, 0)
        self.assertGreater(len(e.enemies), 0)

    def test_pause_reset_and_new_run(self):
        e = self.engine
        e.start(countdown_s=5)
        self.step(1.5)
        e.pause(True)
        before = e.snapshot()['start_countdown']
        self.step(3)
        self.assertEqual(e.snapshot()['start_countdown'], before)
        e.pause(False)
        self.step(.5)
        self.assertEqual(e.snapshot()['start_countdown']['remaining_s'], 3)
        e.reset()
        self.assertEqual(e.snapshot()['start_countdown']['duration_s'], 0)
        e.start(countdown_s=5)
        self.assertEqual(e.snapshot()['start_countdown']['remaining_s'], 5)

    def test_countdown_preserves_preparation_time(self):
        e = self.engine
        e.start({'first_wave_delay_s': 10}, countdown_s=5)
        self.step(5)
        self.assertEqual(e.sim_time, 0)
        self.assertEqual(e.next_wave_at, 10)
        self.step(9)
        self.assertEqual(e.current_wave, 0)
        self.step(1.1)
        self.assertEqual(e.current_wave, 1)

    def test_operator_start_publishes_countdown_and_reset_clears_it(self):
        with tempfile.TemporaryDirectory() as folder:
            app, game, view = fixture_app(folder)
            try:
                game._engine.stop_background()
                with app.test_client() as client:
                    url = '/s/gamemaster/p/photon-game/api/command'
                    response = client.post(url, json={'action': 'start'})
                    self.assertEqual(response.status_code, 200)
                    state = game.game_snapshot()
                    self.assertEqual(state['start_countdown']['remaining_s'], 5)
                    self.assertEqual(state['phase'], 'running')
                    self.assertIsNotNone(state['run_id'])
                    self.assertEqual(client.post(url, json={'action':'reset'}).status_code, 200)
                    self.assertEqual(game.game_snapshot()['start_countdown']['duration_s'], 0)
            finally:
                view.hub_stop()
                game.hub_stop()


if __name__ == '__main__':
    unittest.main()
