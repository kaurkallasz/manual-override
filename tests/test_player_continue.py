"""Player-owned continuation through the real Game/Progress APIs; fake arms only."""
import copy
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import test_event_game as fixture
from test_control_journey import CalFixture


class PlayerContinueTests(unittest.TestCase):
    setUp = fixture.EventGameTests.setUp
    command = fixture.EventGameTests.command
    start = fixture.EventGameTests.start

    def finish(self):
        engine = self.g._engine
        with engine.lock:
            engine.phase = 'won'
            engine.rewards.victory_method = 'center_stack'
            engine.telemetry['core_health_at_stack'] = {'hp': engine.core_hp, 'max_hp': engine.core_max_hp}
        self.g._progress.flush()
        return self.g._run_id

    def ready(self, side, run):
        return self.g.mobile_journey_command(side, {'action': 'ready', 'event_id': self.event, 'run_id': run})

    def test_both_continue_start_once_with_saved_progress_and_countdown(self):
        run = self.start(); self.finish()
        before = self.g._progress.roster()
        self.ready('green', run)
        self.assertEqual(self.g._engine.phase, 'won')
        self.assertEqual(self.g._run_id, run)
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda _: self.ready('purple', run), range(4)))
        next_run = self.g._run_id
        self.assertNotEqual(next_run, run)
        state = self.g.game_snapshot()
        self.assertEqual(state['phase'], 'running')
        self.assertEqual(state['contract_control_tier'], 2)
        self.assertEqual(state['start_countdown']['duration_s'], 5)
        after = self.g._progress.roster()
        self.assertEqual(before['saved_games']['active_id'], after['saved_games']['active_id'])
        self.assertEqual(len(after['active_attempts']), 1)
        for side in ('green', 'purple'):
            for field in ('credits', 'levels', 'wins'):
                self.assertEqual(before['roster'][side][field], after['roster'][side][field])
        self.ready('green', run)
        self.assertEqual(self.g._run_id, next_run)

    def test_old_result_or_event_cannot_mark_the_next_result_ready(self):
        run = self.start(); self.finish()
        self.ready('green', run); self.ready('purple', run)
        self.finish()
        with self.assertRaisesRegex(ValueError, 'result changed'):
            self.ready('green', run)
        with self.assertRaisesRegex(ValueError, 'Event changed'):
            self.g.mobile_journey_command('green', {'action': 'ready', 'event_id': 'old-event', 'run_id': self.g._run_id})
        self.assertEqual(self.g._journey.snapshot()['ready'], {})

    def test_saved_results_can_continue_after_the_battlefield_was_reset(self):
        run = self.start(); self.finish()
        self.g._engine.reset(); self.g._run_id = None
        self.ready('green', run); self.ready('purple', run)
        self.assertEqual(self.g._engine.phase, 'running')
        self.assertEqual(self.g.game_snapshot()['contract_control_tier'], 2)

    def test_stop_failure_preserves_field_and_can_be_retried_from_either_phone(self):
        run = self.start(); self.finish(); self.ready('green', run)
        with patch.object(self.g, '_stop_for_saved_game', side_effect=ValueError('arm stop pending')):
            with self.assertRaisesRegex(ValueError, 'arm stop pending'):
                self.ready('purple', run)
        self.assertEqual(self.g._run_id, run)
        self.assertEqual(self.g._engine.phase, 'won')
        self.ready('green', run)
        self.assertEqual(self.g._engine.phase, 'running')

    def test_camera_failure_is_visible_and_requires_explicit_phone_retry(self):
        run = self.start(); self.finish(); self.ready('green', run)
        self.c.post('/__test/camera', json={'stale': True})
        with self.assertRaisesRegex(ValueError, 'Next level could not start'):
            self.ready('purple', run)
        self.assertEqual(self.g._engine.phase, 'setup')
        self.assertTrue(self.g._journey.snapshot()['auto_start']['error'])
        self.assertEqual(self.g._progress.roster()['active_attempts'], [])
        self.c.post('/__test/camera', json={'stale': False})
        self.g._journey_tick()
        self.assertEqual(self.g._engine.phase, 'setup')
        self.ready('green', run)
        self.assertEqual(self.g._engine.phase, 'running')

    def test_unsaved_result_never_resets_or_starts(self):
        run = self.start()
        owner = self.g._module('photon-progress')
        with patch.object(owner, 'finalize_attempt', side_effect=ValueError('save unavailable')):
            with self.assertRaises(ValueError): self.finish()
            with self.assertRaisesRegex(ValueError, 'finish saving'):
                self.ready('green', run)
        self.assertEqual(self.g._run_id, run)
        self.assertEqual(self.g._engine.phase, 'won')
        self.assertEqual(self.g._journey.snapshot()['ready'], {})

    def restart_after_interruption(self, outcome=None):
        run = self.start()
        engine = self.g._engine
        with engine.lock:
            for _ in range(13):
                engine.rewards.killed({'enemy_type':'grunt','hp':0,'x':400,'y':250,'kill_owner':'green'})
                engine.kills += 1
                engine.next_enemy_id += 1
        # A crash keeps the last checkpoint; a clean shutdown saves a terminal
        # receipt. Neither path grants a win or advances the saved level.
        self.g._progress.last_checkpoint = 0
        self.g._progress.flush(outcome=outcome)
        before = copy.deepcopy(self.g._progress.roster())
        old = self.g._progress
        old.stop()
        self.g._progress = self.g.ProgressLink(old.module_reader, old.engine_reader,
            old.wake, old.path, old.result_listener, old.tick)
        journey = self.g._journey
        self.g._journey = self.g.Journey(journey.path, journey.module_reader, journey.wake)
        engine.reset(); self.g._run_id = None
        self.g._progress.roster()
        self.g._journey_tick()
        return run, before

    def assert_recovered_retry(self, outcome=None):
        run, before = self.restart_after_interruption(outcome)
        owner = self.g._module('photon-progress')
        self.assertEqual(owner.attempt_snapshot(run)['attempt']['outcome'], outcome or 'interrupted')
        for side in ('green', 'purple'):
            # Refresh reads only state; it must not acknowledge or start a run.
            state = self.c.get('/s/gamemaster/p/mobile-ltz-api/api/state?side='+side).get_json()
            self.assertEqual(state['journey']['phase'], 'results')
            self.assertTrue(state['mobile_progress']['latest_result']['saved'])
            self.assertEqual(state['journey']['ready'], {})
        self.ready('green', run)
        self.assertEqual(self.g._engine.phase, 'setup')
        self.ready('purple', run)
        new_run = self.g._run_id
        self.assertNotEqual(new_run, run)
        self.assertEqual(self.g._engine.phase, 'running')
        after = self.g._progress.roster()
        self.assertEqual(after['saved_games']['active_id'], before['saved_games']['active_id'])
        self.assertEqual(after['saved_games']['active']['level'], 1)
        self.assertEqual(len(after['active_attempts']), 1)
        for side in ('green', 'purple'):
            self.assertEqual(after['roster'][side]['credits'], 13)
            for key in ('credits', 'wins', 'levels'):
                self.assertEqual(after['roster'][side][key], before['roster'][side][key])
        self.ready('purple', run)
        self.assertEqual(self.g._run_id, new_run)

    def test_saved_interruption_can_retry_same_level_after_restart_and_refresh(self):
        self.assert_recovered_retry('interrupted')

    def test_crash_checkpoint_can_retry_same_level_after_restart_and_refresh(self):
        self.assert_recovered_retry()

    def test_saved_abort_can_retry_same_level_after_restart_and_refresh(self):
        self.assert_recovered_retry('aborted')

    def test_recovered_result_for_other_pair_or_event_cannot_mark_ready(self):
        run, _ = self.restart_after_interruption('interrupted')
        owner = self.g._module('photon-progress')
        original = owner.attempt_snapshot(run)
        for key in ('event_id', 'game_id'):
            receipt = copy.deepcopy(original); receipt['attempt'][key] = 'other'
            with self.subTest(key=key), patch.object(owner, 'attempt_snapshot', return_value=receipt):
                with self.assertRaisesRegex(ValueError, 'another saved pair or event'):
                    self.ready('green', run)
            self.assertEqual(self.g._journey.snapshot()['ready'], {})
            self.assertEqual(self.g._engine.phase, 'setup')

    def test_disagreement_keeps_choices_until_both_choose_the_same_action(self):
        run, _ = self.restart_after_interruption('interrupted')
        selections = {}
        for side, choice in (('green','continue'), ('purple','replay_level'),
                             ('green','new'), ('purple','continue')):
            selections[side] = choice
            self.g.mobile_journey_command(side, {'action':'ready','choice':choice,
                                                'event_id':self.event,'run_id':run})
            for viewer in ('green','purple'):
                state = self.c.get('/s/gamemaster/p/mobile-ltz-api/api/state?side='+viewer).get_json()
                self.assertEqual({s:a['choice'] for s,a in state['journey']['ready'].items()}, selections)
                self.assertFalse(state['journey']['readiness']['all_ready'])
                self.assertEqual(state['journey']['phase'], 'results')
                self.assertIsNone(state['journey']['auto_start'])
            self.assertEqual(self.g._engine.phase, 'setup')
            self.assertEqual(self.g._progress.roster()['active_attempts'], [])
        self.ready('green', run)
        self.assertEqual(self.g._engine.phase, 'running')
        new_run = self.g._run_id
        self.ready('purple', run)
        self.assertEqual(self.g._run_id, new_run)
        self.assertEqual(len(self.g._progress.roster()['active_attempts']), 1)

    def prepare_l3(self):
        self.start()
        run = self.finish(); self.ready('green', run); self.ready('purple', run)
        run = self.finish()
        cal = CalFixture()
        self.g._hub_ctx.modules['auto-pickup-game'] = cal
        self.ready('green', run)
        self.assertEqual(self.g._journey.snapshot()['phase'], 'results')
        self.ready('purple', run)
        self.assertEqual(self.g._journey.snapshot()['phase'], 'calibration')
        self.assertEqual(self.g._engine.phase, 'setup')
        return run, cal

    def test_required_calibration_retains_both_consents_then_auto_starts_l3(self):
        run, cal = self.prepare_l3()
        # The stored continuation survives a Journey reload, but cannot skip a turn.
        old = self.g._journey
        self.g._journey = self.g.Journey(old.path, old.module_reader, old.wake)
        self.ready('purple', run)  # Delayed Continue is harmless during calibration.
        self.g._journey_tick()
        self.assertEqual(self.g._engine.phase, 'setup')
        self.g.mobile_journey_command('green', {'action': 'complete'})
        self.assertEqual(self.g._engine.phase, 'setup')
        self.g.mobile_journey_command('purple', {'action': 'complete'})
        self.assertEqual(self.g._engine.phase, 'running')
        self.assertEqual(self.g.game_snapshot()['contract_control_tier'], 3)
        self.assertEqual(cal.order, ['green', 'purple'])
        self.assertIsNone(self.g._journey.snapshot()['auto_start'])

    def test_operator_cancel_removes_queued_automatic_start(self):
        self.prepare_l3()
        self.assertEqual(self.command('journey_cancel').status_code, 200)
        self.assertIsNone(self.g._journey.snapshot()['auto_start'])
        self.g._journey_tick()
        self.assertNotEqual(self.g._engine.phase, 'running')

    def test_changed_pair_or_loadout_cannot_use_previous_consent(self):
        run = self.start(); self.finish(); self.ready('green', run)
        self.c.post('/__test/camera', json={'stale': True})
        with self.assertRaises(ValueError): self.ready('purple', run)
        state = self.g._journey.snapshot()
        context = copy.deepcopy(state['auto_start']); context.pop('error')
        context['players']['green']['id'] = 'other-player'
        self.g._journey.queue_start(context)
        self.c.post('/__test/camera', json={'stale': False})
        self.g._journey_tick()
        self.assertEqual(self.g._engine.phase, 'setup')
        self.assertIn('both players must press Ready', self.g._journey.snapshot()['auto_start']['error'])


if __name__ == '__main__':
    unittest.main()
