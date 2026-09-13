"""Fixture-only module checks; no test loads another Photon module as a producer."""

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
PROTOTYPES = ROOT / "sandboxes/gamemaster/prototypes"
sys.path.insert(0, str(ROOT / "hub"))


def load(slug):
    path = PROTOTYPES / slug / "prototype.py"
    name = "isolation_" + slug.replace("-", "_")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    sys.path.insert(0, str(path.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


class ContractContext:
    sandbox = "gamemaster"

    def __init__(self, modules=None):
        self.modules = dict(modules or {})

    def is_prototype_enabled(self, slug):
        return slug in self.modules

    def get_prototype(self, slug):
        return self.modules.get(slug)


def level_runtime_fixture():
    width, height = 1000, 600
    groups = ("green_a", "green_b", "purple_a", "purple_b")
    nodes = {0: {"name": "core", "node_kind": "core", "x": 500, "y": 300}}
    edges, route_edge_ids, paths = {0: []}, {}, {}
    spawn_points = ((20, 120), (20, 480), (980, 120), (980, 480))
    for node_id, (group, point) in enumerate(zip(groups, spawn_points), 1):
        nodes[node_id] = {
            "name": group, "node_kind": "spawn", "spawn_group": group,
            "x": point[0], "y": point[1],
        }
        edge_id = f"{group}-core"
        length = ((point[0] - 500) ** 2 + (point[1] - 300) ** 2) ** 0.5
        edge = {
            "edge_id": edge_id, "from": node_id, "to": 0, "cost": length,
            "points": [list(point), [500, 300]],
            "segment_lengths": [length], "path_length": length,
        }
        edges[node_id] = [edge]
        route_edge_ids[group] = [edge_id]
        paths[group] = [list(point), [500, 300]]
    sockets = {}
    socket_by_marker = {}
    ring = []
    for offset, marker_id in enumerate(range(40, 56)):
        socket_id = f"socket-{offset + 1}"
        ring.append(socket_id)
        sockets[socket_id] = {
            "id": socket_id, "x": 100 + offset * 48, "y": 200 + (offset % 2) * 160,
            "size": 96, "owner": "green" if offset < 8 else "purple",
            "aruco_id": marker_id, "marker_x": 100 + offset * 48,
            "marker_y": 200 + (offset % 2) * 160, "marker_size": 48,
        }
        socket_by_marker[marker_id] = socket_id
    ring_edges = [[ring[index], ring[(index + 1) % len(ring)]] for index in range(len(ring))]
    runtime = {
        "layout_revision": 1, "width": width, "height": height,
        "aruco_code_footprint_px": 48, "core_aruco_code_footprint_px": 64,
        "force_field_marker_clearance_px": 20, "nodes": nodes, "edges": edges,
        "route_edge_ids": route_edge_ids, "paths": paths, "junctions": [],
        "sockets": sockets, "socket_by_marker": socket_by_marker,
        "ring_adjacency": {
            socket_id: [ring[(index - 1) % len(ring)], ring[(index + 1) % len(ring)]]
            for index, socket_id in enumerate(ring)
        },
        "ring_edges": ring_edges, "ring_cycles": [ring], "force_field_blockers": [],
        "map_properties": {"level_id": "fixture-level"},
        "core_visual": {"x": 500, "y": 300, "marker_x": 500, "marker_y": 300, "marker_size": 64},
    }
    waves = [{
        "wave": 1,
        "groups": [{"enemy": "grunt", "count": 1, "duration_s": 1, "lane_weights": {groups[0]: 1}}],
    }]
    return {
        "contract": "photon.level.runtime", "version": 1, "status": "ready",
        "revision": 1, "runtime": runtime, "waves": waves,
    }


class PhotonModuleIsolationTests(unittest.TestCase):
    def test_level_runs_from_only_its_own_files(self):
        level = load("photon-level")
        self.assertEqual(level.runtime_bundle()["contract"], "photon.level.runtime")
        self.assertEqual(level.editor_snapshot()["contract"], "photon.level.editor")
        self.assertEqual(level.presentation_assets()["contract"], "photon.level.assets")

    def test_board_runs_from_fixture_input_without_producer_source(self):
        board = load("photon-board")
        board.hub_init(ContractContext())
        try:
            output = board.set_simulation(True, [
                {"id": 40, "nx": 0.50, "ny": 0.50},
                {"id": 100, "nx": 0.52, "ny": 0.50},
            ], {"green": {"connected": True, "enabled": True, "pump_mode": "off"}})
            self.assertEqual(output["contract"], "photon.board")
            self.assertEqual(output["status"], "ready")
            self.assertEqual(output["placement"]["contract"], "photon.board.placement")
        finally:
            board.hub_stop()

    def test_game_runs_from_value_fixture_without_level_or_board_source(self):
        game = load("photon-game")
        bundle = level_runtime_fixture()
        producer = SimpleNamespace(runtime_bundle=lambda: json.loads(json.dumps(bundle)))
        with tempfile.TemporaryDirectory() as folder:
            game.LOG_PATH = str(Path(folder) / "runs.jsonl")
            game._settings = game.SettingsStore(Path(folder) / "settings.json")
            game.hub_init(ContractContext({"photon-level": producer}))
            try:
                output = game.game_snapshot()
                self.assertEqual(output["contract"], "photon.game")
                self.assertEqual(output["status"], "ready")
                self.assertEqual(output["level"]["name"], "fixture-level")
                self.assertEqual(output["inputs"]["board"]["status"], "unavailable")
            finally:
                game.hub_stop()

    @unittest.skipUnless(shutil.which("node"), "Node.js is required for Y isolation checks")
    def test_y_derives_game_identifiers_and_counts_from_a_changed_fixture(self):
        renderer = PROTOTYPES / "laser-tag-y/tower-defence-view.js"
        state = {
            "loadout": {"205": "water_cannon", "901": "light_beam"},
            "level": {"sockets": [{"id": "a"}, {"id": "b"}, {"id": "c"}]},
            "core_sequence": {"marker_id": 77, "ring_min_turrets": 3, "ring_max_turrets": 5},
        }
        script = f"""
require({json.dumps(str(renderer))});
const facts = globalThis.TowerDefenceView.presentation.gameFacts({json.dumps(state)});
if (JSON.stringify(facts.atom_ids) !== '[205,901]') throw Error('loadout IDs were not derived');
if (facts.loadout[0].label !== 'Water cannon') throw Error('tower label was not derived');
if (facts.socket_count !== 3) throw Error('socket count was not derived');
if (facts.core_marker_id !== 77) throw Error('core marker was not derived');
if (facts.ring_min_turrets !== 3 || facts.ring_max_turrets !== 5) throw Error('ring limits were not derived');
"""
        result = subprocess.run(
            [shutil.which("node"), "-e", script], capture_output=True, text=True, check=False
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        page = (PROTOTYPES / "laser-tag-y/index.html").read_text(encoding="utf-8")
        source = renderer.read_text(encoding="utf-8")
        for copied_default in ("const ATOMS", "Atom 100–103", "/ 8–16", "/ 16", "core 38"):
            self.assertNotIn(copied_default, page)
        self.assertNotIn("|| 180", source)
        self.assertNotIn("Array.from({ length: 16 }", source)


if __name__ == "__main__":
    unittest.main()
