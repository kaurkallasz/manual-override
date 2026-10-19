"""Reward/catalog transactions against isolated SQLite stores; no venue data."""
import copy
import json
import sys
import time
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from test_photon_progress import ProgressTests, module, scored_profile
from test_photon_framework import load

class EconomyTests(unittest.TestCase):
    setUp=ProgressTests.setUp
    player=ProgressTests.player
    start=ProgressTests.start
    finish=ProgressTests.finish

    def begin_weighted(self,scored=True):
        self.rules={'version':1,'revision':'fixture-v1','values':dict(grunt=1,runner=1,breaker=2,brute=10),
                    'scheduled_counts':dict(grunt=900,runner=0,breaker=0,brute=10),'scheduled_value':1000,
                    'bonus':dict(stack_bonus_enabled=1,stack_bonus_fraction=.2,stack_health_exponent=2.,stack_forgone_fraction=.5)}
        return self.store.begin(dict(run_id=uuid.uuid4().hex,reward_enabled=scored,metadata={'reward_rules':self.rules}))

    def evidence(self,a,grunt=80,brute=7,sequence=1,outcome=None,health=1):
        counts=dict(grunt=grunt,runner=0,breaker=0,brute=brute);credits=grunt+brute*10
        bonus=min(int(1000*.2*health**2+1e-9),int((1000-credits)*.5)) if outcome=='won' and a['reward_enabled'] else 0
        r=dict(version=1,revision='fixture-v1',sequence=sequence,counts=counts,combat_kills=counts.copy(),purge_kills=dict.fromkeys(counts,0),kill_credits=credits,stack_bonus=bonus,total_earned=credits+bonus,victory_method='center_stack' if outcome=='won' else None,core_health_at_stack={'hp':health*1000,'max_hp':1000})
        v=dict(run_id=a['run_id'],kills=grunt+brute,sequence=sequence,reward=r)
        if outcome:v.update(outcome=outcome,active_seconds=100,finished_at=time.time(),released_orcs=grunt+brute)
        return v

    def buy(self,track,level,**extra):
        p=self.player();q=self.store.snapshot('green')['shop']
        return self.store.mutate_player('green',dict(action='purchase',track=track,level=level,revision=p['revision'],catalog_revision=q['catalog_revision'],operation_id=uuid.uuid4().hex,**extra))

    def save_prices(self,prices):
        return self.store.save_prices(dict(prices=prices,revision=self.store.economy_snapshot()['revision'],operation_id=uuid.uuid4().hex))

    def test_weighted_delta_87_kills_150_credits_each_and_retry(self):
        a=self.begin_weighted();self.store.record(self.evidence(a,40,2));final=self.evidence(a,sequence=2,outcome='overrun')
        self.store.record(final,final=True);self.store.record(final,final=True)
        for side in ('green','purple'):
            p=self.store.snapshot(side)['player']
            self.assertEqual((p['credits'],p['lifetime_score'],p['lifetime_kills'],p['lifetime_kill_credits'],p['lifetime_bonus_credits']),(150,87,87,150,0))
        receipt=self.store.snapshot('green')['latest_result'];self.assertEqual((receipt['kills'],receipt['total_earned']),(87,150))
        restored=module.ProgressStore(self.store.path.with_name('restored.sqlite3'));restored.initialize();restored.import_backup(self.store.export());restored.select_player('green',self.green)
        self.assertEqual(restored.snapshot('green')['player']['credits'],150)

    def test_bonus_health_cap_and_practice(self):
        for health,expected in [(1,200),(.8,128),(.5,50),(.25,12)]:
            a=self.begin_weighted();final=self.evidence(a,300,10,outcome='won',health=health);self.store.record(final,final=True)
            self.assertEqual(self.store.attempt(a['run_id'])['bonus_credits'],expected)
        a=self.begin_weighted();final=self.evidence(a,800,10,outcome='won');self.store.record(final,final=True)
        self.assertEqual(self.store.attempt(a['run_id'])['bonus_credits'],50)
        before=self.player()['credits'];a=self.begin_weighted(False);self.store.record(self.evidence(a,outcome='won'),final=True)
        self.assertEqual(self.player()['credits'],before+150);self.assertEqual(self.store.snapshot('green')['latest_result']['total_earned'],150)
        self.assertEqual(self.store.snapshot('green')['latest_result']['stack_bonus'],0)

    def test_first_loss_funds_an_upgrade_for_the_retry_without_a_win(self):
        a=self.begin_weighted()
        final=self.evidence(a,grunt=300,brute=0,outcome='overrun')
        self.store.record(final,final=True)
        self.store.record(final,final=True)
        self.store.open_shop({'id':a['run_id']})
        for side in ('green','purple'):
            state=self.store.snapshot(side)
            self.assertEqual((state['player']['credits'],state['player']['wins'],state['player']['attempts']),(300,0,1))
            self.assertEqual(state['latest_result']['total_earned'],300)
            self.assertTrue(next(c for c in state['shop']['cards'] if c['track']=='damage-machine-gun' and c['level']==2)['can_buy'])
        self.assertEqual(self.buy('damage-machine-gun',2)['balance'],50)
        retry=self.begin_weighted()
        green=next(p for p in retry['participants'] if p['side']=='green')
        self.assertEqual(green['levels']['damage-machine-gun'],2)
        self.assertEqual(self.player()['wins'],0)

    def test_forged_reward_and_counts_fail_without_partial_commit(self):
        a=self.begin_weighted()
        for change in [lambda v:v['reward'].update(kill_credits=151),lambda v:v['reward']['counts'].update(brute=8),lambda v:v['reward'].update(revision='changed'),lambda v:v['reward'].update(stack_bonus=999)]:
            v=self.evidence(a,outcome='won');change(v)
            with self.assertRaises(ValueError):self.store.record(v,final=True)
        self.assertEqual(self.player()['credits'],0)
        self.store.recover();self.assertEqual(self.store.attempt(a['run_id'])['outcome'],'interrupted')

    def test_only_practice_can_finish_with_a_changed_spawn_budget(self):
        before=copy.deepcopy(self.player())
        for scored in (False,True):
            a=self.begin_weighted(scored)
            final=self.evidence(a,grunt=1000,brute=10,outcome='overrun')
            if scored:
                with self.assertRaisesRegex(ValueError,'kill counts'):self.store.record(final,final=True)
            else:
                invalid=copy.deepcopy(final);invalid['reward']['kill_credits']+=1
                with self.assertRaisesRegex(ValueError,'weighted credits'):self.store.record(invalid,final=True)
                final['outcome']='won';final['reward']['victory_method']='waves_cleared'
                self.store.record(final,final=True)
                self.assertEqual(self.store.attempt(a['run_id'])['kills'],1010)
        self.assertEqual(scored_profile(self.player()),scored_profile(before))
        self.assertEqual(self.player()['lifetime_practice_credits'],1100)

    def test_recovery_preserves_weighted_checkpoint_and_new_final_pays_once(self):
        a=self.begin_weighted();self.store.record(self.evidence(a));self.store.recover();self.store.recover()
        final=self.evidence(a,sequence=4,outcome='won');self.store.record(final,final=True);self.store.record(final,final=True)
        self.assertEqual(self.player()['credits'],350);self.assertEqual(self.player()['attempts'],1)

    def test_all_fifteen_prices_quote_charge_and_duplicate_receipts(self):
        self.finish(self.start(),kills=100000)
        candidate={t:{str(l):(i+1)*100+l for l in range(2,5)} for i,t in enumerate(module.TRACKS)}
        self.save_prices(candidate);before=self.player()['credits']
        for track in module.TRACKS:
            for level in range(2,5):
                result=self.buy(track,level)
                self.assertEqual(result['price'],candidate[track][str(level)])
                self.assertEqual(result['level'],level)
        self.assertEqual(before-self.player()['credits'],sum(sum(v.values()) for v in candidate.values()))
        reloaded=module.ProgressStore(self.store.path);reloaded.initialize()
        self.assertEqual(reloaded.economy_snapshot()['catalog']['prices'],candidate)

    def test_staged_prices_window_binding_expiry_and_stale_client(self):
        a=self.start();candidate=self.store.economy_snapshot()['candidate'];self.assertTrue(self.save_prices(candidate)['staged'])
        self.finish(a,kills=1000);window=self.store.open_shop({'id':a['run_id']})
        self.assertEqual(window,self.store.open_shop({'id':a['run_id']}))
        q=self.store.snapshot('green')['shop'];self.assertEqual(q['catalog_revision'],2)
        self.assertTrue(self.save_prices({t:dict.fromkeys(('2','3','4'),0) for t in module.TRACKS})['staged'])
        self.assertEqual(self.store.snapshot('purple')['shop']['catalog_revision'],2)
        p=self.player();request=dict(action='purchase',track=module.TRACKS[0],level=2,revision=p['revision'],catalog_revision=2,operation_id=uuid.uuid4().hex)
        result=self.store.mutate_player('green',request);self.assertEqual(result['price'],200)
        with patch('ltz_economy.time.time',return_value=window['deadline']+1):
            self.assertEqual(self.store.mutate_player('green',request),result)
            with self.assertRaisesRegex(ValueError,'closed'):self.buy(module.TRACKS[1],2)
        p=self.player()
        with self.assertRaisesRegex(ValueError,'refresh'):
            self.store.mutate_player('green',dict(action='purchase',track=module.TRACKS[1],level=2,revision=p['revision'],operation_id=uuid.uuid4().hex))
        self.store.reserve_roster(a['run_id'])
        with self.assertRaisesRegex(ValueError,'ready roster'):self.buy(module.TRACKS[1],2)

    def test_catalog_validation_zero_prices_and_backup_pending_window(self):
        for bad in [True,-1,1.5,100001]:
            c=copy.deepcopy(self.store.economy_snapshot()['candidate']);c[module.TRACKS[0]]['2']=bad
            with self.assertRaises(ValueError):self.save_prices(c)
        self.save_prices({t:dict.fromkeys(('2','3','4'),0) for t in module.TRACKS})
        self.assertEqual(self.buy(module.TRACKS[0],2)['price'],0)
        a=self.start();self.finish(a);self.store.open_shop({'id':a['run_id']});self.save_prices(self.store.economy_snapshot()['candidate'])
        other=module.ProgressStore(self.store.path.with_name('copy.sqlite3'));other.initialize();other.import_backup(self.store.export())
        self.assertEqual(other.economy_snapshot(),self.store.economy_snapshot());other.select_player('green',self.green)
        self.assertEqual(other.snapshot('green')['shop']['catalog_revision'],2)

class RuntimeRewardTests(unittest.TestCase):
    def test_actual_deaths_weighting_purge_and_frozen_settings(self):
        game=load('photon-game');level=load('photon-level');b=level.runtime_bundle();e=game.DefenseEngine(b['runtime'],b['waves']);e.set_virtual_play(True)
        e.start({'first_wave_delay_s':1500})
        for kind in ['grunt','brute','breaker']:e._spawn_enemy(kind,{})
        for enemy in e.enemies.values():enemy['hp']=0
        list(e.enemies.values())[0]['purge_burn']=True
        e.step(.05);score=e.snapshot()['match_score']
        self.assertEqual((e.kills,score['kill_credits'],score['purge_kills']['grunt']),(3,13,1))
        e.settings['reward_brute']=100
        e._spawn_enemy('brute',{});e.enemies[e.next_enemy_id-1]['hp']=0;e.step(.05)
        self.assertEqual(e.snapshot()['match_score']['kill_credits'],23)
        self.assertEqual(e.rewards.rule['scheduled_counts'],e.ranged.counts['scheduled'])
