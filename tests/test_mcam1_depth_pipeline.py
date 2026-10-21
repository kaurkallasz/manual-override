"""Deterministic geometry, real optical flow, timing and module boundary tests."""
import copy
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from unittest import mock
import cv2
import numpy as np
from flask import Flask
from test_photon_framework import load, FakeContext

module = load('mcam1-depth')
from depth_config import DEFAULT, validate, ConfigStore
from depth_geometry import camera_pose, lens_model, triangulate, translation_depth, fit_surface, clearance
from depth_motion import PoseHistory
from depth_vision import attachment, LensCalibration
from depth_service import DepthService


def arm(stamp, pose=(0, 0, 41.5, 0), **extra):
    return dict(connected=True, feedback_ok=True, feedback_at=stamp, pose=list(pose),
                motion_epoch=1, pump_mode='suck', **extra)


def fixture_frame(gray, stamp, sequence=1):
    return dict(contract='hhh.camera.still', version=1, status='ready', width=gray.shape[1],
                height=gray.shape[0], image=cv2.imencode('.jpg', gray)[1].tobytes(),
                frame_id=sequence, captured_at=stamp, corrected=False, mime_type='image/jpeg')


def project(points, pose, config, matrix):
    rotation, centre = camera_pose(pose, config)
    camera = (points-centre)@rotation
    image = camera@matrix.T
    return image[:, :2]/image[:, 2:]


def plane_image(pose, config, height=0):
    rng = np.random.default_rng(42)
    texture = rng.integers(0, 256, (1000, 1000), np.uint8)
    texture = cv2.GaussianBlur(texture, (15, 15), 3)
    texture = cv2.normalize(texture, None, 0, 255, cv2.NORM_MINMAX)
    matrix, _, _ = lens_model(config, 480, 320)
    rotation, centre = camera_pose(pose, config)
    world_from_texture = np.array([[.4, 0, -200], [0, .4, -200], [0, 0, height], [0, 0, 1.]])
    h = matrix@np.column_stack((rotation.T, -rotation.T@centre))@world_from_texture
    return cv2.warpPerspective(texture, h, (480, 320))


