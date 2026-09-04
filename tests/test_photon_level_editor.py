"""Run: .venv/bin/python -m unittest discover -s tests -p test_photon_level_editor.py"""

import copy
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "sandboxes/gamemaster/prototypes/photon-level"


class PhotonLevelEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path[:0] = [str(ROOT / "hub"), str(MODULE)]
        try:
            spec = importlib.util.spec_from_file_location("test_level_editor", MODULE / "prototype.py")
            cls.level = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.level)
            from level_layout import apply_socket_layout
            cls.apply_layout = staticmethod(apply_socket_layout)
        finally:
            del sys.path[:2]
        cls.app = Flask("isolated-level-editor-test")
        cls.app.register_blueprint(cls.level.bp, url_prefix="/s/gamemaster/p/photon-level")
        cls.prefix = "/s/gamemaster/p/photon-level"

    def test_preview_is_local_complete_and_does_not_change_public_outputs(self):
        before = self.level.runtime_bundle()
        with self.app.test_client() as client:
            response = client.get(self.prefix + "/api/editor")
            body = response.get_json()
            self.assertEqual(response.status_code, 200)
            self.assertEqual((body["contract"], body["version"]), ("photon.level.editor", 1))
            self.assertEqual(response.headers["Cache-Control"], "no-store")
            self.assertEqual(body["revision"], before["revision"])
            self.assertEqual(body["level"]["scene"], before["runtime"]["visual_scene"])
            self.assertEqual(len(body["level"]["sockets"]), 16)
            for asset_url in body["assets"].values():
                self.assertTrue(asset_url.startswith(self.prefix + "/assets/"))
                with client.get(asset_url) as image:
                    self.assertEqual(image.status_code, 200, asset_url)
                    self.assertTrue(image.data.startswith(b"\x89PNG"))
            for page in ("/", "/level-editor.js"):
                with client.get(self.prefix + page) as result:
                    self.assertEqual(result.status_code, 200)
        self.assertEqual(self.level.runtime_bundle(), before)
        self.assertNotIn("image_path", json.dumps(before))
        source = (MODULE / "level-editor.js").read_text()
        self.assertNotIn("window.confirm", source)
        self.assertIn("confirmReload.hidden = false", source)
        for forbidden in ("photon-game", "photon-art", "laser-tag", ".tmj", ".tsj", "aruco_optical_center_v"):
            self.assertNotIn(forbidden, source)

    def test_local_markers_decode_to_their_declared_ids(self):
        import cv2

        for marker_id in (38, *range(40, 56)):
            image = cv2.imread(str(MODULE / f"assets/aruco/{marker_id}.png"), cv2.IMREAD_GRAYSCALE)
            dictionary = cv2.aruco.getPredefinedDictionary(
                cv2.aruco.DICT_4X4_50 if marker_id <= 49 else cv2.aruco.DICT_4X4_100
            )
            _, ids, _ = cv2.aruco.ArucoDetector(dictionary).detectMarkers(image)
            self.assertIsNotNone(ids, marker_id)
            self.assertEqual(ids.flatten().tolist(), [marker_id])

    def test_missing_or_outside_assets_fail_locally_and_explicitly(self):
        before = self.level.runtime_bundle()
        alignments, catalog = self.level._tileset_catalog(Path(self.level.MAP_PATH), self.level._raw_map)
        used_id = next(item["asset_id"] for layer in before["runtime"]["visual_scene"]["layers"]
                       for item in layer["items"] if item["kind"] == "sprite")
        bad_catalog = copy.deepcopy(catalog)
        for item in bad_catalog.values():
            if item["asset_id"] == used_id:
                item["image_path"] = Path("/tmp/not-a-level-owned-asset.png")
        with patch.object(self.level, "_tileset_catalog", return_value=(alignments, bad_catalog)):
            with self.app.test_client() as client:
                result = client.get(self.prefix + "/api/editor")
            self.assertEqual(result.status_code, 503)
            self.assertEqual(result.get_json()["status"], "unavailable")
            self.assertIn("preview asset unavailable", result.get_json()["error"])
        self.assertEqual(self.level.runtime_bundle(), before)

    def test_source_errors_do_not_return_an_old_preview(self):
        with patch.object(self.level, "_load_error", "invalid authored map"):
            with self.app.test_client() as client:
                result = client.get(self.prefix + "/api/editor")
            self.assertEqual(result.status_code, 503)
            self.assertEqual(result.get_json()["error"], "invalid authored map")
            self.assertNotIn("level", result.get_json())

    def test_browser_marker_resize_and_move_match_the_server_parser(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node is needed for the editor geometry smoke test")
        editor = self.level.editor_snapshot()
        cases = []
        with tempfile.TemporaryDirectory() as folder:
            for size in (96, 160, 208):
                sockets = [{"socket_id": s["socket_id"], "x": int(s["x"]) + 6,
                            "y": int(s["y"]) - 4, "size": size} for s in editor["level"]["sockets"]]
                candidate = self.apply_layout(self.level._raw_map, sockets)
                for reference in candidate["tilesets"]:
                    reference["source"] = str((Path(self.level.MAP_PATH).parent / reference["source"]).resolve())
                path = Path(folder) / "candidate.tmj"
                path.write_text(json.dumps(candidate))
                parsed = self.level.parse_tiled_level(path)
                for original in editor["level"]["sockets"]:
                    expected = parsed["sockets"][original["socket_id"]]
                    cases.append({"original": original, "edited": expected})
        script = """
const assert = require('node:assert/strict');
const view = require(process.argv[1]);
const cases = JSON.parse(process.argv[2]);
for (const {original, edited} of cases) {
  const marker = view.markerForSocket(edited, original);
  assert.ok(Math.abs(marker.x - edited.marker_x) < 1e-9);
  assert.ok(Math.abs(marker.y - edited.marker_y) < 1e-9);
  assert.equal(marker.size, edited.marker_size);
}
assert.deepEqual(view.mapPoint(524, 330, {left: 100, top: 90, width: 848, height: 480}, 1696, 960), {x: 848, y: 480});
const calls = [];
const ctx = Object.fromEntries(['save', 'restore', 'translate', 'rotate', 'drawImage'].map(name => [name, (...args) => calls.push([name, ...args])]));
view.drawSceneItem(ctx, {kind: 'sprite', asset_id: 'road', origin_x: 12, origin_y: 34, rotation_degrees: 90, draw_x: -80, draw_y: -80, width: 160, height: 160}, new Map([['road', 'image']]));
assert.deepEqual(calls, [['save'], ['translate', 12, 34], ['rotate', Math.PI/2], ['drawImage', 'image', -80, -80, 160, 160], ['restore']]);
calls.length = 0;
view.drawSceneItem(ctx, {kind: 'sprite', asset_id: 'road', origin_x: 0, origin_y: 0, draw_x: 0, draw_y: 0, width: 160, height: 160, source: [10, 20, 320, 320]}, new Map([['road', 'image']]));
assert.deepEqual(calls[3], ['drawImage', 'image', 10, 20, 320, 320, 0, 0, 160, 160]);
"""
        result = subprocess.run([node, "-e", script, str(MODULE / "level-editor.js"), json.dumps(cases)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_save_still_requires_auth_and_rejects_invalid_or_stale_layout(self):
        original = self.level.level_snapshot()
        sockets = [{k: s[k] for k in ("socket_id", "x", "y", "size")} for s in original["level"]["sockets"]]
        with self.app.test_client() as client:
            denied = client.post(self.prefix + "/api/layout", json={"sockets": sockets})
            invalid = client.post(self.prefix + "/api/layout", json={"sockets": []}, environ_overrides={"hhh.roles": {"gamemaster"}})
            stale = client.post(self.prefix + "/api/layout", json={"sockets": sockets, "expected_revision": original["revision"] - 1}, environ_overrides={"hhh.roles": {"gamemaster"}})
        self.assertEqual((denied.status_code, invalid.status_code, stale.status_code), (403, 400, 409))
        self.assertEqual(self.level.level_snapshot(), original)


if __name__ == "__main__":
    unittest.main()
