"""Ready acknowledgements and failed/restarted Start, using fake hardware only."""
import copy
import sys
from pathlib import Path
import unittest
from unittest.mock import patch
import test_event_game as fixture


class StartReadinessTests(unittest.TestCase):
    setUp = fixture.EventGameTests.setUp
    command = fixture.EventGameTests.command
    start = fixture.EventGameTests.start

    def ready_both(self):
        for side in ('green', 'purple'):
            self.g.mobile_journey_command(side, {'action': 'ready', 'event_id': self.event})
        self.assertTrue(self.readiness()['all_ready'])

    def readiness(self):
        return self.g.game_snapshot()['journey']['readiness']

    def owner(self):
        return self.g._module('photon-progress')

    def reservations(self, table='ready_rosters'):
        with self.owner()._ready().transaction() as db:
            return [row[0] for row in db.execute('SELECT id FROM '+table)]

    def test_gamemaster_start_after_hub_unloads_helper_imports(self):
        self.ready_both()
        self.app.testing = True
        # Hub._load_one removes owned helpers from sys.modules after import and
        # removes the prototype directory from sys.path. Ordinary test loaders
        # used to retain these helpers, masking request-time local imports.
        owned = {name: module for name, module in list(sys.modules.items())
                 if str(getattr(module, '__file__', '') or '').startswith(
                     str(Path(self.g.HERE).parent)+'/')}
        try:
            for name in owned:
                del sys.modules[name]
            result = self.c.post('/s/gamemaster/p/laser-tag-y/api/command', json={
                'action': 'start', 'event_id': self.event,
                'starting_atoms': {'green': 100, 'purple': 102}})
            self.assertEqual(result.status_code, 200, result.get_data(as_text=True))
            self.assertEqual(result.get_json()['output']['phase'], 'running')
        finally:
            sys.modules.update(owned)

    def test_unexpected_start_failure_returns_json_and_keeps_retry_available(self):
        self.ready_both()
        for slug in ('laser-tag-y', 'photon-game'):
            with self.subTest(slug=slug), self.assertLogs(self.app.logger, level='ERROR') as logs:
                with patch.object(self.g._progress, 'begin', side_effect=RuntimeError('injected unexpected failure')):
                    result = self.c.post('/s/gamemaster/p/'+slug+'/api/command', json={
                        'action': 'start', 'event_id': self.event,
                        'starting_atoms': {'green': 100, 'purple': 102}})
                self.assertEqual(result.status_code, 500)
                self.assertEqual(result.mimetype, 'application/json')
                self.assertIn('server log', result.get_json()['error'])
                self.assertIn('injected unexpected failure', '\n'.join(logs.output))
                self.assertEqual(self.reservations(), [])
                self.assertTrue(self.readiness()['all_ready'])
        self.start()

    def test_ready_survives_fresh_game_bookkeeping_then_starts(self):
        self.g._presets = self.g.Presets(Path(self.folder.name)/'presets.json')
        self.ready_both()
        before = self.g._progress.roster()['roster']
        self.owner().prepare_game()
        after = self.g._progress.roster()['roster']
        for side in before:
            self.assertGreater(after[side]['revision'], before[side]['revision'])
        self.assertTrue(self.readiness()['all_ready'])
        for side in ('green', 'purple'):
            state = self.c.get('/s/gamemaster/p/mobile-ltz-api/api/state?side='+side).get_json()
            self.assertTrue(state['journey']['readiness']['players'][side]['ready'])
        self.start()
        self.assertEqual(self.reservations(), [])
        self.assertEqual(self.g._engine.phase, 'running')
        self.assertFalse(self.readiness()['all_ready'])

    def test_failed_begin_releases_only_start_lock_and_retry_works(self):
        self.ready_both()
        with patch.object(self.g._progress, 'begin', side_effect=ValueError('injected begin failure')):
            result = self.command('start', starting_atoms={'green': 100, 'purple': 102})
        self.assertEqual(result.status_code, 400)
        self.assertIn('injected begin failure', result.get_json()['error'])
        self.assertEqual(self.reservations(), [])
        self.assertTrue(self.readiness()['all_ready'])
        self.start()
        for player in self.g._progress.roster()['roster'].values():
            self.assertEqual(player['credits'], 0)
            self.assertTrue(all(level == 1 for level in player['levels'].values()))

    def test_persisted_old_start_lock_is_recovered_on_retry(self):
        self.ready_both()
        self.owner().prepare_game()
        reservation = self.g._journey.start()
        self.assertEqual(self.reservations(), [reservation])
        previous = self.g._journey
        self.g._journey = self.g.Journey(previous.path, previous.module_reader, previous.wake)
        self.assertTrue(self.readiness()['all_ready'])
        self.start()
        self.assertEqual(self.reservations(), [])
        self.assertEqual(len(self.g._progress.roster()['active_attempts']), 1)

    def test_journey_save_failure_does_not_leave_reservation(self):
        self.ready_both()
        with patch.object(self.g._journey, '_save', side_effect=ValueError('injected journey save failure')):
            result = self.command('start', starting_atoms={'green': 100, 'purple': 102})
        self.assertEqual(result.status_code, 400)
        self.assertEqual(self.reservations(), [])
        self.start()

    def test_changed_partner_requires_ready_again(self):
        self.ready_both()
        self.owner().player_command('purple', {'action': 'create', 'name': 'New partner',
                                   'operation_id': 'new-partner', 'event_id': self.event, 'select': True})
        readiness = self.readiness()
        self.assertFalse(readiness['all_ready'])
        self.assertFalse(readiness['players']['green']['ready'])
        self.assertFalse(readiness['players']['purple']['ready'])
        self.ready_both()

    def test_legacy_ack_preserved_but_control_or_loadout_changes_invalidate_new_ack(self):
        self.ready_both()
        snapshot = self.g.game_snapshot()
        state, teams = snapshot['journey'], snapshot['next_loadouts']['teams']
        legacy = copy.deepcopy(state)
        legacy['ready'] = {s: {'id': p['id'], 'revision': 1} for s, p in teams.items()}
        self.assertTrue(self.g.Journey.readiness(legacy, teams)['all_ready'])
        changed = copy.deepcopy(teams)
        changed['purple']['tier'] = 2
        self.assertFalse(self.g.Journey.readiness(state, changed)['players']['purple']['ready'])
        changed = copy.deepcopy(teams)
        changed['green']['levels']['damage-machine-gun'] = 2
        self.assertFalse(self.g.Journey.readiness(state, changed)['players']['green']['ready'])
        changed = copy.deepcopy(teams)
        changed['green']['progression_stage'] = 'calibration_pending'
        self.assertEqual(self.g.Journey.readiness(state, changed)['players']['green']['state'], 'calibration')

    def test_start_cleanup_cannot_release_a_calibration_lock(self):
        self.owner().reserve_lesson_roster({'id': 'shared-lesson'})
        self.owner().release_start_reservation({'id': 'shared-lesson'})
        self.assertEqual(self.reservations('lesson_rosters'), ['shared-lesson'])
        result = self.command('start', starting_atoms={'green': 100, 'purple': 102})
        self.assertEqual(result.status_code, 400)
        self.assertEqual(self.reservations('lesson_rosters'), ['shared-lesson'])
        self.assertEqual(self.g._engine.phase, 'setup')


if __name__ == '__main__':
    unittest.main()
