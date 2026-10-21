"""Multi-view accuracy, conflicting evidence, viewpoint identity and real flow."""
import copy
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
import cv2
import numpy as np
from test_mcam1_depth_pipeline import DEFAULT, DepthService, plane_image, fixture_frame
from depth_geometry import triangulate, lens_model
from depth_fusion import DepthFusion


class FusionGeometryTests(unittest.TestCase):
    def setUp(self):
        self.config = {**copy.deepcopy(DEFAULT), 'camera_offset_mm':[0,0,0], 'mount_rpy_deg':[0,0,0]}
        self.matrix, self.distortion, _ = lens_model(self.config, 480, 320)
        self.world = np.array([[x,y,120.+(x%4)*5] for x in range(-30,31,6) for y in range(-24,25,6)])
        self.rng = np.random.default_rng(28)
        self.first = self.project(self.world) + self.rng.normal(0,.12,(len(self.world),2))
        self.fusion = DepthFusion()
        self.fusion.begin(dict(gray=np.zeros((320,480),np.uint8),stamp=10),self.matrix,self.distortion,None)
        self.fusion.seeds = self.first.astype(np.float32)
        self.fusion.rays = np.column_stack((cv2.undistortPoints(self.first.reshape(-1,1,2),self.matrix,self.distortion).reshape(-1,2),np.ones(len(self.first))))

    def project(self, points):
        projected=points@self.matrix.T
        return projected[:,:2]/projected[:,2:]

    def observe(self, x, index, noise=0., wrong_depth=False, measured_position=None):
        centre=np.array([x,0.,0.])
        world=self.world if not wrong_depth else self.fusion.rays*(self.world[:,2]*1.6)[:,None]
        second=self.project(world-centre)+self.rng.normal(0,noise,self.first.shape)
        _,pixels,_,residuals,geometry=triangulate(self.first,second,[0,0,0,0],[x,0,0,0],self.config,self.matrix,self.distortion,details=True)
        return self.fusion.update(np.arange(len(self.first)),pixels,geometry,residuals,
            frame_key=(index,10+index*.1),stamp=10+index*.1,baseline=x,timing_motion=0,
            tracked_count=len(self.first),view_position=centre if measured_position is None else np.array(measured_position))

    def test_several_measured_views_reduce_error_against_known_geometry(self):
        errors=[]
        for i,x in enumerate([10,14,18,22,26,30],1):
            camera,_,evidence=self.observe(x,i,noise=.5)
            expected=np.array([self.world[int(row['track_id'].split(':')[1]),2] for row in evidence])
            self.assertGreater(len(camera),70)
            errors.append(float(np.sqrt(np.mean((camera[:,2]-expected)**2))))
        self.assertLess(errors[-1],errors[0]*.65,(errors,self.fusion.stats))
        self.assertGreater(self.fusion.stats['combined_points'],70)
        self.assertEqual(self.fusion.stats['max_views'],7)
        self.assertEqual(self.fusion.stats['state'],'refined')

    def test_conflicting_surface_is_hidden_and_does_not_poison_later_views(self):
        self.observe(12,1);self.observe(16,2)
        bad,_,_=self.observe(20,3,wrong_depth=True)
        self.assertEqual(len(bad),0)
        self.assertEqual(self.fusion.stats['rejected_observations'],len(self.first))
        recovered,_,evidence=self.observe(24,4)
        self.assertGreater(len(recovered),80)
        self.assertTrue(all(row['views']==4 for row in evidence),'Rejected viewpoint cannot increase accepted support')
        expected=np.array([self.world[int(row['track_id'].split(':')[1]),2] for row in evidence])
        self.assertLess(float(np.mean(abs(recovered[:,2]-expected))),.4)

    def test_bad_first_measurement_is_replaced_by_later_agreement(self):
        self.observe(12,1,wrong_depth=True)
        conflict,_,_=self.observe(16,2)
        self.assertEqual(len(conflict),0)
        recovered,_,evidence=self.observe(20,3)
        self.assertGreater(len(recovered),80)
        self.assertTrue(all(row['views']==3 for row in evidence))

    def test_same_measured_viewpoint_and_duplicate_frames_do_not_add_votes(self):
        self.observe(12,1)
        self.observe(12,1)
        for i in range(2,12):
            # Inferred camera-direction jitter must not masquerade as arm travel.
            self.observe(12+(i%2)*.4,i,measured_position=[12,0,0])
        self.assertEqual(self.fusion.stats['max_views'],2)
        self.assertEqual(self.fusion.stats['combined_points'],0)
        self.assertTrue(all(len(track['samples'])==1 for track in self.fusion.tracks.values()))

    def test_storage_is_bounded_and_clear_removes_all_feature_identity(self):
        for i,x in enumerate(np.arange(10,39,2),1):self.observe(float(x),i)
        self.assertTrue(all(len(track['samples'])<=8 for track in self.fusion.tracks.values()))
        self.assertLessEqual(self.fusion.stats['max_views'],9)
        generation=self.fusion.generation
        self.fusion.clear('Tracking lost')
        self.assertIsNone(self.fusion.reference);self.assertFalse(self.fusion.tracks)
        self.assertGreater(self.fusion.generation,generation)


class FusionPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.service=DepthService(SimpleNamespace(),Path(self.temp.name)/'calibration.json')
        self.service.running=True

    def tearDown(self):
        self.service.close();self.temp.cleanup()

    def frame(self, i, x, *, gray=None):
        stamp=10+i*.1;pose=np.array([x,0,41.5,0.])
        frame=fixture_frame(plane_image(pose,self.service.store.value) if gray is None else gray,stamp,i)
        self.service.motion=dict(speed_mm_s=30,pump_mode='off',pose=pose.tolist(),feedback_at=stamp)
        self.service._process(dict(stamp=stamp,received_at=stamp,jpeg=frame['image'],width=480,height=320,frame_id=i),pose,stamp)
        self.service.camera=dict(received_at=stamp,image=frame['image'],width=480,height=320)

    def test_real_optical_flow_refines_both_automatic_and_configured_paths(self):
        for configured in (False,True):
            with self.subTest(configured=configured):
                self.service.configure({**DEFAULT,'mounting_confirmed':configured})
                for i in range(11):self.frame(i,i*3)
                measured=self.service.snapshot(11.01)['measurement']
                self.assertIsNotNone(measured,self.service.message)
                self.assertEqual(measured['fusion']['state'],'refined')
                self.assertGreater(measured['fusion']['combined_points'],40)
                self.assertGreaterEqual(measured['fusion']['max_views'],5)
                self.assertAlmostEqual(float(np.median([p['depth_mm'] for p in measured['points']])),121.5,delta=1)
                self.assertTrue(all('track_id' in point and 'views' in point for point in measured['points']))
                self.assertIsNone(self.service.snapshot(11.01)['clearance_if_held_mm'])

    def test_stopping_does_not_add_support_and_loss_of_texture_clears_visible_map(self):
        for i in range(8):self.frame(i,i*3)
        views=self.service.measurement['fusion']['max_views']
        for i in range(8,12):self.frame(i,21)
        self.assertEqual(self.service.measurement['fusion']['max_views'],views)
        self.frame(12,24,gray=np.zeros((320,480),np.uint8))
        self.assertIsNone(self.service.measurement)

    def test_setup_pause_and_tracking_gap_reset_accumulated_evidence(self):
        for i in range(8):self.frame(i,i*3)
        self.assertTrue(self.service.fusion.tracks)
        self.service.configure(DEFAULT)
        self.assertFalse(self.service.fusion.tracks)
        for i in range(8):self.frame(i,i*3)
        self.service.set_running(False)
        self.assertIsNone(self.service.fusion.reference)
        self.service.set_running(True)
        for i in range(8):self.frame(i,i*3)
        self.frame(20,24)
        self.assertEqual(self.service.fusion.reference['frame_id'],20)
        self.assertFalse(self.service.fusion.tracks)
        self.assertIsNone(self.service.snapshot(12.01)['measurement'])


if __name__=='__main__':unittest.main()
