"""Actual calibration/display owners with temporary persistence and fake sensors."""
import copy
from pathlib import Path
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from test_photon_framework import load,FakeContext


class DisplayOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup);self.path=Path(self.folder.name)
        self.field=load('playfield-areas');self.field.HERE=str(self.path);self.field.SETTINGS_PATH=str(self.path/'settings.json');self.field.AREAS_PATH=str(self.path/'areas.json')
        self.owner=load('auto-pickup-game');self.owner._lessons=self.owner.LessonStore(self.path/'lessons.json')
        self.relay=SimpleNamespace(stop_side=lambda side:dict(contract='hhh.relay.stop',version=1,status='ready',stopped=True))
        self.owner._hub_ctx=FakeContext({'playfield-areas':self.field,'dobot-mg400-relay':self.relay})
        self.cal={'revision':1,'playfield':{'saved_areas':[{'id':f'a{i}','marker':i,'color':'#33ff88','glow':4} for i in range(30,36)]},
                  'arms':{side:{'points':{str(i):{'marker':i,'camera':{'u':.1,'v':.1},'pose':{'set':True}} for i in range(30,36)}} for side in ('green','purple')}}
        self.cal_patch=patch.object(self.owner,'_calibration2_public',side_effect=lambda:copy.deepcopy(self.cal));self.cal_patch.start();self.addCleanup(self.cal_patch.stop)
        self.measure_patch=patch.object(self.owner,'_fresh_calibration_measurement',side_effect=lambda side,marker=None:{'pose':[300+(marker or 30),0,10,0],'camera':{'u':.1,'v':.2},'frame_at':time.time(),'feedback_at':time.time(),'camera_revision':'lens','rig_identity':{'ip':'test'}})
        self.measure_patch.start();self.addCleanup(self.measure_patch.stop)
        self.value={'id':'run:green','side':'green','player_id':'test','practice':False,'piece_ids':[100]}
    def test_new_turn_resets_old_glows_and_only_durable_capture_is_green(self):
        self.owner.calibration_session_begin(self.value)
        self.assertTrue(all(a['color']=='#82baff' for a in self.field.list_areas()))
        self.owner.calibration_session_command('green',{'action':'capture','id':self.value['id'],'marker':30})
        green=[a['marker'] for a in self.field.list_areas() if a['color']=='#33ff88']
        self.assertEqual(green,[30])
        self.assertTrue(next(a for a in self.field.list_areas() if a['marker']==30)['show_area'])
        self.assertGreater(self.field.display_snapshot()['settings']['bloom'],0)
        self.owner.calibration_session_begin(self.value)
        self.assertEqual([a['marker'] for a in self.field.list_areas() if a['color']=='#33ff88'],[30])

    def test_initial_calibration_uses_workspace_guard_without_a_finished_camera_fit(self):
        self.cal['format']='auto-pp-calibration-2-v1'
        self.owner.calibration_session_begin(self.value)
        scope=self.owner.calibration_safety_snapshot('green')
        self.assertEqual(scope['status'],'ready')
        self.assertEqual(len(scope['guard']['polygon']),4)
        self.assertGreaterEqual(scope['guard']['radius_min'],220)
        self.assertEqual(self.owner.calibration_safety_snapshot('purple')['status'],'unavailable')
        with patch.object(self.owner,'_fresh_calibration_measurement',side_effect=ValueError('stale arm')):
            self.assertEqual(self.owner.calibration_safety_snapshot('green')['status'],'unavailable')

    def test_previous_rig_is_archived_once_and_history_is_scoped_to_arm(self):
        self.owner._lessons.archive_rig('green',self.cal)
        original=copy.deepcopy(self.cal['arms']['green'])
        self.cal['arms']['green']['points']['30']['camera']['u']=.9
        self.owner._lessons.archive_rig('green',self.cal)
        rows=self.owner.calibration_history('green')['rows']
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['draft'],original)
        self.assertEqual(rows[0]['side'],'green')
        self.assertTrue(all(r['side']=='purple' for r in self.owner.calibration_history('purple')['rows']))

    def test_raised_sample_uses_selected_video_center_without_redetecting_occluded_ground(self):
        self.owner.calibration_session_begin(self.value)
        draft=self.owner._lessons.state['sessions'][self.value['id']]
        draft.update(captures={str(i):time.time()-1 for i in range(30,36)},camera_revision='lens',rig_identity={'ip':'test'})
        draft['ground']={'31':{'camera':{'u':.2,'v':.3},'frame_at':time.time()-1}}
        value={'id':self.value['id'],'action':'raised','marker':31,'camera':{'u':.23,'v':.34}}
        result=self.owner.calibration_session_command('green',value)
        sample=result['sessions'][self.value['id']]['draft']['parallax_points']['31']
        self.assertEqual(sample['ground'],{'u':.2,'v':.3});self.assertEqual(sample['raised'],value['camera'])
        self.assertEqual(sample['height_mm'],30)
        self.measure_patch.target._fresh_calibration_measurement.assert_called_with('green')
        for point in ({'u':float('nan'),'v':.2},{'u':True,'v':.3},{'u':1.1,'v':.2},None):
            with self.assertRaises(ValueError):self.owner.calibration_session_command('green',{**value,'camera':point})
    def test_idless_auto_pp_cal_2_template_and_camera_settings_are_used(self):
        template=self.owner._fixed_cal2_playfield()
        self.assertTrue(all('id' not in a for a in template['areas']))
        self.owner.calibration_session_begin(self.value)
        displayed=self.field.list_areas()
        self.assertEqual(len({a['id'] for a in displayed}),6)
        self.assertEqual([(a['marker'],a['x'],a['z'],a['size']) for a in displayed],
                         [(a['marker'],a['x'],a['z'],a['size']) for a in template['areas']])
        self.assertEqual(self.field.display_snapshot()['settings']['fov'],template['settings']['fov'])
        self.assertTrue(all(a['show_aruco'] and not a['show_area'] for a in displayed))

    def test_targets_show_before_feedback_and_blocked_begin_can_be_cancelled(self):
        from types import SimpleNamespace
        from test_photon_framework import FakeContext
        relay=SimpleNamespace(stop_side=lambda side:dict(contract='hhh.relay.stop',version=1,status='ready',stopped=True))
        self.owner._hub_ctx=FakeContext({'playfield-areas':self.field,'dobot-mg400-relay':relay})
        before=self.field.list_areas()
        with patch.object(self.owner,'_fresh_calibration_measurement',side_effect=ValueError('camera stale')):
            with self.assertRaisesRegex(ValueError,'camera stale'):self.owner.calibration_session_begin(self.value)
        scope=self.owner.calibration_session_snapshot()
        self.assertEqual(scope['display']['path'],'/s/gamemaster/p/playfield-areas/screen')
        self.assertEqual([a['marker'] for a in self.field.list_areas()],list(range(30,36)))
        self.assertNotIn('run:green',scope['sessions'])
        with self.assertRaises(ValueError):self.owner.calibration_session_release({**self.value,'side':'purple'})
        with patch.object(relay,'stop_side',return_value=dict(contract='hhh.relay.stop',version=1,status='ready',stopped=False)):
            with self.assertRaisesRegex(ValueError,'stopped'):self.owner.calibration_session_release(self.value)
        self.assertIsNotNone(self.field.display_snapshot()['display_session'])
        self.owner.calibration_session_release(self.value)
        self.assertIsNone(self.field.display_snapshot()['display_session'])
        self.assertEqual(self.field.list_areas(),before)

    def test_purple_turn_rotates_targets_and_preserves_marker_identity_and_raw_captures(self):
        before=self.field.display_snapshot()
        self.owner.calibration_session_begin(self.value)
        green={a['marker']:a for a in self.field.list_areas()}
        self.owner.calibration_session_release(self.value)
        purple={**self.value,'id':'run:purple','side':'purple'}
        result=self.owner.calibration_session_begin(purple)
        session=result['sessions'][purple['id']]
        self.assertEqual(session['display_camera_view'],'rot180')
        self.assertEqual(session['draft']['camera_view'],'rot180')
        for a in self.field.list_areas():
            original=green[a['marker']]
            self.assertEqual((a['x'],a['z']),(-original['x'],-original['z']))
            for key in ('id','marker','size','y'):
                self.assertEqual(a[key],original[key])
        captured=self.owner.calibration_session_command('purple',{'action':'capture','id':purple['id'],'marker':31})
        point=captured['sessions'][purple['id']]['draft']['points']['31']
        self.assertEqual(point['camera'],{'u':.1,'v':.2},'Store measured corrected-camera coordinates without another rotation')
        displayed=self.field.list_areas()
        self.owner.calibration_session_begin(purple)
        self.assertEqual(self.field.list_areas(),displayed,'Resuming does not rotate twice or lose the captured glow')
        self.assertEqual([a['marker'] for a in displayed if a['color']=='#33ff88'],[31])
        self.owner.calibration_session_release(purple)
        after=self.field.display_snapshot()
        self.assertEqual(after['areas'],before['areas'])
        self.assertEqual(after['settings'],before['settings'])

    def test_already_rotated_template_is_not_rotated_twice(self):
        normal=self.owner._fixed_cal2_playfield()
        rotated=copy.deepcopy(normal);rotated['camera_view']='rot180'
        for a in rotated['areas']:a['x'],a['z']=-a['x'],-a['z']
        with patch.object(self.owner,'_fixed_cal2_playfield',return_value=rotated):
            for side in ('green','purple'):
                value={**self.value,'id':'rotated:'+side,'side':side}
                self.owner.calibration_session_begin(value)
                expected=normal if side=='green' else rotated
                self.assertEqual([(a['marker'],a['x'],a['z']) for a in self.field.list_areas()],
                                 [(a['marker'],a['x'],a['z']) for a in expected['areas']])
                self.owner.calibration_session_release(value)

    def test_legacy_captures_cannot_resume_after_target_orientation_changes(self):
        value={**self.value,'id':'legacy:purple','side':'purple'}
        self.owner._lessons.begin(value,self.cal)
        self.owner._lessons.capture('purple',{'id':value['id'],'marker':30},self.owner._fresh_calibration_measurement('purple',30))
        before=self.field.display_snapshot()
        with self.assertRaisesRegex(ValueError,'cancel and reopen'):
            self.owner.calibration_session_begin(value)
        self.assertEqual(self.field.display_snapshot()['areas'],before['areas'])
        self.assertIsNone(self.field.display_snapshot()['display_session'])

    def test_empty_legacy_draft_adopts_the_correct_orientation(self):
        value={**self.value,'id':'empty:purple','side':'purple'}
        self.owner._lessons.begin(value,self.cal)
        session=self.owner.calibration_session_begin(value)['sessions'][value['id']]
        self.assertEqual(session['display_camera_view'],'rot180')
        self.assertEqual(session['draft']['camera_view'],'rot180')

    def test_restart_keeps_display_reserved_but_requires_fresh_lesson_activation(self):
        self.owner.calibration_session_begin(self.value)
        self.owner.calibration_session_command('green',{'action':'capture','id':self.value['id'],'marker':30})
        self.owner._lessons=self.owner.LessonStore(self.path/'lessons.json')
        state=self.owner.calibration_session_maintain()
        self.assertTrue(state['requires_activation'])
        self.assertEqual(state['active_side'],'green')
        self.assertNotEqual(state['epoch'],state['sessions'][self.value['id']]['epoch'])
        with self.assertRaises(PermissionError):
            self.owner.calibration_session_command('green',{'action':'capture','id':self.value['id'],'marker':31})
        with patch.object(self.owner,'_fresh_calibration_measurement',side_effect=ValueError('camera stale')):
            with self.assertRaisesRegex(ValueError,'camera stale'):self.owner.calibration_session_begin(self.value)
        self.assertTrue(self.owner.calibration_session_snapshot()['requires_activation'])
        self.owner.calibration_session_begin(self.value)
        state=self.owner.calibration_session_snapshot()
        self.assertFalse(state.get('requires_activation',False))
        self.assertEqual(state['epoch'],state['sessions'][self.value['id']]['epoch'])
        self.assertEqual([a['marker'] for a in self.field.list_areas() if a['color']=='#33ff88'],[30])

    def test_offline_arm_cannot_trap_projection_or_reenable_motion_after_release(self):
        before=self.field.display_snapshot()
        self.owner.calibration_session_begin(self.value)
        green={a['marker']:a for a in self.field.list_areas()}
        offline=dict(contract='hhh.relay.stop',version=1,status='unavailable',stopped=False,error='arm offline')
        with patch.object(self.relay,'stop_side',return_value=offline):
            self.owner.calibration_session_release({**self.value,'defer_stop':True})
            self.assertEqual(self.field.list_areas(),before['areas'])
            state=self.owner.calibration_session_snapshot()
            self.assertTrue(state['motion_blocked']);self.assertIsNone(state['active_side'])
            with self.assertRaises(PermissionError):self.owner._lessons.heartbeat('green',self.value['id'])
            self.owner._lessons=self.owner.LessonStore(self.path/'lessons.json')
            self.assertTrue(self.owner.calibration_session_maintain()['motion_blocked'],'Pending stop survives restart')
            purple={'side':'purple','id':'test:purple','practice':True}
            with self.assertRaisesRegex(ValueError,'previous calibration stop'):
                self.owner.calibration_session_begin(purple)
            for area in self.field.list_areas():
                self.assertEqual((area['x'],area['z']),(-green[area['marker']]['x'],-green[area['marker']]['z']))
            self.assertNotIn(purple['id'],self.owner._lessons.snapshot()['sessions'],'Preview grants no lesson access')
            self.owner.calibration_session_release({**purple,'defer_stop':True})
            self.assertEqual(self.field.list_areas(),before['areas'])
            self.assertEqual(self.owner.calibration_session_snapshot()['pending_stops'],{'green':self.value['id']},'Display-only Purple creates no spurious hardware stop')
        self.owner.calibration_session_maintain()
        self.assertFalse(self.owner.calibration_session_snapshot()['motion_blocked'])
        self.owner.calibration_session_begin(purple)
        self.assertEqual(self.owner._lessons.snapshot()['active_side'],'purple')

    def test_restart_then_offline_release_does_not_maintain_the_historical_green_draft(self):
        self.owner.calibration_session_begin(self.value)
        self.owner._lessons=self.owner.LessonStore(self.path/'lessons.json')
        self.assertIsNone(self.owner._lessons.snapshot().get('active_id'))
        # Reproduce legacy persisted state from the venue: no active side, but
        # the previous epoch's Green ID is still present and the arm is offline.
        self.owner._lessons.state['active_id']=self.value['id']
        offline=dict(contract='hhh.relay.stop',version=1,status='unavailable',stopped=False,error='arm offline')
        with patch.object(self.relay,'stop_side',return_value=offline):
            self.owner.calibration_session_release({**self.value,'defer_stop':True})
            self.assertIsNone(self.owner._lessons.snapshot().get('active_id'))
            # Maintenance must also tolerate an old in-memory copy directly.
            self.owner._lessons.state['active_id']=self.value['id']
            state=self.owner.calibration_session_maintain()
            self.assertEqual(state['status'],'ready');self.assertTrue(state['motion_blocked'])
            purple={'side':'purple','id':'restart:purple','practice':True}
            with self.assertRaisesRegex(ValueError,'previous calibration stop'):
                self.owner.calibration_session_begin(purple)
            self.assertEqual(self.field.display_snapshot()['display_session']['side'],'purple')
            self.assertEqual(self.owner.calibration_session_snapshot()['display']['status'],'ready')
            self.assertNotIn(purple['id'],self.owner._lessons.snapshot()['sessions'])

    def test_cancel_unactivated_preview_needs_no_robot_connection(self):
        before=self.field.list_areas()
        with patch.object(self.owner,'_fresh_calibration_measurement',side_effect=ValueError('camera stale')):
            with self.assertRaises(ValueError):self.owner.calibration_session_begin(self.value)
        with patch.object(self.relay,'stop_side',side_effect=AssertionError('No motion grant ever existed')):
            self.owner.calibration_session_release({**self.value,'defer_stop':True})
        self.assertEqual(self.field.list_areas(),before)
        self.assertFalse(self.owner.calibration_session_snapshot()['motion_blocked'])

    def test_field_mutations_cannot_bypass_calibration_reservation(self):
        self.owner.calibration_session_begin(self.value)
        for fn in (lambda:self.field.create_area(),lambda:self.field.update_area('cal2-30',x=1),
                   lambda:self.field.remove_area('cal2-30'),lambda:self.field.replace_areas([]),
                   lambda:self.field.set_view_settings(bloom=1),lambda:self.field.add_link('cal2-30','cal2-31')):
            with self.assertRaisesRegex(ValueError,'Calibration owns'):fn()
        with self.assertRaisesRegex(ValueError,'another display'):self.owner.calibration_session_begin({**self.value,'id':'run:purple','side':'purple'})
    def test_failed_lesson_begin_retains_blocked_reservation_and_retries_same_id(self):
        with patch.object(self.owner._lessons,'_save',side_effect=OSError('disk')):
            with self.assertRaises(OSError):self.owner.calibration_session_begin(self.value)
        scope=self.owner.calibration_session_snapshot()
        self.assertEqual((scope['active_side'],scope['active_id']),('green','run:green'))
        self.assertNotIn(scope['active_id'],scope['sessions']) # No live movement grant.
        self.owner.calibration_session_begin(self.value)
        self.assertIn('run:green',self.owner.calibration_session_snapshot()['sessions'])


if __name__=='__main__':unittest.main()
