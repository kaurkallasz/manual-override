"""Result choices and spatial evidence through real owners, with fake hardware."""
import copy
from pathlib import Path
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import test_player_continue as continuation
from test_control_journey import CalFixture
import test_level_results as result_tests


class ResultChoiceTests(unittest.TestCase):
    setUp=continuation.PlayerContinueTests.setUp
    command=continuation.PlayerContinueTests.command
    start=continuation.PlayerContinueTests.start
    finish=continuation.PlayerContinueTests.finish
    ready=continuation.PlayerContinueTests.ready
    restart_after_interruption=continuation.PlayerContinueTests.restart_after_interruption

    def choose(self,side,run,choice):
        return self.g.mobile_journey_command(side,dict(action='ready',run_id=run,event_id=self.event,choice=choice))

    def recovered_replay(self, outcome, choice):
        run, before = self.restart_after_interruption(outcome)
        self.choose('green', run, 'continue')
        self.choose('purple', run, choice)
        self.assertEqual(self.g._engine.phase, 'setup')
        self.assertIsNone(self.g._journey.snapshot()['auto_start'])
        self.choose('green', run, choice)
        self.assertEqual(self.g._engine.phase, 'running')
        self.assertEqual(self.g.game_snapshot()['contract_control_tier'], 1)
        after = self.g._progress.roster()
        self.assertNotEqual(after['saved_games']['active_id'], before['saved_games']['active_id'])
        for side in ('green', 'purple'):
            for key in ('id', 'credits', 'wins', 'levels'):
                self.assertEqual(after['roster'][side][key], before['roster'][side][key])
        replay = self.g._run_id
        self.choose('purple', run, choice)
        self.assertEqual(self.g._run_id, replay)
        self.assertEqual(len(self.g._progress.roster()['active_attempts']), 1)

    def test_interrupted_disagreement_can_match_replay_level(self):
        self.recovered_replay('interrupted', 'replay_level')

    def test_interrupted_disagreement_can_match_replay_game(self):
        self.recovered_replay('interrupted', 'replay_game')

    def test_aborted_disagreement_can_match_replay_level(self):
        self.recovered_replay('aborted', 'replay_level')

    def test_aborted_disagreement_can_match_replay_game(self):
        self.recovered_replay('aborted', 'replay_game')

    def l4_result(self):
        self.start()
        cal=CalFixture();self.g._hub_ctx.modules['auto-pickup-game']=cal
        for level in range(1,4):
            run=self.finish();self.ready('green',run);self.ready('purple',run)
            if self.g._journey.snapshot()['phase']=='calibration':
                self.g.mobile_journey_command('green',{'action':'complete'})
                self.g.mobile_journey_command('purple',{'action':'complete'})
            self.assertEqual(self.g.game_snapshot()['contract_control_tier'],level+1)
        return self.finish()

    def test_final_win_waits_for_explicit_matching_replay_choices(self):
        run=self.l4_result();before=self.g._progress.roster()
        self.assertTrue(self.g._journey.snapshot()['game_complete'])
        with self.assertRaisesRegex(ValueError,'Game Over'):self.ready('green',run)
        self.assertEqual(self.command('next_match').status_code,400)
        self.choose('green',run,'replay_level');self.choose('purple',run,'replay_game')
        self.assertEqual(self.g._engine.phase,'won')
        with ThreadPoolExecutor(max_workers=3) as pool:
            list(pool.map(lambda _:self.choose('purple',run,'replay_level'),range(3)))
        self.assertEqual(self.g._engine.phase,'running')
        self.assertEqual(self.g.game_snapshot()['contract_control_tier'],4)
        self.assertEqual(self.g.game_snapshot()['start_countdown']['duration_s'],5)
        after=self.g._progress.roster()
        self.assertNotEqual(after['saved_games']['active_id'],before['saved_games']['active_id'])
        self.assertEqual(len(after['active_attempts']),1)
        for side in ('green','purple'):
            for field in ('credits','levels','wins','attempts'):
                self.assertEqual(before['roster'][side][field],after['roster'][side][field])

    def test_replay_last_level_restores_played_level_not_unlocked_next(self):
        run=self.start();self.finish()
        self.assertEqual(self.g._progress.roster()['saved_games']['active']['level'],2)
        self.choose('green',run,'replay_level');self.choose('purple',run,'replay_level')
        self.assertEqual(self.g.game_snapshot()['contract_control_tier'],1)
        self.assertEqual(self.g._engine.phase,'running')
        heatmap=self.g._engine.rewards.heatmap.snapshot()
        self.assertEqual(sum(heatmap['counts'])+heatmap['unlocated'],0)

    def test_whole_game_replay_retains_pair_and_new_game_clears_selection(self):
        run=self.l4_result();before=self.g._progress.roster()
        self.choose('green',run,'replay_game');self.choose('purple',run,'replay_game')
        self.assertEqual(self.g.game_snapshot()['contract_control_tier'],1)
        after=self.g._progress.roster()
        for side in ('green','purple'):
            for field in ('id','credits','wins','attempts'):
                self.assertEqual(before['roster'][side][field],after['roster'][side][field])
            self.assertEqual(after['roster'][side]['levels']['forcefield'],1)
        run=self.finish();total=self.g._module('photon-progress').event_results_snapshot({'event_id':self.event})['results']['total']
        self.choose('green',run,'new');self.choose('purple',run,'new');self.choose('green',run,'new')
        self.assertEqual(self.g._progress.roster()['roster'],{})
        self.assertEqual(self.g._journey.snapshot()['phase'],'lobby')
        self.assertEqual(self.g._module('photon-progress').event_results_snapshot({'event_id':self.event})['results']['total'],total)

    def test_saved_heatmap_and_replay_survive_backup_without_repaying_rewards(self):
        run=self.start();e=self.g._engine
        with e.lock:
            e.sim_time=12.25
            e.rewards.killed({'enemy_type':'grunt','x':400,'y':250,'kill_owner':'green'})
            e.kills=1;e.next_enemy_id=2
        self.finish()
        owner=self.g._module('photon-progress');store=owner._store
        receipt=owner.public_snapshot('green')['latest_result']
        h=receipt['statistics']['kill_heatmap'];self.assertEqual(sum(h['counts']),1)
        self.assertTrue(h['roads']);self.assertTrue(h['markers'])
        self.assertEqual(h['timeline']['events'][0][0],12.25)
        self.assertTrue(h['floor']['layers']);self.assertTrue(h['floor']['assets'])
        self.choose('green',run,'replay_level');self.choose('purple',run,'replay_level');self.finish()
        restored=owner.ProgressStore(Path(self.folder.name)/'restored.db');restored.initialize()
        backup=store.export();restored.import_backup(backup)
        self.assertEqual(restored.event_results(self.event),store.event_results(self.event))
        restored.event_command({'action':'select','event_id':self.event,'operation_id':'select-restored-event'})
        self.assertEqual(restored.history(receipt['player_id'],{})['rows'][0]['kill_heatmap'],h)
        invalid=copy.deepcopy(h);invalid['counts'][0]+=1
        with self.assertRaisesRegex(ValueError,'reconcile'):
            store.record({**store.attempt(run)['result'],'kill_heatmap':invalid},final=True)

    def test_timeline_validation_rejects_invalid_evidence_and_accepts_legacy(self):
        self.start();e=self.g._engine
        for at,enemy in [(1.25,{'enemy_type':'grunt','x':400,'y':250}), (2.5,{'enemy_type':'grunt'})]:
            e.sim_time=at;e.rewards.killed(enemy);e.kills+=1
        h=e.rewards.heatmap.snapshot()
        validate_heatmap=self.g._module('photon-progress').ProgressStore.record.__globals__['validate_heatmap']
        validate_heatmap(h,2,3)
        old=copy.deepcopy(h);del old['timeline'];validate_heatmap(old,2,3)
        for event in [[4,0,1],[float('nan'),0,1],[1,-2,1],[1,576,1],[1,0,0],[1,0,True],[1,0,3]]:
            bad=copy.deepcopy(h);bad['timeline']['events'][0]=event
            with self.subTest(event=event),self.assertRaises(ValueError):validate_heatmap(bad,2,3)
        bad=copy.deepcopy(h);bad['timeline']['events'].reverse()
        with self.assertRaisesRegex(ValueError,'time'):validate_heatmap(bad,2,3)
        bad=copy.deepcopy(h);bad['timeline']['events']*=8192
        with self.assertRaisesRegex(ValueError,'size'):validate_heatmap(bad,2,3)

    def test_replay_stop_failure_and_start_failure_can_retry_without_duplicate_save(self):
        run=self.start();self.finish();self.choose('green',run,'replay_level')
        before=self.g._progress.roster()['saved_games']['active_id']
        with patch.object(self.g,'_stop_for_saved_game',side_effect=ValueError('arm stop pending')):
            with self.assertRaisesRegex(ValueError,'arm stop pending'):self.choose('purple',run,'replay_level')
        self.assertEqual(self.g._progress.roster()['saved_games']['active_id'],before)
        self.c.post('/__test/camera',json={'stale':True})
        with self.assertRaisesRegex(ValueError,'could not start'):self.choose('green',run,'replay_level')
        replay=self.g._progress.roster()['saved_games']['active_id']
        self.c.post('/__test/camera',json={'stale':False})
        self.ready('green',run)
        self.assertEqual(self.g._progress.roster()['saved_games']['active_id'],replay)
        self.assertEqual(self.g._engine.phase,'running')


