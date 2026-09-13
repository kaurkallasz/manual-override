"""Scheduling, shared SSE delivery, and revision-cache correctness checks."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest
from unittest import mock

from test_photon_framework import load, FakeContext
from live import LiveState


def decode(frame):
    return json.loads(frame.split("data: ", 1)[1])


class PhotonPerformanceTests(unittest.TestCase):
    def test_renderer_cadence_quality_recovery_and_incremental_state(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node is unavailable")
        result = subprocess.run([node, str(Path(__file__).with_name("photon_performance_renderer.cjs"))], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_shared_sse_prepares_once_and_reconnects_with_complete_state(self):
        live = LiveState()
        value = {"level": {"revision": 1}, "enemies": [1]}
        snapshot = mock.Mock(side_effect=lambda: value)
        responses = [live.stream(snapshot, shared=True, static_fields=("level",)) for _ in range(2)]
        a, b = [iter(response.response) for response in responses]
        try:
            first = next(a)
            self.assertEqual(first, next(b))
            self.assertEqual(snapshot.call_count, 1)
            self.assertNotIn("event: update", first)
            value = {"level": {"revision": 1}, "enemies": [1, 2]}
            live.bump()
            patch = next(a)
            self.assertEqual(patch, next(b))
            self.assertIn("event: update", patch)
            self.assertEqual(decode(patch), {"enemies": [1, 2]})
            self.assertEqual(snapshot.call_count, 2)
            reconnect = live.stream(snapshot, shared=True, static_fields=("level",))
            try:
                full = next(iter(reconnect.response))
                self.assertEqual(decode(full), value)
                self.assertNotIn("event: update", full)
                self.assertEqual(snapshot.call_count, 2)
            finally:
                reconnect.close()
            value = {"level": None, "enemies": []}
            live.bump()
            self.assertEqual(decode(next(a)), value)
            self.assertEqual(decode(next(b)), value)
        finally:
            for response in responses:
                response.close()

    def test_shared_sse_rechecks_health_on_timeout_and_keeps_default_format(self):
        live = LiveState()
        snapshot = mock.Mock(return_value={"ready": True})
        with mock.patch("live.time.monotonic", return_value=0):
            first = live.stream(snapshot, interval=0.001, shared=True)
            iterator = iter(first.response)
            self.assertTrue(next(iterator).startswith("data: "))
        with mock.patch("live.time.monotonic", return_value=1):
            snapshot.return_value = {"ready": False}
            self.assertEqual(decode(next(iterator)), {"ready": False})
            self.assertEqual(snapshot.call_count, 2)
            live.bump()
            self.assertEqual(next(iterator), ": ping\n\n")
        first.close()

    def test_level_status_is_lightweight_isolated_and_fails_closed(self):
        level = load("photon-level")
        original = level.runtime_bundle()
        with mock.patch.object(level, "runtime_bundle", side_effect=AssertionError("unnecessary full copy")):
            status = level.runtime_status()
            self.assertEqual(status["revision"], original["revision"])
            self.assertNotIn("runtime", status)
            status["presentation"]["assets"].clear()
            self.assertTrue(level.runtime_status()["presentation"]["assets"])
            with mock.patch.object(level, "_load_error", "invalid level"):
                self.assertEqual(level.runtime_status()["status"], "unavailable")

    def test_game_fast_read_preserves_contract_checks_and_disabled_inputs(self):
        level, game = load("photon-level"), load("photon-game")
        bundle = level.runtime_bundle()
        game._install_level(bundle)
        modules = {"photon-level": level}
        game._hub_ctx = FakeContext(modules)  # no background engine or hardware
        with mock.patch.object(level, "runtime_bundle", side_effect=AssertionError("unnecessary full copy")):
            self.assertTrue(game._sync_level())
        with mock.patch.object(level, "runtime_status", return_value={"contract": "photon.level.runtime", "version": True, "revision": 1, "status": "ready"}):
            self.assertFalse(game._sync_level())
        modules.clear()
        self.assertFalse(game._sync_level())
        self.assertEqual(game._inputs["level"]["status"], "unavailable")
        self.assertEqual(game._presentation["status"], "unavailable")

    def test_art_changes_are_rechecked_and_level_revision_changes_read_a_bundle(self):
        level, game = load("photon-level"), load("photon-game")
        bundle = level.runtime_bundle()
        game._install_level(bundle)
        game._hub_ctx = FakeContext({"photon-level": level})
        with mock.patch.object(level.time, "monotonic", return_value=100):
            level._runtime_asset_cache = None
            before = level.runtime_status()
        new_art = {**before["presentation"], "revision": "updated-art"}
        with mock.patch.object(level, "presentation_assets", return_value=new_art):
            with mock.patch.object(level.time, "monotonic", return_value=100.1):
                self.assertEqual(level.runtime_status()["presentation"], before["presentation"])
            with mock.patch.object(level.time, "monotonic", return_value=100.26):
                self.assertTrue(game._sync_level())
                self.assertEqual(game._presentation["revision"], "updated-art")
        new_revision = bundle["revision"] + 1
        runtime = {**bundle["runtime"], "layout_revision": new_revision}
        with mock.patch.object(level, "runtime_status", return_value={**before, "revision": new_revision}):
            with mock.patch.object(level, "runtime_bundle", return_value={**bundle, "revision": new_revision, "runtime": runtime}) as read:
                self.assertTrue(game._sync_level())
                read.assert_called_once()
                self.assertEqual(game._engine.level.layout_revision, new_revision)

    def test_y_inline_scripts_parse(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node is unavailable")
        root = Path(__file__).resolve().parents[1] / "sandboxes/gamemaster/prototypes/laser-tag-y"
        script = "const fs=require('fs'),vm=require('vm');for(const path of process.argv.slice(1)){for(const [,js] of fs.readFileSync(path,'utf8').matchAll(/<script>([\\s\\S]*?)<\\/script>/g))new vm.Script(js)}"
        result = subprocess.run([node, "-e", script, str(root / "index.html"), str(root / "screen.html")], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
