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
        self.tags=[{'id':i,'nx':.1+(i-30)*.13,'ny':.3,'missing':0} for i in range(30,36)]
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
          'dobot-mg400-relay':SimpleNamespace(arms_snapshot=lambda:self.arms(),stop_side=lambda side:dict(contract='hhh.relay.stop',version=1,status='ready',stopped=True))})
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

    def test_new_visible_measurement_updates_cache_and_ground_parallax_uses_it(self):
        self.warm();self.visible[1]['nx']=.24
        refreshed=self.warm();self.assertEqual(refreshed['31']['camera']['u'],.24)
        self.visible=[];result=self.capture(31)
        ground=result['sessions'][self.value['id']]['ground']['31']
        self.assertEqual(ground['camera'],{'u':.24,'v':.3});self.assertTrue(ground['camera_cached'])
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
        with self.assertRaisesRegex(ValueError,'Preparing calibration'):self.capture()

    def test_changed_correction_resolution_or_display_drops_old_positions(self):
        for change in ('correction','resolution','layout','reservation'):
            self.visible=copy.deepcopy(self.tags);self.warm();self.visible=[]
            if change=='correction':self.revision+='-new'
            elif change=='resolution':self.raw_size=[1920,1080]
            elif change=='layout':self.field._store['cal2-30']['x']+=1
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


if __name__=='__main__':unittest.main()
