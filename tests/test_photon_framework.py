"""Small contract and lifecycle tests for the modular Photon vertical slice."""

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit


ROOT = Path(__file__).resolve().parents[1]
HUB_DIR = ROOT / "hub"
PROTOTYPES = ROOT / "sandboxes/gamemaster/prototypes"
sys.path.insert(0, str(HUB_DIR))
sys.path.insert(0, str(ROOT))

from flask import Flask  # noqa: E402
from hub import AUTH_HEADER, Hub  # noqa: E402


def load(slug):
    path = PROTOTYPES / slug / "prototype.py"
    name = "test_" + slug.replace("-", "_")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    sys.path.insert(0, str(path.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


class FakeContext:
    sandbox = "gamemaster"

    def __init__(self, modules):
        self.modules = modules

    def is_prototype_enabled(self, slug):
        return slug in self.modules

    def get_prototype(self, slug):
        return self.modules.get(slug)


class PhotonContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.level = load("photon-level")
        cls.board = load("photon-board")
        cls.game = load("photon-game")
        cls.presentation = load("laser-tag-y")
        cls.log_folder = tempfile.TemporaryDirectory()
        cls.game.LOG_PATH = str(Path(cls.log_folder.name) / "runs.jsonl")
        cls.game._settings = cls.game.SettingsStore(
            Path(cls.log_folder.name) / "settings.json"
        )
        cls.board.hub_init(FakeContext({}))
        level = cls.level.level_snapshot()["level"]
        first = level["sockets"][0]
        cls.board.set_simulation(True, [{
            "id": 100,
            "nx": first["x"] / level["width"],
            "ny": first["y"] / level["height"],
        }])
        modules = {
            "photon-level": cls.level,
            "photon-board": cls.board,
            "photon-game": cls.game,
        }
        cls.modules = modules
        cls.game.hub_init(FakeContext(modules))
        cls.presentation.hub_init(FakeContext(modules))

    @classmethod
    def tearDownClass(cls):
        cls.presentation.hub_stop()
        cls.game.hub_stop()
        cls.board.hub_stop()
        cls.log_folder.cleanup()

    def test_each_output_has_one_named_integer_version_contract(self):
        outputs = [
            self.level.level_snapshot(), self.board.board_snapshot(),
            self.game.game_snapshot(), self.level.presentation_assets(),
        ]
        for output in outputs:
            self.assertIsInstance(output["contract"], str)
            self.assertIsInstance(output["version"], int)
            self.assertEqual(output["status"], "ready")

    def test_invalid_level_input_is_rejected_without_mutating_output(self):
        before = self.level.level_snapshot()
        with self.assertRaises(ValueError):
            self.level.update_layout([], expected_revision=before["revision"])
        self.assertEqual(self.level.level_snapshot(), before)

    def test_game_consumes_contracts_and_simulates_without_the_presenter(self):
        self.game.apply_command({"action": "reset"})
        self.game.apply_command({"action": "set_virtual", "virtual_play": True})
        socket_id = self.game.game_snapshot()["level"]["sockets"][0]["id"]
        self.game.apply_command({
            "action": "place", "atom_tag_id": 100, "socket_id": socket_id,
        })
        self.game.apply_command({
            "action": "configure", "settings": {"wave_count": 1},
        })
        self.game.apply_command({"action": "start", "virtual_play": True})
        deadline = time.time() + 1.5
        snapshot = self.game.game_snapshot()
        while time.time() < deadline and not (snapshot["wave"] and snapshot["towers"]):
            time.sleep(0.05)
            snapshot = self.game.game_snapshot()
        self.assertEqual(snapshot["wave"], 1)
        self.assertEqual(snapshot["towers"][0]["atom_tag_id"], 100)
        self.assertEqual(snapshot["level"]["name"], "z_pixel_first_map_01")

    def test_presentation_returns_game_output_and_art_manifest(self):
        app = Flask("photon-presentation-test")
        app.register_blueprint(self.presentation.bp, url_prefix="/p/laser-tag-y")
        with app.test_client() as client:
            response = client.get("/p/laser-tag-y/api/state")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json()["contract"], "photon.game")
            self.assertEqual(
                response.get_json()["configuration"]["contract"],
                "photon.game.settings",
            )
            art = client.get("/p/laser-tag-y/api/art")
            self.assertEqual(art.get_json()["contract"], "photon.level.assets")
            self.assertEqual(response.get_json()["presentation"], self.level.presentation_assets())

    def test_changed_sibling_contract_fails_locally_not_system_wide(self):
        class ChangedGame:
            @staticmethod
            def game_snapshot():
                return {"contract": "photon.game", "version": 3, "status": "ready"}

        self.presentation.hub_init(FakeContext({
            "photon-game": ChangedGame(),
        }))
        try:
            app = Flask("photon-contract-mismatch-test")
            app.register_blueprint(self.presentation.bp, url_prefix="/p/laser-tag-y")
            with app.test_client() as client:
                state = client.get("/p/laser-tag-y/api/state")
                art = client.get("/p/laser-tag-y/api/art")
            self.assertEqual(state.status_code, 503)
            self.assertIn("contract mismatch", state.get_json()["error"])
            self.assertEqual(art.status_code, 503)
        finally:
            self.presentation.hub_init(FakeContext(self.modules))

    def test_y_serves_separate_gamemaster_and_external_presentations(self):
        app = Flask("laser-tag-y-pages-test")
        app.register_blueprint(self.presentation.bp, url_prefix="/p/laser-tag-y")
        app.register_blueprint(self.game.bp, url_prefix="/p/photon-game")
        with app.test_client() as client:
            game = client.get("/p/laser-tag-y/game")
            shortcut = client.get("/p/laser-tag-y/settings")
            self.assertEqual(shortcut.status_code, 302)
            self.assertEqual(shortcut.headers["Location"], "/p/photon-game/settings")
            settings = client.get(shortcut.headers["Location"])
            screen = client.get("/p/laser-tag-y/screen")
            renderer = client.get("/p/laser-tag-y/tower-defence-view.js")
        self.assertEqual(
            (game.status_code, settings.status_code, screen.status_code, renderer.status_code),
            (200, 200, 200, 200),
        )
        self.assertIn(b"Tower Defense settings", game.data)
        self.assertIn(b"owned and validated by Photon Game", settings.data)
        self.assertIn(b"photon.game.settings", settings.data)
        self.assertFalse((PROTOTYPES / "laser-tag-y/settings.html").exists())
        self.assertIn(b"Virtual Atom controls", game.data)
        self.assertNotIn(b"Virtual Atom controls", screen.data)
        self.assertIn(b"TowerDefenceView", renderer.data)
        game.close()
        settings.close()
        screen.close()
        renderer.close()

    def test_y_settings_shortcut_checks_game_and_keeps_sandbox_prefix(self):
        app = Flask("settings-shortcut-test")
        app.register_blueprint(self.presentation.bp, url_prefix="/p/laser-tag-y")
        with app.test_client() as client:
            result = client.get("/p/laser-tag-y/settings", environ_overrides={"SCRIPT_NAME": "/s/gamemaster"})
        self.assertEqual(result.headers["Location"], "/s/gamemaster/p/photon-game/settings")

        class IncompatibleGame:
            @staticmethod
            def game_snapshot():
                return {"contract": "photon.game", "version": 999}

        try:
            for modules in ({}, {"photon-game": IncompatibleGame()}):
                self.presentation.hub_init(FakeContext(modules))
                with app.test_client() as client:
                    result = client.get("/p/laser-tag-y/settings")
                self.assertEqual(result.status_code, 503)
                self.assertEqual(result.get_json()["status"], "unavailable")
                self.assertNotIn("Location", result.headers)
        finally:
            self.presentation.hub_init(FakeContext(self.modules))

    def test_y_forwards_operator_intent_without_implementing_commands(self):
        class RecordingGame:
            command = None

            @staticmethod
            def game_snapshot():
                return {
                    "contract": "photon.game", "version": 2,
                    "status": "ready", "phase": "setup",
                }

            @classmethod
            def apply_command(cls, command):
                cls.command = command
                return {**cls.game_snapshot(), "accepted": True}

        self.presentation.hub_init(FakeContext({"photon-game": RecordingGame()}))
        try:
            app = Flask("laser-tag-y-command-test")
            app.register_blueprint(self.presentation.bp, url_prefix="/p/laser-tag-y")
            with app.test_client() as client:
                denied = client.post("/p/laser-tag-y/api/command", json={"action": "pause"})
                accepted = client.post(
                    "/p/laser-tag-y/api/command",
                    json={"action": "aim", "atom_tag_id": 100, "spread": 0.4},
                    environ_overrides={"hhh.roles": {"gamemaster"}},
                )
            self.assertEqual(denied.status_code, 403)
            self.assertEqual(accepted.status_code, 200)
            self.assertEqual(RecordingGame.command, {
                "action": "aim", "atom_tag_id": 100, "spread": 0.4,
            })
        finally:
            self.presentation.hub_init(FakeContext(self.modules))


class LaserTagYExtractionTests(unittest.TestCase):
    def test_y_has_no_level_board_camera_or_editor_runtime_dependency(self):
        module_dir = PROTOTYPES / "laser-tag-y"
        runtime_source = "\n".join(
            (module_dir / name).read_text(encoding="utf-8")
            for name in ("prototype.py", "index.html", "screen.html", "tower-defence-view.js")
        ).lower()
        for forbidden in (
            "photon-level", "photon-board", "webcam", "camera-calibration",
            ".tmj", "layout-edit", "loadlevel", "setsocket",
        ):
            self.assertNotIn(forbidden, runtime_source)
        self.assertNotIn("fetch(", (module_dir / "tower-defence-view.js").read_text(encoding="utf-8"))
        # The diagram may NAME upstream modules/files, but must never read them.
        diagram = (module_dir / "data-flow.js").read_text(encoding="utf-8")
        for forbidden in ("fetch(", "new EventSource", "XMLHttpRequest", "get_prototype", "import("):
            self.assertNotIn(forbidden, diagram)

    def test_y_keeps_z_combat_presentation_and_canvas_fallbacks(self):
        renderer = (PROTOTYPES / "laser-tag-y/tower-defence-view.js").read_text(
            encoding="utf-8"
        )
        for behavior in (
            "drawFlamethrowerPilotFlame", "drawMortarEffects", "drawLightning",
            "drawForceFields", "drawCoreSequence", "drawTowerDestruction",
        ):
            self.assertIn(f"function {behavior}", renderer)
        self.assertIn("Promise.allSettled", renderer)
        self.assertIn('context.fillStyle = "#84c74a"', renderer)

    def test_y_displays_the_authoritative_ring_immunity_countdown(self):
        game_page = (PROTOTYPES / "laser-tag-y/index.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("sequence.field_immunity_remaining_s", game_page)
        self.assertIn("Ring immune ${Math.ceil(immunity)}s", game_page)
        self.assertNotIn("field_immunity_until", game_page)

    def test_y_exposes_synchronized_sliders_and_one_drag_commit(self):
        game_page = (PROTOTYPES / "laser-tag-y/index.html").read_text(
            encoding="utf-8"
        )
        renderer = (PROTOTYPES / "laser-tag-y/tower-defence-view.js").read_text(
            encoding="utf-8"
        )
        self.assertIn('id="aimDirection"', game_page)
        self.assertIn('id="aimReach"', game_page)
        self.assertIn("function beginAimPointer", game_page)
        self.assertIn("function moveAimPointer", game_page)
        self.assertIn("function finishAimPointer", game_page)
        self.assertIn("setPointerCapture", game_page)
        self.assertIn("else saveAim()", game_page)
        self.assertIn("function drawAimHandle", renderer)
        self.assertIn("function clearTowerAimPreview", renderer)
        self.assertIn("function aimFromPoint", renderer)

    def test_y_drag_geometry_matches_photon_game_aim_semantics(self):
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node.js is required for renderer geometry verification")
        game_module = load("photon-game")
        bundle = load("photon-level").runtime_bundle()
        engine = game_module.DefenseEngine(bundle["runtime"], bundle["waves"])
        controls = {
            tower_type: engine._tower_targeting({
                "tower_type": tower_type, "x": 100, "y": 100,
                "aim_angle": 0, "aim_spread": .5, "aruco_id": 40,
            })["control"]
            for tower_type in (
                "machine_gun", "flamethrower", "mortar", "tesla_coil"
            )
        }
        renderer_path = json.dumps(str(
            PROTOTYPES / "laser-tag-y/tower-defence-view.js"
        ))
        script = f"""
require({renderer_path});
const geometry = globalThis.TowerDefenceView.geometry;
const controls = {json.dumps(controls)};
const close = (actual, expected, label) => {{
  if (Math.abs(actual - expected) > 1e-6) {{
    throw new Error(`${{label}}: expected ${{expected}}, got ${{actual}}`);
  }}
}};
const narrow = geometry.towerAimFromPoint(controls.machine_gun, 100, 100, 460, 100);
close(narrow.angle, 0, 'machine-gun direction');
close(narrow.spread, 0, 'machine-gun narrow spread');
close(narrow.distance, 360, 'machine-gun far distance');
const wide = geometry.towerAimFromPoint(controls.machine_gun, 100, 100, 100, 290);
close(wide.angle, 90, 'machine-gun direction after drag');
close(wide.spread, 1, 'machine-gun wide spread');
close(wide.distance, 190, 'machine-gun near distance');
const mortar = geometry.towerAimFromPoint(controls.mortar, 100, 100, 600, 100);
close(mortar.spread, 1, 'mortar far spread');
close(mortar.distance, 500, 'mortar far distance');
const tesla = geometry.towerAimFromPoint(controls.tesla_coil, 100, 100, 100, 292.5, 33);
close(tesla.angle, 33, 'tesla retains its irrelevant direction');
close(tesla.spread, 0.5, 'tesla reach');
close(tesla.distance, 192.5, 'tesla distance');
const upward = geometry.towerAimFromPoint(controls.flamethrower, 100, 100, 100, -135);
close(upward.angle, 270, 'normalized upward direction');
const aligned = geometry.targetingHandlePoint(
  {{x: 10, y: 20}},
  {{angle: Math.PI / 2, range: 50, target_x: 999, target_y: 999}},
);
close(aligned.x, 10, 'handle uses displayed turret x');
close(aligned.y, 70, 'handle uses displayed turret y');
"""
        result = subprocess.run(
            [node, "-e", script], capture_output=True, text=True, check=False
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_y_has_no_weapon_rule_table_and_freezes_visual_age_without_feed(self):
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node.js is required for renderer timing verification")
        renderer = PROTOTYPES / "laser-tag-y/tower-defence-view.js"
        source = renderer.read_text(encoding="utf-8")
        self.assertNotIn("AIM_GEOMETRY", source)
        self.assertNotIn("0.9 + (linkedTurretCount - 1) * 0.1", source)
        script = f"""
require({json.dumps(str(renderer))});
const age = globalThis.TowerDefenceView.geometry.boundedVisualAge;
if (age(1000, 9000, true, 0) !== 0.5) throw Error('live interpolation must be bounded');
if (age(1000, 9000, false, 0.23) !== 0.23) throw Error('disconnected visuals must freeze');
"""
        result = subprocess.run(
            [node, "-e", script], capture_output=True, text=True, check=False
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_photon_level_owns_the_copied_runtime_pack(self):
        manifest = load("photon-level").presentation_assets()
        self.assertEqual((manifest["contract"], manifest["version"]), ("photon.level.assets", 1))
        self.assertTrue(manifest["assets"]["fallback/enemy"].startswith("enemy.svg?v="))
        pack = PROTOTYPES / "photon-level/assets/game-art"
        self.assertTrue((pack / "sprites/enemies-light-orcs-v2/grunt-walk-01.png").is_file())
        self.assertTrue((pack / "z-pixel-v2/normalized/structures/runtime/mortar-base-v1.png").is_file())
        self.assertTrue((pack / "z-pixel-v2/normalized/effects/combat/core-purge-wave-v1.png").is_file())
        self.assertGreaterEqual(len(list(pack.rglob("*.png"))), 60)

    def test_every_scene_and_marker_asset_resolves_inside_photon_level(self):
        import cv2

        art = load("photon-level").presentation_assets()
        level = load("photon-level").runtime_bundle()["runtime"]
        art_root = PROTOTYPES / "photon-level/assets"
        scene_keys = {
            f"map/{item['asset_id']}"
            for layer in level["visual_scene"]["layers"]
            for item in layer["items"]
            if item["kind"] == "sprite"
        }
        self.assertFalse(scene_keys - set(art["assets"]))
        for key in scene_keys:
            self.assertTrue((art_root / unquote(urlsplit(art["assets"][key]).path)).is_file())
        for marker_id in (38, *range(40, 56)):
            marker = cv2.imread(
                str(art_root / urlsplit(art["assets"][f"marker/{marker_id}"]).path),
                cv2.IMREAD_GRAYSCALE,
            )
            dictionary = cv2.aruco.getPredefinedDictionary(
                cv2.aruco.DICT_4X4_50
                if marker_id <= 49 else cv2.aruco.DICT_4X4_100
            )
            _, detected, _ = cv2.aruco.ArucoDetector(dictionary).detectMarkers(marker)
            self.assertEqual(detected.flatten().tolist(), [marker_id])


class PhotonLevelExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.level = load("photon-level")
        cls.z_dir = PROTOTYPES / "laser-tag-z"
        sys.path.insert(0, str(cls.z_dir))
        from photon_defence import ContractLevelModel, DefenseEngine, LevelModel

        cls.ContractLevelModel = ContractLevelModel
        cls.DefenseEngine = DefenseEngine
        cls.LevelModel = LevelModel
        cls.legacy_map = ROOT / "assets/tiled/levels/z-pixel-first-map.tmj"
        cls.legacy_waves = ROOT / "assets/tiled/levels/z-pixel-first-map.waves.json"

    @classmethod
    def tearDownClass(cls):
        sys.path.remove(str(cls.z_dir))

    def test_production_sources_are_owned_inside_photon_level(self):
        module_map = Path(self.level.MAP_PATH)
        module_waves = Path(self.level.WAVE_PATH)
        self.assertTrue(module_map.is_relative_to(PROTOTYPES / "photon-level"))
        self.assertTrue(module_waves.is_relative_to(PROTOTYPES / "photon-level"))
        module_root = PROTOTYPES / "photon-level"
        map_data = json.loads(module_map.read_text(encoding="utf-8"))
        for reference in map_data["tilesets"]:
            tileset = (module_map.parent / reference["source"]).resolve()
            self.assertTrue(tileset.is_relative_to(module_root))
            tileset_data = json.loads(tileset.read_text(encoding="utf-8"))
            for tile in tileset_data.get("tiles", []):
                if not tile.get("image"):
                    continue
                image = (tileset.parent / tile["image"]).resolve()
                self.assertTrue(image.is_relative_to(module_root))
                self.assertTrue(image.is_file())

    def test_runtime_contract_matches_legacy_z_parser(self):
        bundle = self.level.runtime_bundle()
        self.assertEqual(bundle["contract"], "photon.level.runtime")
        self.assertEqual(bundle["version"], 1)
        legacy = self.LevelModel(self.level.MAP_PATH)
        adapted = self.ContractLevelModel(bundle["runtime"])
        self.assertEqual(adapted.layout_revision, legacy.layout_revision)
        self.assertEqual((adapted.width, adapted.height), (legacy.width, legacy.height))
        self.assertEqual(adapted.paths, legacy.paths)
        self.assertEqual(adapted.route_edge_ids, legacy.route_edge_ids)
        self.assertEqual(adapted.socket_by_marker, legacy.socket_by_marker)
        self.assertEqual(adapted.ring_adjacency, legacy.ring_adjacency)
        self.assertEqual(adapted.ring_edges, legacy.ring_edges)
        self.assertEqual(adapted.ring_cycles, legacy.ring_cycles)
        self.assertEqual(adapted.force_field_blockers, legacy.force_field_blockers)
        for socket_id, socket in legacy.sockets.items():
            for key in ("socket_id", "aruco_id", "owner", "x", "y", "size"):
                self.assertEqual(adapted.sockets[socket_id][key], socket[key])

    def test_runtime_projects_the_modular_scene_and_exact_marker_alignment(self):
        runtime = self.level.runtime_bundle()["runtime"]
        scene = runtime["visual_scene"]
        self.assertEqual(
            (scene["contract"], scene["version"]),
            ("photon.visual-scene", 1),
        )
        counts = {
            layer["name"]: len(layer["items"])
            for layer in scene["layers"]
        }
        self.assertEqual(counts, {
            "02 Ground Modules": 18,
            "03 Road Modules": 61,
            "12 Central Square Core": 2,
            "14 Activation Unit Staging": 5,
        })
        serialized = json.dumps(scene).lower()
        self.assertNotIn(".tmj", serialized)
        self.assertNotIn(".tsj", serialized)
        self.assertNotIn("gid", serialized)
        for socket in runtime["sockets"].values():
            expected_distance = 112 / 2 + socket["marker_size"] / 2
            actual_distance = abs(socket["marker_x"] - socket["x"])
            self.assertAlmostEqual(actual_distance, expected_distance, places=5)
        core = runtime["core_visual"]
        self.assertEqual((core["x"], core["y"]), (880.0, 480.0))
        self.assertEqual(core["marker_size"], 116.0)

    def test_z_engine_runs_from_contract_without_level_file_knowledge(self):
        bundle = self.level.runtime_bundle()
        engine = self.DefenseEngine(self.legacy_map, self.legacy_waves)
        contract_level = self.ContractLevelModel(bundle["runtime"])
        engine.reload_level(contract_level, bundle["waves"])
        self.assertIsNone(engine.level.map_path)
        self.assertEqual(engine.level.layout_revision, bundle["revision"])
        self.assertEqual(engine.wave_source, bundle["waves"])
        engine.set_virtual_play(True)
        engine.start({"enemy_count": 1})
        engine.step(0.1)
        self.assertEqual(engine.snapshot()["level_revision"], bundle["revision"])

    def test_tiled_endpoint_rewrites_only_repository_boundary_paths(self):
        app = Flask("photon-level-route-test")
        app.register_blueprint(
            self.level.bp, url_prefix="/p/photon-level",
            name="proto_gamemaster_photon_level",
        )
        with app.test_client() as client:
            response = client.get("/p/photon-level/api/tiled-map")
            source = response.get_json()["tilesets"][0]["source"]
            tileset = client.get(source)
            tileset_data = json.loads(tileset.get_data())
            image_path = urljoin(source, tileset_data["tiles"][0]["image"])
            image = client.get(image_path)
            image.get_data()
            image.close()
            tileset.close()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(source.startswith("/p/photon-level/assets/tiled/tilesets/"))
        self.assertEqual(tileset.status_code, 200)
        self.assertEqual(image.status_code, 200)

    def test_laser_tag_z_adopts_level_output_and_proxies_owned_assets(self):
        z = load("laser-tag-z")
        z.hub_init(FakeContext({"photon-level": self.level}))
        try:
            app = Flask("laser-tag-z-level-contract-test")
            app.register_blueprint(
                self.level.bp, url_prefix="/p/photon-level",
                name="proto_gamemaster_photon_level",
            )
            app.register_blueprint(
                z.bp, url_prefix="/p/laser-tag-z",
                name="proto_gamemaster_laser_tag_z",
            )
            with app.test_client() as client:
                state = client.get("/p/laser-tag-z/api/defence/state")
                level = client.get("/p/laser-tag-z/api/defence/level")
                waves = client.get("/p/laser-tag-z/api/defence/waves")
            self.assertEqual(state.get_json()["level_source"], "photon-level")
            self.assertEqual(state.get_json()["level_input_error"], None)
            self.assertEqual(level.headers["X-Level-Source"], "photon-level")
            self.assertIn("/p/photon-level/assets/", level.get_json()["tilesets"][0]["source"])
            self.assertEqual(waves.headers["X-Level-Source"], "photon-level")
            self.assertEqual(len(waves.get_json()["waves"]), 12)
        finally:
            z.hub_stop()

    def test_incompatible_level_is_contained_and_z_keeps_rollback_state(self):
        class ChangedLevel:
            @staticmethod
            def level_snapshot():
                return {"contract": "photon.level", "version": 3, "status": "ready"}

        z = load("laser-tag-z")
        z.hub_init(FakeContext({"photon-level": ChangedLevel()}))
        try:
            app = Flask("laser-tag-z-level-mismatch-test")
            app.register_blueprint(z.bp, url_prefix="/p/laser-tag-z")
            with app.test_client() as client:
                state = client.get("/p/laser-tag-z/api/defence/state")
                level = client.get("/p/laser-tag-z/api/defence/level")
            self.assertEqual(state.status_code, 200)
            self.assertEqual(state.get_json()["level_source"], "legacy-fallback")
            self.assertIn("contract mismatch", state.get_json()["level_input_error"])
            self.assertEqual(level.status_code, 503)
            self.assertIn("contract mismatch", level.get_json()["error"])
        finally:
            z.hub_stop()


class PhotonBoardExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.board = load("photon-board")
        cls.level = load("photon-level")

    def tearDown(self):
        self.board.hub_stop()

    @staticmethod
    def _production_inputs(*, webcam_version=1, correction_version=1, relay_version=1):
        class Webcam:
            calls = 0

            @classmethod
            def tag_snapshot(cls):
                cls.calls += 1
                tag = {
                    "id": 100, "x": 420, "y": 300,
                    "nx": 0.25, "ny": 0.3125, "rotation": 12.5,
                    "missing": 0.04, "tracked": True,
                    "corners": [[400, 280], [440, 280], [440, 320], [400, 320]],
                }
                return {
                    "contract": "hhh.webcam.tags", "version": webcam_version,
                    "status": "ready", "observed_at": time.time(),
                    "width": 1696, "height": 960,
                    "tags": [tag], "detections": [tag], "visible_ids": [100],
                }

        class Calibration:
            calls = 0

            @classmethod
            def corrected_tag_snapshot(cls, tags, detections):
                cls.calls += 1
                corrected_tags = [dict(tag, nx=0.255, ny=0.31) for tag in tags]
                corrected_detections = [
                    dict(tag, nx=0.255, ny=0.31, ncorners=[
                        [0.24, 0.29], [0.27, 0.29],
                        [0.27, 0.33], [0.24, 0.33],
                    ])
                    for tag in detections
                ]
                return {
                    "contract": "hhh.camera-correction",
                    "version": correction_version,
                    "status": "ready", "corrected": True,
                    "observed_at": time.time(),
                    "width": 1696, "height": 960,
                    "tags": corrected_tags,
                    "detections": corrected_detections,
                }

        class Relay:
            calls = 0

            @classmethod
            def arms_snapshot(cls):
                cls.calls += 1
                return {
                    "contract": "hhh.relay.arms", "version": relay_version,
                    "status": "ready", "observed_at": time.time(),
                    "arms": {
                        "green": {
                            "connected": True, "enabled": True,
                            "mode_name": "ServoP", "pose": [1, 2, 3, 4],
                            "target": [5, 6, 7, 8], "pump_mode": "off",
                        },
                        "purple": {
                            "connected": False, "enabled": False,
                            "pump_mode": "off",
                        },
                    },
                }

        return Webcam, Calibration, Relay

    def test_runtime_composes_three_versioned_inputs_without_game_knowledge(self):
        webcam, calibration, relay = self._production_inputs()
        self.board.hub_init(FakeContext({
            "webcam": webcam,
            "camera-calibration": calibration,
            "dobot-mg400-relay": relay,
        }))
        self.board.set_simulation(False, [])

        runtime = self.board.runtime_observation()
        generic = self.board.board_snapshot()
        app = Flask("photon-board-runtime-route-test")
        app.register_blueprint(self.board.bp, url_prefix="/p/photon-board")
        with app.test_client() as client:
            runtime_response = client.get("/p/photon-board/api/runtime")

        self.assertEqual(runtime["contract"], "photon.board.runtime")
        self.assertEqual(runtime["version"], 1)
        self.assertEqual(runtime["status"], "ready")
        self.assertEqual(runtime["source"], "camera")
        self.assertEqual(runtime["tags"][0]["nx"], 0.255)
        self.assertEqual(runtime["detections"][0]["ncorners"][0], [0.24, 0.29])
        self.assertEqual(runtime["visible_ids"], [100])
        self.assertEqual(runtime["arms"]["green"]["pose"], [1.0, 2.0, 3.0, 4.0])
        self.assertEqual(generic["contract"], "photon.board")
        self.assertEqual(runtime_response.status_code, 200)
        self.assertEqual(
            runtime_response.get_json()["contract"], "photon.board.runtime"
        )
        self.assertNotIn("corners", generic["tags"][0])
        self.assertNotIn("ncorners", generic["tags"][0])
        self.assertNotIn("level", runtime)
        self.assertNotIn("game", runtime)

    def test_changed_hardware_contract_fails_closed_inside_board(self):
        cases = (
            ("webcam", {"webcam_version": 2}),
            ("camera_calibration", {"correction_version": 2}),
            ("relay", {"relay_version": 2}),
        )
        for changed_input, versions in cases:
            with self.subTest(changed_input=changed_input):
                webcam, calibration, relay = self._production_inputs(**versions)
                self.board.hub_init(FakeContext({
                    "webcam": webcam,
                    "camera-calibration": calibration,
                    "dobot-mg400-relay": relay,
                }))
                self.board.set_simulation(False, [])

                runtime = self.board.runtime_observation()

                self.assertEqual(runtime["status"], "unavailable")
                self.assertEqual(runtime["tags"], [])
                self.assertIn("contract mismatch", "; ".join(runtime["errors"]))
                self.assertEqual(
                    runtime["inputs"][changed_input]["status"], "unavailable"
                )

    def test_z_prefers_board_and_does_not_read_legacy_siblings(self):
        class Board:
            @staticmethod
            def runtime_observation():
                return {
                    "contract": "photon.board.runtime", "version": 1,
                    "status": "ready", "source": "camera", "corrected": True,
                    "revision": 7, "observed_at": time.time(),
                    "tags": [{"id": 100, "nx": 0.25, "ny": 0.31, "missing": 0}],
                    "arms": {
                        "green": {
                            "connected": True, "enabled": True, "pump_mode": "off"
                        }
                    },
                }

        class LegacyMustNotRun:
            def __getattr__(self, name):
                raise AssertionError(f"legacy sibling was read through {name}")

        z = load("laser-tag-z")
        z.hub_init(FakeContext({
            "photon-level": self.level,
            "photon-board": Board(),
            "webcam": LegacyMustNotRun(),
            "camera-calibration": LegacyMustNotRun(),
            "dobot-mg400-relay": LegacyMustNotRun(),
        }))
        try:
            tags, arms = z._defence._physical_source()
            state = z._defence_snapshot()
            app = Flask("laser-tag-z-board-contract-test")
            app.register_blueprint(z.bp, url_prefix="/p/laser-tag-z")
            with app.test_client() as client:
                arm_response = client.get("/p/laser-tag-z/api/defence/arms")
            self.assertEqual(tags[0]["id"], 100)
            self.assertTrue(arms["green"]["connected"])
            self.assertEqual(state["board_source"], "photon-board")
            self.assertEqual(state["board_status"], "ready")
            self.assertEqual(state["board_revision"], 7)
            self.assertIsNone(state["board_input_error"])
            self.assertEqual(arm_response.status_code, 200)
            self.assertEqual(arm_response.get_json()["board_source"], "photon-board")
        finally:
            z.hub_stop()

    def test_incompatible_board_is_contained_and_does_not_bypass_to_legacy(self):
        class ChangedBoard:
            @staticmethod
            def runtime_observation():
                return {
                    "contract": "photon.board.runtime", "version": 2,
                    "status": "ready",
                }

        class LegacyMustNotRun:
            def __getattr__(self, name):
                raise AssertionError(f"legacy sibling was read through {name}")

        z = load("laser-tag-z")
        z.hub_init(FakeContext({
            "photon-level": self.level,
            "photon-board": ChangedBoard(),
            "webcam": LegacyMustNotRun(),
            "camera-calibration": LegacyMustNotRun(),
            "dobot-mg400-relay": LegacyMustNotRun(),
        }))
        try:
            tags, arms = z._defence._physical_source()
            state = z._defence_snapshot()
            self.assertEqual(tags, [])
            self.assertEqual(arms, {})
            self.assertEqual(state["board_source"], "photon-board")
            self.assertEqual(state["board_status"], "unavailable")
            self.assertIn("contract mismatch", state["board_input_error"])
        finally:
            z.hub_stop()

    def test_absent_board_keeps_the_read_only_standalone_fallback(self):
        class Webcam:
            @staticmethod
            def get_tags():
                return [{"id": 100, "nx": 0.25, "ny": 0.31, "missing": 0}]

        class Calibration:
            @staticmethod
            def correct_tag_sets(tags, detections):
                return tags, detections, True

        class Relay:
            @staticmethod
            def arm_state(side):
                return {
                    "connected": side == "green", "enabled": side == "green",
                    "pump_mode": "off", "pose": [1, 2, 3, 4],
                }

        z = load("laser-tag-z")
        z.hub_init(FakeContext({
            "photon-level": self.level,
            "webcam": Webcam(),
            "camera-calibration": Calibration(),
            "dobot-mg400-relay": Relay(),
        }))
        try:
            tags, arms = z._defence._physical_source()
            state = z._defence_snapshot()
            self.assertEqual(tags[0]["id"], 100)
            self.assertTrue(arms["green"]["connected"])
            self.assertEqual(state["board_source"], "legacy-fallback")
            self.assertEqual(state["board_status"], "ready")
            self.assertIn("Photon Board", state["board_input_error"])
        finally:
            z.hub_stop()


class PhotonGameExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.level = load("photon-level")
        package_dir = PROTOTYPES / "laser-tag-z" / "photon_defence"
        spec = importlib.util.spec_from_file_location(
            "phase6_legacy_photon_defence",
            package_dir / "__init__.py",
            submodule_search_locations=[str(package_dir)],
        )
        cls.legacy_runtime = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.legacy_runtime
        spec.loader.exec_module(cls.legacy_runtime)

    def _game(self, folder, modules=None):
        game = load("photon-game")
        game.LOG_PATH = str(Path(folder) / "runs.jsonl")
        game._settings = game.SettingsStore(Path(folder) / "settings.json")
        game.hub_init(FakeContext(modules or {"photon-level": self.level}))
        return game

    def test_proven_simulation_matches_z_for_the_same_contract_input(self):
        bundle = self.level.runtime_bundle()
        legacy = self.legacy_runtime.DefenseEngine(
            ROOT / "assets/tiled/levels/z-pixel-first-map.tmj",
            ROOT / "assets/tiled/levels/z-pixel-first-map.waves.json",
        )
        legacy.reload_level(
            self.legacy_runtime.ContractLevelModel(bundle["runtime"]),
            bundle["waves"],
        )
        extracted = load("photon-game").DefenseEngine(
            bundle["runtime"], bundle["waves"]
        )
        socket_id = sorted(extracted.level.sockets)[0]
        settings = {"wave_count": 1, "max_active_enemies": 20}
        for engine in (legacy, extracted):
            engine.set_virtual_play(True)
            engine.place(100, socket_id, source="virtual")
            engine.start(settings)
            for _ in range(20):
                engine.step(0.1)

        def comparable(engine):
            value = engine.snapshot()
            value.pop("server_time", None)
            value.pop("physical_input_error", None)
            for tower in value["towers"]:
                tower.get("targeting", {}).pop("control", None)
            for event in value["events"]:
                event.pop("sequence", None)
            return value

        self.assertEqual(comparable(extracted), comparable(legacy))

    def test_board_relationship_path_matches_z_physical_placement_policy(self):
        bundle = self.level.runtime_bundle()
        legacy = self.legacy_runtime.DefenseEngine(
            ROOT / "assets/tiled/levels/z-pixel-first-map.tmj",
            ROOT / "assets/tiled/levels/z-pixel-first-map.waves.json",
        )
        legacy.reload_level(
            self.legacy_runtime.ContractLevelModel(bundle["runtime"]),
            bundle["waves"],
        )
        extracted = load("photon-game").DefenseEngine(
            bundle["runtime"], bundle["waves"]
        )
        board = load("photon-board")
        tracker = board.PhysicalPlacementTracker()
        for engine in (legacy, extracted):
            engine.set_virtual_play(False)
            engine.start()
        extracted.run_started_at = 100.0

        tags = [
            {"id": 48, "nx": .2, "ny": .3, "missing": 0},
            {"id": 100, "nx": .2, "ny": .3, "missing": 0},
        ]
        arm_state = {
            "green": {"connected": True, "enabled": True, "pump_mode": "suck"},
        }

        def new_sample(at):
            arms = json.loads(json.dumps(arm_state))
            for arm in arms.values():
                arm["feedback_at"] = at
            runtime = {
                "status": "ready", "source": "camera", "frame_at": at,
                "tags": json.loads(json.dumps(tags)), "arms": arms,
            }
            extracted.ingest_physical(tracker.update(runtime, at))

        for legacy_at, wall_at in ((1.0, 100.0), (1.6, 100.6)):
            legacy.ingest_physical(tags, arm_state, now=legacy_at)
            new_sample(wall_at)
        self.assertEqual(legacy.snapshot()["towers"], extracted.snapshot()["towers"])

        arm_state["green"]["pump_mode"] = "off"
        for legacy_at, wall_at in ((2.0, 101.0), (2.6, 101.6)):
            legacy.ingest_physical(tags, arm_state, now=legacy_at)
            new_sample(wall_at)
        self.assertEqual(
            [(tower["atom_tag_id"], tower["aruco_id"]) for tower in legacy.snapshot()["towers"]],
            [(tower["atom_tag_id"], tower["aruco_id"]) for tower in extracted.snapshot()["towers"]],
        )

        tags[:] = [
            {"id": 48, "nx": .2, "ny": .3, "missing": 0},
            {"id": 49, "nx": .4, "ny": .3, "missing": 0},
            {"id": 100, "nx": .4, "ny": .3, "missing": 0},
        ]
        for legacy_at, wall_at in ((3.0, 102.0), (3.6, 102.6)):
            legacy.ingest_physical(tags, arm_state, now=legacy_at)
            new_sample(wall_at)
        self.assertEqual(
            [(tower["atom_tag_id"], tower["aruco_id"]) for tower in legacy.snapshot()["towers"]],
            [(tower["atom_tag_id"], tower["aruco_id"]) for tower in extracted.snapshot()["towers"]],
        )

    def test_settings_corruption_is_explicit_and_defaults_remain_repairable(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "settings.json"
            path.write_text("[]", encoding="utf-8")
            store = load("photon-game").SettingsStore(path)
            response = store.response()
            self.assertEqual(response["status"], "unavailable")
            self.assertIn("must be an object", response["error"])
            self.assertEqual(response["settings"], response["defaults"])
            repaired, errors = store.update(response["defaults"], "balanced")
            self.assertEqual(errors, {})
            self.assertEqual(repaired["status"], "ready")

    def test_failed_settings_save_never_changes_live_draft_or_revision(self):
        with tempfile.TemporaryDirectory() as folder:
            store = load("photon-game").SettingsStore(
                Path(folder) / "settings.json"
            )
            before = store.response()
            changed = dict(before["settings"], wave_count=2)
            with mock.patch.object(
                store, "_save_locked", side_effect=OSError("disk full")
            ):
                with self.assertRaisesRegex(OSError, "disk full"):
                    store.update(changed)
            after = store.response()
            self.assertEqual(after["settings"], before["settings"])
            self.assertEqual(after["revision"], before["revision"])
            self.assertEqual(after["status"], "unavailable")
            self.assertIn("previous values remain active", after["error"])

    def test_settings_api_surfaces_write_failure_and_preserves_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            game = self._game(folder)
            before = game._settings.response()
            changed = dict(before["settings"], wave_count=2)
            try:
                with mock.patch.object(
                    game._settings, "_save_locked", side_effect=OSError("disk full")
                ):
                    with self.assertRaisesRegex(game.GameError, "not saved"):
                        game.apply_command({"action": "configure", "settings": changed})
                snapshot = game.game_snapshot()
                self.assertEqual(snapshot["configuration"]["settings"], before["settings"])
                self.assertEqual(snapshot["configuration"]["revision"], before["revision"])
                self.assertEqual(snapshot["configuration"]["status"], "unavailable")
                self.assertEqual(snapshot["storage"]["settings"]["status"], "unavailable")
            finally:
                game.hub_stop()

    def test_core_placement_waits_for_board_declared_post_gate_window(self):
        game_module = load("photon-game")
        bundle = self.level.runtime_bundle()
        engine = game_module.DefenseEngine(bundle["runtime"], bundle["waves"])
        engine.set_virtual_play(False)
        engine.start()
        engine.run_started_at = 90.0
        engine.ring_completed_at = 0.0
        engine.ring_completed_wall_at = 100.0
        engine.core_stage = "ring_ready"

        def descriptor(sampled_at):
            return {
                "contract": "photon.board.placement", "version": 1,
                "status": "ready", "sampled_at": sampled_at,
                "relations": [
                    {
                        "relation_id": f"core:{atom}", "movable_id": atom,
                        "marker_id": 38, "arm": side, "distance": 0,
                        "observed_since": 90.0, "stable_at": 90.55,
                        "stable": True,
                    }
                    for atom, side in ((100, "green"), (102, "purple"))
                ],
            }

        engine.ingest_physical(descriptor(100.54))
        self.assertEqual(engine.core_stage, "ring_ready")
        engine.ingest_physical(descriptor(100.56))
        self.assertEqual(engine.core_stage, "detonating")

    def test_runtime_has_no_file_level_camera_render_or_asset_dependency(self):
        module_dir = PROTOTYPES / "photon-game"
        engine_source = (module_dir / "photon_game_runtime/engine.py").read_text(
            encoding="utf-8"
        )
        prototype_source = (module_dir / "prototype.py").read_text(encoding="utf-8")
        self.assertNotIn("\nclass LevelModel:", engine_source)
        self.assertNotIn("read_text(", engine_source)
        self.assertNotIn(".tmj", engine_source.lower())
        self.assertNotIn("webcam", prototype_source.lower())
        self.assertNotIn("camera-calibration", prototype_source.lower())
        self.assertNotIn("dobot-mg400-relay", prototype_source.lower())
        self.assertNotIn("/assets/", prototype_source)
        self.assertFalse((module_dir / "assets").exists())

    def test_settings_and_jsonl_history_are_owned_and_run_settings_are_frozen(self):
        with tempfile.TemporaryDirectory() as folder:
            game = self._game(folder)
            try:
                self.assertTrue(
                    Path(game.SETTINGS_PATH).is_relative_to(PROTOTYPES / "photon-game")
                )
                self.assertTrue(
                    Path(game.LOG_PATH).is_relative_to(PROTOTYPES / "photon-game")
                    or Path(game.LOG_PATH).is_relative_to(Path(folder))
                )
                game.apply_command({
                    "action": "configure", "settings": {"wave_count": 1},
                })
                game.apply_command({"action": "start", "virtual_play": True})
                active_settings = game.game_snapshot()["settings"]
                game.apply_command({"action": "configure", "preset": "onslaught"})
                self.assertEqual(game.game_snapshot()["settings"], active_settings)
                lines = Path(game.LOG_PATH).read_text(encoding="utf-8").splitlines()
                events = [json.loads(line) for line in lines]
                self.assertTrue(any(item["kind"] == "game_event" for item in events))
                self.assertTrue(any(item["kind"] == "settings_saved" for item in events))
                self.assertEqual(game.game_snapshot()["storage"]["history"]["status"], "ready")
            finally:
                game.hub_stop()

    def test_settings_projection_and_commands_work_without_a_level(self):
        with tempfile.TemporaryDirectory() as folder:
            game = load("photon-game")
            game.LOG_PATH = str(Path(folder) / "runs.jsonl")
            game._settings = game.SettingsStore(Path(folder) / "settings.json")
            game.hub_init(FakeContext({}))
            try:
                before = game.game_snapshot()
                self.assertEqual(before["status"], "unavailable")
                configuration = before["configuration"]
                self.assertEqual(
                    (configuration["contract"], configuration["version"]),
                    ("photon.game.settings", 1),
                )
                self.assertEqual(configuration["status"], "ready")
                self.assertIn("balanced", configuration["presets"])
                self.assertIn("wave_count", configuration["limits"])

                after = game.apply_command({
                    "action": "configure", "preset": "training",
                })
                self.assertEqual(after["status"], "unavailable")
                self.assertEqual(after["configuration"]["preset"], "training")
                self.assertTrue((Path(folder) / "settings.json").is_file())

                with self.assertRaises(game.GameError) as rejected:
                    game.apply_command({
                        "action": "configure",
                        "settings": {"wave_count": 99},
                    })
                self.assertIn("wave_count", rejected.exception.fields)
            finally:
                game.hub_stop()

    def test_settings_projection_summarizes_authored_waves(self):
        with tempfile.TemporaryDirectory() as folder:
            game = self._game(folder)
            try:
                configuration = game.game_snapshot()["configuration"]
                counts = configuration["authored_wave_enemy_counts"]
                self.assertEqual(len(counts), 12)
                self.assertEqual(counts[0], 118)
                self.assertTrue(all(count > 0 for count in counts))
            finally:
                game.hub_stop()

    def test_game_settings_page_and_http_validation_work_without_siblings(self):
        with tempfile.TemporaryDirectory() as folder:
            game = load("photon-game")
            game.LOG_PATH = str(Path(folder) / "runs.jsonl")
            game._settings = game.SettingsStore(Path(folder) / "settings.json")
            game.hub_init(FakeContext({}))
            try:
                app = Flask("game-owned-settings-test")
                app.register_blueprint(game.bp, url_prefix="/p/photon-game")
                operator = {"hhh.roles": {"gamemaster"}}
                before = game._settings.snapshot()
                with app.test_client() as client:
                    with client.get("/p/photon-game/") as page, client.get("/p/photon-game/settings") as alias:
                        self.assertEqual(page.status_code, 200)
                        self.assertEqual(page.data, alias.data)
                        self.assertIn(b"owned and validated by Photon Game", page.data)
                        self.assertIn(b"Input and storage diagnostics", page.data)
                        self.assertNotIn(b"laser-tag-y", page.data)
                        for key in game._settings.response()["limits"]:
                            self.assertIn(f'data-key="{key}"'.encode(), page.data)
                    denied = client.post("/p/photon-game/api/command", json={"action": "configure", "preset": "training"})
                    self.assertEqual(denied.status_code, 403)
                    invalid = client.post("/p/photon-game/api/command", json={"action": "configure", "settings": {"wave_count": 99}}, environ_overrides=operator)
                    self.assertEqual(invalid.status_code, 400)
                    self.assertIn("wave_count", invalid.get_json()["errors"])
                    self.assertEqual(game._settings.snapshot(), before)
                    accepted = client.post("/p/photon-game/api/command", json={"action": "configure", "preset": "training"}, environ_overrides=operator)
                    self.assertEqual(accepted.status_code, 200)
                    state = accepted.get_json()["output"]
                    self.assertEqual(state["status"], "unavailable")
                    self.assertEqual(state["configuration"]["preset"], "training")
                    self.assertEqual(game.SettingsStore(Path(folder) / "settings.json").snapshot(), state["configuration"]["settings"])
                    reset = client.post("/p/photon-game/api/command", json={"action": "reset_settings"}, environ_overrides=operator)
                    self.assertEqual(reset.status_code, 200)
                    self.assertEqual(game._settings.snapshot(), before)
            finally:
                game.hub_stop()

    def test_game_settings_form_keeps_unsaved_edits_during_sse_updates(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node required for settings form smoke test")
        with tempfile.TemporaryDirectory() as folder:
            game = load("photon-game")
            game._settings = game.SettingsStore(Path(folder) / "settings.json")
            state = game.game_snapshot()
        script = r"""
const assert = require('node:assert/strict'), fs = require('node:fs'), vm = require('node:vm');
const html = fs.readFileSync(process.argv[1], 'utf8'), initial = JSON.parse(process.argv[2]);
const elements = new Map(), requests = [], streams = [];
function element(id = '') {
  return {id, value:'', textContent:'', dataset:{}, handlers:{}, disabled:false, open:false,
    addEventListener(name, callback) {this.handlers[name] = callback;},
    replaceChildren(...children) {this.children = children; this.value = children[0]?.value || '';},
    prepend(child) {this.children.unshift(child);},
    closest() {return {querySelector: () => this.error};},
  };
}
for (const match of html.matchAll(/id="([^"]+)"/g)) elements.set(match[1], element(match[1]));
const fields = [...html.matchAll(/<input[^>]+data-key="([^"]+)"[^>]*>/g)].map(match => {
  const input = elements.get(match[1]); input.dataset.key = match[1]; input.error = element(); return input;
});
const context = vm.createContext({
  document: {getElementById: id => elements.get(id), createElement: () => element(),
    querySelectorAll: () => fields,
    querySelector: selector => elements.get(selector.match(/data-key="([^"]+)"/)[1])},
  location: {pathname:'/s/gamemaster/p/photon-game/settings'}, window:{addEventListener(){}},
  fetch: async (url, options = {}) => {
    requests.push({url, options});
    const post = options.method === 'POST';
    const body = post ? {error:'settings validation failed', errors:{wave_count:'must be between 1 and 12'}} : initial;
    return {ok:!post, status:post?400:200, text:async()=>JSON.stringify(body)};
  },
  EventSource: function(url) {this.url=url; this.close=()=>{}; streams.push(this);},
});
vm.runInContext(html.split('<script>')[1].split('</script>')[0], context);
(async () => {
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(elements.get('save').disabled, false, 'settings work without a ready Level');
  assert.equal(elements.get('wave_count').value, initial.configuration.settings.wave_count);
  elements.get('wave_count').value = '7';
  const update = structuredClone(initial);
  update.phase = 'running'; update.paused = true; update.settings = initial.configuration.settings;
  update.configuration.settings.wave_count = 2;
  streams[0].onmessage({data:JSON.stringify(update)});
  assert.equal(elements.get('wave_count').value, '7', 'SSE must not replace the unsaved draft');
  assert.match(elements.get('activeNotice').textContent, /paused run.*next Start/);
  assert.equal(streams.length, 1);
  assert.equal(streams[0].url, '/s/gamemaster/p/photon-game/api/events');
  await elements.get('save').handlers.click();
  assert.equal(elements.get('wave_count').error.textContent, 'must be between 1 and 12');
  assert.equal(elements.get('wave_count').value, '7', 'validation preserves draft');
  assert.equal(elements.get('save').disabled, false);
  assert.equal(JSON.parse(requests.at(-1).options.body).settings.wave_count, '7');
  assert.ok(requests.every(request => request.url.startsWith('/s/gamemaster/p/photon-game/api/')));
})().catch(error => {console.error(error); process.exitCode=1;});
"""
        result = subprocess.run([node, "-e", script, str(PROTOTYPES / "photon-game/index.html"), json.dumps(state)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_game_exposes_one_snapshot_and_one_sse_stream(self):
        with tempfile.TemporaryDirectory() as folder:
            game = self._game(folder)
            try:
                app = Flask("photon-game-output-test")
                app.register_blueprint(game.bp, url_prefix="/p/photon-game")
                api_gets = sorted(
                    rule.rule for rule in app.url_map.iter_rules()
                    if rule.rule.startswith("/p/photon-game/api/")
                    and "GET" in rule.methods
                )
                self.assertEqual(api_gets, [
                    "/p/photon-game/api/events", "/p/photon-game/api/state",
                ])
                with app.test_request_context("/p/photon-game/api/events"):
                    response = game.game_events()
                    first = next(iter(response.response))
                    if isinstance(first, bytes):
                        first = first.decode("utf-8")
                    response.close()
                payload = json.loads(first.removeprefix("data: ").strip())
                self.assertEqual(payload["contract"], "photon.game")
                self.assertEqual(payload["version"], 2)
            finally:
                game.hub_stop()

    def test_game_projection_is_complete_for_a_presentation(self):
        with tempfile.TemporaryDirectory() as folder:
            game = self._game(folder)
            try:
                snapshot = game.game_snapshot()
                socket = snapshot["level"]["sockets"][0]
                self.assertEqual(
                    set((
                        "id", "socket_id", "owner", "aruco_id", "x", "y",
                        "size", "radius", "marker_x", "marker_y", "marker_size",
                    ))
                    - set(socket),
                    set(),
                )
                self.assertEqual(socket["id"], socket["socket_id"])
                self.assertGreater(socket["size"], 0)
                self.assertEqual(
                    snapshot["level"]["scene"]["contract"],
                    "photon.visual-scene",
                )
                self.assertEqual(snapshot["level"]["core"]["marker_size"], 116.0)
            finally:
                game.hub_stop()

    def test_additive_level_visuals_keep_an_older_version_one_input_running(self):
        game = load("photon-game")
        runtime = json.loads(json.dumps(self.level.runtime_bundle()["runtime"]))
        runtime.pop("visual_scene")
        runtime.pop("core_visual")
        for socket in runtime["sockets"].values():
            socket.pop("marker_x")
            socket.pop("marker_y")
            socket.pop("marker_size")
        projection = game._simple_level(runtime)
        self.assertIsNone(projection["scene"])
        self.assertEqual(
            (projection["sockets"][0]["marker_x"], projection["sockets"][0]["marker_y"]),
            (projection["sockets"][0]["x"], projection["sockets"][0]["y"]),
        )
        self.assertGreater(projection["core"]["marker_size"], 0)

    def test_physical_start_readiness_is_decided_by_game_not_presentation(self):
        with tempfile.TemporaryDirectory() as folder:
            game = self._game(folder)
            try:
                with self.assertRaisesRegex(game.GameError, "Photon Board"):
                    game.apply_command({"action": "start", "virtual_play": False})
                self.assertEqual(game.game_snapshot()["phase"], "setup")
                started = game.apply_command({"action": "start", "virtual_play": True})
                self.assertEqual(started["phase"], "running")
            finally:
                game.hub_stop()

    def test_changed_inputs_fail_locally_and_board_contributes_no_evidence(self):
        class ChangedLevel:
            @staticmethod
            def runtime_bundle():
                return {
                    "contract": "photon.level.runtime", "version": 2,
                    "status": "ready",
                }

        class ChangedBoard:
            @staticmethod
            def runtime_observation():
                return {
                    "contract": "photon.board.runtime", "version": 2,
                    "status": "ready",
                }

        with tempfile.TemporaryDirectory() as folder:
            unavailable = self._game(folder, {"photon-level": ChangedLevel()})
            try:
                snapshot = unavailable.game_snapshot()
                self.assertEqual(snapshot["status"], "unavailable")
                self.assertIn("contract mismatch", snapshot["inputs"]["level"]["error"])
            finally:
                unavailable.hub_stop()

        with tempfile.TemporaryDirectory() as folder:
            game = self._game(folder, {
                "photon-level": self.level, "photon-board": ChangedBoard(),
            })
            try:
                placement = game._physical_observation()
                self.assertEqual(placement["status"], "unavailable")
                self.assertEqual(placement["relations"], [])
                self.assertEqual(game.game_snapshot()["status"], "ready")
                self.assertIn(
                    "contract mismatch", game.game_snapshot()["inputs"]["board"]["error"]
                )
            finally:
                game.hub_stop()

    def test_level_revision_waits_for_reset(self):
        class MutableLevel:
            def __init__(self, value):
                self.value = value

            def runtime_bundle(self):
                return json.loads(json.dumps(self.value))

        bundle = self.level.runtime_bundle()
        source = MutableLevel(bundle)
        with tempfile.TemporaryDirectory() as folder:
            game = self._game(folder, {"photon-level": source})
            try:
                game.apply_command({"action": "start", "virtual_play": True})
                previous = game.game_snapshot()["level_revision"]
                source.value["revision"] += 1
                source.value["runtime"]["layout_revision"] += 1
                during = game.game_snapshot()
                self.assertEqual(during["level_revision"], previous)
                self.assertEqual(
                    during["inputs"]["level"]["pending_revision"], previous + 1
                )
                game.apply_command({"action": "reset"})
                self.assertEqual(game.game_snapshot()["level_revision"], previous + 1)
            finally:
                game.hub_stop()


class HubLifecycleTests(unittest.TestCase):
    def test_group_is_reported_and_disabled_module_never_starts(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config = {
                "port": 8765, "secret": "x" * 32,
                "sandboxes": {
                    "gamemaster": {
                        "label": "GM", "accent": "#fff", "admin": True,
                        "password": "test", "shared_api": {},
                    },
                    "green": {"label": "G", "accent": "#0f0", "password": "g"},
                    "purple": {"label": "P", "accent": "#f0f", "password": "p"},
                },
            }
            (root / "hub-config.json").write_text(json.dumps(config), encoding="utf-8")
            machines = root / "sandboxes/gamemaster/prototypes"
            machine = machines / "sample"
            machine.mkdir(parents=True)
            (machines / "hub-settings.json").write_text(
                json.dumps({"disabled": ["sample"]}), encoding="utf-8"
            )
            (machine / "prototype.py").write_text(
                "from flask import Blueprint, jsonify\n"
                "MANIFEST={'name':'Sample','group':'Photon Engine'}\n"
                "bp=Blueprint('sample',__name__)\nstarted=False\n"
                "def hub_init(ctx):\n global started; started=True\n"
                "@bp.route('/api/ping')\ndef ping(): return jsonify(ok=True)\n",
                encoding="utf-8",
            )
            active = machines / "active"
            active.mkdir()
            (active / "prototype.py").write_text(
                "from flask import Blueprint, jsonify\n"
                "MANIFEST={'name':'Active','group':'Photon Engine'}\n"
                "bp=Blueprint('active',__name__)\nstarted=False\nstopped=False\n"
                "def hub_init(ctx):\n global started; started=True\n"
                "def hub_stop():\n global stopped; stopped=True\n"
                "@bp.route('/api/ping')\ndef ping(): return jsonify(ok=True)\n",
                encoding="utf-8",
            )
            hub = Hub(root)
            sandbox = hub.sandboxes["gamemaster"]
            sandbox.discover()
            self.assertFalse(sandbox._modules["sample"].started)
            self.assertTrue(sandbox._modules["active"].started)
            self.assertTrue(all(item["group"] == "Photon Engine" for item in sandbox._prototypes))
            token = hub.service_tokens["gamemaster"]
            with sandbox.app.test_client() as client:
                response = client.get("/p/sample/api/ping", headers={AUTH_HEADER: token})
                listing = client.get("/api/prototypes", headers={AUTH_HEADER: token})
                disabled = client.post(
                    "/api/prototypes/active/enabled",
                    headers={AUTH_HEADER: token}, json={"enabled": False},
                )
                stopped = client.get("/p/active/api/ping", headers={AUTH_HEADER: token})
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.get_json()["error"], "machine disabled")
            self.assertEqual(listing.get_json()[0]["group"], "Photon Engine")
            self.assertEqual(disabled.status_code, 200)
            self.assertTrue(sandbox._modules["active"].stopped)
            self.assertEqual(stopped.status_code, 503)


if __name__ == "__main__":
    unittest.main()
