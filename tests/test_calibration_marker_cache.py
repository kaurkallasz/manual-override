"""Occluded calibration targets with real owner code, fake optics and fake arms."""
import copy
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from test_photon_framework import load, FakeContext


class CalibrationMarkerCacheTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        root=Path(self.folder.name)
        self.owner=load('auto-pickup-game');self.owner._lessons=self.owner.LessonStore(root/'lessons.json')
        self.field=load('playfield-areas');self.field.HERE=str(root)
        self.field.SETTINGS_PATH=str(root/'settings.json');self.field.AREAS_PATH=str(root/'areas.json')
        self.tags=[{'id':i,'nx':.1+(i-30)*.13,'ny':(.3,.3,.5,.7,.7,.3)[i-30],'missing':0} for i in range(30,36)]
        self.visible=copy.deepcopy(self.tags);self.tracked=copy.deepcopy(self.tags)
        self.revision='lens-v1';self.camera_age=0;self.arm_age=0;self.connected=True
        self.pose=[300,20,50,0];self.raw_size=[1280,720]
        self.raw=lambda:dict(contract='hhh.webcam.tags',version=1,status='ready',frame_at=time.time()-self.camera_age,
                             tags=self.tracked,detections=self.visible,width=self.raw_size[0],height=self.raw_size[1])
        self.correction=lambda tags,detections:dict(contract='hhh.camera-correction',version=1,status='ready',
                       corrected=True,calibration_revision=self.revision,tags=copy.deepcopy(tags),detections=copy.deepcopy(detections))
        self.arms=lambda:dict(contract='hhh.relay.arms',version=1,status='ready',arms={side:dict(connected=self.connected,
                             enabled=True,feedback_at=time.time()-self.arm_age,pose=list(self.pose),device={'ip':side}) for side in ('green','purple')})
        self.owner._hub_ctx=FakeContext({'playfield-areas':self.field,
          'webcam':SimpleNamespace(tag_snapshot=lambda:self.raw()),
          'camera-calibration':SimpleNamespace(corrected_tag_snapshot=lambda *args:self.correction(*args)),
          'dobot-mg400-relay':SimpleNamespace(arms_snapshot=lambda:self.arms(),stop_side=lambda side:dict(contract='hhh.relay.stop',version=1,status='ready',stopped=True),disable_side=lambda side:dict(contract='hhh.relay.disabled',version=1,status='ready',inhibited=True,connected=True,disabled=True))})
        self.value={'id':'occluded:green','side':'green','practice':True}
        self.owner.calibration_session_begin(self.value)

    def warm(self):
        return self.owner.calibration_session_maintain()['sessions'][self.value['id']]['marker_positions']

    def capture(self,marker=30):
        return self.owner.calibration_session_command(self.value['side'],dict(id=self.value['id'],action='capture',marker=marker))

    def test_visible_once_then_fully_covered_captures_current_pose_for_both_players(self):
        for side in ('green','purple'):
            if side=='purple':
                self.owner.calibration_session_release(self.value)
                self.value={'id':'occluded:purple','side':'purple','practice':True}
                self.visible=copy.deepcopy(self.tags)
                self.owner.calibration_session_begin(self.value)
            located=self.warm();self.assertEqual(len(located),6)
            self.visible=[]  # Even tracked tags must not pretend to be new detections.
            self.pose=[335,26,10,0]
            with patch('time.time',return_value=time.time()+8):
                result=self.capture()
            point=result['sessions'][self.value['id']]['draft']['points']['p1']
            self.assertEqual(point['camera'],{'u':.1,'v':.3})
            self.assertEqual(point['pose']['x'],335)
            self.assertTrue(point['camera_cached'])
            self.assertEqual(point['camera_observed_at'],located['30']['frame_at'])
            self.assertEqual([a['marker'] for a in self.field.list_areas() if a['color']=='#33ff88'],[30])

    def test_distorted_visible_measurement_cannot_replace_frozen_ground(self):
        self.warm();self.visible[1]['nx']=.24
        refreshed=self.warm();self.assertEqual(refreshed['31']['camera']['u'],.23)
        self.visible=[];result=self.capture(31)
        ground=result['sessions'][self.value['id']]['ground']['31']
        self.assertEqual(ground['camera'],{'u':.23,'v':.3});self.assertTrue(ground['camera_cached'])
        # Glow changes must not invalidate the other five positions.
        self.assertEqual(len(self.warm()),6)

    def test_missing_or_invalid_detections_cannot_seed_a_cache(self):
        for detected in ([],[dict(self.tags[0],missing=.1)],[dict(self.tags[0],nx=float('nan'))]):
            self.owner._lessons.clear_marker_cache();self.visible=detected
            with self.assertRaisesRegex(ValueError,'Preparing calibration'):self.capture()

    def test_cache_cannot_replace_current_camera_and_robot_feedback(self):
        self.warm();self.visible=[]
        self.arm_age=4
        with self.assertRaisesRegex(ValueError,'fresh camera and arm'):self.capture()
        self.arm_age=0;self.connected=False
        with self.assertRaisesRegex(ValueError,'fresh enabled arm'):self.capture()
        self.connected=True;self.camera_age=4
        with self.assertRaisesRegex(ValueError,'fresh camera and arm'):self.capture()
        self.camera_age=0
        self.assertTrue(self.capture()['sessions'][self.value['id']]['draft']['points']['p1']['camera_cached'])

    def test_changed_correction_resolution_or_display_drops_old_positions(self):
        for change in ('correction','resolution','layout','source','reservation'):
            self.visible=copy.deepcopy(self.tags);self.warm();self.visible=[]
            if change=='correction':self.revision+='-new'
            elif change=='resolution':self.raw_size=[1920,1080]
            elif change=='layout':self.field._store['cal2-30']['x']+=1
            elif change=='source':
                raw=self.raw
                self.raw=lambda:dict(raw(),camera_identity='replacement-camera:2')
            else:self.field._display_session['side']='purple'
            with self.assertRaises(ValueError):self.capture()
            self.assertEqual(self.owner._lessons.snapshot()['sessions'][self.value['id']].get('captures'),{})

    def test_same_display_reactivation_preserves_cache_but_restart_and_release_clear_it(self):
        self.warm();self.visible=[]
        self.owner._lessons.begin(self.value,self.owner._calibration2_public())
        self.assertTrue(self.capture()['sessions'][self.value['id']]['draft']['points']['p1']['camera_cached'])
        self.visible=copy.deepcopy(self.tags);self.warm()
        restored=self.owner.LessonStore(self.owner._lessons.path)
        self.assertIsNone(restored.marker_cache)
        self.assertNotIn('marker_positions',restored.snapshot()['sessions'][self.value['id']])
        self.owner.calibration_session_release(self.value)
        self.assertNotIn('marker_preparation',self.owner.calibration_session_snapshot())

    def test_offline_preparation_accumulates_all_six_before_connect_for_both_players(self):
        self.owner.calibration_session_release(self.value)
        for side in ('green','purple'):
            self.value={'id':'prepare:'+side,'side':side,'practice':True}
            self.connected=False;self.visible=[self.tags[0]]
            with self.assertRaisesRegex(ValueError,'fresh enabled arm'):
                self.owner.calibration_session_begin(self.value)
            for marker in range(30,36):
                self.visible=[self.tags[marker-30]]
                state=self.owner.calibration_session_maintain()
                preparation=state['marker_preparation']
                self.assertNotIn(self.value['id'],state['sessions'])
                self.assertTrue(state['requires_activation'])
                self.assertEqual(set(preparation['marker_positions']),{str(i) for i in range(30,marker+1)})
                self.assertEqual(preparation['ready'],marker==35)
                # Game retries begin while hardware is disconnected.
                with self.assertRaises(ValueError):self.owner.calibration_session_begin(self.value)
            self.visible=[];self.connected=True
            self.owner.calibration_session_begin(self.value)
            self.assertTrue(self.capture()['sessions'][self.value['id']]['draft']['points']['p1']['camera_cached'])
            self.owner.calibration_session_release(self.value)

    def test_current_frame_ids_accept_poll_delay_but_reject_held_detections(self):
        raw=self.raw
        self.owner._lessons.clear_marker_cache()
        self.visible=[dict(t,missing=.12) for t in self.tags]
        self.raw=lambda:dict(raw(),visible_ids=list(range(30,36)))
        self.assertEqual(len(self.warm()),6)
        self.owner._lessons.clear_marker_cache()
        self.raw=lambda:dict(raw(),visible_ids=[])
        self.assertEqual(self.warm(),{})
        with self.assertRaisesRegex(ValueError,'Preparing calibration'):self.capture()

    def test_capture_waits_for_all_six_even_when_requested_marker_is_visible(self):
        self.owner._lessons.clear_marker_cache();self.visible=self.tags[:5]
        with self.assertRaisesRegex(ValueError,'markers 35 visible'):self.capture()
        self.assertFalse(self.owner.calibration_session_snapshot()['marker_preparation']['ready'])

    def test_unconfirmed_detections_wait_for_tracker_promotion(self):
        self.owner._lessons.clear_marker_cache();self.tracked=[]
        self.assertEqual(self.warm(),{})
        with self.assertRaisesRegex(ValueError,'Preparing calibration'):self.capture()
        self.tracked=copy.deepcopy(self.tags)
        self.assertEqual(len(self.warm()),6)

    def capture_six(self):
        for marker in range(30,36):
            self.pose[0]=300+(marker-30)*10
            result=self.capture(marker)
        return result['sessions'][self.value['id']]

    def test_six_ground_and_four_raised_samples_share_one_frozen_reference_set(self):
        for side in ('green','purple'):
            if side=='purple':
                self.owner.calibration_session_release(self.value)
                self.value={'id':'frozen:purple','side':side,'practice':True}
                self.visible=copy.deepcopy(self.tags)
                self.owner.calibration_session_begin(self.value)
            original=self.warm()
            self.visible[1]['nx']+=.02  # A projected code displaced onto the arm.
            session=self.capture_six()
            self.assertEqual(session['stage'],'perspective')
            # The real display hides the centres. This must not reset the cache.
            self.visible=[t for t in self.visible if t['id'] in (31,35,33,34)]
            self.assertEqual(self.warm(),original)
            for marker in (31,35,33,34):
                raised={'u':.3,'v':.4}
                result=self.owner.calibration_session_command(side,dict(id=self.value['id'],action='raised',marker=marker,camera=raised))
                sample=result['sessions'][self.value['id']]['draft']['parallax_points'][str(marker)]
                self.assertEqual(sample['ground'],original[str(marker)]['camera'])
                self.assertEqual(sample['raised'],raised)
            self.assertEqual(self.warm(),original)

    def moved_frames(self, offsets=(.1,.4,.7)):
        base=time.time()
        for seconds in offsets:
            with patch('time.time',return_value=base+seconds):
                result=self.owner.calibration_session_maintain()
        return result

    def test_camera_translation_clears_draft_and_requires_new_ground_and_raised_samples(self):
        original=self.warm();self.capture_six()
        self.owner.calibration_session_command('green',dict(id=self.value['id'],action='raised',marker=31,camera={'u':.3,'v':.4}))
        stale=self.owner._fresh_calibration_measurement('green',31)
        for tag in self.visible:tag.update(nx=tag['nx']+.02,ny=tag['ny']-.018)
        pending=self.moved_frames((.1,))
        self.assertTrue(pending['marker_preparation']['movement_pending'])
        self.assertFalse(pending['marker_preparation']['ready'])
        with self.assertRaisesRegex(ValueError,'Camera movement'):self.capture()
        with self.assertRaisesRegex(ValueError,'Camera movement'):
            self.owner._lessons.derive_heights('green',self.value['id'],offline=True)
        result=self.moved_frames()
        self.assertEqual(result['marker_preparation']['marker_positions'],{})
        session=result['sessions'][self.value['id']]
        self.assertEqual(session['captures'],{});self.assertEqual(session['ground'],{})
        self.assertEqual(session['stage'],'points');self.assertIsNone(session['pickup_height'])
        self.assertTrue(all(not p['pose']['set'] and p['camera'] is None for p in session['draft']['points'].values()))
        self.assertTrue(all(p is None for p in session['draft']['parallax_points'].values()))
        self.assertIn('Camera moved',session['reference_reset']['reason'])
        with self.assertRaisesRegex(ValueError,'references changed'):
            self.owner._lessons.capture('green',dict(id=self.value['id'],marker=31),stale)
        with patch('time.time',return_value=time.time()+1):
            updated=self.warm()
        self.assertEqual(len(updated),6)
        self.assertAlmostEqual(updated['31']['camera']['u'],original['31']['camera']['u']+.02)
        restored=self.owner.LessonStore(self.owner._lessons.path)
        self.assertEqual(restored.snapshot()['sessions'][self.value['id']]['captures'],{})

    def test_camera_rotation_is_detected_with_only_four_outer_targets_visible(self):
        import math
        self.warm()
        self.visible=[t for t in self.visible if t['id'] in (31,35,33,34)]
        angle=.03
        for tag in self.visible:
            u,v=tag['nx']-.5,tag['ny']-.5
            tag.update(nx=.5+u*math.cos(angle)-v*math.sin(angle),ny=.5+u*math.sin(angle)+v*math.cos(angle))
        self.assertEqual(self.moved_frames()['marker_preparation']['marker_positions'],{})

    def test_noise_one_bad_tag_occlusion_and_one_bad_frame_preserve_frozen_references(self):
        original=self.warm()
        for tag in self.visible:tag['nx']+=.001
        self.assertEqual(self.moved_frames()['marker_preparation']['marker_positions'],original)
        self.visible[0]['nx']+=.08
        self.assertEqual(self.moved_frames()['marker_preparation']['marker_positions'],original)
        # One apparent whole-board jump suspends capture, but does not reset.
        for tag in self.visible:tag['nx']+=.02
        with patch('time.time',return_value=time.time()+2):
            self.warm()
            self.assertTrue(self.owner._lessons.snapshot()['marker_preparation']['movement_pending'])
        self.visible=[]
        with patch('time.time',return_value=time.time()+3):
            self.assertEqual(self.warm(),original)
            self.assertTrue(self.owner._lessons.snapshot()['marker_preparation']['ready'])

    def test_repolling_one_frame_cannot_confirm_camera_movement(self):
        original=self.warm()
        for tag in self.visible:tag['nx']+=.02
        raw=self.raw;stamp=time.time()+.1
        self.raw=lambda:dict(raw(),frame_at=stamp)
        for offset in (.1,.4,.7,1):
            with patch('time.time',return_value=stamp+offset):self.warm()
        state=self.owner._lessons.snapshot()
        self.assertEqual(state['marker_preparation']['marker_positions'],original)
        self.assertTrue(state['marker_preparation']['movement_pending'])

    def test_context_change_clears_captured_pairs_not_just_optical_cache(self):
        self.warm();self.capture(31)
        self.revision='lens-v2';self.visible=[]
        self.warm()
        session=self.owner._lessons.snapshot()['sessions'][self.value['id']]
        self.assertEqual(session['captures'],{});self.assertEqual(session['ground'],{})
        self.assertIsNone(session['camera_revision'])

    def test_commit_cannot_save_snapshot_invalidated_by_its_camera_check(self):
        self.warm();self.capture_six()
        for marker in (31,35,33,34):
            self.owner.calibration_session_command('green',dict(id=self.value['id'],action='raised',marker=marker,camera={'u':.3,'v':.4}))
        self.revision='lens-v2'
        with patch.object(self.owner,'atomic_json') as persist:
            with self.assertRaisesRegex(ValueError,'measurements changed'):
                self.owner._commit_calibration_measurements('green',self.value['id'])
            persist.assert_not_called()
        self.assertEqual(self.owner._lessons.snapshot()['sessions'][self.value['id']]['captures'],{})

    def test_glow_visibility_and_brightness_changes_do_not_reset_ground_references(self):
        original=self.warm();self.capture(31)
        self.field._store['cal2-30'].update(show_aruco=False,glow=2.5)
        self.field._settings.update(bloom=2,global_brightness=.8)
        self.visible=[]
        self.assertEqual(self.warm(),original)
        self.assertIn('31',self.owner._lessons.snapshot()['sessions'][self.value['id']]['captures'])


if __name__=='__main__':unittest.main()
