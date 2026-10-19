"""Feedback races and transport delays, using fake arms only. No hardware I/O."""
import importlib.util
import io
import json
import threading
import unittest
from unittest.mock import Mock, patch

from test_photon_framework import load, ROOT, Flask


def adapter(side):
    path = ROOT / 'sandboxes' / side / 'prototypes/cartesian-xyz-test/relay_client.py'
    spec = importlib.util.spec_from_file_location('stream_feedback_' + side, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, module.RelayClient('http://fake', side, auth='test-auth')


def packet(mode=5):
    return dict(robot_mode=mode, joints=[0., 20., 30., 9.],
                pose=[300., 100., 50., 9.], digital_in=0, digital_out=0)


class FeedbackAtomicityTests(unittest.TestCase):
    def test_a_reader_cannot_validate_its_old_copy_after_continuous_feedback_advances(self):
        load('dobot-mg400-relay')
        driver = __import__('relay_arm')
        robot = driver.DobotMG400('test-no-network')
        robot._state['connected'] = True
        clock = [100.]
        validate = robot.feedback_fresh

        def concurrent_feedback(state):
            # Reproduce scheduling between the copy and validation. It is
            # possible only if the reader has left the publication lock.
            if robot._servo_lock.acquire(blocking=False):
                robot._servo_lock.release()
                for at in (100.15, 100.3, 100.45):
                    clock[0] = at
                    robot._apply_feedback(packet())
            return validate(state)

        with patch.object(driver.time, 'time', side_effect=lambda: clock[0]):
            robot._apply_feedback(packet())
            epoch = robot.get_state()['motion_epoch']
            with patch.object(robot, 'feedback_fresh', side_effect=concurrent_feedback):
                state = robot.get_state()
            self.assertTrue(state['feedback_ok'])
            self.assertEqual(state['motion_epoch'], epoch, 'A stale reader revoked healthy feedback')

    def test_delayed_reader_cannot_expire_feedback_that_arrived_while_it_waited(self):
        load('dobot-mg400-relay')
        driver = __import__('relay_arm')
        robot = driver.DobotMG400('test-no-network')
        robot._state['connected'] = True
        clock = [100.]
        reached, resume = threading.Event(), threading.Event()
        lock = robot._servo_lock

        class DelayedReaderLock:
            def __enter__(self):
                if threading.current_thread().name == 'delayed-status':
                    reached.set()
                    if not resume.wait(2):
                        raise AssertionError('Reader was not released')
                lock.acquire()

            def __exit__(self, *args):
                lock.release()

        result = []
        with patch.object(driver.time, 'time', side_effect=lambda: clock[0]):
            robot._apply_feedback(packet())
            epoch = robot.get_state()['motion_epoch']
            robot._servo_lock = DelayedReaderLock()
            reader = threading.Thread(target=lambda: result.append(robot.get_state()), name='delayed-status')
            reader.start()
            try:
                self.assertTrue(reached.wait(2))
                # Feedback remains continuous while an HTTP reader is delayed.
                # Its original snapshot would now be over the 250 ms limit.
                for at in (100.15, 100.3, 100.45):
                    clock[0] = at
                    robot._apply_feedback(packet())
            finally:
                resume.set()
                reader.join(2)
            self.assertFalse(reader.is_alive())
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]['last_feedback'], 100.45)
            self.assertTrue(result[0]['feedback_ok'])
            self.assertEqual(robot.get_state()['motion_epoch'], epoch)

    def test_real_gap_and_brief_unlock_still_latch_the_original_safety_limits(self):
        load('dobot-mg400-relay')
        driver = __import__('relay_arm')
        for fault, reason in [('gap', 'feedback_gap'), ('stale', 'feedback_stale'),
                              ('unlock', 'robot_mode_6')]:
            with self.subTest(fault=fault):
                robot = driver.DobotMG400('test-no-network')
                robot._state['connected'] = True
                clock = [100.]
                with patch.object(driver.time, 'time', side_effect=lambda: clock[0]):
                    robot._apply_feedback(packet())
                    robot._target = robot._setpoint = [300., 100., 50., 9.]
                    robot._servo_running = True
                    epoch = robot.get_state()['motion_epoch']
                    if fault == 'unlock':
                        robot._apply_feedback(packet(6))
                        robot._apply_feedback(packet())
                    else:
                        clock[0] += .251
                        if fault == 'gap':
                            robot._apply_feedback(packet())
                    state = robot.get_state()
                    self.assertEqual(state['motion_epoch'], epoch + 1)
                    self.assertEqual(state['motion_invalidation'], reason)
                    self.assertFalse(robot._servo_running)
                    self.assertIsNone(robot.get_target())


