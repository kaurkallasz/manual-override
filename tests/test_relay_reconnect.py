"""Reconnect/unlock regressions. Fake feedback and sockets; never contacts an arm."""
import importlib.util
from contextlib import ExitStack
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from test_photon_framework import load, ROOT, Flask


class DormantThread:
    def __init__(self, **kwargs):
        pass

    def start(self):
        pass

    def is_alive(self):
        return False


class RelayReconnectTests(unittest.TestCase):
    def setUp(self):
        self.relay = load('dobot-mg400-relay')
        self.driver = __import__('relay_arm')
        self.robot = self.driver.DobotMG400('test-no-network')
        self.robot._state['connected'] = True
        self.now = 100.0
        self.feed = True
        self.mode = 5
        self.joints = [10., 25., 35., 9.]
        self.pose = [300., 100., 50., 9.]
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(self.driver.time, 'time', side_effect=lambda: self.now))
        self.stack.enter_context(patch.object(self.driver.time, 'monotonic', side_effect=lambda: self.now))
        self.stack.enter_context(patch.object(self.driver.time, 'sleep', side_effect=self.tick))
        self.stack.enter_context(patch.object(self.driver.threading, 'Thread', DormantThread))
        self.robot.servo_j = Mock(return_value=(0, 'fake'))
        self.robot.servo_p = Mock(return_value=(0, 'fake'))
        self.robot.enable = Mock(return_value=(0, 'fake'))
        self.robot.clear_error = Mock(return_value=(0, 'fake'))
        self.feedback()

    def feedback(self):
        self.robot._apply_feedback(dict(robot_mode=self.mode, joints=list(self.joints),
                                        pose=list(self.pose), digital_in=0, digital_out=0))

    def tick(self, seconds):
        self.now += seconds
        if self.feed:
            self.feedback()

    def route_client(self):
        for name, value in [('_arm', lambda side: self.robot), ('_log_command', Mock()),
                            ('_log_incoming', Mock()), ('_ltz_motion_error', lambda *a: None),
                            ('_server_cal2_guard', lambda side: None)]:
            self.stack.enter_context(patch.object(self.relay, name, value))
        app = Flask('reconnect-test')
        app.register_blueprint(self.relay.bp)
        return app.test_client()

    def test_start_requires_new_stable_feedback_not_cached_or_missing_position(self):
        for feedback_ok in (False, True):
            with self.subTest(feedback_ok=feedback_ok):
                self.feed = False
                self.robot._state.update(feedback_ok=feedback_ok, last_feedback=self.now-10)
                with self.assertRaisesRegex(self.driver.DobotError, 'Fresh, settled'):
                    self.robot.start_servo('joint')
                self.assertFalse(self.robot._servo_running)
                self.assertIsNone(self.robot.get_target())
                self.robot.servo_j.assert_not_called()

    def test_first_setpoint_and_zero_velocity_use_position_after_manual_move(self):
        for mode, key, actual in [('joint', 'joints', [-30., 40., 55., 9.]),
                                  ('cartesian', 'pose', [370., 80., 90., 9.])]:
            with self.subTest(mode=mode):
                self.robot.reset_motion()
                setattr(self, key, actual)
                epoch = self.robot.get_state()['motion_epoch']
                self.robot.start_servo(mode, expected_epoch=epoch)
                self.assertEqual(self.robot.get_target(), actual)
                self.assertEqual(self.robot._vel, [0.]*4)
                def capture(*values, **kwargs):
                    self.robot._servo_running = False
                    self.assertEqual(list(values), actual)
                    return 0, 'fake'
                with patch.object(self.robot, 'servo_j', side_effect=capture), \
                     patch.object(self.robot, 'servo_p', side_effect=capture):
                    self.robot._servo_loop()

    def test_brief_unlock_is_latched_before_servo_or_browser_can_poll(self):
        self.robot.start_servo('joint')
        epoch = self.robot.get_state()['motion_epoch']
        self.robot.set_target_joints(20, 30, 40, 9, expected_epoch=epoch)
        self.mode = 6
        self.feedback()
        self.joints = [-30., 40., 55., 9.]
        self.mode = 5
        self.feedback()
        self.assertGreater(self.robot.get_state()['motion_epoch'], epoch)
        self.assertFalse(self.robot._servo_running)
        self.assertIsNone(self.robot.get_target())
        with self.assertRaisesRegex(self.driver.DobotError, 'position changed'):
            self.robot.set_target_joints(20, 30, 40, 9, expected_epoch=epoch)
        self.robot._servo_loop()
        self.robot.servo_j.assert_not_called()

    def test_feedback_loss_and_unexpected_displacement_stop_without_catchup(self):
        for mode in ('joint', 'cartesian'):
            for fault in ('stale', 'displaced'):
                with self.subTest(mode=mode, fault=fault):
                    self.feedback()
                    self.robot.start_servo(mode)
                    epoch = self.robot.get_state()['motion_epoch']
                    if fault == 'stale':
                        self.now += 1
                    else:
                        self.joints[0] += 40
                        self.pose[0] += 70
                        self.feedback()
                    self.robot._servo_loop()
                    self.assertGreater(self.robot.get_state()['motion_epoch'], epoch)
                    self.assertIsNone(self.robot.get_target())
                    self.robot.servo_j.assert_not_called()
                    self.robot.servo_p.assert_not_called()

    def test_unlock_between_frame_calculation_and_socket_send_cancels_packet(self):
        self.robot.start_servo('joint')
        epoch = self.robot.get_state()['motion_epoch']
        sock = Mock()
        self.robot._motion = sock
        self.mode = 6; self.feedback()
        self.mode = 5; self.feedback()
        with self.assertRaises(self.driver.DobotError):
            self.driver.DobotMG400.servo_j(self.robot, 10,25,35,9,expected_epoch=epoch)
        sock.sendall.assert_not_called()

    def test_socket_failure_cancels_generation_and_clears_target(self):
        self.robot.start_servo('joint')
        epoch = self.robot.get_state()['motion_epoch']
        self.robot.servo_j.side_effect = self.driver.DobotError(-1, 'connection lost', 'ServoJ')
        self.robot._servo_loop()
        self.assertFalse(self.robot._servo_running)
        self.assertIsNone(self.robot.get_target())
        self.assertGreater(self.robot.get_state()['motion_epoch'], epoch)

    def test_acquire_and_enable_never_start_stream_and_old_epoch_cannot_move(self):
        client = self.route_client()
        for side in ('green', 'purple'):
            acquired = client.post('/api/acquire', json={'side':side}).get_json()
            self.assertTrue(acquired['ok'])
            enabled = client.post('/api/enable', json={'side':side, 'token':acquired['token']}).get_json()
            self.assertTrue(enabled['ok'])
            self.assertFalse(self.robot._servo_running)
            self.assertIsNone(self.robot.get_target())
            self.robot.servo_j.assert_not_called()
            self.robot.servo_p.assert_not_called()
            old = client.post('/api/move', json={'side':side, 'token':acquired['token'],
                'motion_epoch':acquired['motion_epoch'], 'mode':'cartesian', 'pose':self.pose}).get_json()
            self.assertFalse(old['ok'])
            self.assertEqual(old['code'], 'motion_resync_required')
            self.assertFalse(self.robot._servo_running)

    def test_both_player_connect_routes_really_enable_without_streaming(self):
        from test_mobile_teams import player_module
        relay_http = self.route_client()
        for side in ('green','purple'):
            player = player_module(side, 'cartesian-xyz-test')
            adapter = player.RelayClient('http://fake', side)
            def post(path, data):
                response = relay_http.post(path, json=data)
                return response.status_code, response.get_json()
            def get(path):
                response = relay_http.get(path)
                return response.status_code, response.get_json()
            app = Flask('real-player-connect-'+side); app.register_blueprint(player.bp)
            with patch.object(player, '_identity', return_value={'is_player':True,'side':side}), \
                 patch.object(player, 'RelayClient', return_value=adapter), \
                 patch.object(adapter, '_start_heartbeat'), patch.object(adapter, '_post', side_effect=post), \
                 patch.object(adapter, '_get', side_effect=get):
                result = app.test_client().post('/api/connect',json={'mode':'relay'}).get_json()
                self.assertTrue(result['ok'], result)
                self.assertEqual(result['control_session'], adapter.control_session)
                state = app.test_client().get('/api/status').get_json()
                self.assertTrue(state['motion_ready'])
                self.assertEqual(state['pose'],self.pose)
                self.assertEqual(state['joints'],self.joints)
                self.assertFalse(self.robot._servo_running)
                self.assertIsNone(self.robot.get_target())
                self.robot.servo_j.assert_not_called()
                self.robot.servo_p.assert_not_called()
                app.test_client().post('/api/disconnect')

    def test_unlock_during_path_validation_rejects_old_move_then_fresh_input_works(self):
        client = self.route_client()
        acquired = client.post('/api/acquire', json={'side':'green'}).get_json()
        enabled = client.post('/api/enable', json={'side':'green', 'token':acquired['token']}).get_json()
        move = dict(side='green', token=acquired['token'], motion_epoch=enabled['motion_epoch'],
                    mode='cartesian', pose=[310,100,50,9])
        def interrupt(*args):
            self.mode = 6; self.feedback()
            self.mode = 5; self.pose = [320.,110.,60.,9.]; self.feedback()
            return None
        with patch.object(self.relay, '_validate_cal2_cartesian_path', side_effect=interrupt):
            result = client.post('/api/move', json=move).get_json()
        self.assertFalse(result['ok'])
        self.assertFalse(self.robot._servo_running)
        self.robot.servo_p.assert_not_called()
        # Reacquisition cancels old requests; only a new valid command starts.
        new = client.post('/api/acquire', json={'side':'green'}).get_json()
        enabled = client.post('/api/enable', json={'side':'green','token':new['token']}).get_json()
        with patch.object(self.relay, '_validate_cal2_cartesian_path', return_value=None):
            self.assertFalse(client.post('/api/move', json=move).get_json()['ok'])
            move.update(token=new['token'], motion_epoch=enabled['motion_epoch'])
            self.assertTrue(client.post('/api/move', json=move).get_json()['ok'])
        self.assertEqual(self.robot._setpoint, self.pose)
        self.assertEqual(self.robot.get_target(), [310.,100.,50.,9.])

    def test_enable_timeout_and_unsafe_target_do_not_start_follower(self):
        client = self.route_client()
        acquired = client.post('/api/acquire', json={'side':'green'}).get_json()
        self.feed = False
        result = client.post('/api/enable', json={'side':'green','token':acquired['token']}).get_json()
        self.assertFalse(result['ok'])
        self.assertFalse(self.robot._servo_running)
        self.feed = True; self.feedback()
        enabled = client.post('/api/enable', json={'side':'green','token':acquired['token']}).get_json()
        with patch.object(self.relay, '_validate_cal2_cartesian_path', return_value='outside safety boundary'):
            result = client.post('/api/move', json=dict(side='green',token=acquired['token'],
                motion_epoch=enabled['motion_epoch'],mode='cartesian',pose=[400,100,50,9])).get_json()
        self.assertFalse(result['ok'])
        self.assertFalse(self.robot._servo_running)
        self.assertIsNone(self.robot.get_target())


