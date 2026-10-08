"""Saved-rig restore contracts and persistence with fake public hardware APIs."""
import copy
import json
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from test_photon_framework import load, FakeContext, Flask
from saved_calibration_fixture import seed


class SavedCalibrationTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup);self.path=Path(folder.name)
        self.owner=load('auto-pickup-game');self.owner._lessons=self.owner.LessonStore(self.path/'lessons.json')
        self.owner.CALIBRATION2_PATH=str(self.path/'cal2.json');seed(self.owner)
        self.stops=[];self.connected=True;self.stopped=True
        field=load('playfield-areas');field.HERE=str(self.path);field.SETTINGS_PATH=str(self.path/'settings.json');field.AREAS_PATH=str(self.path/'areas.json')
        self.relay=SimpleNamespace(arms_snapshot=lambda:dict(contract='hhh.relay.arms',version=1,status='ready',observed_at=time.time(),arms={s:dict(connected=self.connected,device={'ip':'fixture'}) for s in ('green','purple')}),stop_side=self.stop)
        self.camera_revision='fixture'
        self.camera=SimpleNamespace(corrected_tag_snapshot=lambda a,b:dict(contract='hhh.camera-correction',version=1,status='ready',calibration_revision=self.camera_revision))
        self.owner._hub_ctx=FakeContext({'dobot-mg400-relay':self.relay,'playfield-areas':field,'camera-calibration':self.camera})
        self.value={'side':'green','id':'rig:green:2','expected_revision':3}
    def stop(self,side):
        self.stops.append(side)
        return dict(contract='hhh.relay.stop',version=1,status='ready',stopped=self.stopped)

    def test_latest_default_preview_is_read_only_and_side_scoped(self):
        before=self.owner._calibration2_public();durable=copy.deepcopy(self.owner._lessons.state)
        for side in ('green','purple'):
            history=self.owner.calibration_history(side)
            self.assertEqual(history['selection'],'latest');self.assertEqual(history['latest_id'],'rig:'+side+':3')
            self.assertTrue(all(r['applicable'] and r['side']==side for r in history['rows']))
            self.assertEqual(self.owner.calibration_saved_preview({'side':side})['row']['id'],history['latest_id'])
        self.assertEqual(self.owner._calibration2_public(),before);self.assertEqual(self.owner._lessons.state,durable);self.assertEqual(self.stops,[])

    def test_restore_archive_latest_and_restart_persistence_for_each_arm(self):
        for side in ('green','purple'):
            other='purple' if side=='green' else 'green'
            before=self.owner._calibration2_public()
            result=self.owner.calibration_saved_apply({'side':side,'id':'rig:'+side+':2'})
            after=self.owner._calibration2_public()
            self.assertTrue(result['applied']);self.assertEqual(after['revision'],before['revision']+1)
            # Only metadata may be added to the partner; its measured rig stays untouched.
            self.assertEqual(after['arms'][other],before['arms'][other])
            self.assertEqual(self.owner.calibration_history(side)['latest_id'],'rig:'+side+':3')
            self.assertEqual(after['arms'][side]['points']['p1']['camera']['u'],before['arms'][side]['points']['p1']['camera']['u']-.025)
            self.owner._load_calibration2()
            self.assertEqual(self.owner.calibration_history(side)['selection'],'rig:'+side+':2')
            self.assertEqual(self.owner._calibration2['arms'][side]['camera_revision'],'fixture')
            self.owner.calibration_saved_apply({'side':side,'id':'latest'})
            for key,point in before['arms'][side]['points'].items():
                for field in ('camera','pose'):
                    for axis,value in point[field].items():
                        self.assertAlmostEqual(self.owner._calibration2['arms'][side]['points'][key][field][axis],value)
            self.assertEqual(self.owner.calibration_history(side)['selection'],'latest')
        self.assertEqual(self.stops,['green','purple']*4)
        self.assertEqual(self.owner._lessons.snapshot()['pending_stops'],{})

    def test_disconnected_arms_do_not_need_enable_or_motion(self):
        self.connected=False;self.owner.calibration_saved_apply(self.value)
        self.assertEqual(self.stops,[]);self.assertEqual(self.owner._lessons.snapshot()['pending_stops'],{})

    def test_failed_stop_keeps_rig_and_durable_motion_gate(self):
        before=Path(self.owner.CALIBRATION2_PATH).read_bytes();self.stopped=False
        with self.assertRaisesRegex(ValueError,'stop'):self.owner.calibration_saved_apply(self.value)
        self.assertEqual(Path(self.owner.CALIBRATION2_PATH).read_bytes(),before)
        self.assertTrue(self.owner.calibration_session_snapshot()['motion_blocked'])

    def test_wrong_side_missing_id_and_stale_revision_are_rejected(self):
        for value in ({**self.value,'side':'purple'},{**self.value,'id':'missing'},{**self.value,'expected_revision':2},{**self.value,'expected_revision':True}):
            with self.assertRaises(ValueError):self.owner.calibration_saved_apply(value)
        self.assertEqual(self.stops,[])

    def test_incomplete_and_nonfinite_saved_data_never_applied(self):
        rows=self.owner._lessons.state['saved_calibrations'];row=rows['rig:green:2'];original=copy.deepcopy(row)
        mutations=[lambda r:r['draft']['points'].pop('p1'),lambda r:r['draft']['points']['p1']['pose'].update(z=float('nan')),
                   lambda r:r['draft']['parallax_points'].update({'31':None}),lambda r:r.update(transport_height=float('inf')),
                   lambda r:r.update(draft=[])]
        for mutate in mutations:
            rows['rig:green:2']=copy.deepcopy(original);mutate(rows['rig:green:2'])
            history=self.owner.calibration_history('green')
            self.assertFalse(next(r for r in history['rows'] if r['id']=='rig:green:2')['applicable'])
            self.assertEqual(history['latest_id'],'rig:green:3')
            with self.assertRaises(ValueError):self.owner.calibration_saved_apply(self.value)
        self.assertEqual(self.stops,[])

    def test_old_camera_session_applies_with_warning_and_keeps_all_controls(self):
        self.camera_revision='current-camera'
        for side in ('green','purple'):
            saved=self.owner._lessons.state['saved_calibrations']['rig:'+side+':2']
            original=copy.deepcopy(saved)
            before=self.owner._calibration2_public()['arms']['purple' if side=='green' else 'green']
            result=self.owner.calibration_saved_apply({'side':side,'id':saved['id']})
            compatibility=result['camera_compatibility']
            self.assertEqual(compatibility['status'],'approximate')
            self.assertEqual(compatibility['source_camera_revision'],'fixture')
            self.assertEqual(compatibility['current_camera_revision'],'current-camera')
            self.assertIn('less precise',compatibility['warning'])
            self.assertIn('All control levels remain available',compatibility['warning'])
            self.assertEqual(self.owner._lessons.state['saved_calibrations'][saved['id']],original)
            applied=self.owner._calibration2_public()['arms'][side]
            self.assertEqual(applied['points'],original['draft']['points'])
            self.assertEqual(applied['parallax_points'],original['draft']['parallax_points'])
            self.assertEqual(applied['camera_revision'],'fixture')
            self.assertEqual(applied['camera_binding']['revision'],'current-camera')
            self.assertEqual(self.owner._calibration2_public()['arms']['purple' if side=='green' else 'green'],before)
            self.owner._load_calibration2()
            self.assertEqual(self.owner.calibration_safety_snapshot(side)['status'],'ready')
            active=next(row for row in self.owner.calibration_history(side)['rows'] if row['active'])
            self.assertEqual(active['camera_compatibility']['status'],'approximate')
            relay=load('dobot-mg400-relay')
            game=SimpleNamespace(motion_policy=lambda s:dict(contract='photon.game.motion',version=1,status='ready',scope='practice',tier=4))
            relay._hub_ctx=FakeContext({'auto-pickup-game':self.owner,'photon-game':game})
            for mode,action in [('joint','joint'),('cartesian','xyz'),('cartesian','image'),('cartesian','cue')]:
                self.assertIsNone(relay._ltz_motion_error(side,{'mode':mode,'ltz_action':action}))
                self.assertGreaterEqual(len(relay._server_cal2_guard(side)['polygon']),3)

    def test_matching_source_camera_removes_warning_after_reapply(self):
        self.camera_revision='current-camera'
        self.owner.calibration_saved_apply(self.value)
        self.camera_revision='fixture'
        result=self.owner.calibration_saved_apply({'side':'green','id':'rig:green:2'})
        self.assertEqual(result['camera_compatibility']['status'],'matched')
        self.assertIsNone(result['camera_compatibility']['warning'])
        self.assertEqual(self.owner.calibration_safety_snapshot('green')['status'],'ready')

    def test_unknown_original_camera_is_usable_but_never_claimed_matched(self):
        row=self.owner._lessons.state['saved_calibrations']['rig:green:2']
        row['camera_revision']=None
        result=self.owner.calibration_saved_apply(self.value)
        self.assertEqual(result['camera_compatibility']['status'],'approximate')
        self.assertEqual(self.owner.calibration_safety_snapshot('green')['status'],'ready')

    def test_camera_change_after_apply_requires_an_explicit_new_association(self):
        self.owner.calibration_saved_apply(self.value)
        self.camera_revision='newer-camera'
        self.assertEqual(self.owner.calibration_safety_snapshot('green')['status'],'unavailable')
        self.owner.calibration_saved_apply({'side':'green','id':'rig:green:2'})
        self.assertEqual(self.owner.calibration_safety_snapshot('green')['status'],'ready')

    def test_camera_unavailable_or_changed_during_stop_never_saves_an_unverified_binding(self):
        before=Path(self.owner.CALIBRATION2_PATH).read_bytes()
        valid=self.camera.corrected_tag_snapshot
        self.camera.corrected_tag_snapshot=lambda *a:dict(contract='hhh.camera-correction',version=1,status='unavailable',error='camera offline')
        with self.assertRaisesRegex(ValueError,'camera-correction v1 unavailable'):self.owner.calibration_saved_apply(self.value)
        self.assertEqual(self.stops,[])
        self.camera.corrected_tag_snapshot=valid
        def stop(side):
            self.camera_revision='changed-during-stop'
            return self.stop(side)
        self.relay.stop_side=stop
        with self.assertRaisesRegex(ValueError,'changed while applying'):self.owner.calibration_saved_apply(self.value)
        self.assertEqual(Path(self.owner.CALIBRATION2_PATH).read_bytes(),before)

    def test_known_arm_identity_must_still_match(self):
        row=self.owner._lessons.state['saved_calibrations']['rig:green:2']
        row['camera_revision']='different';row['draft']['rig_identity']={'ip':'other'}
        with self.assertRaisesRegex(ValueError,'arm connection'):self.owner.calibration_saved_apply(self.value)
        self.assertEqual(self.stops,[])

    def test_malformed_persisted_camera_binding_fails_closed(self):
        self.owner.calibration_saved_apply(self.value)
        saved=self.owner._calibration2_public()
        saved['arms']['green']['camera_binding']={'revision':'fixture','applied_at':True}
        Path(self.owner.CALIBRATION2_PATH).write_text(json.dumps(saved))
        self.owner._load_calibration2()
        safety=self.owner.calibration_safety_snapshot('green')
        self.assertEqual(safety['status'],'unavailable')
        self.assertIn('association is invalid',safety['error'])

    def test_malformed_public_contract_fails_closed(self):
        self.relay.arms_snapshot=lambda:dict(contract='hhh.relay.arms',version=True,status='ready')
        with self.assertRaises(ValueError):self.owner.calibration_saved_apply(self.value)
        self.assertEqual(self.stops,[])

    def test_stale_arm_connection_states_fail_closed(self):
        valid=self.relay.arms_snapshot()
        self.relay.arms_snapshot=lambda:{**valid,'observed_at':time.time()-4}
        with self.assertRaisesRegex(ValueError,'Fresh arm'):self.owner.calibration_saved_apply(self.value)
        self.assertEqual(self.stops,[])

    def test_shared_height_is_archived_for_both_arms(self):
        self.owner._lessons.state['saved_calibrations']['rig:green:2']['transport_height']=65
        self.owner.calibration_saved_apply(self.value)
        self.assertEqual(self.owner._calibration2['shared_z']['transport_height'],65)
        archive=self.owner._lessons.snapshot()['saved_calibrations']
        self.assertEqual(archive['rig:green:3']['transport_height'],60)
        self.assertEqual(archive['rig:purple:3']['transport_height'],60)

    def measured_session(self,side='green',z=10):
        self.owner._lessons.begin({'id':'measured:'+side,'side':side,'practice':True},self.owner._calibration2_public())
        session=self.owner._lessons.state['sessions']['measured:'+side]
        session.update(draft=copy.deepcopy(self.owner._calibration2['arms'][side]),captures={str(m):time.time() for m in range(30,36)},
                       stage='perspective',camera_revision='fixture')
        for point in session['draft']['points'].values():point['pose']['z']=z
        return session

    def test_measured_completion_validates_commits_and_is_idempotent_without_tutorial(self):
        self.measured_session();value={'id':'measured:green','side':'green'}
        with patch.object(self.owner,'_fresh_calibration_measurement',return_value={'camera_revision':'fixture','rig_identity':None}):
            result=self.owner.calibration_session_complete(value)
            session=result['sessions'][value['id']]
            self.assertEqual(session['stage'],'complete');self.assertEqual(session['completion_basis'],'measured-targets')
            self.assertEqual(session['arrivals'],[]);self.assertIsNone(session['pickup_evidence'])
            self.assertEqual(result['active_side'],'green','Measured completion alone does not release motion ownership')
            self.assertEqual(self.owner._calibration2['revision'],4)
            self.assertEqual((session['pickup_height'],session['transport_height']),(10,50))
            self.owner.calibration_session_complete(value)
            self.assertEqual(self.owner._calibration2['revision'],4,'Lost acknowledgements never recommit')
            self.assertEqual(self.owner.calibration_history('green')['active_id'],self.owner.calibration_history('green')['latest_id'])

    def test_new_measurements_replace_approximate_camera_binding(self):
        self.camera_revision='current-camera'
        self.owner.calibration_saved_apply(self.value)
        session=self.measured_session()
        self.assertIn('camera_binding',session['draft'])
        self.connected=False
        self.owner.calibration_session_complete({'id':session['id'],'side':'green'})
        self.owner._load_calibration2()
        arm=self.owner._calibration2_public()['arms']['green']
        self.assertNotIn('camera_binding',arm)
        self.assertEqual(arm['camera_revision'],'fixture')
        self.assertEqual(self.owner.calibration_safety_snapshot('green')['status'],'unavailable')
        self.camera_revision='fixture'
        self.assertEqual(self.owner.calibration_safety_snapshot('green')['camera_compatibility']['status'],'matched')

    def test_incomplete_or_other_player_cannot_complete_measurements(self):
        original=copy.deepcopy(self.measured_session());value={'id':'measured:green','side':'green'}
        mutations=[lambda s:s['captures'].pop('30'),lambda s:s['draft']['parallax_points'].update({'31':None}),
                   lambda s:s['draft']['parallax_points'].update({'31':{'height_mm':30}}),
                   lambda s:s['draft']['points']['p1']['pose'].update(z=float('nan')),
                   lambda s:[p['pose'].update(z=200) for p in s['draft']['points'].values()]]
        with patch.object(self.owner,'_fresh_calibration_measurement',return_value={'camera_revision':'fixture','rig_identity':None}):
            for mutate in mutations:
                session=copy.deepcopy(original);mutate(session)
                self.owner._lessons.state['sessions'][value['id']]=session
                # Missing/invalid captures never borrow a saved rig's heights.
                with self.assertRaises(ValueError):self.owner.calibration_session_complete(value)
                self.assertNotEqual(self.owner._lessons.state['sessions'][value['id']]['stage'],'complete')
            with self.assertRaises(PermissionError):self.owner.calibration_session_complete({**value,'side':'purple'})

    def test_expired_disconnected_session_completes_without_renewing_motion(self):
        session=self.measured_session();session.update(paused=True,access_until=0,epoch='before-restart')
        self.connected=False
        with patch.object(self.owner,'_fresh_calibration_measurement',side_effect=AssertionError('Completion must not measure or connect hardware')):
            result=self.owner.calibration_session_complete({'id':session['id'],'side':'green'})
        saved=result['sessions'][session['id']]
        self.assertEqual(saved['stage'],'complete')
        self.assertTrue(saved['paused']);self.assertEqual(saved['access_until'],0)
        self.assertEqual(saved['epoch'],'before-restart')
        self.assertEqual((saved['pickup_height'],saved['transport_height']),(10,50))
        self.assertEqual(self.stops,[])

    def test_failed_disable_keeps_completed_session_motion_gate(self):
        session=self.measured_session()
        self.owner.calibration_session_complete({'id':session['id'],'side':'green'})
        self.owner._lessons.defer_stop('green',session['id'])
        self.relay.disable_side=lambda side:dict(contract='hhh.relay.disabled',version=1,status='unavailable',error='disable failed')
        self.owner._settle_deferred_stops()
        self.assertEqual(self.owner._lessons.snapshot()['pending_stops'],{'green':session['id']})
        self.assertEqual(self.stops,[],'A hold alone cannot clear a failed disable')
        self.relay.disable_side=lambda side:dict(contract='hhh.relay.disabled',version=1,status='ready',inhibited=True,connected=True,disabled=True)
        self.owner._settle_deferred_stops()
        self.assertEqual(self.owner._lessons.snapshot()['pending_stops'],{})

    def test_completion_rederives_heights_after_optional_practice_and_point_edit(self):
        self.measured_session();value={'id':'measured:green','side':'green'}
        with patch.object(self.owner,'_fresh_calibration_measurement',return_value={'camera_revision':'fixture','rig_identity':None}):
            self.owner.calibration_session_command('green',{'id':value['id'],'action':'commit'})
            self.owner.calibration_session_command('green',{'id':value['id'],'action':'commit'})
            self.assertEqual(self.owner._calibration2['revision'],4,'Repeated save reuses its revision')
            session=self.owner._lessons.state['sessions'][value['id']]
            session['draft']['points']['p1']['pose']['z']=16
            self.owner.calibration_session_complete(value)
            self.assertEqual(self.owner._calibration2['revision'],5)
            self.assertEqual(self.owner._calibration2['arms']['green']['transport_height'],51)
            self.assertEqual(self.owner._calibration2['shared_z']['transport_height'],60,'Legacy fallback stays unchanged')

    def test_each_arm_keeps_its_own_derived_transport_height_on_save_restore_and_restart(self):
        with patch.object(self.owner,'_fresh_calibration_measurement',return_value={'camera_revision':'fixture','rig_identity':None}):
            for side,z in [('green',10),('purple',25)]:
                self.measured_session(side,z)
                self.owner.calibration_session_complete({'id':'measured:'+side,'side':side})
                self.owner._lessons.release(side,'measured:'+side)
        self.owner._load_calibration2()
        for side,expected in [('green',50),('purple',65)]:
            self.assertEqual(self.owner._calibration2['arms'][side]['transport_height'],expected)
            row=self.owner.calibration_saved_preview({'side':side})['row']
            self.assertEqual(row['transport_height'],expected)
        purple=copy.deepcopy(self.owner._calibration2['arms']['purple'])
        self.owner.calibration_saved_apply({'side':'green','id':'latest'})
        self.assertEqual(self.owner._calibration2['arms']['purple'],purple)

    def test_gm_history_route_requires_role_enabled_owner_and_exact_contract(self):
        renderer=load('laser-tag-y');renderer.hub_init(FakeContext({'auto-pickup-game':self.owner}))
        app=Flask(__name__);app.register_blueprint(renderer.bp);client=app.test_client()
        self.assertEqual(client.get('/api/calibrations').status_code,403)
        self.assertEqual(client.get('/api/calibrations',environ_overrides={'hhh.roles':{'green'}}).status_code,403)
        gm={'hhh.roles':{'gamemaster'}}
        self.assertEqual(client.get('/api/calibrations?side=purple',environ_overrides=gm).json['latest_id'],'rig:purple:3')
        self.owner.calibration_history=lambda side:dict(contract='wrong',version=1,status='ready')
        self.assertEqual(client.get('/api/calibrations',environ_overrides=gm).status_code,503)


if __name__=='__main__':unittest.main()
