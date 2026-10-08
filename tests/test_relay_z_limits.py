"""Z ceiling persistence, relay enforcement and both player adapters; fake arms only."""
import json
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from test_photon_framework import load, Flask
from test_mobile_teams import player_module


class RelayZLimitsTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
        self.relay=load('dobot-mg400-relay')
        self.relay.Z_FLOOR_PATH=str(Path(folder.name)/'z-floor.json')
        self.relay.COMMAND_LOG_FILE=str(Path(folder.name)/'commands.log')
        self.relay._z_floor=-72.;self.relay._z_floor_enabled=True
        self.relay._z_ceiling=80.;self.relay._z_ceiling_enabled=True
        app=Flask('z-limits');app.register_blueprint(self.relay.bp);self.client=app.test_client()
        self.state=dict(connected=True,enabled=True,motion_epoch=1,motion_ready=True,
                        joints=[0.,20.,30.,0.],pose=[300.,100.,50.,0.],last_feedback=time.time())
        self.robot=SimpleNamespace(is_connected=lambda:True,get_state=lambda:dict(self.state),
            positive_solution=Mock(return_value=[300.,100.,60.,0.]),
            set_target_joints=Mock(),set_target_pose=Mock())
        self.relay._sides['green'].update(token='test',motion_epoch=1)

    def move(self, mode, target):
        key='joints' if mode=='joint' else 'pose'
        with patch.object(self.relay,'_arm',return_value=self.robot), \
             patch.object(self.relay,'_ltz_motion_error',return_value=None), \
             patch.object(self.relay,'_server_cal2_guard',return_value=None), \
             patch.object(self.relay,'_validate_cal2_cartesian_path',return_value=None), \
             patch.object(self.relay,'_ensure_follower'):
            return self.client.post('/api/move',json=dict(side='green',token='test',motion_epoch=1,mode=mode,**{key:target})).get_json()

    def test_default_and_legacy_floor_file_keep_floor_and_add_80_ceiling(self):
        Path(self.relay.Z_FLOOR_PATH).write_text(json.dumps({'z_floor':-102.,'enabled':True}))
        self.relay._load_z_floor()
        for path in ['/api/config','/api/state']:
            value=self.client.get(path).get_json()
            self.assertEqual(value['z_floor']['value'],-102.)
            self.assertEqual(value['z_ceiling'],dict(value=80.,enabled=True,**({'default':80.} if path.endswith('config') else {})))
            self.assertEqual(value['z_limits']['maximum'],80.)

    def test_save_is_persisted_and_shared_by_effective_bounds(self):
        value=self.client.post('/api/z-ceiling',json={'value':65,'enabled':True}).get_json()
        self.assertTrue(value['ok']);self.assertEqual(value['z_limits']['maximum'],65)
        self.relay._z_ceiling=80.;self.relay._load_z_floor()
        self.assertEqual(self.relay.z_limits_snapshot()['maximum'],65)
        self.assertEqual(self.client.get('/api/z-ceiling').get_json()['value'],65)
        self.assertFalse(Path(self.relay.Z_FLOOR_PATH+'.tmp').exists())

    def test_disabling_and_reenabling_ceiling_uses_workspace_then_saved_value(self):
        for enabled,expected in [(False,230.),(True,80.)]:
            value=self.client.post('/api/z-ceiling',json={'enabled':enabled}).get_json()
            self.assertTrue(value['ok']);self.assertEqual(value['z_limits']['maximum'],expected)

    def test_invalid_values_never_change_live_or_saved_limits(self):
        before=self.relay.z_limits_snapshot()
        for payload in [{'value':x} for x in [True,None,'80',float('nan'),float('inf'),-151,231,-72]]+ [{'enabled':1},[]]:
            result=self.client.post('/api/z-ceiling',json=payload)
            self.assertEqual(result.status_code,400,payload)
            self.assertEqual(self.relay.z_limits_snapshot(),before)
            self.assertFalse(Path(self.relay.Z_FLOOR_PATH).exists())
        self.assertEqual(self.client.post('/api/z-floor',json={'value':90}).status_code,400)

    def test_player_cannot_edit_either_limit(self):
        for side in ('green','purple'):
            for path in ('/api/z-floor','/api/z-ceiling'):
                self.assertEqual(self.client.post(path,json={'value':70},environ_overrides={'hhh.roles':{side}}).status_code,403)

    def test_save_stops_both_arms_before_persisting_and_failure_preserves_limit(self):
        events=[]
        def stop(side):events.append(side);return {'stopped':True}
        with patch.object(self.relay,'_arm',return_value=self.robot),patch.object(self.relay,'stop_side',side_effect=stop):
            self.assertTrue(self.client.post('/api/z-ceiling',json={'value':70}).get_json()['ok'])
        self.assertEqual(events,list(self.relay.SIDES))
        before=Path(self.relay.Z_FLOOR_PATH).read_bytes()
        with patch.object(self.relay,'_arm',return_value=self.robot),patch.object(self.relay,'stop_side',return_value={'stopped':False}):
            self.assertEqual(self.client.post('/api/z-ceiling',json={'value':60}).status_code,409)
        self.assertEqual(self.relay.z_limits_snapshot()['maximum'],70)
        self.assertEqual(Path(self.relay.Z_FLOOR_PATH).read_bytes(),before)

    def test_persistence_failure_is_reported_without_changing_memory(self):
        with patch.object(self.relay,'_save_z_floor',side_effect=OSError('fixture disk failure')):
            result=self.client.post('/api/z-ceiling',json={'value':70})
        self.assertEqual(result.status_code,500);self.assertIn('disk failure',result.get_json()['error'])
        self.assertEqual(self.relay.z_limits_snapshot()['maximum'],80)

    def test_changed_limit_revokes_existing_controller_before_accepting_any_new_goal(self):
        self.robot.hold=Mock()
        with patch.object(self.relay,'_arm',return_value=self.robot):
            result=self.client.post('/api/z-ceiling',json={'value':65})
        self.assertTrue(result.get_json()['ok'])
        self.robot.hold.assert_called()
        self.assertIsNone(self.relay._sides['green']['token'])
        self.assertFalse(self.move('cartesian',[300,100,60,0])['ok'])
        self.robot.set_target_pose.assert_not_called()

    def test_cartesian_above_ceiling_rejected_not_clamped_into_unrequested_motion(self):
        self.assertFalse(self.move('cartesian',[300,100,81,0])['ok'])
        self.robot.set_target_pose.assert_not_called()
        self.assertTrue(self.move('cartesian',[300,100,80,0])['ok'])
        self.assertEqual(self.robot.set_target_pose.call_args.args[2],80)

    def test_joint_path_is_checked_without_a_learned_floor_model(self):
        self.relay._z_coef['green']=None
        self.robot.positive_solution.return_value=[300.,100.,90.,0.]
        result=self.move('joint',[0,25,30,0])
        self.assertFalse(result['ok']);self.assertIn('Z ceiling 80',result['error'])
        self.robot.set_target_joints.assert_not_called()
        self.robot.positive_solution.return_value=[300.,100.,80.,0.]
        self.assertTrue(self.move('joint',[0,25,30,0])['ok'])

    def test_joint_intermediate_height_and_missing_kinematics_fail_closed(self):
        self.robot.positive_solution.side_effect=[[300,100,90,0],[300,100,60,0]]
        self.assertFalse(self.move('joint',[0,30,30,0])['ok'])
        self.robot.positive_solution.side_effect=ValueError('kinematics unavailable')
        self.assertFalse(self.move('joint',[0,25,30,0])['ok'])
        self.robot.set_target_joints.assert_not_called()

    def test_manual_position_above_ceiling_allows_only_downward_joint_recovery(self):
        self.state['pose'][2]=100
        for target_z,allowed in [(105,False),(100,False),(95,True),(80,True)]:
            self.robot.positive_solution.return_value=[300,100,target_z,0]
            self.assertEqual(self.move('joint',[0,25,30,0])['ok'],allowed)

    def test_both_player_configs_and_feedback_project_relay_limits(self):
        for side in ('green','purple'):
            player=player_module(side,'cartesian-xyz-test')
            adapter=player.RelayClient('http://fake',side)
            adapter._relay_state={'z_limits':self.relay.z_limits_snapshot()}
            self.assertEqual(adapter.get_state()['z_limits']['maximum'],80)
            self.relay._z_ceiling=65
            adapter._relay_state['z_limits']=self.relay.z_limits_snapshot()
            self.assertEqual(adapter.get_state()['z_limits']['maximum'],65)
            app=Flask('z-player-'+side);app.register_blueprint(player.bp)
            with patch.object(player,'_identity',return_value={'is_player':True,'side':side}), \
                 patch.object(player,'_current',return_value=adapter), \
                 patch.object(adapter,'_get',return_value=(200,self.relay.z_limits_snapshot())):
                config=app.test_client().get('/api/config').get_json()
            self.assertEqual(config['workspace']['z'],[-72,65])
            self.relay._z_ceiling=80
            for limits in [None,dict(adapter._relay_state['z_limits'],version=True),dict(adapter._relay_state['z_limits'],maximum=float('nan'))]:
                self.assertEqual(adapter.validate_z_limits(limits)['status'],'unavailable')


if __name__=='__main__':unittest.main()
