"""Operator grants and practice transitions, including retries, restarts and isolation."""
import copy
import json
from pathlib import Path
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import patch
import uuid
from test_photon_framework import load
from test_photon_progress import scored_profile


class AdminTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.progress=load('photon-progress');self.progress.DATA_DIR=Path(self.folder.name)/'progress'
        self.progress.hub_init(None);self.addCleanup(self.progress.hub_stop);self.store=self.progress._store
        self.real=self.store.create_player('Real player',uuid.uuid4().hex)['player_id']
        self.store.select_player('green','ltz-test-green');self.store.select_player('purple',self.real)

    def grant(self, player_id='ltz-test-green', amount=2000, operation_id=None):
        return self.store.grant_credits({'player_id':player_id,'amount':amount,'operation_id':operation_id or uuid.uuid4().hex})

    def finish(self):
        a=self.store.begin({'run_id':uuid.uuid4().hex,'metadata':{},'reward_enabled':True})
        return self.store.record({'run_id':a['run_id'],'sequence':1,'kills':50,'outcome':'aborted','active_seconds':10,'finished_at':time.time(),'released_orcs':50},final=True)

    def buy(self,side='green',track='damage-machine-gun',level=2):
        s=self.store.snapshot(side)
        return self.store.mutate_player(side,{'action':'purchase','track':track,'level':level,
               'revision':s['player']['revision'],'catalog_revision':s['shop']['catalog_revision'],'operation_id':uuid.uuid4().hex})

    def test_grants_retry_and_race_once_without_score_or_mastery(self):
        operation_id=uuid.uuid4().hex
        with ThreadPoolExecutor(max_workers=4) as executor:
            results=list(executor.map(lambda _:self.grant(self.real,1000,operation_id),range(4)))
        self.assertTrue(all(r==results[0] for r in results))
        with self.assertRaises(ValueError):self.grant(self.real,1001,operation_id)
        p=self.store.snapshot('purple')['player']
        self.assertEqual((p['credits'],p['lifetime_granted_credits']),(1000,1000))
        for key in ('lifetime_kills','lifetime_score','lifetime_kill_credits','lifetime_bonus_credits','lifetime_credits_earned','wins','attempts'):
            self.assertEqual(p[key],0,key)
        self.assertEqual(p['wins_by_tier'],[0]*4);self.assertEqual(self.store.history(None,{'combined':True})['total'],0)
        self.buy('purple');self.assertEqual(self.store.snapshot('purple')['player']['credits'],750)

    def test_invalid_grants_and_player_api_cannot_grant_or_advance(self):
        for amount in (True,0,-1,1.5,100001,'100'):
            with self.assertRaises(ValueError):self.grant(amount=amount)
        for action in ('grant_credits','advance_test'):
            with self.assertRaises(ValueError):self.progress.player_command('green',{'action':action,'amount':100,'operation_id':uuid.uuid4().hex,'revision':1})
        self.assertEqual(self.store.snapshot('green')['player']['credits'],0)

    def test_test_shop_has_no_deadline_and_advances_only_tests_once(self):
        self.grant();before=self.store.snapshot('purple')['player'];a=self.finish()
        w=self.store.open_shop({'id':a['run_id']});self.assertTrue(w['practice']);self.assertIsNone(w['deadline'])
        with patch('time.time',return_value=w['opened_at']+86400):self.buy()
        self.assertEqual(self.store.snapshot('green')['player']['credits'],1800)
        self.assertEqual(self.store.snapshot('green')['player']['levels']['damage-machine-gun'],2)
        r=self.store.advance_test({'run_id':a['run_id']})
        self.assertEqual(r['tier'],2);self.assertEqual(self.store.advance_test({'run_id':a['run_id']}),r)
        self.assertEqual(scored_profile(self.store.snapshot('purple')['player']),scored_profile(before))
        self.assertEqual(self.store.snapshot('purple')['player']['credits'],50)
        for _ in range(4):
            a=self.finish();self.store.open_shop({'id':a['run_id']});self.store.advance_test({'run_id':a['run_id']})
        p=self.store.snapshot('green')['player']
        self.assertEqual((p['current_control_tier'],p['credits'],p['wins'],p['attempts']),(4,2000,0,0))
        self.assertFalse(p['lesson']['complete']);self.assertEqual(p['progression_stage'],'playing')
        self.assertEqual(self.store.history(None,{'combined':True})['total'],0)
        self.assertEqual(self.store.history(None,{'combined':True,'dataset':'practice'})['total'],5)

    def test_grant_during_match_does_not_change_frozen_loadout_or_earnings(self):
        a=self.store.begin({'run_id':uuid.uuid4().hex,'metadata':{},'reward_enabled':True})
        self.grant();self.grant(self.real)
        self.assertTrue(all(p['levels']['damage-machine-gun']==1 for p in a['participants']))
        with self.assertRaisesRegex(ValueError,'active attempt'):self.buy()
        self.store.record({'run_id':a['run_id'],'sequence':1,'kills':50,'outcome':'aborted','active_seconds':10,'finished_at':time.time(),'released_orcs':50},final=True)
        self.assertTrue(all(p['credits']==2050 and p['lifetime_practice_credits']==50 and p['lifetime_credits_earned']==0 for p in self.store.snapshot()['roster'].values()))

    def test_backup_preview_restart_and_ledger_validation_for_test_and_real_wallets(self):
        self.grant();self.grant(self.real);a=self.finish();self.store.open_shop({'id':a['run_id']});self.buy();self.store.advance_test({'run_id':a['run_id']})
        self.buy('purple');backup=self.store.export()
        other=type(self.store)(Path(self.folder.name)/'restored.sqlite3');other.initialize()
        other.import_backup(backup,preview=True);other.select_player('green','ltz-test-green')
        self.assertEqual(other.snapshot('green')['player']['credits'],0)
        other.import_backup(backup);other.initialize();other.import_backup(backup)
        self.assertEqual(other.snapshot('green')['player'],self.store.snapshot('green')['player'])
        other.select_player('purple',self.real);self.assertEqual(other.snapshot('purple')['player'],self.store.snapshot('purple')['player'])
        for key in ('credits','lifetime_granted_credits','lifetime_kills'):
            broken=copy.deepcopy(backup);row=next(r for r in broken['tables']['players'] if r['id']=='ltz-test-green');p=json.loads(row['data']);p[key]+=1;row['data']=json.dumps(p)
            bad=type(self.store)(Path(self.folder.name)/(key+'.sqlite3'));bad.initialize()
            with self.assertRaises(ValueError):bad.import_backup(broken)

    def test_next_requires_finished_saved_shop_and_original_roster(self):
        a=self.finish()
        with self.assertRaisesRegex(ValueError,'shop'):self.store.advance_test({'run_id':a['run_id']})
        self.store.open_shop({'id':a['run_id']});self.store.select_player('purple',None)
        with self.assertRaisesRegex(ValueError,'players changed'):self.store.advance_test({'run_id':a['run_id']})


