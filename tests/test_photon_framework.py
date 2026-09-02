"""Small contract and lifecycle tests for the modular Photon vertical slice."""

import importlib.util
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from urllib.parse import urljoin


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
        cls.art = load("photon-art")
        cls.game = load("photon-game")
        cls.presentation = load("laser-tag-y")
        cls.log_folder = tempfile.TemporaryDirectory()
        cls.game.LOG_PATH = str(Path(cls.log_folder.name) / "runs.jsonl")
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
            "photon-art": cls.art,
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
            self.game.game_snapshot(), self.art.art_snapshot(),
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
        self.game.apply_command({"action": "configure", "enemy_count": 2, "spawn_interval": 0.2})
        self.game.apply_command({"action": "start"})
        deadline = time.time() + 1.5
        snapshot = self.game.game_snapshot()
        while time.time() < deadline and not (snapshot["spawned"] and snapshot["towers"]):
            time.sleep(0.05)
            snapshot = self.game.game_snapshot()
        self.assertGreaterEqual(snapshot["spawned"], 1)
        self.assertEqual(snapshot["towers"][0]["atom_tag_id"], 100)
        self.assertEqual(snapshot["level"]["name"], "z_pixel_first_map_01")

    def test_presentation_returns_game_output_and_art_manifest(self):
        app = Flask("photon-presentation-test")
        app.register_blueprint(self.presentation.bp, url_prefix="/p/laser-tag-y")
        with app.test_client() as client:
            response = client.get("/p/laser-tag-y/api/state")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json()["contract"], "photon.game")
            art = client.get("/p/laser-tag-y/api/art")
            self.assertEqual(art.get_json()["contract"], "photon.art")

    def test_changed_sibling_contract_fails_locally_not_system_wide(self):
        class ChangedGame:
            @staticmethod
            def game_snapshot():
                return {"contract": "photon.game", "version": 2, "status": "ready"}

        self.presentation.hub_init(FakeContext({
            "photon-game": ChangedGame(), "photon-art": self.art,
        }))
        try:
            app = Flask("photon-contract-mismatch-test")
            app.register_blueprint(self.presentation.bp, url_prefix="/p/laser-tag-y")
            with app.test_client() as client:
                state = client.get("/p/laser-tag-y/api/state")
                art = client.get("/p/laser-tag-y/api/art")
            self.assertEqual(state.status_code, 503)
            self.assertIn("contract mismatch", state.get_json()["error"])
            self.assertEqual(art.status_code, 200)
        finally:
            self.presentation.hub_init(FakeContext(self.modules))


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