class HeatmapRingTests(unittest.TestCase):
    setUpClass=classmethod(result_tests.KillOwnershipTests.setUpClass.__func__)
    engine=result_tests.KillOwnershipTests.engine

    def test_heatmap_locates_kills_and_resets(self):
        e=self.engine();e.start();e.start_countdown_remaining_s=0
        e._spawn_enemy('grunt',{});enemy=next(iter(e.enemies.values()))
        enemy.update(x=800,y=450,hp=.01,burn_until=10,burn_damage_per_s=100,burn_owner='green')
        with patch.object(e,'_spawn_due'):
            e.step(.1);e.step(.1)
        h=e.rewards.heatmap.snapshot()
        self.assertEqual(sum(h['counts']),1);self.assertEqual(h['unlocated'],0)
        self.assertEqual(h['counts'][int(450/h['height']*18)*32+int(800/h['width']*32)],1)
        self.assertEqual(h['timeline']['events'][0][0],.1)
        e.reset();self.assertEqual(sum(e.rewards.heatmap.snapshot()['counts']),0)
        self.assertEqual(e.rewards.heatmap.snapshot()['timeline']['events'],[])

    def test_heatmap_timeline_compacts_without_losing_kills_or_showing_them_early(self):
        e=self.engine();h=e.rewards.heatmap
        for i in range(10000):
            cell=i%576
            enemy={'x':(cell%32+.5)*e.level.width/32,'y':(cell//32+.5)*e.level.height/18}
            if i%101==0:enemy={}
            h.killed(enemy,i+.25)
        value=h.snapshot();events=value['timeline']['events']
        self.assertLessEqual(len(events),8192);self.assertGreater(value['timeline']['bin_seconds'],1)
        self.assertEqual(sum(row[2] for row in events),10000)
        rebuilt=[0]*576;unlocated=0
        for at,cell,count in events:
            if cell<0:unlocated+=count
            else:rebuilt[cell]+=count
        self.assertEqual(rebuilt,value['counts']);self.assertEqual(unlocated,value['unlocated'])
        for time in (0,4000,9999.25):
            self.assertLessEqual(sum(n for at,cell,n in events if at<=time),max(0,int(time-.25)+1))
        self.assertEqual(events[-1][0],9999.25)
        events.clear();self.assertTrue(h.snapshot()['timeline']['events'])

    def test_ring_break_locks_center_clears_first_atom_and_repair_announces(self):
        e=self.engine();e.start({'first_wave_delay_s':300})
        for i,marker in enumerate((41,43,42,45,54,46,52,53)):
            e.place(100 if i%2==0 else 102,e.level.socket_by_marker[marker],source='virtual')
        self.assertEqual(e.snapshot()['core_sequence']['ring_notice']['kind'],'activated')
        e.activate_core_tag(100,source='virtual')
        field=e._field_between(*e._ring_pairs(e.ring_socket_ids)[0]);field['broken']=True
        with self.assertRaisesRegex(ValueError,'ring'):e.activate_core_tag(102,source='virtual')
        s=e.snapshot()['core_sequence'];self.assertEqual(s['stage'],'locked')
        self.assertIsNone(s['first_atom_tag_id']);self.assertEqual(s['ring_notice']['kind'],'incomplete')
        seq=s['ring_notice']['sequence'];e._check_ring_integrity()
        self.assertEqual(e.ring_notice['sequence'],seq)
        field['broken']=False;e._evaluate_ring_topology()
        s=e.snapshot()['core_sequence'];self.assertEqual(s['stage'],'ring_ready')
        self.assertEqual(s['ring_notice']['kind'],'activated');self.assertEqual(s['ring_notice']['sequence'],seq+1)


if __name__=='__main__':unittest.main()
