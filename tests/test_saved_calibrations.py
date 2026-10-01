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
        self.camera=SimpleNamespace(corrected_tag_snapshot=lambda a,b:dict(contract='hhh.camera-correction',version=1,status='ready',calibration_revision='fixture'))
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

    def test_known_camera_and_arm_identity_must_match(self):
        row=self.owner._lessons.state['saved_calibrations']['rig:green:2']
        row['camera_revision']='different'
        with self.assertRaisesRegex(ValueError,'camera correction'):self.owner.calibration_saved_apply(self.value)
        row['camera_revision']='fixture';row['draft']['rig_identity']={'ip':'other'}
        with self.assertRaisesRegex(ValueError,'arm connection'):self.owner.calibration_saved_apply(self.value)
        self.assertEqual(self.stops,[])

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

    def measured_session(self):
        self.owner._lessons.begin({'id':'measured:green','side':'green','practice':True},self.owner._calibration2_public())
        session=self.owner._lessons.state['sessions']['measured:green']
        session.update(draft=copy.deepcopy(self.owner._calibration2['arms']['green']),captures={str(m):time.time() for m in range(30,36)},
                       stage='perspective',pickup_height=10,transport_height=60,camera_revision='fixture')
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
            self.owner.calibration_session_complete(value)
            self.assertEqual(self.owner._calibration2['revision'],4,'Lost acknowledgements never recommit')
            self.assertEqual(self.owner.calibration_history('green')['active_id'],self.owner.calibration_history('green')['latest_id'])

    def test_incomplete_or_other_player_cannot_complete_measurements(self):
        original=copy.deepcopy(self.measured_session());value={'id':'measured:green','side':'green'}
        mutations=[lambda s:s['captures'].pop('30'),lambda s:s['draft']['parallax_points'].update({'31':None}),
                   lambda s:s.update(transport_height=None),lambda s:s['draft'].update(pickup_height=None)]
        with patch.object(self.owner,'_fresh_calibration_measurement',return_value={'camera_revision':'fixture','rig_identity':None}):
            for mutate in mutations:
                session=copy.deepcopy(original);mutate(session)
                self.owner._lessons.state['sessions'][value['id']]=session
                # No fallback to the previous shared height counts as a fresh measurement.
                with self.assertRaises(ValueError):self.owner.calibration_session_complete(value)
                self.assertNotEqual(self.owner._lessons.state['sessions'][value['id']]['stage'],'complete')
            with self.assertRaises(PermissionError):self.owner.calibration_session_complete({**value,'side':'purple'})

    def test_completion_after_optional_practice_installs_changed_height(self):
        self.measured_session();value={'id':'measured:green','side':'green'}
        with patch.object(self.owner,'_fresh_calibration_measurement',return_value={'camera_revision':'fixture','rig_identity':None}):
            self.owner.calibration_session_command('green',{'id':value['id'],'action':'commit'})
            self.owner.calibration_session_command('green',{'id':value['id'],'action':'commit'})
            self.assertEqual(self.owner._calibration2['revision'],4,'Repeated save reuses its revision')
            self.owner._lessons.height('green',{'id':value['id'],'height':'transport_height'},[300,0,61,0])
            self.owner.calibration_session_complete(value)
            self.assertEqual(self.owner._calibration2['revision'],5)
            self.assertEqual(self.owner._calibration2['shared_z']['transport_height'],61)

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
