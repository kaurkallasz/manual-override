"""Durable team statistics and authoritative lethal-hit ownership; no hardware."""
import copy
import json
import tempfile
import unittest
from flask import request
from pathlib import Path
from unittest.mock import patch

import test_event_progression as fixture
from test_photon_framework import load


class LevelResultTests(unittest.TestCase):
    setUp = fixture.EventProgressionTests.setUp
    pair = fixture.EventProgressionTests.pair
    new_event = fixture.EventProgressionTests.new_event
    play = fixture.EventProgressionTests.play

    def test_previous_average_zero_baseline_and_restart(self):
        first,_=self.play(0,'overrun')
        self.assertIsNone(first['statistics']['previous'])
        second,_=self.play(100,'overrun')
        self.assertIsNone(second['statistics']['previous']['percent'])
        self.assertEqual(second['statistics']['previous']['delta'],100)
        third,data=self.play(150,'overrun')
        stats=third['statistics']
        self.assertEqual(stats['previous']['percent'],50)
        self.assertEqual(stats['average']['baseline'],50)
        self.assertEqual(stats['average']['percent'],200)
        self.assertEqual(self.s.record(data,final=True),third)
        restarted=self.module.ProgressStore(self.path);restarted.initialize()
        receipt=restarted.snapshot('green')['latest_result']['statistics']
        self.assertEqual([r['score'] for r in receipt['history']],[0,100,150])
        self.assertEqual(receipt['history_total'],3)
        self.assertEqual(receipt['kill_attribution']['green'],None)
        self.assertEqual(receipt['kill_attribution']['unattributed'],150)

    def new_pair(self):
        self.serial+=1
        self.s.game_command({'action':'new','event_id':self.event,'operation_id':f'new:{self.serial}'})
        self.pair()

    def test_peer_teams_weighted_equally_and_assisted_excluded(self):
        self.play(100,'overrun');self.play(300,'overrun')
        self.new_pair();self.play(400,'overrun')
        self.new_pair();a,_=self.play(300,'overrun')
        c=a['statistics']['other_teams']
        self.assertEqual(c['baseline'],300)  # mean(team average 200, team average 400)
        self.assertEqual(c['sample_count'],2)
        self.assertEqual((c['rank'],c['team_count']),(2,3))
        self.s.advance_level({'event_id':self.event,'run_id':a['run_id']})
        receipt=self.s.snapshot('green')['latest_result']['statistics']
        self.assertTrue(receipt['assisted']);self.assertIsNone(receipt['other_teams'])
        self.new_pair();a,_=self.play(300,'overrun')
        self.assertEqual(a['statistics']['other_teams']['sample_count'],2)

    def test_event_peers_use_the_same_core_rule(self):
        self.play(100,'overrun')  # Earlier kill-gated rule, no version field.
        self.new_pair()
        new,_=self.play(200,'overrun',core_rule_version=2)
        self.assertIsNone(new['statistics']['other_teams'])
        self.new_pair()
        peer,_=self.play(300,'overrun',core_rule_version=2)
        self.assertEqual(peer['statistics']['other_teams']['sample_count'],1)
        self.assertEqual(peer['statistics']['other_teams']['baseline'],200)

    def test_same_pair_new_save_keeps_history_event_paging_and_backup(self):
        a,_=self.play(100,'overrun');team=a['statistics']['team_id']
        self.s.game_command({'action':'new','event_id':self.event,'operation_id':'same-pair'})
        self.s.prepare_game();game=self.s.snapshot()['saved_games']['active']
        self.s.bind_atoms({'event_id':self.event,'game_id':game['id'],'atoms':self.game['atoms'] or {
            'green':{'tag':100,'track':'damage-machine-gun','source':'camera'},
            'purple':{'tag':102,'track':'damage-mortar','source':'camera'}}})
        b,_=self.play(200,'overrun')
        self.assertEqual(b['statistics']['team_id'],team)
        self.assertEqual(b['statistics']['previous']['baseline'],100)
        page=self.s.event_results(self.event,limit=1)
        self.assertEqual((page['total'],page['next_cursor']),(2,1))
        self.assertEqual(self.s.event_results(self.event,cursor=1)['rows'][0]['run_id'],b['run_id'])
        self.assertNotIn('credits',str(page))
        other=self.module.ProgressStore(Path(self.folder.name)/'restored.db');other.initialize()
        other.import_backup(self.s.export())
        self.assertEqual(other.event_results(self.event),self.s.event_results(self.event))
        old=self.event;self.event=self.new_event('Empty new event');self.pair()
        self.assertEqual(self.s.event_results(self.event)['total'],0)
        self.assertEqual(self.s.event_results(old)['total'],2)

    def test_attribution_validation_and_roundtrip(self):
        # Start a fresh run with the same frozen rule as a real completed fixture.
        a,_=self.play(10,'overrun')
        self.s.begin({'run_id':'attributed','event_id':self.event,'reward_enabled':True,'metadata':a['metadata']})
        data=copy.deepcopy(a['result']);data.update(run_id='attributed',finished_at=a['finished_at']+.01)
        data['reward']['attribution']={'version':1,'method':'lethal_damage','kills':dict(green=4,purple=3,shared=3,unattributed=0)}
        bad=copy.deepcopy(data);bad['reward']['attribution']['kills']['green']=5
        with self.assertRaisesRegex(ValueError,'reconcile'):self.s.record(bad,final=True)
        self.s.record(data,final=True)
        r=self.s.snapshot('purple')['latest_result']
        self.assertEqual(r['statistics']['kill_attribution'],dict(green=4,purple=3,shared=3,unattributed=0))
        backup=self.s.export();other=self.module.ProgressStore(Path(self.folder.name)/'attr.db');other.initialize();other.import_backup(backup)
        self.assertEqual(other.event_results(self.event),self.s.event_results(self.event))

    def test_l4_second_atoms_and_assisted_export(self):
        for _ in range(3):
            for side in self.ids:
                p=self.s.snapshot(side)['player']
                if p['progression_stage']=='calibration_pending':
                    self.s.complete_lesson({'player_id':p['id'],'operation_id':'lesson:'+side,
                        'lesson_version':1,'evidence_id':'measured','calibration_revision':1,'milestone_id':p['calibration_milestone']})
            a,_=self.play(10,'operator_ended')
            self.s.advance_level({'event_id':self.event,'run_id':a['run_id']})
        receipt=self.s.snapshot('green')['latest_result']
        self.assertEqual(receipt['unlocked_control'],4)
        self.assertEqual({r['track'] for r in receipt['statistics']['atoms_unlocked']},{'damage-flamethrower','damage-tesla-coil'})
        row=self.s.event_results(self.event)['rows'][-1]
        self.assertTrue(row['assisted'])
        self.assertNotIn('balance',str(row))
        self.assertEqual(row['comparisons_at_finish']['event_comparison_status'],'assisted')

    def test_no_unfinished_battlefield_in_event_results(self):
        a,_=self.play(10,'overrun')
        self.s.begin({'run_id':'unfinished','event_id':self.event,'reward_enabled':True,'metadata':a['metadata']})
        self.assertEqual(self.s.event_results(self.event)['total'],1)

    def test_changing_partner_does_not_show_another_teams_receipt(self):
        self.play(100,'overrun')
        self.s.game_command({'action':'new','event_id':self.event,'operation_id':'new-partner'})
        self.s.create_player('New partner','new-partner-player',side='purple',event_id=self.event)
        self.assertIsNone(self.s.snapshot('green')['latest_result'])
        self.s.select_player('purple',self.ids['purple'],self.event)
        self.assertEqual(self.s.snapshot('green')['latest_result']['kills'],100)

    def test_backup_rejects_corrupt_comparison_without_partial_import(self):
        self.play(100,'overrun');self.play(200,'overrun')
        backup=self.s.export()
        for row in backup['tables']['attempts']:
            a=json.loads(row['data'])
            if a['statistics']['previous']:
                a['statistics']['previous']['percent']=500
                row['data']=json.dumps(a)
        other=self.module.ProgressStore(Path(self.folder.name)/'corrupt.db');other.initialize()
        with self.assertRaisesRegex(ValueError,'percentage'):other.import_backup(backup)
        self.assertEqual(other.snapshot()['events']['rows'],[])


