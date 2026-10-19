"""Event isolation, automatic purchases, debt and durable operator overrides."""
import copy
import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch
from test_photon_framework import load


class EventProgressionTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.module=load('photon-progress');self.path=Path(self.folder.name)/'progress.sqlite3'
        self.s=self.module.ProgressStore(self.path);self.s.initialize();self.serial=0
        self.event=self.new_event('First event');self.pair()

    def new_event(self,name):
        self.serial+=1
        return self.s.event_command({'action':'create','name':name,'operation_id':f'event:{self.serial}'})['event_id']

    def pair(self):
        self.ids={}
        for side in ('green','purple'):
            self.serial+=1
            self.ids[side]=self.s.create_player(side,f'player:{self.serial}',side=side,event_id=self.event)['player_id']
        self.s.prepare_game();self.game=self.s.snapshot()['saved_games']['active']
        self.s.bind_atoms({'event_id':self.event,'game_id':self.game['id'],'atoms':{
            'green':{'tag':100,'track':'damage-machine-gun','source':'camera'},
            'purple':{'tag':102,'track':'damage-mortar','source':'gamemaster'}}})

    def play(self,kills=0,outcome='operator_ended',stack=False,core_rule_version=None):
        self.serial+=1;run=f'run:{self.serial}'
        level=self.s.snapshot()['saved_games']['active']['level']
        rule={'version':1,'revision':'test','values':dict(grunt=1,runner=1,breaker=2,brute=10),
              'scheduled_counts':dict(grunt=10000,runner=0,breaker=0,brute=0),'scheduled_value':10000,
              'bonus':dict(stack_bonus_enabled=0,stack_bonus_fraction=.2,stack_health_exponent=2,stack_forgone_fraction=.5)}
        metadata={'contract_control_tier':level,'reward_rules':rule,'stack_combat_target':10}
        if core_rule_version is not None:metadata['core_rule_version']=core_rule_version
        a=self.s.begin({'run_id':run,'event_id':self.event,'reward_enabled':True,'metadata':metadata})
        counts=dict(grunt=kills,runner=0,breaker=0,brute=0)
        reward={'version':1,'revision':'test','sequence':kills,'counts':counts,'combat_kills':counts,
                'purge_kills':dict.fromkeys(counts,0),'kill_credits':kills,'stack_bonus':0,'total_earned':kills,
                'victory_method':'center_stack' if stack else 'waves_cleared' if outcome=='won' else None,
                'core_health_at_stack':{'hp':100,'max_hp':100} if stack else None}
        data={'run_id':run,'sequence':1,'kills':kills,'outcome':outcome,'active_seconds':30,
              'finished_at':time.time(),'released_orcs':kills,'reward':reward}
        return self.s.record(data,final=True),data

    def test_forced_upgrade_preserves_score_and_debt_once_across_restart(self):
        a,data=self.play(150)
        self.assertEqual(self.s.snapshot('green')['player']['credits'],-350)
        self.assertEqual(self.s.snapshot('green')['player']['lifetime_kill_credits'],150)
        self.assertEqual(len(a['purchases'][self.ids['green']]),1)
        self.assertEqual(self.s.record(data,final=True),a)
        restarted=self.module.ProgressStore(self.path);restarted.initialize()
        self.assertEqual(restarted.record(data,final=True),a)
        self.assertEqual(restarted.snapshot('green')['player']['levels']['damage-machine-gun'],2)
        with restarted.transaction() as db:self.assertEqual(db.execute('SELECT count(*) FROM ledger WHERE amount<0').fetchone()[0],2)

    def test_debt_paid_before_automatic_upgrade_and_multiple_affordable_tiers(self):
        self.play(150)
        self.play(350,'overrun')
        p=self.s.snapshot('green')['player'];self.assertEqual(p['credits'],0);self.assertEqual(p['levels']['damage-machine-gun'],2)
        self.play(2500,'overrun')
        p=self.s.snapshot('green')['player'];self.assertEqual(p['credits'],0);self.assertEqual(p['levels']['damage-machine-gun'],4)
        a,_=self.play(0)
        self.assertEqual(a['purchases'][self.ids['green']],[])
        self.assertEqual(self.s.snapshot('green')['player']['credits'],0)

    def test_stack_advances_both_and_forcefield_once_then_calibration(self):
        a,_=self.play(10,'won',True)
        self.assertEqual(self.s.snapshot()['saved_games']['active']['level'],2)
        self.s.advance_level({'run_id':a['run_id'],'event_id':self.event})
        self.assertEqual(self.s.snapshot()['saved_games']['active']['level'],2)
        self.play(10,'won',True)
        for side in self.ids:
            p=self.s.snapshot(side)['player'];self.assertEqual(p['current_control_tier'],3)
            self.assertEqual(p['levels']['forcefield'],3);self.assertEqual(p['progression_stage'],'calibration_pending')

    def test_zero_kill_stack_accepts_legacy_target_metadata_and_advances_once(self):
        # This fixture freezes the obsolete target=10, as an older attempt may.
        a,data=self.play(0,'won',True)
        self.assertEqual(a['kills'],0)
        self.assertEqual(a['kill_credits'],0)
        self.assertEqual(self.s.snapshot()['saved_games']['active']['level'],2)
        for side in self.ids:
            p=self.s.snapshot(side)['player']
            self.assertEqual((p['current_control_tier'],p['levels']['forcefield'],p['wins']),(2,2,1))
        self.assertEqual(self.s.record(data,final=True),a)
        restarted=self.module.ProgressStore(self.path);restarted.initialize()
        self.assertEqual(restarted.record(data,final=True),a)
        for side in self.ids:
            p=restarted.snapshot(side)['player']
            self.assertEqual((p['wins'],p['credits']),(1,0))

    def test_manual_next_level_is_paired_and_cannot_repeat(self):
        a,_=self.play()
        first=self.s.advance_level({'run_id':a['run_id'],'event_id':self.event})
        self.assertEqual(self.s.advance_level({'run_id':a['run_id'],'event_id':self.event}),first)
        self.assertTrue(self.s.snapshot()['saved_games']['active']['assisted'])
        for side in self.ids:self.assertEqual(self.s.snapshot(side)['player']['current_control_tier'],2)
        self.assertFalse(self.s.history(None,{'combined':True})['summary']['comparable'])

    def test_events_isolate_members_wallets_history_and_saves(self):
        a,_=self.play(200);old=self.event;old_game=self.game['id'];old_ids=dict(self.ids)
        self.event=self.new_event('Second event');self.pair()
        self.assertEqual(self.s.snapshot('green')['player']['credits'],0)
        self.assertEqual(self.s.history(None,{'combined':True})['total'],0)
        with self.assertRaisesRegex(ValueError,'another event'):self.s.select_player('green',old_ids['green'],self.event)
        with self.assertRaisesRegex(ValueError,'another event'):self.s.game_command({'action':'load','game_id':old_game,'event_id':self.event,'operation_id':'cross-event'})
        self.s.event_command({'action':'select','event_id':old,'operation_id':'return'})
        self.s.game_command({'action':'load','game_id':old_game,'event_id':old,'operation_id':'load-original'})
        self.assertEqual(self.s.snapshot('green')['player']['credits'],-300)
        self.assertEqual(self.s.history(None,{'combined':True})['total'],1)
        self.assertEqual(self.s.snapshot()['events']['active']['name'],'First event')

    def test_pair_and_atom_binding_lock_new_game_preserves_wallet(self):
        self.play(150)
        with self.assertRaises(ValueError):self.s.select_player('green',None,self.event)
        with self.assertRaises(ValueError):self.s.bind_atoms({'game_id':self.game['id'],'event_id':self.event,'atoms':{
            'green':{'tag':101,'track':'damage-flamethrower','source':'camera'},'purple':{'tag':102,'track':'damage-mortar','source':'camera'}}})
        self.s.game_command({'action':'new','event_id':self.event,'operation_id':'fresh'})
        p=self.s.snapshot('green')['player'];self.assertEqual((p['credits'],p['current_control_tier']),(-350,1))
        self.assertEqual(p['levels']['damage-machine-gun'],2)
        self.assertEqual(self.s.snapshot()['saved_games']['active']['atoms'],{})

    def test_l4_only_then_second_turret_gets_priority(self):
        for _ in range(3):
            p=self.s.snapshot('green')['player']
            if p['current_control_tier']==3:
                for side in self.ids:
                    p=self.s.snapshot(side)['player']
                    self.s.complete_lesson({'player_id':p['id'],'operation_id':'lesson:'+side,'lesson_version':1,'evidence_id':'measured','calibration_revision':1,'milestone_id':p['calibration_milestone']})
            a,_=self.play();self.s.advance_level({'run_id':a['run_id'],'event_id':self.event})
        a,_=self.play()
        self.assertEqual(a['purchases'][self.ids['green']][0]['track'],'damage-flamethrower')
        self.assertEqual(a['purchases'][self.ids['purple']][0]['track'],'damage-tesla-coil')
        self.assertEqual(self.s.snapshot('green')['player']['credits'],-3500)
        self.assertEqual(self.s.snapshot()['saved_games']['active']['level'],4)

    def test_signed_backup_roundtrip_and_reject_legacy_tampering(self):
        self.play(150);backup=self.s.export()
        other=self.module.ProgressStore(Path(self.folder.name)/'restored.db');other.initialize();other.import_backup(backup)
        self.assertEqual(other.import_backup(backup,preview=True)['new_records'],0)
        other.event_command({'action':'select','event_id':self.event,'operation_id':'event'})
        other.game_command({'action':'load','game_id':self.game['id'],'event_id':self.event,'operation_id':'load'})
        self.assertEqual(other.snapshot('green')['player']['credits'],-350)
        with self.assertRaisesRegex(ValueError,'conflict'):other.import_backup(backup,preview=True)
        with self.assertRaises(ValueError):other.import_backup({'schema_version':4})
        bad=copy.deepcopy(backup);p=json.loads(bad['tables']['players'][0]['data']);p['credits']+=1;bad['tables']['players'][0]['data']=json.dumps(p)
        blank=self.module.ProgressStore(Path(self.folder.name)/'bad.db');blank.initialize()
        with self.assertRaises(ValueError):blank.import_backup(bad)
        self.assertEqual(blank.snapshot()['events']['rows'],[])

    def test_no_practice_or_player_purchases(self):
        with self.assertRaises(ValueError):self.s.begin({'run_id':'practice','reward_enabled':False,'metadata':{}})
        with self.assertRaises(ValueError):self.s.mutate_player('green',{'action':'purchase'})
        self.assertFalse(any(p['is_test'] for p in self.s.snapshot()['players']))

    def test_wave_clear_does_not_advance_and_old_match_cannot_advance_later(self):
        first,_=self.play(10000,'won')
        self.assertEqual(self.s.snapshot()['saved_games']['active']['level'],1)
        self.play(1,'overrun')
        with self.assertRaisesRegex(ValueError,'latest match'):
            self.s.advance_level({'event_id':self.event,'run_id':first['run_id']})

    def test_failure_for_second_player_rolls_back_all_settlement(self):
        original=self.s.settle_upgrades
        def failing(db,p,member,attempt,**kw):
            if member['side']=='purple':raise OSError('simulated disk failure')
            return original(db,p,member,attempt,**kw)
        with patch.object(self.s,'settle_upgrades',side_effect=failing):
            with self.assertRaises(OSError):self.play(150)
        for side in self.ids:
            p=self.s.snapshot(side)['player'];self.assertEqual(p['credits'],0)
            self.assertEqual(p['attempts'],0);self.assertTrue(all(v==1 for v in p['levels'].values()))
        with self.s.transaction() as db:self.assertEqual(db.execute('SELECT count(*) FROM ledger').fetchone()[0],0)

    def test_late_durable_result_updates_original_game_after_event_switch(self):
        self.s.begin({'run_id':'late','event_id':self.event,'reward_enabled':True,'metadata':{'contract_control_tier':1}})
        self.s.recover();old_event=self.event;old_game=self.game['id'];old_ids=dict(self.ids)
        self.event=self.new_event('Later event');self.pair()
        self.s.record({'run_id':'late','sequence':2,'kills':150,'outcome':'operator_ended',
            'active_seconds':10,'finished_at':time.time()+1,'released_orcs':150},final=True)
        for side in self.ids:self.assertEqual(self.s.snapshot(side)['player']['credits'],0)
        self.assertEqual(self.s.history(None,{'combined':True})['total'],0)
        self.s.event_command({'action':'select','event_id':old_event,'operation_id':'return-late'})
        self.s.game_command({'action':'load','game_id':old_game,'event_id':old_event,'operation_id':'load-late'})
        for side in old_ids:
            p=self.s.snapshot(side)['player'];self.assertEqual(p['credits'],-350);self.assertEqual(p['attempts'],1)


if __name__=='__main__':unittest.main()
