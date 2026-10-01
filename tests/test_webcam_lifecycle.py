"""Camera startup/replacement smoke tests; no hardware is opened.

Run: .venv/bin/python -m unittest discover -s tests -p test_webcam_lifecycle.py
"""
import concurrent.futures
import threading
import time
import unittest
from unittest import mock

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
