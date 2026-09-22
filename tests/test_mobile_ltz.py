"""Real simulation and route checks, isolated from hardware and saved profiles."""
import importlib.util
import json
import math
import time
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from test_photon_framework import load, FakeContext, ROOT, Flask

class MobileTests(unittest.TestCase):
    def setUp(self):
        self.game=load('photon-game');self.level=load('photon-level')
        self.folder=tempfile.TemporaryDirectory(prefix='mobile-test-');self.addCleanup(self.folder.cleanup)
        self.game._settings=self.game.SettingsStore(Path(self.folder.name)/'settings.json')
        self.game.LOG_PATH=str(Path(self.folder.name)/'runs.jsonl')
        bundle=self.level.runtime_bundle()
        self.engine=self.game.DefenseEngine(bundle['runtime'],bundle['waves'])
        self.engine.set_virtual_play(True)
        self.arm=self.engine.mobile_arm
    def connect(self):
        self.token=self.arm.command({'action':'connect'},self.engine)['session'];self.seq=0
    def command(self,action,**args):
        self.seq+=1
        return self.arm.command(dict(action=action,session=self.token,sequence=self.seq,**args),self.engine)
    def test_pose_and_pick_place_follow_server_geometry(self):
        self.connect();self.command('pump',mode='suction');self.assertEqual(self.arm.held,100)
        self.command('joints',joints=[-70,-5,-5]);self.engine.step(.1)
        self.assertAlmostEqual(self.arm.joints[0],-78.8)
        self.assertAlmostEqual(self.arm.tags[100]['x'],self.arm.pose()['tip']['x'])
        with patch.object(self.arm,'pose',return_value={'tip':dict(x=next(iter(self.engine.level.sockets.values()))['x'],y=next(iter(self.engine.level.sockets.values()))['y'],z=40)}):
            self.command('pump',mode='blow')
        self.assertEqual(len(self.engine.placements),1);self.assertIsNone(self.arm.held)
        self.assertEqual(next(iter(self.engine.placements.values()))['owner'],'green')
    def test_low_speed_applies_to_every_control_and_arrives_without_overshoot(self):
        self.connect()
        self.engine.set_virtual_test_loadout(None, 4)
        for mode in ('joint', 'xyz', 'targeting', 'cue'):
            with self.subTest(mode=mode):
                self.command('control_mode', mode=mode)
                start = list(self.arm.joints)
                # Exercise the shared follower used by manual and cue targets.
                self.arm.targets = [start[0]+24, start[1]-24, start[2]+.5]
                for _ in range(10): self.engine.step(.1)
                self.assertAlmostEqual(self.arm.joints[0], start[0]+12)
                self.assertAlmostEqual(self.arm.joints[1], start[1]-12)
                self.assertEqual(self.arm.joints[2], start[2]+.5)
                for _ in range(11): self.engine.step(.1)
                for actual, target in zip(self.arm.joints, self.arm.targets):
                    self.assertAlmostEqual(actual, target)

    def test_core_release_uses_existing_cooperative_rules(self):
        self.connect();self.command('pump',mode='suction')
        self.engine.phase='running';self.engine.ring_completed_at=0;self.engine.core_stage='ring_ready'
        core=self.engine.level.core
        with patch.object(self.arm,'pose',return_value={'tip':dict(x=core['x'],y=core['y'],z=40)}):
            self.command('pump',mode='blow')
        self.assertEqual(self.engine.core_stage,'first_tag')
        self.assertEqual(self.engine.core_first_team,'green');self.assertIsNone(self.arm.held)
    def test_stop_invalidates_queued_commands_and_lease(self):
        self.connect();self.command('joints',joints=[60,30,30]);self.arm.command({'action':'stop'},self.engine)
        before=self.arm.joints[:];self.engine.step(.1);self.assertEqual(self.arm.joints,before)
        with self.assertRaises(ValueError):self.command('joints',joints=[60,30,30])
        self.connect();self.arm.deadline=time.monotonic()-1;self.engine.step(.1);self.assertFalse(self.arm.snapshot()['connected'])
    def test_limits_sequence_and_mode(self):
        self.connect()
        for values in ([math.nan,0,0],[181,0,0],[True,0,0],[-80,181,0]):
            with self.assertRaises(ValueError):self.command('joints',joints=values)
        self.command('heartbeat')
        with self.assertRaises(ValueError):self.arm.command({'action':'heartbeat','session':self.token,'sequence':self.seq},self.engine)
        self.engine.set_virtual_play(False)
        with self.assertRaises(ValueError):self.arm.command({'action':'connect'},self.engine)
    def test_virtual_owner_rejoins_after_outage_without_replaying_motion(self):
        identity={'action':'connect','client_id':'a'*32,'request_id':'b'*32}
        joined=self.arm.command(identity,self.engine)
        duplicate=self.arm.command(identity,self.engine)
        self.assertEqual(joined['session'],duplicate['session'],'ambiguous join retries are idempotent')
        with self.assertRaises(ValueError):self.arm.command({**identity,'client_id':'c'*32},self.engine)
        self.arm.command({'action':'joints','session':joined['session'],'sequence':1,'joints':[50,20,20]},self.engine)
        before=self.arm.joints[:];self.arm.deadline=time.monotonic()-1;self.engine.step(.1)
        self.assertEqual(self.arm.targets,before);self.assertEqual(self.arm.joints,before)
        self.assertTrue(self.arm.snapshot()['suspended']);self.assertFalse(self.arm.snapshot()['connected'])
        with self.assertRaises(ValueError):self.arm.command({'action':'heartbeat','session':joined['session'],'sequence':2},self.engine)
        resumed=self.arm.command({**identity,'request_id':'d'*32},self.engine)
        self.assertTrue(resumed['connected']);self.assertNotEqual(resumed['session'],joined['session'])
        for action in ('joints','stop','suspend'):
            with self.assertRaises(ValueError):self.arm.command({'action':action,'session':joined['session'],'sequence':99,'joints':[90,20,20]},self.engine)
        self.assertTrue(self.arm.snapshot()['connected'])
        self.arm.command({'action':'stop','session':resumed['session']},self.engine)
        self.assertIsNone(self.arm.token);self.assertIsNone(self.arm.owner)

    def test_join_identity_validation_and_secret_not_in_snapshots(self):
        for value in ('bad',True,'a'*33):
            with self.assertRaises(ValueError):self.arm.command({'action':'connect','client_id':value,'request_id':'b'*32},self.engine)
        result=self.arm.command({'action':'connect','client_id':'a'*32,'request_id':'b'*32},self.engine)
        snapshot=self.arm.snapshot()
        self.assertNotIn(result['session'],json.dumps(snapshot));self.assertNotIn('a'*32,json.dumps(snapshot))
    def test_start_preserves_setup_controller_but_pause_reset_revoke(self):
        self.connect();self.engine.start();self.assertIs(self.arm,self.engine.mobile_arm)
        self.engine.pause();self.assertFalse(self.arm.snapshot()['connected'])
        self.engine.reset();self.assertIsNot(self.arm,self.engine.mobile_arm)
    def test_start_and_reset_push_complete_scenes_to_waiting_teams(self):
        facade=load('mobile-ltz-api')
        app=Flask('mobile-start-stream');app.register_blueprint(facade.bp)
        self.game._hub_ctx=FakeContext({'photon-level':self.level})
        facade.hub_init(FakeContext({'photon-game':self.game,'photon-level':self.level}))
        self.game._sync_level();self.game._engine.set_virtual_play(True)
        with app.test_client() as client:
            response=client.get('/api/events',environ_overrides={'hhh.roles':{'green'}},buffered=False)
            stream=iter(response.response)
            before=next(stream).decode();self.assertIn('"level":',before)
            initial=json.loads(before.split('data: ',1)[1])
            self.assertEqual((initial['contract'], initial['version'], initial['kind']),('hub.live',1,'snapshot'))
            facade._live.bump()
            delta=json.loads(next(stream).decode().split('data: ',1)[1])
            self.assertEqual(delta['kind'],'update')
            self.assertIn('run_id',delta['state']);self.assertIn('level_revision',delta['state'])
            self.assertNotIn('level',delta['state'])
            self.game.apply_command({'action':'start','virtual_play':True,'reward_enabled':False})
            facade._live.bump()
            started=next(stream).decode()
            self.assertTrue(started.startswith('data: '), 'Start must send a full scene, not only an incremental update')
            self.assertIn('"phase":"running"',started);self.assertIn('"level":',started)
            self.assertNotIn('"connected":true',started, 'The shared game starts without a controller connection')
            self.game.apply_command({'action':'reset','virtual_play':True});facade._live.bump()
            reset=next(stream).decode();self.assertTrue(reset.startswith('data: '));self.assertIn('"level":',reset)
            response.close()
        self.game.hub_stop()
    def test_mobile_routes_reject_other_teams_and_operator_actions(self):
        self.game._hub_ctx=FakeContext({'photon-level':self.level,'laser-tag-y':load('laser-tag-y')})
        facade=load('mobile-ltz-api');facade.hub_init(FakeContext({'photon-game':self.game,'photon-level':self.level,'laser-tag-y':load('laser-tag-y')}))
        app=Flask('mobile-test');app.register_blueprint(facade.bp,url_prefix='/game')
        with patch.object(self.game,'_require_engine',return_value=(self.engine,True)):
            c=app.test_client();green={'hhh.roles':{'green'}};purple={'hhh.roles':{'purple'}}
            self.assertEqual(c.post('/game/api/command',json={'action':'connect'},environ_overrides=purple).status_code,403)
            self.assertEqual(c.post('/game/api/command',json={'action':'start'},environ_overrides=green).status_code,400)
            self.assertEqual(c.post('/game/api/command',json={'action':'connect'},headers={'Origin':'https://evil.example'},environ_overrides=green).status_code,403)
            self.assertEqual(c.post('/game/api/command',json={'action':'connect'},environ_overrides=green).status_code,200)
            self.assertEqual(c.get('/game/api/assets/no-such-secret',environ_overrides=green).status_code,404)
            response=c.get('/game/api/renderer.js',environ_overrides=green)
            self.assertEqual(response.status_code,200);response.close()

if __name__=='__main__':unittest.main()