class GeometryTests(unittest.TestCase):
    def setUp(self):
        self.config = copy.deepcopy(DEFAULT)
        self.matrix, self.distortion, _ = lens_model(self.config, 480, 320)
        self.points = np.array([[x, y, 0.] for x in range(-30, 31, 10) for y in range(-25, 26, 10)])

    def test_measured_motion_recovers_metric_surface_and_atom_clearance(self):
        a, b = [0, 0, 41.5, 0], [20, 0, 41.5, 0]
        first, second = [project(self.points, pose, self.config, self.matrix) for pose in (a, b)]
        points, _, _, _ = triangulate(first, second, a, b, self.config, self.matrix, self.distortion)
        np.testing.assert_allclose(points, self.points, atol=1e-8)
        plane, _ = fit_surface(points)
        self.assertAlmostEqual(clearance(b, plane, self.config), 10, places=6)

    def test_base_corner_matters_for_tilted_plane(self):
        normal = np.array([.1, 0, 1.]);normal /= np.linalg.norm(normal)
        p = dict(normal=normal, offset=0)
        self.assertAlmostEqual(clearance([0,0,41.5,0],p,self.config),9/np.sqrt(1.01))

    def test_rotation_only_cannot_generate_depth(self):
        # Same optical centre with a camera offset on the rotation axis.
        a,b=[0,0,41.5,0],[0,0,41.5,10]
        first,second=[project(self.points,p,self.config,self.matrix) for p in (a,b)]
        world,*_=triangulate(first,second,a,b,self.config,self.matrix,self.distortion)
        self.assertEqual(len(world),0)

    def test_wrong_correspondences_and_vertical_planes_are_rejected(self):
        with self.assertRaises(ValueError):fit_surface(np.array([[0.,y,z] for y in range(10) for z in range(10)]))
        a,b=[0,0,41.5,0],[20,0,41.5,0]
        first=project(self.points,a,self.config,self.matrix)
        second=project(self.points,b,self.config,self.matrix)+[0,30]
        points,*_=triangulate(first,second,a,b,self.config,self.matrix,self.distortion)
        self.assertEqual(len(points),0)

    def test_calibrated_lens_rejects_changed_video_mode(self):
        self.config['intrinsics']=dict(width=480,height=320,matrix=self.matrix.tolist(),distortion=[0]*5,rms=.2)
        with self.assertRaisesRegex(ValueError,'mode changed'):lens_model(self.config,640,480)

    def test_automatic_translation_recovers_distances_without_mount_orientation(self):
        # Arbitrary lens location/orientation used only to render the fixture.
        config={**self.config,'camera_offset_mm':[30,-17,90],'mount_rpy_deg':[180,12,37]}
        a,b=np.array([0,0,41.5,0.]),np.array([16,8,41.5,0.])
        ra,ca=camera_pose(a,config);rb,cb=camera_pose(b,config)
        camera_points=np.array([[x,y,100+(x%3)*20] for x in range(-36,37,9) for y in range(-27,28,9)],float)
        world=camera_points@ra.T+ca
        first,second=[project(world,p,config,self.matrix) for p in (a,b)]
        got,pixels,_,_=translation_depth(first,second,np.linalg.norm(b[:3]-a[:3]),self.matrix,self.distortion)
        self.assertEqual(len(got),len(world))
        np.testing.assert_allclose(got,(world-cb)@rb,atol=1e-6)
        np.testing.assert_allclose(pixels,second)

    def test_automatic_translation_rejects_no_parallax_and_inconsistent_tracks(self):
        first=project(self.points,[0,0,41.5,0],self.config,self.matrix)
        self.assertEqual(len(translation_depth(first,first,20,self.matrix,self.distortion)[0]),0)
        scrambled=first+np.random.default_rng(4).uniform(-50,50,first.shape)
        self.assertEqual(len(translation_depth(first,scrambled,20,self.matrix,self.distortion)[0]),0)

    def test_automatic_translation_ignores_static_head_and_bad_correspondences(self):
        a,b=[0,0,41.5,0],[16,5,41.5,0]
        first,second=[project(self.points,p,self.config,self.matrix) for p in (a,b)]
        first=np.concatenate([first,first[:20],first[:8]])
        second=np.concatenate([second,first[:20],first[:8]+[0,35]])
        got,*_=translation_depth(first,second,np.hypot(16,5),self.matrix,self.distortion)
        self.assertGreaterEqual(len(got),len(self.points))
        self.assertAlmostEqual(float(np.median(got[:,2])),121.5,delta=.1)


class TimingTests(unittest.TestCase):
    def test_interpolation_follows_deceleration_and_never_extrapolates(self):
        history=PoseHistory()
        for t,x in [(1.,0),(1.1,10),(1.2,20),(1.3,25),(1.4,27)]:history.add(arm(t,[x,0,41.5,0]),t+.001)
        self.assertAlmostEqual(history.at(1.35)[0],26)
        self.assertIsNone(history.at(1.5))
        self.assertEqual(history.motion(arm(1.4))['phase'],'slowing')

    def test_stale_feedback_epoch_changes_and_large_gaps(self):
        h=PoseHistory();h.add(arm(1),1.01)
        h.add(arm(1.3),1.31)
        self.assertIsNone(h.at(1.1))
        h.add({**arm(1.4),'motion_epoch':2},1.41)
        self.assertEqual(len(h.samples),1)
        with self.assertRaises(ValueError):h.add(arm(1.4),2)
        self.assertFalse(h.samples)

    def test_specific_feedback_errors_keep_strict_freshness_checks(self):
        cases = [({'connected':False},'disconnected'),
                 ({'feedback_at':None},'timestamp is missing'),
                 ({'feedback_at':1.01},'ahead of'),
                 ({'feedback_at':.749},'stale'),
                 ({'feedback_ok':False},'invalid measured feedback'),
                 ({'pose':[0,float('nan'),0,0]},'position is missing or invalid'),
                 ({'motion_epoch':True},'motion generation')]
        for changes, message in cases:
            with self.subTest(changes=changes):
                h=PoseHistory();h.add(arm(.99),1.)
                with self.assertRaisesRegex(ValueError,message):h.add({**arm(1.),**changes},1.)
                self.assertFalse(h.samples)
        h=PoseHistory();h.add(arm(.75),1.)  # The 250 ms boundary is unchanged.
        self.assertEqual(len(h.samples),1)


