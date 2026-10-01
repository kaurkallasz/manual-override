"""Malformed reservation evidence fails closed before reaching robot routes."""
import time
from types import SimpleNamespace
import unittest
from test_photon_framework import load, FakeContext, Flask


class RelayCalibrationReservationTests(unittest.TestCase):
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