class AdminGameTests(unittest.TestCase):
    def setUp(self):
        from mobile_ltz_fixture import create_app
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.app,self.game=create_app(self.folder.name);self.addCleanup(self.app.config['fixture_cleanup']);self.addCleanup(self.game.hub_stop)
        self.game._engine.stop_background();self.progress=self.game._module('photon-progress')
        for side in ('green','purple'):self.progress.player_command(side,{'action':'select','player_id':'ltz-test-'+side})
        self.game._engine.set_virtual_test_loadout(None,None)

    def start(self):
        return self.game.apply_command({'action':'start','virtual_play':True,'reward_enabled':False})

    def test_paused_zero_kill_end_shop_purchase_next_actual_loadout_and_retries(self):
        state=self.start();run=state['run_id'];self.game.apply_command({'action':'pause'})
        for side in ('green','purple'):
            self.progress.admin_command({'action':'grant_credits','player_id':'ltz-test-'+side,'amount':2000,'operation_id':uuid.uuid4().hex})
        state=self.game.apply_command({'action':'test_end_match','run_id':run})
        self.assertEqual((state['phase'],state['journey']['phase'],state['result_save']['status']),('aborted','upgrades','saved'))
        self.assertTrue(self.game.motion_policy('green')['blocked'])
        self.assertIsNone(state['journey']['deadline']);self.game._journey.tick();self.assertEqual(self.game._journey.snapshot()['phase'],'upgrades')
        self.game.apply_command({'action':'test_end_match','run_id':run})
        p=self.progress.progress_snapshot({'side':'green'})
        self.progress.player_command('green',{'action':'purchase','track':'damage-machine-gun','level':2,'operation_id':uuid.uuid4().hex,'revision':p['player']['revision'],'catalog_revision':p['shop']['catalog_revision']})
        result=self.game.apply_command({'action':'test_next_level','run_id':run})
        self.assertEqual((result['phase'],result['journey']['phase']),('setup','lobby'))
        self.assertIsNone(result['virtual_test_loadout']);self.assertIsNone(result['virtual_test_control'])
        self.game.apply_command({'action':'test_next_level','run_id':run})
        state=self.start();self.assertEqual(state['contract_control_tier'],2)
        self.assertEqual(state['player_progression']['green']['levels']['damage-machine-gun'],2)
        with self.assertRaises(ValueError):self.game.apply_command({'action':'test_end_match','run_id':run})
        with self.assertRaises(ValueError):self.game.apply_command({'action':'test_next_level','run_id':run})
        self.assertEqual(self.game._engine.phase,'running')
        self.assertEqual(self.progress._store.history(None,{'combined':True})['total'],0)

    def test_failed_save_keeps_shop_closed_until_durable_retry_succeeds(self):
        run=self.start()['run_id']
        with patch.object(self.progress,'finalize_attempt',side_effect=ValueError('storage offline')):
            with self.assertRaisesRegex(ValueError,'pending save'):
                self.game.apply_command({'action':'test_end_match','run_id':run})
            self.assertEqual(self.game._engine.phase,'aborted')
            self.assertEqual(self.game.game_snapshot()['result_save']['status'],'saving')
            self.assertNotEqual(self.game._journey.snapshot()['phase'],'upgrades')
            self.assertTrue(self.game._progress.path.exists())
            with self.assertRaises(ValueError):self.game.apply_command({'action':'test_next_level','run_id':run})
        self.game.apply_command({'action':'test_end_match','run_id':run})
        self.assertEqual(self.game._journey.snapshot()['phase'],'upgrades')
        self.assertFalse(self.game._progress.path.exists())
        self.game.apply_command({'action':'journey_cancel'})
        self.assertFalse(self.game.motion_policy('green')['blocked'])
        with self.progress._store.transaction() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM shop_windows').fetchone()[0],1)
        self.assertEqual(self.progress._store.history(None,{'combined':True})['total'],0)

    def test_practice_shop_survives_journey_restart(self):
        run=self.start()['run_id'];self.game.apply_command({'action':'test_end_match','run_id':run})
        j=self.game._journey;self.game._journey=type(j)(j.path,j.module_reader,j.wake)
        self.game._journey.tick();self.assertTrue(self.game._journey.snapshot()['practice_shop'])
        self.game._run_id=None;self.game._engine.reset()
        self.game.apply_command({'action':'test_next_level','run_id':run})
        self.assertEqual(self.progress.progress_snapshot({'side':'green'})['player']['current_control_tier'],2)

    def test_start_closes_persisted_practice_shop_without_advancing_tier_or_waiting(self):
        run=self.start()['run_id'];self.game.apply_command({'action':'test_end_match','run_id':run})
        self.game.apply_command({'action':'reset','virtual_play':True})
        self.assertTrue(self.game.game_snapshot()['journey']['practice_shop'])
        state=self.start()
        self.assertEqual((state['phase'],state['journey']['phase'],state['contract_control_tier']),('running','playing',1))
        self.assertFalse(state['journey']['practice_shop'])
        with self.progress._store.transaction() as db:
            import json
            self.assertFalse(json.loads(db.execute('SELECT data FROM shop_windows WHERE id=?',(run,)).fetchone()[0])['active'])

    def test_operator_next_level_advances_without_either_player_ready(self):
        run=self.start()['run_id'];self.game.apply_command({'action':'test_end_match','run_id':run})
        state=self.game.apply_command({'action':'next_level','run_id':run})
        self.assertEqual((state['phase'],state['journey']['phase']),('setup','lobby'))
        self.assertEqual(state['journey']['ready'],{})
        self.assertEqual(self.start()['contract_control_tier'],2)

    def test_scored_match_cannot_use_test_end_and_admin_routes_are_gamemaster_only(self):
        state=self.start()
        self.game._progress.attempt['reward_enabled']=True
        with self.assertRaises(ValueError):self.game.apply_command({'action':'test_end_match','run_id':state['run_id']})
        self.assertEqual(self.game._engine.phase,'running');self.game._progress.attempt['reward_enabled']=False
        # A separate Flask app verifies the real role guard without fixture authentication.
        from flask import Flask
        app=Flask('admin_auth');app.register_blueprint(self.game.bp);client=app.test_client()
        for roles in (set(),{'green'},{'purple'}):
            for method in (client.get,client.post):self.assertEqual(method('/api/player-admin',environ_overrides={'hhh.roles':roles}).status_code,403)
            self.assertEqual(client.post('/api/command',json={'action':'test_end_match','run_id':state['run_id']},environ_overrides={'hhh.roles':roles}).status_code,403)
        self.assertEqual(client.get('/api/player-admin',environ_overrides={'hhh.roles':{'gamemaster'}}).status_code,200)
        self.assertEqual(client.post('/api/player-admin',json={'action':'advance_test'},environ_overrides={'hhh.roles':{'gamemaster'}}).status_code,400)
        import post_match
        for version in (True,'1',2):
            owner=SimpleNamespace(admin_snapshot=lambda:{'contract':'photon.progress.admin','version':version,'status':'ready'})
            with self.assertRaises(ValueError):post_match.admin(lambda slug:owner)

if __name__=='__main__':unittest.main()
