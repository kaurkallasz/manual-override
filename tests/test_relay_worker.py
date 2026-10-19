"""Process isolation with the real follower and fake feedback; no robot sockets."""
import ctypes
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] /
                      'sandboxes/gamemaster/prototypes/dobot-mg400-relay'))
from relay_arm import DobotMG400, DobotError
from arm_worker import ArmWorker, PARENT_TIMEOUT


class FakeArm(DobotMG400):
    """Exercise production freshness/epochs/servo with an 8 ms simulated feed."""
    def record(self, event):
        with open(self.ip, 'a') as file:
            file.write(event + '\n')

    def connect(self):
        self.iface = 'fake-loopback-only'
        self._state['connected'] = True
        self.feeding = True
        self.done = threading.Event()
        self.feed()
        def produce():
            while not self.done.wait(.008):
                if self.feeding:
                    self.feed()
        self.producer = threading.Thread(target=produce, daemon=True)
        self.producer.start()

    def feed(self, mode=5):
        self._apply_feedback(dict(robot_mode=mode, joints=[0., 20., 30., 9.],
                                  pose=[300., 100., 50., 9.], digital_in=0, digital_out=0))

    def clear_error(self):
        return 0, 'fake clear'

    def enable(self):
        return 0, 'fake enable'

    def set_pump(self, mode, suck_do=2, blow_do=1):
        if mode == 'test-stale':
            self.feeding = False
        elif mode == 'test-fresh':
            self.feeding = True
        elif mode == 'test-unlock':
            self.feed(6)
            self.feed()
        elif mode == 'test-delay':
            time.sleep(.6)
        else:
            self.record('pump:' + mode)
        return 0, 'fake pump'

    def get_state(self):
        return dict(super().get_state(), worker_pid=os.getpid())

    def servo_p(self, *values, **kwargs):
        self.record('servo')
        return 0, 'fake motion'

    servo_j = servo_p

    def stop_robot(self):
        self.record('stop')

    def close(self):
        self.stop_servo()
        if hasattr(self, 'done'):
            self.done.set()
            self.producer.join(1)
        self.record('close')


class FailingArm(FakeArm):
    def connect(self):
        raise DobotError(-1, 'test connect failed', 'connect')


def block_python(seconds):
    # PyDLL deliberately holds the GIL, like a slow C encoder/GC operation in
    # the hub. Other processes and the simulated robot continue independently.
    delay = ctypes.PyDLL(None).usleep
    delay.argtypes = [ctypes.c_uint]
    delay.restype = ctypes.c_int
    delay(int(seconds * 1_000_000))


class RelayWorkerTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = str(Path(self.folder.name) / 'fake-arm-events.txt')

    def worker(self, factory=FakeArm):
        robot = ArmWorker(self.path, _driver_factory=factory, command_timeout=1)
        self.addCleanup(robot.close)
        robot.connect()
        return robot

    def test_hub_gil_stall_cannot_expire_continuous_robot_feedback(self):
        # First demonstrate the old shared-process failure with the same driver.
        local = FakeArm(self.path)
        local.connect()
        try:
            before = local.get_state()['motion_epoch']
            block_python(.4)
            self.assertGreater(local.get_state()['motion_epoch'], before)
        finally:
            local.close()
        robot = self.worker()
        before = robot.get_state()
        self.assertNotEqual(before['worker_pid'], os.getpid())
        robot.start_servo('cartesian', expected_epoch=before['motion_epoch'])
        for _ in range(3):
            frames = Path(self.path).read_text().count('servo')
            block_python(.6)
            state = robot.get_state()
            self.assertTrue(state['feedback_ok'])
            self.assertTrue(state['motion_ready'])
            self.assertEqual(state['motion_epoch'], before['motion_epoch'])
            self.assertLess(time.time() - state['last_feedback'], .25)
            self.assertGreater(Path(self.path).read_text().count('servo'), frames)
            time.sleep(.12)  # Let the hub heartbeat run between pauses.
        self.assertEqual(robot.iface, 'fake-loopback-only')

    def test_connect_enable_do_not_move_and_slow_command_does_not_block_status(self):
        robot = self.worker()
        robot.enable()
        self.assertIsNone(robot.get_target())
        self.assertFalse(Path(self.path).exists())
        command = threading.Thread(target=lambda: robot.set_pump('test-delay'))
        command.start()
        try:
            for _ in range(5):
                self.assertTrue(robot.get_state()['motion_ready'])
                time.sleep(.03)
            # Stop/reset cannot queue behind a stalled dashboard response.
            robot.reset_motion()
            self.assertTrue(command.is_alive(), 'Status waited for dashboard I/O')
        finally:
            command.join(2)

    def test_real_feedback_gap_and_unlock_still_cancel_and_reject_old_targets(self):
        for fault in ('test-stale', 'test-unlock'):
            with self.subTest(fault=fault):
                robot = self.worker()
                epoch = robot.reset_motion()
                robot.start_servo('cartesian', expected_epoch=epoch)
                robot.set_target_pose(301., 100., 50., 9., expected_epoch=epoch)
                robot.set_pump(fault)
                if fault == 'test-stale':
                    time.sleep(.35)
                stopped = robot.get_state()
                self.assertGreater(stopped['motion_epoch'], epoch)
                self.assertIsNone(robot.get_target())
                deadline = time.monotonic() + .3
                while stopped['servo_active'] and time.monotonic() < deadline:
                    time.sleep(.01)
                    stopped = robot.get_state()
                self.assertFalse(stopped['servo_active'])
                robot.set_pump('test-fresh')
                with self.assertRaises(DobotError):
                    robot.set_target_pose(301., 100., 50., 9., expected_epoch=epoch)
                self.assertIsNone(robot.get_target())
                robot.close()

    def test_target_waiting_behind_slow_dashboard_command_expires_without_replay(self):
        robot = self.worker()
        epoch = robot.reset_motion()
        robot.start_servo('cartesian', expected_epoch=epoch)
        delayed = threading.Thread(target=lambda: robot.set_pump('test-delay'))
        delayed.start()
        try:
            time.sleep(.05)
            with self.assertRaisesRegex(DobotError, 'expired'):
                robot.set_target_pose(301, 100, 50, 9, expected_epoch=epoch)
        finally:
            delayed.join(2)
        self.assertEqual(robot.get_target(), [300., 100., 50., 9.])

    def test_lost_parent_watchdog_stops_arm_and_does_not_reconnect(self):
        robot = self.worker()
        robot.start_servo('cartesian')
        robot._stop.set()  # Simulate the parent heartbeat disappearing.
        robot._process.join(PARENT_TIMEOUT + 2)
        self.assertFalse(robot._process.is_alive())
        events = Path(self.path).read_text().splitlines()
        self.assertIn('stop', events)
        self.assertIn('pump:off', events)
        self.assertIn('close', events)
        self.assertFalse(robot.get_state()['connected'])
        with self.assertRaises(DobotError):
            robot.enable()

    def test_worker_crash_fails_closed_and_close_releases_resources(self):
        robot = self.worker()
        robot._process.terminate()
        robot._process.join(2)
        self.assertFalse(robot.get_state()['motion_ready'])
        with self.assertRaises(DobotError):
            robot.set_target_pose(301, 100, 50, 9, expected_epoch=0)
        robot.close()
        self.assertFalse(robot._pulse_thread.is_alive())
        self.assertFalse(robot._process.is_alive())

    def test_parent_pipe_loss_stops_without_waiting_for_heartbeat_timeout(self):
        robot = self.worker()
        robot._reads.close()
        robot._process.join(1)
        self.assertFalse(robot._process.is_alive())
        events = Path(self.path).read_text().splitlines()
        self.assertIn('stop', events)
        self.assertIn('pump:off', events)

    def test_connect_failure_tears_down_worker(self):
        robot = ArmWorker(self.path, _driver_factory=FailingArm, command_timeout=1)
        self.addCleanup(robot.close)
        with self.assertRaisesRegex(DobotError, 'test connect failed'):
            robot.connect()
        self.assertFalse(robot._process.is_alive())
        self.assertFalse(robot._pulse_thread.is_alive())

    def test_hub_stop_closes_both_owned_drivers(self):
        from test_photon_framework import load
        relay = load('dobot-mg400-relay')
        arms = [Mock(), Mock()]
        for side, arm in zip(relay.SIDES, arms):
            relay._robots[side] = arm
        relay.hub_stop()
        for arm in arms:
            arm.close.assert_called_once()
        self.assertTrue(all(arm is None for arm in relay._robots.values()))

    def test_both_relay_connect_routes_use_owned_workers_and_fresh_measurements(self):
        from test_photon_framework import load, Flask
        relay = load('dobot-mg400-relay')
        app = Flask('isolated-driver-routes')
        app.register_blueprint(relay.bp)
        client = app.test_client()
        workers = []
        def make_worker(ip, **kwargs):
            arm = ArmWorker(ip, **kwargs, _driver_factory=FakeArm, command_timeout=1)
            workers.append(arm)
            return arm
        try:
            with patch.object(relay, 'ArmWorker', side_effect=make_worker), \
                 patch.object(relay, '_log_command'), patch.object(relay, '_log_incoming'):
                for side in relay.SIDES:
                    result = client.post('/api/connect', json={'side':side, 'ip':self.path}).json
                    self.assertTrue(result['ok'], result)
                    acquired = client.post('/api/acquire', json={'side':side}).json
                    self.assertTrue(acquired['ok'], acquired)
                    enabled = client.post('/api/enable', json={'side':side,'token':acquired['token']}).json
                    self.assertTrue(enabled['ok'], enabled)
                    state = client.get('/api/state').json['arms'][side]
                    self.assertTrue(state['feedback_ok'])
                    self.assertTrue(state['motion_ready'])
                    self.assertFalse(state['servo_active'])
                self.assertNotEqual(workers[0]._process.pid, workers[1]._process.pid)
        finally:
            relay.hub_stop()
        self.assertTrue(all(not arm._process.is_alive() for arm in workers))

    def test_failed_route_setup_does_not_leave_an_unowned_worker(self):
        from test_photon_framework import load, Flask
        relay = load('dobot-mg400-relay')
        app = Flask('failed-worker-setup')
        app.register_blueprint(relay.bp)
        robot = ArmWorker(self.path, _driver_factory=FakeArm, command_timeout=1)
        self.addCleanup(robot.close)
        with patch.object(relay, 'ArmWorker', return_value=robot), \
             patch.object(relay, '_apply_motion', side_effect=DobotError(-1, 'setup failed', 'settings')), \
             patch.object(relay, '_log_command'), patch.object(relay, '_log_incoming'):
            result = app.test_client().post('/api/connect', json={'side':'green'}).json
        self.assertFalse(result['ok'])
        self.assertIsNone(relay._robots['green'])
        self.assertFalse(robot._process.is_alive())

    def test_production_hub_loader_can_spawn_workers_after_helper_cache_cleanup(self):
        result = subprocess.run([sys.executable, str(Path(__file__).with_name('relay_worker_hub_smoke.py'))],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('"status": "passed"', result.stdout)

    def test_spawn_failure_is_reported_as_json_and_leaves_no_owned_arm(self):
        from test_photon_framework import load, Flask
        relay = load('dobot-mg400-relay')
        app = Flask('failed-worker-startup')
        app.register_blueprint(relay.bp)
        robot = ArmWorker(self.path, _driver_factory=FakeArm)
        self.addCleanup(robot.close)
        with patch.object(relay, 'ArmWorker', return_value=robot), \
             patch.object(ArmWorker.connect.__globals__['multiprocessing'], 'get_context', side_effect=OSError('test process unavailable')), \
             patch.object(relay, '_log_command'), patch.object(relay, '_log_incoming'):
            response = app.test_client().post('/api/connect', json={'side':'green'})
        self.assertTrue(response.is_json)
        self.assertFalse(response.json['ok'])
        self.assertIn('Relay worker startup failed: test process unavailable', response.json['error'])
        self.assertIsNone(relay._robots['green'])
        self.assertIsNone(robot._process)


if __name__ == '__main__':
    unittest.main()