class PlayerFeedbackTests(unittest.TestCase):
    def test_connection_errors_distinguish_relay_failure_from_network_loss(self):
        from test_mobile_teams import player_module
        for side in ('green', 'purple'):
            for slug in ('cartesian-xyz-test', 'joint-angles-test'):
                player = player_module(side, slug)
                app = Flask('connect-errors-'+side+'-'+slug)
                app.register_blueprint(player.bp)
                for status, expected in [(200, 'Relay connection failed'), (None, 'Could not reach relay')]:
                    adapter = Mock()
                    adapter.connect.side_effect = player.RelayError('worker startup failed', status=status)
                    with self.subTest(side=side, slug=slug, status=status), \
                         patch.object(player, '_identity', return_value={'is_player':True,'side':side}), \
                         patch.object(player, 'RelayClient', return_value=adapter):
                        response = app.test_client().post('/api/connect', json={'mode':'relay'})
                        self.assertFalse(response.json['ok'])
                        self.assertIn(expected, response.json['error'])
                        self.assertIn('worker startup failed', response.json['error'])

    def test_both_adapters_preserve_feedback_age_mode_and_acquired_motion_generation(self):
        for side in ('green', 'purple'):
            path = ROOT/'sandboxes'/side/'prototypes/cartesian-xyz-test/relay_client.py'
            spec = importlib.util.spec_from_file_location('feedback_'+side, path)
            module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
            relay = module.RelayClient('http://fake', side)
            relay._token = 'lease'; relay._hb_ok = True; relay._motion_epoch = 3
            arm = dict(connected=True, enabled=True, robot_mode=6, feedback_ok=True,
                       feedback_at=99., motion_epoch=3, motion_ready=True)
            relay._relay_state = {'arms':{side:arm}}
            with patch.object(module.time, 'time', return_value=100.):
                state = relay.get_state()
                self.assertEqual(state['last_feedback'], 99.)
                self.assertEqual(state['robot_mode'], 6)
                self.assertTrue(state['feedback_ok'])
                arm['feedback_at'] = 90.
                self.assertFalse(relay.get_state()['feedback_ok'])
                arm.update(feedback_at=99., motion_epoch=4)
                self.assertFalse(relay.get_state()['motion_ready'])
            with patch.object(relay, '_post') as post:
                self.assertFalse(relay.set_target_pose(300,100,50,9,motion_epoch=4)[0])
                post.assert_not_called()
            # A heartbeat that began before Enable cannot roll feedback back.
            relay._store_state({'arms':{side:dict(arm, motion_epoch=2,feedback_at=100.)}})
            self.assertEqual(relay._relay_state['arms'][side]['motion_epoch'],4)

    def test_delayed_browser_move_cannot_bind_to_replacement_player_connection(self):
        from test_mobile_teams import player_module
        for side in ('green', 'purple'):
            module = player_module(side, 'cartesian-xyz-test')
            robot = SimpleNamespace(is_connected=lambda:True, control_session='new',
                                    set_target_pose=Mock(), set_target_joints_guarded=Mock())
            app = Flask('player-reconnect-'+side); app.register_blueprint(module.bp)
            with patch.object(module, '_current', return_value=robot), patch.object(module, '_link', 'relay'):
                for route in ('move','joint-move'):
                    result = app.test_client().post('/api/'+route, json=dict(
                        control_session='old', motion_epoch=1,ltz_action='xyz',
                        x=300,y=100,z=50,j1=0,j2=20,j3=30,j4=9)).get_json()
                    self.assertFalse(result['ok'])
                    self.assertEqual(result['code'], 'motion_resync_required')
            robot.set_target_pose.assert_not_called()
            robot.set_target_joints_guarded.assert_not_called()

    def test_outside_limit_feedback_is_never_silently_clamped_into_a_move(self):
        from test_mobile_teams import player_module
        for side in ('green', 'purple'):
            module = player_module(side, 'cartesian-xyz-test')
            robot = SimpleNamespace(is_connected=lambda:True, control_session='current',
                get_state=lambda:dict(pose=[300,100,50,170]),
                set_target_pose=Mock(), set_target_joints_guarded=Mock())
            app = Flask('player-limits-'+side); app.register_blueprint(module.bp)
            with patch.object(module, '_current', return_value=robot), patch.object(module, '_link', 'relay'):
                client = app.test_client()
                for route, target in [('move',dict(x=300,y=100,z=50,r=170)),
                                      ('joint-move',dict(j1=0,j2=20,j3=30,j4=170))]:
                    result=client.post('/api/'+route,json=dict(control_session='current',motion_epoch=2,
                                      ltz_action='xyz',**target)).get_json()
                    self.assertFalse(result['ok'])
                    self.assertEqual(result['code'],'motion_limit')
            robot.set_target_pose.assert_not_called()
            robot.set_target_joints_guarded.assert_not_called()


if __name__ == '__main__':
    unittest.main()
