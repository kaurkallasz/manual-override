"""Player turret aim authorization and camera alignment, without robot connections."""
import copy
import math
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from test_photon_framework import load, FakeContext, Flask

class MobileTurretTests(unittest.TestCase):
    def setUp(self):
        self.game=load('photon-game');self.level=load('photon-level')
        self.game._hub_ctx=FakeContext({'photon-level':self.level})
        self.game._sync_level();self.engine=self.game._engine;self.engine.set_virtual_play(True)
        self.sid=self.engine.level.socket_by_marker[44]
        self.engine.place(100,self.sid,source='virtual',team='green')
        self.facade=load('mobile-ltz-api');self.facade.hub_init(FakeContext({'photon-game':self.game}))
        self.app=Flask(__name__);self.app.register_blueprint(self.facade.bp);self.client=self.app.test_client()
        self.addCleanup(self.game.hub_stop)

    def data(self):
        t=self.engine.placements[self.sid]
        return dict(action='turret_aim',socket_id=self.sid,atom_tag_id=100,activation_started_at=t['activation_started_at'],
                    aim_instance=t['aim_instance'],aim_revision=t['aim_revision'],run_id=self.game._run_id,angle_degrees=90,spread=.25)

    def post(self,data=None,role='green'):
        return self.client.post('/api/command',json=data or self.data(),environ_overrides={'hhh.roles':{role}})

    def test_save_no_arm_session_and_reject_stale_revision(self):
        before=self.data();result=self.post(before)
        self.assertEqual(result.status_code,200,result.json)
        self.assertAlmostEqual(result.json['tower']['targeting']['angle_degrees'],90)
        self.assertIsNone(self.engine.mobile_arm.token)
        self.assertEqual(self.post(before).status_code,400)
        self.assertEqual(self.engine.placements[self.sid]['aim_revision'],1)

    def test_ownership_identity_destroyed_and_invalid_inputs(self):
        self.assertEqual(self.post(role='purple').status_code,403)
        for values in ({'socket_id':'missing'},{'atom_tag_id':101},{'aim_revision':True},
                       {'activation_started_at':-1},{'aim_instance':'old'},{'run_id':'old'},{'spread':2},{'spread':True},
                       {'angle_degrees':float('nan')}):
            self.assertEqual(self.post({**self.data(),**values}).status_code,400,values)
        self.engine.placements[self.sid]['owner']='purple';self.assertEqual(self.post().status_code,400)
        self.engine.placements[self.sid]['owner']='green';self.engine.placements[self.sid]['destroyed']=True
        self.assertEqual(self.post().status_code,400)
        self.engine.placements[self.sid]['destroyed']=False;self.engine.paused=True
        self.assertEqual(self.post().status_code,400)

    def observation(self):
        level=self.game.game_snapshot()['level']
        tags=[{'id':s['aruco_id'],'nx':.1+.8*s['marker_x']/level['width'],
               'ny':.05+.9*s['marker_y']/level['height'],'missing':0,'tracked':True} for s in level['sockets']]
        return dict(contract='photon.board.runtime',version=1,status='ready',source='camera',corrected=True,
                    frame_at=time.time(),width=1280,height=720,tags=tags)

    def test_camera_registration_rejects_stale_degenerate_and_wrong_layout(self):
        from camera_view import registration,project
        board=self.observation();level=self.game.game_snapshot()['level']
        matrix,ids=registration(level,board)
        self.assertGreater(len(ids),4)
        x,y=project(matrix,.3,.7);self.assertAlmostEqual(x,.34);self.assertAlmostEqual(y,.68)
        for changed in ({'frame_at':time.time()-10},{'corrected':False},{'tags':board['tags'][:3]}):
            with self.assertRaises(ValueError):registration(level,{**board,**changed})
        bad=copy.deepcopy(board);bad['tags'][0]['nx']+=.2
        with self.assertRaises(ValueError):registration(level,bad)
        bad=copy.deepcopy(board);bad['tags'].append(bad['tags'][0])
        with self.assertRaises(ValueError):registration(level,bad)

    def test_physical_aim_requires_tracking_but_not_virtual_robot_connection(self):
        board=self.observation()
        camera=SimpleNamespace(preview_snapshot=lambda:dict(contract='hhh.camera-preview',version=1,status='ready',coordinate_space='corrected-camera-normalized'))
        self.facade.hub_init(FakeContext({'photon-game':self.game,'photon-board':SimpleNamespace(runtime_observation=lambda:board),'camera-calibration':camera}))
        self.engine.virtual_play=False
        self.assertEqual(self.post().status_code,200)
        self.assertIsNone(self.engine.mobile_arm.token)
        board['frame_at']=time.time()-10
        self.assertEqual(self.post().status_code,400)
        state=self.client.get('/api/state',environ_overrides={'hhh.roles':{'green'}}).json
        self.assertEqual(state['mobile_camera']['status'],'unavailable')

    def test_reset_and_replacement_do_not_reuse_an_aim_identity(self):
        old=self.data()
        self.engine._replace_tower(self.engine.placements[self.sid],100,'machine_gun','green','virtual')
        self.assertNotEqual(old['aim_instance'],self.data()['aim_instance'])
        self.assertEqual(self.post(old).status_code,400)

    def test_camera_owner_returns_only_fresh_cached_jpeg(self):
        camera=load('camera-calibration')
        with patch.object(camera,'_ensure_corrected_worker'):
            camera._corrected_jpeg=b'image';camera._corrected_size=(1280,720);camera._corrected_frame_at=time.time()
            self.assertEqual(camera.preview_frame()['jpeg'],b'image')
            camera._corrected_frame_at=time.time()-5
            self.assertIsNone(camera.preview_frame()['jpeg'])
        camera.hub_stop()

    def test_camera_frame_is_authenticated_and_fresh(self):
        camera=SimpleNamespace(preview_frame=lambda:dict(contract='hhh.camera-frame',version=1,status='ready',
            coordinate_space='corrected-camera-normalized',frame_at=time.time(),jpeg=b'jpeg-fixture'))
        self.facade.hub_init(FakeContext({'camera-calibration':camera}))
        self.assertEqual(self.client.get('/api/assets/mobile-camera.jpg').status_code,403)
        r=self.client.get('/api/assets/mobile-camera.jpg',environ_overrides={'hhh.roles':{'green'}})
        self.assertEqual(r.status_code,200);self.assertEqual(r.data,b'jpeg-fixture')
        self.assertEqual(r.headers['Cache-Control'],'no-store')
