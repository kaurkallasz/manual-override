"""Malformed reservation evidence fails closed before reaching robot routes."""
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from test_photon_framework import load, FakeContext, Flask


class RelayCalibrationReservationTests(unittest.TestCase):
    def test_waiting_arm_revokes_controller_and_disables_servos_after_measured_stop(self):
        relay=load('dobot-mg400-relay');events=[]
        state={'enabled':True,'servo_active':True,'last_feedback':time.time(),'joints':[0,0,0,0]}
        def disable():events.append('disable');state['enabled']=False;return 0,'ok'
        def stop_servo():events.append('stop_servo');state['servo_active']=False
        robot=SimpleNamespace(is_connected=lambda:True,get_state=lambda:dict(state),
                              hold=lambda:events.append('hold'),stop_servo=stop_servo,disable=disable)
        for side in ('green','purple'):
            state.update(enabled=True,servo_active=True,last_feedback=time.time());events.clear()
            relay._sides[side]['token']='old-controller'
            with patch.object(relay,'_arm',return_value=robot),patch.object(relay,'_log_command'):
                result=relay.disable_side(side)
            self.assertEqual(result['status'],'ready');self.assertTrue(result['disabled'])
            self.assertIsNone(relay._sides[side]['token'])
            self.assertLess(events.index('hold'),events.index('disable'))
            self.assertLess(events.index('stop_servo'),events.index('disable'))

    def test_offline_or_stale_waiting_arm_never_gets_enabled_or_claimed_stopped(self):
        relay=load('dobot-mg400-relay')
        with patch.object(relay,'_arm',return_value=None):
            result=relay.disable_side('purple')
        self.assertEqual(result['status'],'ready');self.assertTrue(result['inhibited'])
        self.assertFalse(result['connected']);self.assertFalse(result['disabled'])
        robot=SimpleNamespace(is_connected=lambda:True,get_state=lambda:dict(enabled=False,servo_active=False,last_feedback=0))
        with patch.object(relay,'_arm',return_value=robot):result=relay.disable_side('green')
        self.assertEqual(result['status'],'unavailable');self.assertFalse(result['disabled'])

    def test_selected_player_can_connect_before_activation_without_admitting_motion(self):
        relay=load('dobot-mg400-relay');app=Flask('calibration-connect')
        value={'contract':'hhh.cal2.session','version':1,'status':'ready','active_side':'green',
               'active_id':'selected','epoch':'live','sessions':{},'requires_activation':True,
               'pending_stops':{'green':'old'}}
        owner=SimpleNamespace(calibration_session_snapshot=lambda:value,calibration_session_maintain=lambda:value)
        relay._hub_ctx=FakeContext({'auto-pickup-game':owner})
        def guard(action,side='green'):
            with app.test_request_context('/api/'+action,method='POST',json={'side':side},environ_overrides={'hhh.roles':{side}}):
                return relay._field_reservation_guard()
        self.assertIsNone(guard('connect'))
        for action in ('acquire','enable','move','pump'):self.assertEqual(guard(action)[1],403)
        self.assertEqual(guard('connect','purple')[1],403)
        value['pending_stops']={}
        for action in ('connect','acquire','enable'):self.assertIsNone(guard(action))
        self.assertEqual(guard('move')[1],503)
        self.assertEqual(guard('pump')[1],503)
        for action in ('connect','acquire','enable','move'):self.assertEqual(guard(action,'purple')[1],403)

    def test_reservation_faults_block_motion_but_stop_and_pump_off_remain_available(self):
        relay=load('dobot-mg400-relay')
        app=Flask('reservation-boundary')
        value={'contract':'hhh.cal2.session','version':1,'status':'ready','active_side':'green','active_id':'turn','epoch':'current',
               'sessions':{'turn':{'epoch':'current','access_until':time.time()+30}}}
        def snapshot():
            if isinstance(value,Exception):raise value
            return value
        relay._hub_ctx=FakeContext({'auto-pickup-game':SimpleNamespace(calibration_session_snapshot=snapshot)})
        def guard(action='joints',side='green',**extra):
            with app.test_request_context('/api/'+action,method='POST',json={'side':side,**extra}):
                return relay._field_reservation_guard()
        self.assertIsNone(guard())
        self.assertEqual(guard(side='purple')[1],403)
        for stamp in (float('nan'),float('inf'),'later',None,True):
            value['sessions']['turn']['access_until']=stamp
            self.assertEqual(guard()[1],503)
            self.assertIsNone(guard('stop','purple'))
            self.assertIsNone(guard('pump','purple',mode='off'))
        value['sessions']['turn']['access_until']=time.time()+30
        value['sessions']['turn']['epoch']='old'
        self.assertEqual(guard()[1],503)
        value.update(active_side=None,pending_stops={'green':'old-test'})
        for side in ('green','purple'):
            self.assertEqual(guard(side=side)[1],403)
            self.assertIsNone(guard('stop',side))
            self.assertIsNone(guard('pump',side,mode='off'))
        with app.test_request_context('/api/connect',method='POST',json={'side':'green'},environ_overrides={'hhh.roles':{'gamemaster'}}):
            self.assertIsNone(relay._field_reservation_guard())
        value=None;self.assertEqual(guard()[1],503)
        value=RuntimeError('owner failed');self.assertEqual(guard()[1],503)


if __name__=='__main__':unittest.main()