class LensTests(unittest.TestCase):
    def test_capture_real_checkerboard_and_reject_duplicate(self):
        gray=np.full((320,480),255,np.uint8)
        for y in range(7):
            for x in range(10):
                if (x+y)%2==0:gray[50+y*30:50+(y+1)*30,80+x*30:80+(x+1)*30]=0
        lens=LensCalibration()
        self.assertEqual(lens.capture(gray,9,6,10),1)
        with self.assertRaisesRegex(ValueError,'similar'):lens.capture(gray,9,6,10)

    def test_varied_board_views_recover_lens_intrinsics(self):
        lens=LensCalibration();lens.size=(480,320);lens.pattern=(9,6,10)
        board=np.zeros((54,3),np.float32);board[:,:2]=np.mgrid[0:9,0:6].T.reshape(-1,2)*10
        matrix=np.array([[450.,0,240],[0,450.,160],[0,0,1.]])
        for i in range(12):
            r=np.array([-.3+(i%4)*.2,-.25+(i%3)*.25,(i-6)*.015])
            t=np.array([-40.+i%3*4,-25.+i%4*3,220.+i*8])
            corners,_=cv2.projectPoints(board,r,t,matrix,np.zeros(5))
            lens.samples.append(corners)
        solved=lens.solve()
        self.assertAlmostEqual(solved['matrix'][0][0],450,delta=.2)
        self.assertLess(solved['rms'],.01)


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.camera_output=fixture_frame(np.zeros((320,480),np.uint8),time.time())
        self.arm_output=arm(time.time())
        self.camera=SimpleNamespace(still_snapshot=lambda:self.camera_output)
        self.relay=SimpleNamespace(arms_snapshot=lambda:dict(contract='hhh.relay.arms',version=1,status='ready',arms={'green':self.arm_output}))
        self.ctx=FakeContext({'mcam1':self.camera,'dobot-mg400-relay':self.relay})
        self.service=DepthService(self.ctx,Path(self.temp.name)/'calibration.json')

    def tearDown(self):
        self.service.close();self.temp.cleanup()

    def assert_samples_arriving_during_reads(self, newer_frame=False):
        clock = [10.]
        iterations = [0]
        def camera_read():
            self.camera_output['captured_at'] = clock[0]
            clock[0] += .004
            if newer_frame:self.camera_output['captured_at'] = clock[0]
            self.camera_output['frame_id'] += 1
            return self.camera_output
        def arm_read():
            clock[0] += .004
            self.arm_output = arm(clock[0], [clock[0]*10,0,41.5,0])
            return dict(contract='hhh.relay.arms',version=1,status='ready',arms={'green':self.arm_output})
        self.camera.still_snapshot = camera_read
        self.relay.arms_snapshot = arm_read
        def step(_):
            result = self.service.snapshot()
            self.assertIsNone(result['error'])
            self.assertIsNotNone(result['camera'])
            self.assertIsNotNone(result['motion'])
            iterations[0] += 1
            clock[0] += .03
        stop = SimpleNamespace(is_set=lambda:iterations[0]>=12,wait=step)
        with patch.object(self.service,'stop_event',stop), patch('depth_service.time.time',side_effect=lambda:clock[0]):
            self.service._loop()
        self.assertEqual(len(self.service.poses.samples),12)
        self.assertGreater(self.service.motion['speed_mm_s'],0)

    def test_feedback_arriving_during_owner_reads_is_fresh(self):
        self.assert_samples_arriving_during_reads()

    def test_frame_arriving_during_owner_read_is_fresh(self):
        self.assert_samples_arriving_during_reads(newer_frame=True)

    def test_snapshot_samples_clock_after_observer_lock_is_acquired(self):
        clock = [10.]
        service = self.service
        class UpdatingLock:
            def __enter__(self):
                clock[0] += .01
                service.camera = dict(received_at=clock[0],image=b'x')
                service.motion = dict(feedback_at=clock[0],pose=[0,0,41.5,0])
            def __exit__(self,*args):pass
        with patch.object(service,'lock',UpdatingLock()), patch('depth_service.time.time',side_effect=lambda:clock[0]):
            result = service.snapshot()
        self.assertIsNotNone(result['camera'])
        self.assertIsNotNone(result['motion'])

    def test_real_optical_flow_and_triangulation_recover_plane(self):
        s=self.service
        s.configure({**DEFAULT,'mounting_confirmed':True,'surface_roi':[.1,.1,.8,.8]})
        s.running=True
        a,b=[0,0,41.5,0],[20,0,41.5,0]
        s.motion=dict(speed_mm_s=20,pump_mode='suck',pose=b,feedback_at=11.)
        for t,p in [(10.,a),(11.,b)]:
            gray=plane_image(p,s.store.value)
            frame=fixture_frame(gray,t,int(t))
            s._process(dict(stamp=t,received_at=t,jpeg=frame['image'],width=480,height=320,frame_id=int(t)),np.array(p,float),t)
        self.assertIsNotNone(s.plane,s.message)
        self.assertLess(abs(clearance(b,s.plane,s.store.value)-10),1.)
        self.assertGreater(s.plane['inliers'],20)
        s.camera={'width':480,'height':320,'frame_id':11,'received_at':11.,'image':b'x','preview':'data:image/jpeg;base64,eA=='}
        result=s.snapshot(11.01)
        self.assertEqual(result['status'],'ready')
        self.assertAlmostEqual(result['clearance_if_held_mm'],10,delta=1.)
        self.assertEqual(s.snapshot(11.6)['status'],'unavailable')
        self.assertIsNone(s.snapshot(11.6)['clearance_if_held_mm'])

    def test_scene_map_keeps_raised_objects_outside_the_screen_plane(self):
        s=self.service
        s.configure({**DEFAULT,'mounting_confirmed':True,'surface_roi':[0,.8,1,.2]})
        s.running=True
        matrix,_,_=lens_model(s.store.value,480,320)
        corners=np.array([[-15,-15,35],[15,-15,35],[15,15,35],[-15,15,35]],float)
        for t,p in [(10.,[-8,0,41.5,0]),(11.,[8,0,41.5,0])]:
            gray=plane_image(p,s.store.value)
            mask=np.zeros(gray.shape,np.uint8)
            cv2.fillConvexPoly(mask,np.int32(project(corners,p,s.store.value,matrix)),255)
            raised=plane_image(p,s.store.value,35)
            gray[mask>0]=raised[mask>0]
            frame=fixture_frame(gray,t,int(t))
            s.motion=dict(speed_mm_s=16,pump_mode='off',pose=p,feedback_at=t)
            s._process(dict(stamp=t,received_at=t,jpeg=frame['image'],width=480,height=320,frame_id=int(t)),np.array(p,float),t)
        self.assertIsNotNone(s.measurement,s.message)
        points=s.measurement['points']
        self.assertGreater(len(points),200)
        near=[p['depth_mm'] for p in points if mask[min(319,int(p['y']*320)),min(479,int(p['x']*480))]>0]
        far=[p['depth_mm'] for p in points if p['y']>.8]
        self.assertGreater(len(near),15)
        self.assertAlmostEqual(float(np.median(near)),86.5,delta=2)
        self.assertAlmostEqual(float(np.median(far)),121.5,delta=2)
        self.assertAlmostEqual(s.plane['offset'],0,delta=1)
        self.assertTrue(all(p['distance_mm']>=p['depth_mm']-.1 for p in points))

    def test_scene_depth_does_not_require_a_screen_region_and_expires(self):
        s=self.service;s.configure({**DEFAULT,'mounting_confirmed':True});s.running=True
        for t,p in [(10.,[0,0,41.5,0]),(11.,[20,0,41.5,0])]:
            frame=fixture_frame(plane_image(p,s.store.value),t,int(t))
            s.motion=dict(speed_mm_s=20,pump_mode='off',pose=p,feedback_at=t)
            s._process(dict(stamp=t,received_at=t,jpeg=frame['image'],width=480,height=320,frame_id=int(t)),np.array(p,float),t)
        s.camera=dict(width=480,height=320,frame_id=11,received_at=11.,image=b'x',preview='fixture')
        out=s.snapshot(11.01)
        self.assertEqual(out['status'],'ready')
        self.assertGreater(len(out['measurement']['points']),50)
        self.assertIsNone(out['plane']);self.assertIsNone(out['clearance_if_held_mm'])
        s.camera['received_at']=s.motion['feedback_at']=11.6
        self.assertIsNone(s.snapshot(11.6)['measurement'])

    def test_uncalibrated_motion_depth_uses_video_direction_and_never_clearance(self):
        s=self.service;s.running=True
        # No setup saved; the camera is mounted at a different yaw from defaults.
        actual={**DEFAULT,'mount_rpy_deg':[180,0,25]}
        for t,p in [(10.,[0,0,41.5,0]),(11.,[12,5,41.5,0])]:
            frame=fixture_frame(plane_image(p,actual),t,int(t))
            s.motion=dict(speed_mm_s=13,pump_mode='off',pose=p,feedback_at=t)
            s._process(dict(stamp=t,received_at=t,jpeg=frame['image'],width=480,height=320,frame_id=int(t)),np.array(p,float),t)
        self.assertIsNotNone(s.measurement,s.message)
        self.assertEqual(s.measurement['method'],'automatic_motion')
        self.assertGreater(len(s.measurement['points']),50)
        self.assertAlmostEqual(float(np.median([p['depth_mm'] for p in s.measurement['points']])),121.5,delta=2)
        s.camera=dict(received_at=11.,image=b'x')
        result=s.snapshot(11.01)
        self.assertEqual(result['status'],'ready');self.assertTrue(result['automatic_motion_supported'])
        self.assertIsNone(result['plane']);self.assertIsNone(result['clearance_if_held_mm'])
        self.assertFalse(result['config']['mounting_confirmed'])

    def test_unconfigured_rotating_tool_does_not_supply_automatic_scale(self):
        s=self.service;s.running=True
        for t,p in [(10.,[0,0,41.5,0]),(11.,[20,0,41.5,1])]:
            frame=fixture_frame(plane_image(p,DEFAULT),t,int(t))
            s.motion=dict(speed_mm_s=20,pump_mode='off',pose=p,feedback_at=t)
            s._process(dict(stamp=t,received_at=t,jpeg=frame['image'],width=480,height=320,frame_id=int(t)),np.array(p,float),t)
        self.assertIsNone(s.measurement)

    def test_automatic_motion_recovers_an_angled_view_with_a_co_moving_head(self):
        s=self.service;s.running=True
        actual={**DEFAULT,'mount_rpy_deg':[145,0,25]}
        rng=np.random.default_rng(7)
        head=rng.integers(0,256,(150,100),dtype=np.uint8)
        for t,p in [(10.,[0,0,41.5,0]),(11.,[12,5,41.5,0])]:
            gray=plane_image(p,actual)
            gray[20:170,190:290]=head  # Head texture moves with the camera.
            frame=fixture_frame(gray,t,int(t))
            s.motion=dict(speed_mm_s=13,pump_mode='off',pose=p,feedback_at=t)
            s._process(dict(stamp=t,received_at=t,jpeg=frame['image'],width=480,height=320,frame_id=int(t)),np.array(p,float),t)
        self.assertIsNotNone(s.measurement,s.message)
        self.assertEqual(s.measurement['method'],'automatic_motion')
        points=s.measurement['points'];self.assertGreater(len(points),50)
        matrix,_,_=lens_model(actual,480,320);rotation,centre=camera_pose(p,actual)
        pixels=np.array([[row['x']*480,row['y']*320,1] for row in points])
        rays=pixels@np.linalg.inv(matrix).T@rotation.T
        expected=-centre[2]/rays[:,2]
        error=np.abs(np.array([row['depth_mm'] for row in points])-expected)
        self.assertLess(float(np.median(error)),2)
        self.assertIsNone(s.plane,'Automatic camera direction cannot establish robot-coordinate clearance')

    def test_co_moving_texture_cannot_be_given_camera_depth(self):
        s=self.service;s.configure({**DEFAULT,'mounting_confirmed':True});s.running=True
        gray=plane_image([0,0,41.5,0],s.store.value)
        for t,p in [(10.,[0,0,41.5,0]),(11.,[20,0,41.5,0])]:
            frame=fixture_frame(gray,t,int(t))
            s.motion=dict(speed_mm_s=20,pump_mode='suck',pose=p,feedback_at=t)
            s._process(dict(stamp=t,received_at=t,jpeg=frame['image'],width=480,height=320,frame_id=int(t)),np.array(p,float),t)
        self.assertIsNone(s.measurement)
        self.assertIsNone(s.plane)

    def test_no_unconfigured_metric_output_and_duplicate_frames_are_not_motion(self):
        t=time.time();self.camera_output['captured_at']=t;self.arm_output=arm(t-.01)
        s=self.service;s.running=True;s.tick(t)
        self.assertIsNone(s.snapshot(t)['clearance_if_held_mm']);self.assertFalse(s.keys)
        s.configure({**DEFAULT,'mounting_confirmed':True,'surface_roi':[0,0,1,1]})
        self.arm_output=arm(t-.02);s.tick(t)
        self.arm_output=arm(t+.02);s.tick(t+.03)
        self.assertEqual(len(s.keys),1)
        s.tick(t+.04);self.assertEqual(len(s.keys),1)

    def test_camera_preview_survives_disconnected_arm_but_measurements_do_not(self):
        t=time.time();self.camera_output['captured_at']=t;self.arm_output['connected']=False
        self.service.tick(t)
        out=self.service.snapshot(t)
        self.assertIsNotNone(out['camera']);self.assertIsNone(out['motion']);self.assertEqual(out['status'],'unavailable')
        self.assertIn('Green arm: disconnected',out['error'])

    def test_disabled_and_boolean_version_are_rejected(self):
        self.camera_output['version']=True
        with self.assertRaises(ValueError):self.service.tick(time.time())
        self.ctx.modules.pop('mcam1')
        with self.assertRaises(ValueError):self.service.tick(time.time())

    def test_bad_settings_do_not_replace_calibration(self):
        self.service.configure(DEFAULT)
        before=(Path(self.temp.name)/'calibration.json').read_bytes()
        for patch in [{'horizontal_fov_deg':float('nan')},{'surface_roi':[.9,0,.5,1]}, {'side':'both'}, {'mounting_confirmed':1}, {'intrinsics':{}}]:
            with self.subTest(patch=patch), self.assertRaises(ValueError):self.service.configure({**DEFAULT,**patch})
            self.assertEqual((Path(self.temp.name)/'calibration.json').read_bytes(),before)

    def test_missing_features_never_mean_no_atom_and_co_motion_is_only_evidence(self):
        blank=np.zeros((320,480),np.uint8)
        self.assertEqual(attachment(blank,blank,[.2,.2,.4,.4],10,'suck')['state'],'unknown')
        textured=plane_image([0,0,41.5,0],DEFAULT)
        self.assertEqual(attachment(textured,textured,[.2,.2,.4,.4],10,'suck')['state'],'moves_with_head')
        self.assertEqual(attachment(textured,textured,[.2,.2,.4,.4],0,'suck')['state'],'unknown')
        self.assertEqual(attachment(textured,textured,[.2,.2,.4,.4],10,'off')['state'],'unknown')

    def test_routes_cannot_control_hardware_and_reject_foreign_origin(self):
        module._service=self.service
        app=Flask(__name__);app.register_blueprint(module.bp);client=app.test_client()
        try:
            with client.get('/') as response:self.assertEqual(response.status_code,200)
            with client.get('/checkerboard.svg') as response:self.assertEqual(response.status_code,200)
            self.assertEqual(client.post('/api/config',json=DEFAULT,headers={'Origin':'https://foreign.test'}).status_code,403)
            self.assertEqual(client.post('/api/analysis',json={'running':True}).status_code,200)
            self.assertEqual(client.post('/api/analysis',json={'running':'yes'}).status_code,400)
            self.assertEqual(client.post('/api/lens',json={'action':'solve'}).status_code,400)
            self.assertEqual(client.post('/api/move',json={}).status_code,404)
            self.assertEqual(client.post('/api/pump',json={}).status_code,404)
            self.assertEqual(client.get('/calibration.json').status_code,404)
        finally:module._service=None

    def test_lifecycle_stops_observer_and_clears_state(self):
        self.service.start_worker();self.service.close()
        self.assertFalse(self.service.thread.is_alive());self.assertIsNone(self.service.camera)


if __name__=='__main__':unittest.main()
