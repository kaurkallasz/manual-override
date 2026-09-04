"""Adjustable diagnostic thresholds, with fixed game-facing freshness gates."""

import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask
from test_photon_framework import FakeContext, load
from test_photon_board_tracking import HardwareFixture, arm, tag, calibration
from board_tracking import BoardTracker, DEFAULT_SETTINGS, distance, validate_settings
from tracking_output import CalibrationProjection


class ThresholdTests(unittest.TestCase):
    def test_original_defaults_and_distance_edges_are_unchanged(self):
        self.assertEqual(DEFAULT_SETTINGS, {"near_xy_mm": 90, "near_z_mm": 60, "unique_margin_mm": 20, "stale_s": 1.5})
        self.assertTrue(distance([0, 0, 0], [90, 0], 60)["near"])
        self.assertFalse(distance([0, 0, 0], [90.1, 0], 60)["near"])
        self.assertFalse(distance([0, 0, 0], [90, 0], 60.1)["near"])

    def test_xy_z_and_meter_fill_use_configured_values(self):
        tight = distance([0, 0, 0], [100, 0], 70)
        loose = distance([0, 0, 0], [100, 0], 70, {**DEFAULT_SETTINGS, "near_xy_mm": 120, "near_z_mm": 80})
        self.assertFalse(tight["near"])
        self.assertTrue(loose["near"])
        self.assertGreater(loose["fill"], tight["fill"])
        self.assertFalse(distance([0, 0, 0], [1, 0], None)["near"])

    def sample(self, settings, *, second=.34, age=0):
        tracker = BoardTracker(settings)
        tags = [tag(100, .32, .3), tag(101, second, .3)]
        arms = {"green": arm([150, 150, 0], now=100-age)}
        runtime = {"status": "ready", "source": "camera", "frame_at": 100-age,
                   "detections": tags, "visible_ids": [100, 101], "arms": arms}
        return tracker.update(runtime, CalibrationProjection(calibration()).project(tags, arms), None, 100)

    def test_unique_margin_is_configurable_but_exact_ties_stay_ambiguous(self):
        self.assertTrue(self.sample(DEFAULT_SETTINGS)["arms"]["green"]["ambiguous"])
        changed = {**DEFAULT_SETTINGS, "unique_margin_mm": 5}
        self.assertEqual(self.sample(changed)["arms"]["green"]["considered_tag"], 100)
        tied = self.sample({**DEFAULT_SETTINGS, "unique_margin_mm": 0}, second=.32)
        self.assertTrue(tied["arms"]["green"]["ambiguous"])
        self.assertIsNone(tied["arms"]["green"]["considered_tag"])

    def test_diagnostic_frame_and_arm_freshness_use_custom_timeout(self):
        self.assertEqual(self.sample(DEFAULT_SETTINGS, age=2)["status"], "unavailable")
        self.assertEqual(self.sample({**DEFAULT_SETTINGS, "stale_s": 3}, age=2)["status"], "ready")
        self.assertEqual(self.sample({**DEFAULT_SETTINGS, "stale_s": .5}, age=.6)["status"], "unavailable")

    def test_settings_reject_non_numbers_nonfinite_out_of_range_and_unknown_keys(self):
        invalid = [None, [], {}, {**DEFAULT_SETTINGS, "extra": 1}]
        for key in DEFAULT_SETTINGS:
            invalid += [{**DEFAULT_SETTINGS, key: value} for value in (True, "90", None, float("nan"), float("inf"), -1, 10001)]
        invalid += [{**DEFAULT_SETTINGS, key: 0} for key in ("near_xy_mm", "near_z_mm", "stale_s")]
        for values in invalid:
            with self.subTest(values=values), self.assertRaises(ValueError):
                validate_settings(values)


class SettingsIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.board = load("photon-board")
        self.board.SETTINGS_PATH = str(Path(self.folder.name) / "data/tracking-settings.json")
        self.fixture = HardwareFixture()
        self.context = FakeContext(self.fixture.modules())
        self.board.hub_init(self.context)
        self.app = Flask("board-settings-tests")
        self.app.register_blueprint(self.board.bp, url_prefix="/p/photon-board")

    def tearDown(self):
        self.board.hub_stop()
        self.folder.cleanup()

    def test_first_use_keeps_defaults_without_creating_a_file(self):
        snapshot = self.board.settings_snapshot()
        self.assertEqual(snapshot["settings"], DEFAULT_SETTINGS)
        self.assertEqual(snapshot["defaults"], DEFAULT_SETTINGS)
        self.assertEqual(snapshot["status"], "ready")
        self.assertFalse(Path(self.board.SETTINGS_PATH).exists())
        self.assertEqual(self.board.tracking_snapshot()["configuration"], snapshot)

    def test_settings_are_role_checked_atomic_persisted_and_resettable(self):
        changed = {**DEFAULT_SETTINGS, "near_xy_mm": 110, "near_z_mm": 80, "unique_margin_mm": 25, "stale_s": 2}
        with self.app.test_client() as client:
            url = "/p/photon-board/api/settings"
            self.assertEqual(client.get(url).status_code, 200)
            self.assertEqual(client.post(url, json={"settings": changed}).status_code, 403)
            self.assertFalse(Path(self.board.SETTINGS_PATH).exists())
            auth = {"hhh.roles": {"gamemaster"}}
            response = client.post(url, json={"settings": changed}, environ_overrides=auth)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json()["output"]["settings"], changed)
            original_bytes = Path(self.board.SETTINGS_PATH).read_bytes()
            self.assertEqual(client.post(url, json={"settings": {"near_xy_mm": 1}}, environ_overrides=auth).status_code, 400)
            self.assertEqual(Path(self.board.SETTINGS_PATH).read_bytes(), original_bytes)
            self.board.hub_init(self.context)
            self.assertEqual(self.board.settings_snapshot()["settings"], changed)
            self.assertEqual(self.board.tracking_snapshot()["limits"]["near_xy_mm"], 110)
            response = client.post(url, json={"settings": DEFAULT_SETTINGS}, environ_overrides=auth)
            self.assertEqual(response.status_code, 200)
        self.assertEqual(self.board.settings_snapshot()["defaults"], DEFAULT_SETTINGS)
        self.assertEqual(json.loads(Path(self.board.SETTINGS_PATH).read_text())["settings"], DEFAULT_SETTINGS)

    def test_failed_save_leaves_active_values_and_file_intact(self):
        self.board.update_settings(DEFAULT_SETTINGS)
        before = Path(self.board.SETTINGS_PATH).read_bytes()
        with patch.object(self.board.os, "replace", side_effect=OSError("disk unavailable")):
            with self.assertRaises(OSError):
                self.board.update_settings({**DEFAULT_SETTINGS, "near_xy_mm": 200})
        self.assertEqual(Path(self.board.SETTINGS_PATH).read_bytes(), before)
        self.assertEqual(self.board.settings_snapshot()["settings"], DEFAULT_SETTINGS)
        self.assertIn("previous values remain active", self.board.settings_snapshot()["error"])
        self.assertEqual(len(list(Path(self.board.SETTINGS_PATH).parent.iterdir())), 1)

    def test_bad_saved_file_is_reported_without_silent_overwrite(self):
        path = Path(self.board.SETTINGS_PATH)
        path.parent.mkdir(parents=True)
        path.write_text("not JSON")
        self.board.hub_init(self.context)
        self.assertEqual(self.board.settings_snapshot()["status"], "unavailable")
        self.assertEqual(self.board.settings_snapshot()["settings"], DEFAULT_SETTINGS)
        self.assertIn("using defaults", self.board.settings_snapshot()["error"])
        self.assertEqual(path.read_text(), "not JSON")

    def age_sources(self, age):
        camera, relay = self.fixture.tag_snapshot, self.fixture.arms_snapshot
        def aged_camera():
            value = camera()
            value["frame_at"] -= age
            value["observed_at"] -= age
            return value
        def aged_relay():
            value = relay()
            value["observed_at"] -= age
            for arm in value["arms"].values():
                arm["feedback_at"] -= age
            return value
        self.fixture.tag_snapshot, self.fixture.arms_snapshot = aged_camera, aged_relay

    def test_longer_diagnostic_timeout_cannot_loosen_game_freshness(self):
        self.age_sources(2)
        self.board.update_settings({**DEFAULT_SETTINGS, "stale_s": 3})
        self.board._sample_tracking()
        tracking = self.board.tracking_snapshot()
        self.assertEqual(tracking["status"], "ready")
        self.assertEqual(tracking["arms"]["green"]["status"], "ready")
        runtime = self.board.runtime_observation()
        self.assertEqual(runtime["status"], "unavailable")
        self.assertFalse(runtime["tags"])
        self.assertFalse(runtime["arms"])
        self.assertNotIn("_source_stamps", runtime)

    def test_shorter_diagnostic_timeout_does_not_change_game_projection(self):
        self.age_sources(.8)
        self.board.update_settings({**DEFAULT_SETTINGS, "stale_s": .5})
        self.board._sample_tracking()
        self.assertEqual(self.board.tracking_snapshot()["status"], "unavailable")
        self.assertEqual(self.board.runtime_observation()["status"], "ready")
        self.assertTrue(self.board.runtime_observation()["tags"])

    def test_settings_clear_old_inference_without_reading_hardware(self):
        with self.board._sample_lock:
            old = self.board._tracker
            old.bound["green"] = {"id": 100, "at": time.time(), "release_at": None}
            with patch.object(self.fixture, "tag_snapshot", side_effect=AssertionError("unexpected sensor read")):
                self.board.update_settings({**DEFAULT_SETTINGS, "near_xy_mm": 120})
                self.assertFalse(self.board._tracker.bound)
                self.assertFalse(self.board.tracking_snapshot()["arms"])
                self.assertEqual(self.board.runtime_observation()["status"], "ready")
            self.board._sample_tracking()
            self.assertEqual(self.board.tracking_snapshot()["limits"]["near_xy_mm"], 120)

    def test_settings_remain_editable_without_any_input_modules(self):
        self.board.hub_init(FakeContext({}))
        self.board.update_settings({**DEFAULT_SETTINGS, "near_z_mm": 70})
        snapshot = self.board.tracking_snapshot()
        self.assertEqual(snapshot["status"], "unavailable")
        self.assertEqual(snapshot["configuration"]["settings"]["near_z_mm"], 70)
