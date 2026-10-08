"""Camera startup/replacement smoke tests; no hardware is opened.

Run: .venv/bin/python -m unittest discover -s tests -p test_webcam_lifecycle.py
"""
import base64
import concurrent.futures
import threading
import time
import unittest
import json
import tempfile
from pathlib import Path
from unittest import mock
import numpy as np
from flask import Flask

from test_photon_framework import load


class WebcamLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.webcam = load("webcam")
        self.settings = dict(index=0, width=2560, height=1440,
                             tracking_width=1920, tracking_height=1080,
                             detection_fps=10)

    def test_hub_starts_saved_camera_without_a_video_request(self):
        with mock.patch.object(self.webcam._mgr, "ensure_open") as start:
            self.webcam.hub_init(mock.Mock(is_enabled=lambda: True))
            start.assert_called_once_with()
        with mock.patch.object(self.webcam._mgr, "ensure_open") as start:
            self.webcam.hub_init(mock.Mock(is_enabled=lambda: False))
            start.assert_not_called()
        with mock.patch.object(self.webcam._mgr, "close") as stop:
            self.webcam.hub_stop()
            stop.assert_called_once_with()

    def test_no_saved_selection_does_not_open_hardware(self):
        with mock.patch.object(self.webcam, "_load_settings", return_value=None), \
                mock.patch.object(self.webcam.cv2, "VideoCapture") as capture:
            self.assertFalse(self.webcam._mgr.ensure_open()[0])
            capture.assert_not_called()

    def test_simultaneous_viewers_open_saved_camera_only_once(self):
        manager = self.webcam._mgr
        barrier = threading.Barrier(8)

        def fake_open(*args):
            time.sleep(.02)  # Other viewers arrive while the device opens.
            manager._index = args[0]
            return True, None

        def viewer():
            barrier.wait(timeout=2)
            return manager.ensure_open()

        with mock.patch.object(self.webcam, "_load_settings", return_value=self.settings), \
                mock.patch.object(manager, "_open", side_effect=fake_open) as opened, \
                concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: viewer(), range(8)))
            self.assertEqual(results, [(True, None)] * 8)
            opened.assert_called_once_with(0, 2560, 1440, 1920, 1080, 10)

    def test_close_cannot_overlap_capture_replacement(self):
        manager = self.webcam._mgr
        entered, release, closing, closed = (threading.Event() for _ in range(4))

        def fake_open(*args):
            entered.set()
            self.assertTrue(release.wait(timeout=2))
            return True, None

        def close():
            closing.set()
            manager.close()

        with mock.patch.object(manager, "_open", side_effect=fake_open), \
                mock.patch.object(manager, "_close", side_effect=closed.set), \
                concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(manager.open, 0)
            self.assertTrue(entered.wait(timeout=2))
            second = pool.submit(close)
            self.assertTrue(closing.wait(timeout=2))
            try:
                self.assertFalse(closed.wait(timeout=.05))
            finally:
                release.set()
            first.result(timeout=2)
            second.result(timeout=2)
            self.assertTrue(closed.is_set())

    def live_manager(self):
        manager = self.webcam._mgr
        manager._cap = mock.Mock()
        manager._index = 0
        manager._running = True
        manager._latest_raw = np.zeros((8, 12, 3), np.uint8)
        manager._latest_raw_at = time.time()
        manager._latest = b'fixture-live-frame'
        manager._w, manager._h = 12, 8
        manager._actual_preview_w, manager._actual_preview_h = 12, 8
        manager._fps = 30
        manager._last_detections_at = time.monotonic()
        manager._overlay_detections = {100: {}}
        manager._capture_device = dict(index=0, name='Webcam', unique_id='usb-camera')
        return manager

    def test_stalled_capture_exposes_no_stale_image_dimensions_or_detections(self):
        manager = self.live_manager()
        self.assertTrue(manager.status()['open'])
        manager._latest_raw_at -= 2
        status = manager.status()
        self.assertFalse(status['open'])
        for key in ('width', 'height', 'preview_width', 'preview_height', 'tracking_width', 'fps'):
            self.assertEqual(status[key], 0, key)
        self.assertIn('fresh', status['error'])
        self.assertEqual(manager.latest_jpeg(), manager._no_signal)
        self.assertIsNone(manager.latest_frame())
        self.assertEqual(manager.detection_snapshot(time.monotonic()), ([], []))
        self.assertEqual(self.webcam.camera_status_snapshot()['status'], 'unavailable')
        self.assertEqual(self.webcam.raw_frame_snapshot()['status'], 'unavailable')
        self.assertEqual(self.webcam.tag_snapshot()['visible_ids'], [])

    def test_failed_read_clears_live_state_and_a_new_frame_recovers(self):
        manager = self.live_manager()
        cap = manager._cap
        frame = manager._latest_raw.copy()
        cap.read.return_value = (False, None)
        def after_failure(_):
            self.assertFalse(manager.status()['open'])
            self.assertIsNone(manager._latest_raw)
            self.assertEqual(manager._w, 0)
            self.assertEqual(manager._overlay_detections, {})
            manager._running = False
        with mock.patch.object(self.webcam.time, 'sleep', side_effect=after_failure):
            manager._grab_loop()
        manager._running = True
        def recovered_then_stop():
            if cap.read.call_count > 2:
                manager._running = False
                return False, None
            return True, frame.copy()
        cap.read.side_effect = recovered_then_stop
        with mock.patch.object(manager, '_process_frame', side_effect=lambda frame: frame):
            manager._grab_loop()
        self.assertIsNone(manager._error)
        self.assertEqual((manager._w, manager._h), (12, 8))
        self.assertIsNotNone(manager._latest_raw)

    def test_stop_and_failed_replacement_remove_the_old_device_state(self):
        manager = self.live_manager()
        old_cap = manager._cap
        with mock.patch.object(self.webcam, '_capture_devices', return_value=[]):
            self.assertFalse(manager.open(4)[0])
        old_cap.release.assert_called_once()
        self.assertIsNone(manager.active_index())
        self.assertEqual(manager.status()['width'], 0)
        self.assertIsNone(manager.status()['name'])
        manager.close()
        with mock.patch.object(manager, '_open') as opened:
            self.assertFalse(manager.ensure_open()[0])
            opened.assert_not_called()

    def test_saved_identity_survives_index_changes_and_never_falls_back(self):
        remembered = dict(self.settings, unique_id='usb-camera', name='Webcam')
        devices = [dict(index=0, name='FaceTime', unique_id='builtin'),
                   dict(index=1, name='Webcam', unique_id='usb-camera')]
        manager = self.webcam._mgr
        with mock.patch.object(self.webcam, '_load_settings', return_value=remembered), \
                mock.patch.object(self.webcam, '_capture_devices', return_value=devices), \
                mock.patch.object(manager, '_open', return_value=(True, None)) as opened:
            self.assertTrue(manager.ensure_open()[0])
            self.assertEqual(opened.call_args.args[0], 1)
        for inventory in (devices[:1], None, []):
            with mock.patch.object(self.webcam, '_load_settings', return_value=remembered), \
                    mock.patch.object(self.webcam, '_capture_devices', return_value=inventory), \
                    mock.patch.object(manager, '_open') as opened:
                self.assertFalse(manager.ensure_open()[0])
                opened.assert_not_called()
                self.assertIn('unavailable', manager.status()['error'])

    def test_inventory_does_not_probe_absent_devices_or_label_usb_bus_indices(self):
        manager = self.live_manager()
        manager._latest_raw_at -= 2
        devices = [dict(index=0, name='FaceTime', unique_id='builtin'),
                   dict(index=1, name='Webcam', unique_id='usb-camera')]
        with mock.patch.object(self.webcam, '_capture_devices', return_value=devices), \
                mock.patch.object(self.webcam.cv2, 'VideoCapture') as opened:
            cameras = self.webcam.probe_cameras()
        opened.assert_not_called()
        self.assertEqual([c['name'] for c in cameras], ['FaceTime', 'Webcam'])
        self.assertFalse(any(c['active'] for c in cameras))
        self.assertFalse(any(c['width'] for c in cameras))

    def test_reconnect_uses_saved_identity_after_stop(self):
        manager = self.live_manager()
        manager.close()
        with mock.patch.object(self.webcam, '_load_settings', return_value=self.settings), \
                mock.patch.object(manager, '_open', return_value=(True, None)) as opened:
            self.assertTrue(manager.reconnect()[0])
            opened.assert_called_once()

    def test_selection_persists_identity_with_existing_optical_settings(self):
        device = dict(index=1, name='Webcam', unique_id='usb-camera')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'settings.json'
            path.write_text(json.dumps(dict(self.settings, focus=2, autofocus=False)))
            with mock.patch.object(self.webcam, 'SETTINGS_PATH', str(path)):
                self.webcam._save_settings(index=1, capture_device=device)
                saved = self.webcam._load_settings()
        self.assertEqual(saved['unique_id'], 'usb-camera')
        self.assertEqual(saved['index'], 1)
        self.assertEqual(saved['focus'], 2)
        self.assertFalse(saved['autofocus'])


    def test_preview_events_deliver_image_and_status_without_opening_hardware(self):
        app = Flask(__name__)
        app.register_blueprint(self.webcam.bp)
        manager = self.webcam._mgr
        with mock.patch.object(manager, 'ensure_open') as opened, \
                mock.patch.object(self.webcam, '_load_settings', return_value=None):
            with app.test_client() as client:
                response = client.get('/api/events?preview=1', buffered=False)
                self.assertEqual(response.mimetype, 'text/event-stream')
                event = json.loads(next(iter(response.response)).decode().removeprefix('data: '))
                response.close()
                self.assertFalse(event['status']['open'])
                self.assertEqual(event['tags'], [])
                self.assertEqual(base64.b64decode(event['preview'].split(',', 1)[1]), manager._no_signal)
                response = client.get('/api/events', buffered=False)
                status_event = json.loads(next(iter(response.response)).decode().removeprefix('data: '))
                response.close()
                self.assertNotIn('preview', status_event)
                opened.assert_not_called()

    def test_saved_optics_restore_after_capture_configuration(self):
        manager = self.webcam._mgr
        device = dict(index=0, name='Webcam', unique_id='usb-camera')
        saved = dict(self.settings, unique_id='usb-camera', autofocus=False,
                     focus=2, autoexposure=False, exposure=309)
        cap = mock.Mock()
        commands = []
        state = dict(autofocus_supported=True, focus_supported=True,
                     autofocus=False, focus=2, autoexposure=False, exposure=309)
        cap.set.side_effect = lambda prop, value: commands.append(('capture', prop))
        def native_command(process, command, value):
            commands.append((command, value))
            return state
        with mock.patch.object(self.webcam, '_capture_devices', return_value=[device]), \
                mock.patch.object(self.webcam, '_usb_device_for_capture', return_value={'vendor':'x','product':'y'}), \
                mock.patch.object(self.webcam, '_start_native_focus', return_value=(mock.Mock(), state)), \
                mock.patch.object(self.webcam, '_native_focus_request', side_effect=native_command), \
                mock.patch.object(self.webcam, '_load_settings', return_value=saved), \
                mock.patch.object(self.webcam, '_save_settings'), \
                mock.patch.object(self.webcam.sys, 'platform', 'darwin'), \
                mock.patch.object(self.webcam.cv2, 'VideoCapture', return_value=cap), \
                mock.patch.object(self.webcam.threading.Thread, 'start'):
            self.assertTrue(manager.open(0)[0])
        self.assertLess(commands.index(('capture', self.webcam.cv2.CAP_PROP_FRAME_HEIGHT)),
                        commands.index(('set-autoexposure', 0)))
        self.assertLess(commands.index(('set-autoexposure', 0)), commands.index(('set-exposure', 309)))

    def test_native_controls_do_not_probe_or_mutate_opencv_controls(self):
        manager = self.live_manager()
        manager._native_focus_state = dict(autofocus_supported=True, focus_supported=True,
            autofocus=False, focus=2, autoexposure_supported=True, exposure_supported=True,
            autoexposure=False, exposure=309, exposure_min=1, exposure_max=80000)
        value = manager.focus_controls()
        self.assertFalse(value['autoexposure'])
        self.assertEqual(value['exposure'], 309)
        manager._cap.set.assert_not_called()

    def test_unsupported_exposure_cannot_report_a_successful_change(self):
        manager = self.live_manager()
        with mock.patch.object(self.webcam, '_save_focus_settings') as saved:
            ok, error, value = manager.set_focus_controls(autoexposure=False, exposure=300)
            self.assertFalse(ok)
            self.assertIn('exposure control', error)
            self.assertIsNone(value)
            saved.assert_not_called()
