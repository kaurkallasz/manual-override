"""Practice losses fund upgrades without changing scored progression; isolated stores only."""
import copy
import json
import unittest
import uuid
from unittest.mock import patch
import test_ltz_economy as economy
from test_photon_progress import scored_profile


class PracticeCreditTests(unittest.TestCase):
    setUp=economy.EconomyTests.setUp
    player=economy.EconomyTests.player
    begin_weighted=economy.EconomyTests.begin_weighted
    evidence=economy.EconomyTests.evidence
    buy=economy.EconomyTests.buy

    def loss(self):
        a=self.begin_weighted(False)
        self.store.record(self.evidence(a,grunt=100,brute=10))
        final=self.evidence(a,grunt=300,brute=10,sequence=2,outcome='overrun')
        self.store.record(final,final=True)
        self.store.record(final,final=True)
        return a

    def test_mixed_test_and_real_loss_banks_once_then_buys_retry_loadout(self):
        self.store.select_player('green','ltz-test-green')
        before={s:self.store.snapshot(s)['player'] for s in ('green','purple')}
        a=self.loss();self.store.open_shop({'id':a['run_id']})
        for side in before:
            state=self.store.snapshot(side);p=state['player']
            self.assertEqual((p['credits'],p['lifetime_practice_credits']),(400,400))
            self.assertEqual(scored_profile(p),scored_profile(before[side]))
            self.assertEqual(state['latest_result']['total_earned'],400)
            self.assertTrue(state['latest_result']['practice'])
            self.store.mutate_player(side,{'action':'purchase','track':'damage-machine-gun','level':2,
                'revision':p['revision'],'catalog_revision':state['shop']['catalog_revision'],'operation_id':uuid.uuid4().hex})
        retry=self.begin_weighted(False)
        self.assertTrue(all(p['levels']['damage-machine-gun']==2 for p in retry['participants']))
        self.assertEqual(self.store.history(None,{'combined':True})['total'],0)
        self.assertEqual(self.store.history(None,{'combined':True,'dataset':'practice'})['rows'][0]['total_earned'],400)

    def test_real_player_practice_shop_stays_open_and_wallet_survives_restart(self):
        a=self.loss();w=self.store.open_shop({'id':a['run_id']})
        self.assertTrue(w['practice']);self.assertIsNone(w['deadline'])
        self.store=type(self.store)(self.store.path);self.store.initialize()
        with patch('ltz_economy.time.time',return_value=w['opened_at']+86400):
            self.assertEqual(self.buy('damage-machine-gun',2)['balance'],150)

    def test_recovery_and_late_final_only_pay_new_practice_kills(self):
        a=self.begin_weighted(False);self.store.record(self.evidence(a))
        self.store.recover();self.store.recover()
        final=self.evidence(a,grunt=130,brute=7,sequence=4,outcome='won')
        self.store.record(final,final=True);self.store.record(final,final=True)
        p=self.player()
        self.assertEqual((p['credits'],p['lifetime_practice_credits'],p['wins'],p['attempts']),(200,200,0,0))
        self.assertEqual(self.store.snapshot('green')['latest_result']['stack_bonus'],0)

    def test_legacy_practice_stays_unbanked_on_replay_and_restart(self):
        a=self.begin_weighted(False)
        with self.store.transaction(write=True) as db:
            a.pop('practice_credits_enabled')
            db.execute('UPDATE attempts SET data=? WHERE id=?',(json.dumps(a),a['run_id']))
        final=self.evidence(a,outcome='overrun');self.store.record(final,final=True)
        self.store.initialize();self.store.record(final,final=True)
        self.assertEqual(self.player()['credits'],0)
        self.assertEqual(self.store.snapshot('green')['latest_result']['total_earned'],0)

    def test_practice_backup_restores_and_rejects_forged_totals_or_policy(self):
        self.store.select_player('green','ltz-test-green')
        a=self.loss();self.store.open_shop({'id':a['run_id']});self.buy('damage-machine-gun',2)
        backup=self.store.export()
        other=type(self.store)(self.store.path.with_name('restored.sqlite3'));other.initialize();other.import_backup(backup)
        other.select_player('green','ltz-test-green')
        self.assertEqual(other.snapshot('green')['player'],self.player())
        for field in ('lifetime_practice_credits','credits'):
            broken=copy.deepcopy(backup)
            row=next(r for r in broken['tables']['players'] if r['id']=='ltz-test-green')
            p=json.loads(row['data']);p[field]+=1;row['data']=json.dumps(p)
            target=type(self.store)(self.store.path.with_name(field+'.sqlite3'));target.initialize()
            with self.assertRaises(ValueError):target.import_backup(broken)
        broken=copy.deepcopy(backup);row=broken['tables']['attempts'][0]
        a=json.loads(row['data']);a.pop('practice_credits_enabled');row['data']=json.dumps(a)
        target=type(self.store)(self.store.path.with_name('policy.sqlite3'));target.initialize()
        with self.assertRaisesRegex(ValueError,'practice credits'):target.import_backup(broken)


class PracticeShopFlowTests(unittest.TestCase):
    def test_real_player_loss_purchase_and_next_match_use_saved_upgrade(self):
        import tempfile
        from mobile_ltz_fixture import create_app
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
        app,game=create_app(folder.name);self.addCleanup(app.config['fixture_cleanup']);self.addCleanup(game.hub_stop)
        game._engine.stop_background();game._engine.set_virtual_test_loadout(None,None)
        progress=game._module('photon-progress')
        state=game.apply_command({'action':'start','virtual_play':True,'reward_enabled':False})
        run=state['run_id'];engine=game._engine
        for _ in range(300):engine.rewards.killed({'enemy_type':'grunt'})
        engine.kills=300;engine.sim_time=200;engine.core_hp=0;engine.phase='overrun'
        game._progress.flush();game._journey.tick()
        state=game.game_snapshot()
        self.assertEqual((state['journey']['phase'],state['result_save']['status']),('upgrades','saved'))
        self.assertIsNone(state['journey']['deadline'])
        p=progress.progress_snapshot({'side':'green'})
        progress.player_command('green',{'action':'purchase','track':'damage-machine-gun','level':2,
            'revision':p['player']['revision'],'catalog_revision':p['shop']['catalog_revision'],'operation_id':uuid.uuid4().hex})
        game.apply_command({'action':'next_level','run_id':run})
        game.apply_command({'action':'next_level','run_id':run})
        state=game.apply_command({'action':'start','virtual_play':True,'reward_enabled':False})
        self.assertEqual(state['player_progression']['green']['levels']['damage-machine-gun'],2)
        p=progress.progress_snapshot({'side':'green'})['player']
        self.assertEqual((p['credits'],p['wins'],p['current_control_tier']),(50,0,1))


if __name__=='__main__':unittest.main()
