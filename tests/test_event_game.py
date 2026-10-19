"""Real event APIs with fake camera/relay owners. Never opens physical hardware."""
import copy
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from mobile_ltz_fixture import create_app
from test_photon_framework import load


class EventGameTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.app,self.g=create_app(self.folder.name)
        self.addCleanup(self.app.config['fixture_cleanup']);self.addCleanup(self.g.hub_stop)
        self.c=self.app.test_client();self.c.post('/__test/camera',json={'enabled':True})
        self.event=self.g._progress.roster()['events']['active_id']

    def command(self,action,**kw):
        return self.c.post('/s/gamemaster/p/photon-game/api/command',json={
            'action':action,'event_id':self.event,'run_id':self.g._run_id,**kw})

    def start(self):
        r=self.command('start',starting_atoms={'green':100,'purple':102})
        self.assertEqual(r.status_code,200,r.get_json());return self.g._run_id

    def test_physical_start_is_l1_both_and_pair_atoms_locked(self):
        self.start();snapshot=self.g.game_snapshot()
        self.assertEqual(snapshot['contract_control_tier'],1)
        self.assertEqual(snapshot['event_game']['atoms']['purple']['tag'],102)
        for side in ('green','purple'):
            mobile=self.c.get('/s/gamemaster/p/mobile-ltz-api/api/state?side='+side).get_json()
            self.assertEqual(mobile['mobile_progress']['player']['current_control_tier'],1)
            self.assertEqual(mobile['mobile_motion_policy']['scope'],'player')
            r=self.c.post('/s/gamemaster/p/photon-progress/api/player?side='+side,json={'action':'select','player_id':None,'event_id':self.event})
            self.assertEqual(r.status_code,400)
        locked=self.command('operator_atom',socket_id='socket_01',atom_tag_id=101)
        self.assertEqual(locked.status_code,400);self.assertIn('L4',locked.get_json()['error'])
        self.assertEqual(self.command('operator_atom',socket_id='socket_01',atom_tag_id=100).status_code,200)

    def test_end_retry_concurrent_single_upgrade_and_manual_next_once(self):
        run=self.start();self.command('pause')
        payload={'action':'end_match','event_id':self.event,'run_id':run}
        def end(_):
            with self.app.test_client() as c:return c.post('/s/gamemaster/p/photon-game/api/command',json=payload).status_code
        with ThreadPoolExecutor(max_workers=4) as pool:self.assertEqual(list(pool.map(end,range(4))),[200]*4)
        roster=self.g._progress.roster()
        for side,p in roster['roster'].items():
            self.assertEqual(p['credits'],-500)
            self.assertEqual(p['levels']['damage-machine-gun' if side=='green' else 'damage-mortar'],2)
        self.assertEqual(self.g.journey_snapshot()['phase'],'results')
        self.assertEqual(self.command('unlock_next_level').status_code,200)
        self.assertEqual(self.command('unlock_next_level').status_code,200)
        self.assertEqual(self.g._progress.roster()['saved_games']['active']['level'],2)
        self.assertEqual(self.command('next_match').status_code,200);self.start()
        self.assertEqual(self.g.game_snapshot()['contract_control_tier'],2)
        self.assertEqual(self.command('end_match',run_id=run).status_code,200)
        self.assertEqual(self.g._engine.phase,'running')  # Delayed old request cannot end the new match.
        for p in self.g._progress.roster()['roster'].values():self.assertEqual(p['credits'],-500)

    def test_stop_failure_does_not_end_or_charge(self):
        self.start()
        with patch.object(self.g,'_stop_for_saved_game',side_effect=ValueError('stop unavailable')):
            r=self.command('end_match')
        self.assertEqual(r.status_code,400);self.assertEqual(self.g._engine.phase,'running')
        for p in self.g._progress.roster()['roster'].values():self.assertEqual(p['credits'],0)

    def test_event_change_stale_phone_and_legacy_commands_rejected(self):
        for action in ('set_virtual','test_end_match','test_next_level','virtual_test_loadout'):
            self.assertEqual(self.command(action).status_code,400)
        r=self.c.post('/s/gamemaster/p/photon-game/api/event',json={'action':'create','name':'New event','operation_id':'new-event'})
        self.assertEqual(r.status_code,200,r.get_json())
        with self.assertRaisesRegex(ValueError,'Event changed'):
            self.g.mobile_journey_command('green',{'action':'ready','event_id':self.event})
        self.assertEqual(self.g._progress.roster()['players'],[])
        self.assertEqual(self.command('start').status_code,400)
        self.assertEqual(self.c.post('/s/gamemaster/p/photon-game/api/player-admin',json={'action':'grant_credits'}).status_code,404)

    def test_l3_transition_keeps_required_calibration(self):
        for level in (1,2):
            self.start();self.assertEqual(self.command('end_match').status_code,200)
            self.assertEqual(self.command('unlock_next_level').status_code,200)
            self.assertEqual(self.command('next_match').status_code,200)
        self.assertEqual(self.g._progress.roster()['saved_games']['active']['level'],3)
        self.assertEqual(self.g.journey_snapshot()['phase'],'calibration')
        r=self.command('start');self.assertEqual(r.status_code,400)
        for p in self.g._progress.roster()['roster'].values():self.assertEqual(p['progression_stage'],'calibration_pending')


class EventEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.game=load('photon-game');cls.bundle=load('photon-level').runtime_bundle()
    def setUp(self):
        self.e=self.game.DefenseEngine(self.bundle['runtime'],self.bundle['waves'])
        self.saved={'level':1,'atoms':{'green':{'tag':100},'purple':{'tag':102}}}
        self.e.start(event_game=self.saved,reward_enabled=True)
    def select(self,tag,sid='socket_01'):self.e.operator_turret_command('operator_atom',sid,tag)
    def test_manual_retry_clear_and_rebuild(self):
        self.select(100);t=self.e.placements['socket_01'];t['hp']*=.5;hp=t['hp']
        self.select(100);self.assertEqual(t['hp'],hp)
        self.select(None);self.select(100);self.assertEqual(t['hp'],t['max_hp'])
        self.e.operator_turret_command('operator_turret','socket_01','deactivated')
        self.select(100);self.assertFalse(self.e.placements['socket_01']['destroyed'])
    def test_second_atom_blocked_before_l4_and_ring_unlocks_zero_kill_stack(self):
        for tag in (101,103):
            with self.assertRaisesRegex(ValueError,'L4'):self.select(tag)
        for index,marker in enumerate((41,43,42,45,54,46,52,53)):
            self.select(100 if index%2==0 else 102,self.e.level.socket_by_marker[marker])
        self.assertIsNotNone(self.e.ring_completed_at)
        self.assertEqual(sum(self.e.rewards.combat.values()),0)
        self.assertEqual(self.e.snapshot()['turret_controls']['core']['blocked_reason'],'')
        self.e.operator_turret_command('operator_core',None,100)
        self.e.operator_turret_command('operator_core',None,100)
        self.assertEqual(self.e.core_stage,'first_tag')
        self.e.operator_turret_command('operator_core',None,102)
        self.e.operator_turret_command('operator_core',None,102)
        self.assertEqual(self.e.core_stage,'detonating')
        self.e.event_game['level']=4
        for tag,sid in ((101,'socket_03'),(103,'socket_05')):self.select(tag,sid)


if __name__=='__main__':unittest.main()