class FeedbackRouteTests(unittest.TestCase):
    def setUp(self):
        self.relay = load('dobot-mg400-relay')
        self.app = Flask('feedback-test')
        self.app.register_blueprint(self.relay.bp)
        self.client = self.app.test_client()

    def test_stream_and_compact_heartbeat_never_read_monitor_or_other_arm(self):
        def arm(side):
            self.assertEqual(side, 'green')
            return dict(connected=True, feedback_at=100., motion_epoch=7)

        self.relay._sides['green'].update(token='test', present=True, last_seen=100.)
        with patch.object(self.relay, '_arm_dict', side_effect=arm), \
             patch.object(self.relay, '_command_log_snapshot', side_effect=AssertionError('monitor I/O')), \
             patch.object(self.relay, '_arm', side_effect=AssertionError('hardware access')):
            response = self.client.get('/api/feedback?side=green', buffered=False)
            try:
                data = json.loads(next(iter(response.response)).split(b'data: ', 1)[1])
                self.assertEqual(data['contract'], 'hhh.relay.feedback')
                self.assertEqual(data['version'], 1)
                self.assertEqual(set(data['arms']), {'green'})
                self.assertNotIn('command_log', data)
                self.assertEqual(self.relay._sides['green']['last_seen'], 100., 'Stream cannot renew a lease')
            finally:
                response.close()
            response = self.client.post('/api/heartbeat', json=dict(side='green', token='test', feedback_only=True))
            self.assertTrue(response.json['ok'])
            self.assertEqual(response.json['state']['contract'], 'hhh.relay.feedback')
            self.assertGreater(self.relay._sides['green']['last_seen'], 100.)
        self.assertEqual(self.client.get('/api/feedback?side=unknown').status_code, 400)

    def test_monitor_snapshot_does_not_hold_lease_lock(self):
        def monitor():
            self.assertTrue(self.relay._arb_lock.acquire(blocking=False), 'Lease blocked by monitor')
            self.relay._arb_lock.release()
            return []
        with patch.object(self.relay, '_command_log_snapshot', side_effect=monitor):
            self.relay.full_state()


class FeedbackStreamTests(unittest.TestCase):
    def state(self, side, at, epoch=7):
        return dict(contract='hhh.relay.feedback', version=1, status='ready',
            arms={side: dict(connected=True, enabled=True, feedback_ok=True, feedback_at=at,
                            robot_mode=5, motion_epoch=epoch, motion_ready=True,
                            pose=[300, 100, 50, 9], joints=[0, 20, 30, 9])},
            sides={side: dict(present=True, lease_secs=1.8)})

    def run_stream(self, module, relay, values):
        class Frames(io.BytesIO):
            def readline(self, limit=-1):
                result = super().readline(limit)
                if not result:
                    relay._feedback_stop.set()
                return result
        response = Frames(b''.join(b'data: ' + json.dumps(value).encode() + b'\n\n' for value in values))
        with patch.object(module.urllib.request, 'urlopen', return_value=response) as open_stream:
            relay._feedback_loop()
        return open_stream

    def test_both_players_receive_fresh_feedback_while_heartbeat_reply_is_delayed(self):
        for side in ('green', 'purple'):
            with self.subTest(side=side):
                module, relay = adapter(side)
                relay._token, relay._hb_ok, relay._motion_epoch = 'test', True, 7
                old_heartbeat = self.state(side, 99.)
                relay._store_state(old_heartbeat)
                with patch.object(module.time, 'time', return_value=101.5), \
                     patch.object(relay, '_post', side_effect=AssertionError('Stream sent a command')):
                    stream = self.run_stream(module, relay, [self.state(side, 100.), self.state(side, 101.5)])
                    self.assertTrue(relay.get_state()['motion_ready'])
                    self.assertEqual(relay.get_state()['last_feedback'], 101.5)
                    # The older heartbeat cannot roll back the streamed measurement.
                    relay._store_state(old_heartbeat)
                    self.assertEqual(relay.get_state()['last_feedback'], 101.5)
                    relay._hb_ok = False
                    self.assertFalse(relay.get_state()['connected'], 'Fresh stream cannot replace a lease')
                request = stream.call_args.args[0]
                self.assertTrue(request.full_url.endswith('/api/feedback?side=' + side))
                self.assertEqual(request.get_header('X-hhh-auth'), 'test-auth')

    def test_invalid_stream_does_not_replace_state_and_old_feedback_expires(self):
        for side in ('green', 'purple'):
            for change in ({'version': True}, {'pose': 'bad'}, {'feedback_at': 'new'}, {'motion_epoch': True}):
                with self.subTest(side=side, change=change):
                    module, relay = adapter(side)
                    relay._token, relay._hb_ok, relay._motion_epoch = 'test', True, 7
                    relay._store_state(self.state(side, 100.))
                    invalid = self.state(side, 102.)
                    (invalid if 'version' in change else invalid['arms'][side]).update(change)
                    # A malformed frame reconnects. Stop the test on the first retry.
                    with patch.object(relay._feedback_stop, 'wait', side_effect=lambda _: relay._feedback_stop.set()):
                        self.run_stream(module, relay, [invalid])
                    self.assertIn('unavailable', relay._feedback_error)
                    with patch.object(module.time, 'time', return_value=102.):
                        self.assertFalse(relay.get_state()['feedback_ok'])
                        self.assertFalse(relay.get_state()['motion_ready'])

    def test_close_releases_stream_heartbeat_and_lease(self):
        for side in ('green', 'purple'):
            module, relay = adapter(side)
            relay._token, relay._hb_ok = 'test', True
            stream, heartbeat = Mock(), Mock()
            relay._feedback_thread, relay._hb_thread = stream, heartbeat
            with patch.object(relay, '_post', return_value=(200, {'ok': True})) as post:
                relay.close()
            self.assertTrue(relay._feedback_stop.is_set())
            stream.join.assert_called_once()
            heartbeat.join.assert_called_once()
            post.assert_called_once_with('/api/release', dict(side=side, token='test'))
            self.assertFalse(relay.is_connected())

    def test_player_hub_stop_closes_its_client(self):
        from test_mobile_teams import player_module
        for side in ('green', 'purple'):
            module = player_module(side, 'cartesian-xyz-test')
            robot = Mock()
            module._robot = robot
            module.hub_stop()
            robot.close.assert_called_once()
            self.assertIsNone(module._robot)


if __name__ == '__main__':
    unittest.main()
