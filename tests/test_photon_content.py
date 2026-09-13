"""Merged content boundary: Level -> Game -> Y, with no Art module."""

import copy
import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import unquote, urlsplit

from flask import Flask
from test_photon_framework import FakeContext, PROTOTYPES, load


class PhotonContentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.level = load("photon-level")
        cls.game = load("photon-game")
        cls.y = load("laser-tag-y")
        cls.folder = tempfile.TemporaryDirectory()
        cls.game.LOG_PATH = str(Path(cls.folder.name) / "runs.jsonl")
        cls.game._settings = cls.game.SettingsStore(Path(cls.folder.name) / "settings.json")
        cls.modules = {"photon-level": cls.level}
        cls.game.hub_init(FakeContext(cls.modules))
        # Y cannot even discover Level; its only accessible module is Game.
        cls.y.hub_init(FakeContext({"photon-game": cls.game}))

    @classmethod
    def tearDownClass(cls):
        cls.y.hub_stop()
        cls.game.hub_stop()
        cls.folder.cleanup()

    def tearDown(self):
        self.modules["photon-level"] = self.level
        self.game.apply_command({"action": "reset"})

    def test_level_serves_every_fingerprinted_asset_and_editor_uses_same_files(self):
        app = Flask("merged-content-files")
        app.register_blueprint(self.level.bp, url_prefix="/p/photon-level")
        output = self.level.runtime_bundle()["presentation"]
        root = Path(self.level.ASSET_ROOT)
        with app.test_client() as client:
            for key, relative in output["assets"].items():
                with client.get(output["base"] + "/" + relative,
                                environ_overrides={"SCRIPT_NAME": "/s/gamemaster"}) as response:
                    self.assertEqual(response.status_code, 200, key)
                    digest = hashlib.sha256(response.data).hexdigest()
                    self.assertEqual(urlsplit(relative).query, "v=" + digest)
                    self.assertIn("no-cache", response.headers["Cache-Control"])
                    self.assertEqual(response.data, (root / unquote(urlsplit(relative).path)).read_bytes())
            with client.get("/p/photon-level/api/assets") as response:
                self.assertEqual(response.get_json(), output)
            with client.get("/p/photon-level/art") as response:
                self.assertEqual(response.status_code, 200)
                self.assertIn(b"api/assets", response.data)
        editor = self.level.editor_snapshot()
        for key, path in editor["assets"].items():
            runtime_key = key if key.startswith("marker/") else "map/" + key
            self.assertEqual(unquote(urlsplit(output["assets"][runtime_key]).path), path)

    def test_asset_edits_and_missing_files_update_revision_and_recover(self):
        import level_assets
        with tempfile.TemporaryDirectory() as folder, patch.object(
            level_assets, "runtime_asset_paths", return_value={"test/image": "image.svg"}
        ):
            file = Path(folder) / "image.svg"
            file.write_text("first image")
            first = level_assets.asset_snapshot(folder, {})
            self.assertEqual(first, level_assets.asset_snapshot(folder, {}))
            file.write_text("other image")
            second = level_assets.asset_snapshot(folder, {})
            self.assertNotEqual(first["revision"], second["revision"])
            self.assertNotEqual(first["assets"], second["assets"])
            file.unlink()
            missing = level_assets.asset_snapshot(folder, {})
            self.assertEqual(missing["status"], "unavailable")
            self.assertIn("test/image", missing["error"])
            file.write_text("first image")
            self.assertEqual(first, level_assets.asset_snapshot(folder, {}))

    def test_y_only_needs_game_and_receives_content_in_state_commands_and_sse(self):
        app = Flask("content-through-game")
        app.register_blueprint(self.y.bp, url_prefix="/p/laser-tag-y")
        expected = self.level.presentation_assets()
        with app.test_client() as client:
            state = client.get("/p/laser-tag-y/api/state").get_json()
            self.assertEqual(state["presentation"], expected)
            command = client.post("/p/laser-tag-y/api/command", json={"action": "reset"},
                                  environ_overrides={"hhh.roles": {"gamemaster"}}).get_json()
            self.assertEqual(command["output"]["presentation"], expected)
            with client.get("/p/laser-tag-y/api/events", buffered=False) as response:
                frame = next(response.response).decode()
                output = json.loads(frame.split("data: ", 1)[1].split("\n", 1)[0])
                self.assertEqual(output["presentation"], expected)

    def test_missing_malformed_or_incompatible_art_does_not_stop_simulation(self):
        bundle = self.level.runtime_bundle()
        good = bundle["presentation"]
        cases = [None, {**good, "version": 2}, {**good, "version": True},
                 {**good, "base": "//other-host/assets"},
                 {**good, "base": "http://[invalid"},
                 {**good, "assets": {"test": "../outside.png"}},
                 {**good, "assets": {"test": "https://other-host/image.png"}}]
        for presentation in cases:
            with self.subTest(presentation=presentation):
                self.modules["photon-level"] = SimpleNamespace(runtime_bundle=lambda: {
                    **bundle, "presentation": presentation,
                })
                output = self.game.game_snapshot()
                self.assertEqual(output["status"], "ready")
                self.assertEqual(output["inputs"]["level"]["status"], "ready")
                self.assertEqual(output["presentation"]["status"], "unavailable")
                self.assertTrue(output["presentation"]["error"])
        self.game.apply_command({"action": "start", "virtual_play": True})
        self.assertEqual(self.game.game_snapshot()["phase"], "running")

    def test_art_only_change_does_not_replace_engine_or_active_run(self):
        bundle = self.level.runtime_bundle()
        self.game.apply_command({"action": "start", "virtual_play": True})
        engine = self.game._engine
        run_id = self.game.game_snapshot()["run_id"]
        updated = copy.deepcopy(bundle)
        updated["presentation"]["revision"] = "new-art-only-revision"
        updated["presentation"]["assets"]["marker/38"] += "&test=updated"
        self.modules["photon-level"] = SimpleNamespace(runtime_bundle=lambda: updated)
        output = self.game.game_snapshot()
        self.assertIs(engine, self.game._engine)
        self.assertEqual(run_id, output["run_id"])
        self.assertEqual(output["phase"], "running")
        self.assertEqual(output["presentation"], updated["presentation"])
        self.assertEqual(bundle["runtime"]["layout_revision"], output["level_revision"])

    def test_disabling_level_clears_content_without_breaking_game_settings(self):
        self.modules.pop("photon-level")
        output = self.game.game_snapshot()
        self.assertEqual(output["presentation"]["status"], "unavailable")
        self.assertEqual(output["presentation"]["assets"], {})
        self.assertEqual(output["configuration"]["status"], "ready")

    def test_standalone_art_is_not_discoverable_and_y_has_no_art_lookup(self):
        self.assertFalse((PROTOTYPES / "photon-art/prototype.py").exists())
        for file in ("prototype.py", "index.html", "screen.html"):
            source = (PROTOTYPES / "laser-tag-y" / file).read_text()
            self.assertNotIn('"photon-art"', source)
            if file.endswith("html"):
                self.assertNotIn("/api/art", source)
                self.assertIn("sandboxRoot:ROOT", source)

    @unittest.skipUnless(shutil.which("node"), "Node.js is required for renderer checks")
    def test_renderer_refreshes_assets_from_game_at_unchanged_geometry_revision(self):
        script = Path(__file__).with_name("photon_content_renderer.cjs")
        result = subprocess.run(["node", str(script)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    @unittest.skipUnless(shutil.which("node"), "Node.js is required for renderer checks")
    def test_fps_monitor_measures_draws_and_resets_after_hidden_tabs(self):
        script = Path(__file__).with_name("photon_fps_renderer.cjs")
        result = subprocess.run(["node", str(script)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