class ResultApiTests(unittest.TestCase):
    def test_scoreboard_data_is_not_public(self):
        from mobile_ltz_fixture import create_app
        with tempfile.TemporaryDirectory() as folder:
            app,game=create_app(folder)
            @app.before_request
            def player_role():request.environ['hhh.roles']={'green'}
            try:
                event=game._progress.roster()['events']['active_id']
                r=app.test_client().get('/s/gamemaster/p/photon-progress/api/event-results?event_id='+event)
                self.assertEqual(r.status_code,403)
            finally:game.hub_stop();app.config['fixture_cleanup']()


class KillOwnershipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.game=load('photon-game');cls.bundle=load('photon-level').runtime_bundle()

    def engine(self):
        e=self.game.DefenseEngine(self.bundle['runtime'],self.bundle['waves'])
        e.set_virtual_play(True);return e

    def test_each_weapon_and_delayed_shell_keeps_owner(self):
        for atom in range(100,104):
            with self.subTest(atom=atom):
                e=self.engine();e.place(atom,'socket_01',source='virtual');e.start()
                e.runtime_time=e.sim_time=10
                t=e.placements['socket_01'];t.update(aim_angle=0,aim_spread=.5)
                target=e._tower_targeting(t)
                x,y=(target['target_x'],target['target_y']) if atom==102 else e._flamethrower_path(t,target)[4] if atom==101 else (t['x']+25,t['y'])
                enemy={'id':1,'x':x,'y':y,'hp':.01,'progress':1,'enemy_type':'grunt'}
                e.enemies={1:enemy};dead=set();e._fire_towers(2,dead)
                if atom==102:
                    self.assertNotIn('kill_owner',enemy)
                    e.placements.clear()  # Launched projectile must outlive its turret.
                    e.sim_time=12;e._resolve_mortar_rounds(dead)
                self.assertIn(1,dead)
                expected='green' if atom<102 else 'purple'
                self.assertEqual(enemy['kill_owner'],expected)
                e._hurt_enemy(enemy,100,'shared');e.rewards.killed(enemy)
                self.assertEqual(e.rewards.checkpoint()['attribution']['kills'][expected],1)

    def test_burn_and_core_purge_are_credited_once(self):
        for purge,owner in ((False,'green'),(True,'shared')):
            e=self.engine();e.start();e.start_countdown_remaining_s=0
            e._spawn_enemy('grunt',{});enemy=next(iter(e.enemies.values()))
            enemy.update(hp=.01,burn_until=10,burn_damage_per_s=100,burn_owner='green',purge_burn=purge)
            with patch.object(e,'_spawn_due'):
                e.step(.1);e.step(.1)
            self.assertEqual(e.rewards.attribution[owner],1)
            self.assertEqual(sum(e.rewards.attribution.values()),1)
            self.assertEqual(e.rewards.purge['grunt'],int(purge))

    def test_field_lethal_hit_is_shared(self):
        e=self.engine();e.start();e.runtime_time=10
        for atom,marker in ((100,41),(102,43)):
            e.place(atom,e.level.socket_by_marker[marker],source='virtual')
        e.runtime_time=20
        field=next(iter(e.force_fields.values()))
        enemy={'id':1,'x':(field['ax']+field['bx'])/2,'y':(field['ay']+field['by'])/2,
               'hp':.01,'collision_radius':2,'enemy_type':'grunt'}
        with patch.object(e,'_reroute_enemy'):
            e._handle_force_fields([enemy])
        self.assertEqual(enemy['kill_owner'],'shared')


if __name__=='__main__':unittest.main()
