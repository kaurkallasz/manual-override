"""GM Reset through real Game/Progress APIs, temporary storage and fake hardware."""
import copy
import unittest
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
import test_player_continue as flow


class EventResetTests(unittest.TestCase):
    setUp = flow.PlayerContinueTests.setUp
    command = flow.PlayerContinueTests.command
    start = flow.PlayerContinueTests.start
    finish = flow.PlayerContinueTests.finish
    ready = flow.PlayerContinueTests.ready
    prepare_l3 = flow.PlayerContinueTests.prepare_l3

    def request(self, operation='reset-one'):
        return {'action': 'reset', 'event_id': self.event, 'run_id': self.g._run_id,
                'game_id': self.g._progress.roster()['saved_games']['active_id'],
                'reset_generation': self.g._journey.snapshot().get('reset_operation'),
                'operation_id': operation}

    def reset(self, data=None):
        response = self.c.post('/s/gamemaster/p/photon-game/api/command', json=data or self.request())
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()

    def assert_lobby(self):
        state = self.g.game_snapshot()
        self.assertEqual(state['phase'], 'setup')
        self.assertIsNone(state['run_id'])
        self.assertEqual(state['journey']['phase'], 'lobby')
        self.assertEqual(state['journey']['ready'], {})
        self.assertFalse(state['journey'].get('auto_start'))
        roster = self.g._progress.roster()
        self.assertEqual(roster['events']['active_id'], self.event)
        self.assertEqual(roster['roster'], {})
        self.assertEqual(roster['active_attempts'], [])
        self.assertIsNone(roster['saved_games']['active_id'])
        for side in ('green', 'purple'):
            mobile = self.c.get('/s/gamemaster/p/mobile-ltz-api/api/state?side='+side).get_json()
            self.assertIsNone(mobile['mobile_progress']['player'])
            self.assertIsNone(mobile['mobile_progress']['latest_result'])
            self.assertFalse(mobile['mobile_progress']['saved_games']['pair_locked'])

    def select(self, roster):
        owner = self.g._module('photon-progress')
        for side, player in roster.items():
            owner.player_command(side, {'action': 'select', 'event_id': self.event, 'player_id': player['id']})

    def test_running_reset_stops_both_arms_banks_kills_and_unlocks_names(self):
        run = self.start()
        before = self.g._progress.roster()
        engine = self.g._engine
        with engine.lock:
            for _ in range(12):
                enemy = {'enemy_type': 'grunt', 'hp': 1}
                engine._hurt_enemy(enemy, 1, 'green'); engine.rewards.killed(enemy)
            engine.kills = 12
            engine.next_enemy_id = 13
        relay = self.g._module('dobot-mg400-relay')
        with patch.object(relay, 'stop_side', wraps=relay.stop_side) as stop:
            self.reset()
        self.assertEqual([call.args[0] for call in stop.call_args_list], ['green', 'purple'])
        self.assert_lobby()
        owner = self.g._module('photon-progress')
        result = owner.attempt_snapshot(run)['attempt']
        self.assertEqual(result['outcome'], 'aborted')
        self.assertEqual(result['kills'], 12)
        self.assertNotIn('statistics', result)
        self.assertFalse(result.get('unlocks'))
        self.assertGreater(result['kill_credits'], 0)
        self.select(before['roster'])
        after = self.g._progress.roster()
        for side, player in after['roster'].items():
            self.assertEqual(player['credits'], before['roster'][side]['credits']+result['kill_credits'])
            self.assertEqual(player['levels'], before['roster'][side]['levels'])
        self.start()
        self.assertNotEqual(self.g._run_id, run)
        self.assertNotEqual(self.g._progress.roster()['saved_games']['active_id'], before['saved_games']['active_id'])
        self.assertEqual(self.g.game_snapshot()['contract_control_tier'], 1)

    def test_completed_reset_preserves_saved_pair_wallets_upgrades_and_results(self):
        self.start(); self.command('end_match'); self.command('unlock_next_level')
        owner = self.g._module('photon-progress')
        before = self.g._progress.roster()
        results = copy.deepcopy(owner.event_results_snapshot({'event_id': self.event})['results'])
        self.reset(); self.assert_lobby()
        after = self.g._progress.roster()
        self.assertEqual(after['saved_games']['rows'], before['saved_games']['rows'])
        self.assertEqual(owner.event_results_snapshot({'event_id': self.event})['results'], results)
        self.g.saved_game_command('green', {'action': 'load', 'event_id': self.event,
                                           'game_id': before['saved_games']['active_id'],
                                           'operation_id': 'load-after-reset'})
        for side, player in self.g._progress.roster()['roster'].items():
            for field in ('credits', 'levels', 'wins', 'lifetime_kills'):
                self.assertEqual(player[field], before['roster'][side][field])
        self.assertEqual(self.g._progress.roster()['saved_games']['active']['level'], 2)
        self.reset(self.request('reset-again')); self.select(before['roster'])
        self.start()
        self.assertEqual(self.g.game_snapshot()['contract_control_tier'], 1)

    def test_duplicate_reset_cannot_clear_new_selection_or_restart_new_match(self):
        self.start(); before = self.g._progress.roster(); request = self.request()
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda _: self.g.apply_command(request), range(4)))
        self.assert_lobby(); self.select(before['roster'])
        self.reset(request)
        self.assertEqual({s: p['id'] for s, p in self.g._progress.roster()['roster'].items()},
                         {s: p['id'] for s, p in before['roster'].items()})
        with self.assertRaisesRegex(ValueError, 'result changed'):
            self.ready('green', request['run_id'])
        self.assertEqual(self.g._journey.snapshot()['ready'], {})
        self.start(); run = self.g._run_id
        self.reset(request)
        self.assertEqual(self.g._run_id, run)
        self.assertEqual(self.g._engine.phase, 'running')

    def test_stale_context_and_missing_identity_do_not_touch_match(self):
        run = self.start(); request = self.request()
        for field in ('event_id', 'game_id', 'run_id', 'reset_generation', 'operation_id'):
            with self.subTest(field=field):
                value = {**request, field: 'stale'} if field != 'operation_id' else {**request, field: ''}
                with patch.object(self.g, '_stop_for_saved_game') as stop:
                    response = self.c.post('/s/gamemaster/p/photon-game/api/command', json=value)
                self.assertEqual(response.status_code, 400, response.get_json()); stop.assert_not_called()
                self.assertEqual(self.g._run_id, run)

    def test_old_lobby_retry_after_another_reset_cannot_clear_new_names(self):
        players = self.g._progress.roster()['roster']; first = self.request()
        self.reset(first); self.reset(self.request('reset-two')); self.select(players)
        response = self.c.post('/s/gamemaster/p/photon-game/api/command', json=first)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(set(self.g._progress.roster()['roster']), {'green', 'purple'})

    def test_stop_failure_resets_ui_but_persists_motion_inhibit_until_confirmed(self):
        run = self.start(); before = self.g._progress.roster(); request = self.request()
        with self.g._command_lock, patch.object(self.g, '_stop_for_saved_game', side_effect=ValueError('Stop unconfirmed')):
            self.reset(request); self.assert_lobby()
            self.assertTrue(self.g.journey_snapshot()['motion_blocked'])
            self.assertTrue(self.g.motion_policy('purple')['blocked'])
            old=self.g._journey
            self.g._journey=self.g.Journey(old.path,old.module_reader,old.wake)
            self.assertEqual(self.g._journey.snapshot()['reset_stop_error'],'Stop unconfirmed')
            self.select(before['roster'])
            self.assertEqual(self.command('start',starting_atoms={'green':100,'purple':102}).status_code,400)
            self.g._journey_tick()
            self.assertTrue(self.g.journey_snapshot()['motion_blocked'])
        self.g._journey_tick()
        self.assertFalse(self.g.journey_snapshot()['motion_blocked'])
        self.assertEqual(self.g._module('photon-progress').attempt_snapshot(run)['attempt']['outcome'],'aborted')

    def test_reset_and_load_resume_purple_with_same_partial_draft_after_restart(self):
        _,cal=self.prepare_l3()
        self.g.mobile_journey_command('green',{'action':'complete'})
        current=self.g._journey.snapshot()
        self.assertEqual((current['calibration_side'],current['turn']),('purple',1))
        sid=current['session_id']
        cal.state['sessions'][sid].update(captures={'30':123},draft={'points':{'30':{'pose':{'x':300,'y':10,'z':10}}}})
        draft=copy.deepcopy(cal.state['sessions'][sid]['draft'])
        before=self.g._progress.roster();game_id=before['saved_games']['active_id']
        with self.g._command_lock:
            cal.stopped=False
            self.reset();self.assert_lobby()
            self.assertIn('purple',cal.state['pending_stops'])
            old=self.g._journey
            self.g._journey=self.g.Journey(old.path,old.module_reader,old.wake)
            cal.stopped=True
            self.g.saved_game_command('green',{'action':'load','event_id':self.event,
                                             'game_id':game_id,'operation_id':'reload-partial-calibration'})
            resumed=self.g._journey.snapshot()
            self.assertEqual((resumed['phase'],resumed['calibration_side'],resumed['turn']),('calibration','purple',1))
            self.assertEqual(resumed['session_id'],sid)
            self.assertIsNone(resumed['auto_start'])
            self.assertEqual(cal.state['sessions'][sid]['captures'],{'30':123})
            self.assertEqual(cal.state['sessions'][sid]['draft'],draft)
            self.assertEqual(cal.order,['green','purple','purple'])
            self.assertNotIn('paused_game_calibrations',resumed,'Other saves stay out of the public state')
            self.assertEqual(self.g._progress.roster()['roster']['green']['progression_stage'],'playing')
            self.g.mobile_journey_command('purple',{'action':'complete'})
            self.assertEqual(self.g._journey.snapshot()['phase'],'ready')
            self.assertEqual(self.g._engine.phase,'setup','Loading does not reuse consent from before Reset')

    def test_disconnected_arm_cannot_clear_reset_stop_inhibit(self):
        self.start()
        relay=self.g._module('dobot-mg400-relay')
        snapshot=relay.arms_snapshot
        def disconnected():
            value=snapshot()
            for arm in value['arms'].values():arm['connected']=False
            return value
        with self.g._command_lock, patch.object(relay,'arms_snapshot',side_effect=disconnected), patch.object(relay,'stop_side',return_value={'contract':'hhh.relay.stop','version':1,'status':'unavailable','stopped':False}):
            self.reset();self.assert_lobby()
            self.g._journey_tick()
            self.assertTrue(self.g.motion_policy('green')['blocked'])
        self.g._journey_tick()
        self.assertFalse(self.g.motion_policy('green')['blocked'])

    def test_purple_calibration_reset_does_not_require_disconnected_completed_green(self):
        _,cal=self.prepare_l3()
        self.g.mobile_journey_command('green',{'action':'complete'})
        game_id=self.g._progress.roster()['saved_games']['active_id']
        relay=self.g._module('dobot-mg400-relay');snapshot=relay.arms_snapshot
        def only_purple():
            value=snapshot();value['arms']['green']['connected']=False
            return value
        with self.g._command_lock, patch.object(relay,'arms_snapshot',side_effect=only_purple), patch.object(relay,'stop_side',wraps=relay.stop_side) as stop:
            self.reset();self.assert_lobby()
            self.assertEqual([c.args[0] for c in stop.call_args_list],['purple'])
            self.assertEqual(self.g._journey.snapshot()['reset_stop_sides'],[])
            self.g.saved_game_command('purple',{'action':'load','event_id':self.event,
                                              'game_id':game_id,'operation_id':'purple-only-load'})
            self.assertEqual(self.g._journey.snapshot()['active_side'],'purple')
            self.assertFalse(self.g.motion_policy('purple')['blocked'])
            self.assertNotIn('green',[c.args[0] for c in stop.call_args_list])

    def test_confirmed_reset_stop_is_not_requested_again_after_that_arm_disconnects(self):
        self.start();relay=self.g._module('dobot-mg400-relay');snapshot=relay.arms_snapshot
        connected={'green':True,'purple':True};settled={'green':True,'purple':False}
        def arms():
            value=snapshot()
            for side,arm in value['arms'].items():arm['connected']=connected[side]
            return value
        def stop(side):return {'contract':'hhh.relay.stop','version':1,'status':'ready','stopped':settled[side]}
        with self.g._command_lock, patch.object(relay,'arms_snapshot',side_effect=arms), patch.object(relay,'stop_side',side_effect=stop) as stops:
            self.reset()
            self.assertEqual(self.g._journey.snapshot()['reset_stop_sides'],['purple'])
            old=self.g._journey
            self.g._journey=self.g.Journey(old.path,old.module_reader,old.wake)
            connected['green']=False;settled['green']=False;stops.reset_mock()
            self.g._journey_tick()
            self.assertEqual([c.args[0] for c in stops.call_args_list],['purple'])
            self.assertTrue(self.g.motion_policy('purple')['blocked'])
            settled['purple']=True;self.g._journey_tick()
            self.assertFalse(self.g.motion_policy('purple')['blocked'])

    def test_other_games_do_not_inherit_paused_calibration(self):
        self.prepare_l3();before=self.g._progress.roster()
        self.reset();self.assert_lobby()
        self.select(before['roster']);self.start()
        self.assertEqual(self.g._journey.snapshot()['phase'],'playing')
        self.assertNotEqual(self.g._progress.roster()['saved_games']['active_id'],before['saved_games']['active_id'])
        self.assertEqual(self.g.game_snapshot()['contract_control_tier'],1)

    def test_load_without_checkpoint_recovers_purple_from_green_completion_receipt(self):
        _,cal=self.prepare_l3()
        self.g.mobile_journey_command('green',{'action':'complete'})
        current=self.g._journey.snapshot();sid=current['session_id']
        cal.state['sessions'][sid].update(captures={'30':123},draft={'points':{'30':{'pose':{'x':300,'y':10,'z':10}}}})
        game_id=self.g._progress.roster()['saved_games']['active_id']
        with self.g._command_lock:
            # Older resets did not write a Journey checkpoint. The saved game's
            # Green completion receipt still identifies the original session.
            with patch.object(self.g._journey,'checkpoint_calibration'):
                self.reset()
            self.g.saved_game_command('purple',{'action':'load','event_id':self.event,
                                              'game_id':game_id,'operation_id':'legacy-load'})
            self.g._journey_tick()
            resumed=self.g._journey.snapshot()
            self.assertEqual((resumed['calibration_side'],resumed['turn']),('purple',1))
            self.assertEqual(resumed['session_id'],sid)
            self.assertEqual(cal.state['sessions'][sid]['captures'],{'30':123})
            self.assertEqual(cal.order,['green','purple','purple'])

    def test_existing_wrong_green_turn_recovers_before_unconfirmed_stop(self):
        _,cal=self.prepare_l3()
        self.g.mobile_journey_command('green',{'action':'complete'})
        current=self.g._journey.snapshot();sid=current['session_id']
        cal.state['sessions'][sid]['captures']={'30':123}
        with self.g._command_lock:
            cal.stopped=False
            self.g._journey.cancel(defer_stop=True)
            broken=self.g._journey._state()
            broken.update(phase='calibration',id='resume:legacy-load',queue=['green','purple'],turn=0,active_side=None)
            broken.pop('deferred_calibration',None)
            self.g._journey._save(broken)
            old=self.g._journey
            self.g._journey=self.g.Journey(old.path,old.module_reader,old.wake)
            self.g._journey_tick()
            repaired=self.g._journey.snapshot()
            self.assertEqual((repaired['calibration_side'],repaired['turn'],repaired['id']),('purple',1,current['id']))
            self.assertIsNone(repaired['active_side'])
            self.assertIn('previous stop',repaired['error'])
            self.assertEqual(cal.state['sessions'][sid]['captures'],{'30':123})
            cal.stopped=True
            self.g._journey_tick()
            self.assertEqual(self.g._journey.snapshot()['session_id'],sid)
            self.assertEqual(cal.order,['green','purple','purple'])

    def test_completed_green_is_skipped_without_matching_old_draft(self):
        _,cal=self.prepare_l3()
        self.g.mobile_journey_command('green',{'action':'complete'})
        sid=self.g._journey.snapshot()['session_id']
        game_id=self.g._progress.roster()['saved_games']['active_id']
        with self.g._command_lock:
            with patch.object(self.g._journey,'checkpoint_calibration'):
                self.reset()
            # A different player's draft is never adopted merely because its
            # session prefix matches Green's completion receipt.
            cal.state['sessions'][sid]['player_id']='other-player'
            self.g.saved_game_command('purple',{'action':'load','event_id':self.event,
                                              'game_id':game_id,'operation_id':'legacy-no-draft'})
            self.g._journey_tick()
            self.assertEqual(self.g._journey.snapshot()['calibration_side'],'purple')
            self.assertNotEqual(self.g._journey.snapshot()['session_id'],sid)
            self.assertEqual(cal.order,['green','purple','purple'])

    def test_save_failure_does_not_discard_pair_or_pending_result(self):
        run = self.start(); before = self.g._progress.roster(); request = self.request()
        owner = self.g._module('photon-progress')
        with patch.object(owner, 'finalize_attempt', side_effect=ValueError('Disk unavailable')):
            response = self.c.post('/s/gamemaster/p/photon-game/api/command', json=request)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.g._run_id, run)
        self.assertTrue(self.g._engine.paused)
        self.assertEqual(self.g._progress.roster()['roster'], before['roster'])
        self.assertTrue(self.g._progress.path.exists())
        self.reset(request); self.assert_lobby()

    def test_reset_cancels_calibration_and_queued_automatic_start(self):
        _, cal = self.prepare_l3()
        before = self.g._progress.roster()
        self.reset(); self.assert_lobby()
        self.assertIsNone(cal.state['active_side'])
        self.g._journey_tick(); self.assert_lobby()
        self.select(before['roster']); self.g._journey_tick()
        self.assertEqual(self.g._journey.snapshot()['phase'], 'lobby')
        for side, player in self.g._progress.roster()['roster'].items():
            self.assertEqual(player['current_control_tier'], 1)
            self.assertEqual(player['progression_stage'], 'playing')
            self.assertEqual(player['levels']['forcefield'], 1)
            self.assertEqual(player['credits'], before['roster'][side]['credits'])
        saved = next(row for row in self.g._progress.roster()['saved_games']['rows']
                     if row['id'] == before['saved_games']['active_id'])
        self.assertEqual(saved['level'], 3)
        self.assertTrue(all(member['tier'] == 3 for member in saved['players'].values()))
        self.start()
        self.assertEqual(self.g.game_snapshot()['contract_control_tier'], 1)


if __name__ == '__main__':
    unittest.main()
