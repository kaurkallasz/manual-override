"""Camera/Board/Game core-stack regression tests; no hardware or background work."""

import copy
import time
import unittest
from unittest import mock

from test_photon_framework import FakeContext, load


class CoreStackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.game = load("photon-game")
        cls.board = load("photon-board")
        cls.bundle = load("photon-level").runtime_bundle()

    def setUp(self):
        self.engine = self.game.DefenseEngine(self.bundle["runtime"], self.bundle["waves"])
        self.engine.set_virtual_play(False)
        self.engine.start()
        self.engine.run_started_at = 90.0
        self.engine.ring_completed_at = 0.0
        self.engine.ring_completed_wall_at = 90.0
        self.engine.core_stage = "ring_ready"
        self.tracker = self.board.PhysicalPlacementTracker()
        self.now = 100.0
        self.connected = {"green": True, "purple": False}

    def sample(self, ids, advance=.2, *, source="camera", status="ready", frame_at=None,
               positions=None, tracked_extra=None, ingest=True):
        self.now += advance
        positions = positions or {}
        tags = [{"id": tag, "nx": positions.get(tag, (.5, .5))[0],
                 "ny": positions.get(tag, (.5, .5))[1], "missing": 0} for tag in ids]
        runtime = {
            "contract": "photon.board.runtime", "version": 1, "revision": 1,
            "observed_at": self.now, "errors": [],
            "status": status, "source": source,
            "frame_at": self.now if frame_at is None else frame_at,
            "tags": tags + (tracked_extra or []), "detections": tags, "visible_ids": ids,
            "arms": {side: {"connected": connected, "enabled": connected,
                            "pump_mode": "off", "feedback_at": self.now}
                     for side, connected in self.connected.items()},
        }
        self.runtime = runtime
        placement = self.tracker.update(runtime, self.now)
        if placement["status"] == "ready":
            # Exercise the production consumer's nested contract validation too.
            placement["stacking"] = self.game._validated_stacking(
                placement["stacking"], placement["sampled_at"], placement["source_epoch"],
            )
        if ingest:
            self.engine.ingest_physical(placement)
        return placement

    def activate_first(self, tag=100):
        self.sample([38, tag])
        self.sample([tag], .3)
        self.sample([tag], .3)
        self.assertEqual(self.engine.core_stage, "first_tag")
        self.assertEqual(self.engine.core_first_tag, tag)

    def cover(self, upper=103, **kwargs):
        for advance in (.2, .3, .3):
            placement = self.sample([upper], advance, **kwargs)
        return placement

    def test_100_then_103_wins_without_purple_after_38_expires(self):
        self.activate_first()
        self.sample([100], 121)
        self.assertNotIn(38, self.tracker.marker_cache)
        self.cover()
        self.assertEqual(self.engine.core_stage, "detonating")
        for _ in range(30):
            self.engine.step(.1)
        self.assertEqual(self.engine.phase, "won")
        self.sample([103])
        self.assertEqual(sum(e["kind"] == "core_detonation_started" for e in self.engine.events), 1)

    def test_completion_needs_neither_arm_connected(self):
        self.activate_first()
        self.connected["green"] = False
        self.cover()
        self.assertEqual(self.engine.core_stage, "detonating")

    def test_smaller_target_activation_radius_does_not_change_atom_cover_radius(self):
        self.activate_first()
        self.cover(positions={103: (.545, .5)})
        self.assertEqual(self.engine.core_stage, "detonating")

    def test_stationary_100_near_47_does_not_activate_but_close_placement_does(self):
        # This placement test starts before the core ring is assembled.
        self.engine.core_stage = 'locked'
        self.engine.ring_completed_at = self.engine.ring_completed_wall_at = None
        for jitter in (0, -.0003, -.0002, -.0001, -.0002):
            self.sample([100, 47], .3, positions={100: (.6301, .4915), 47: (.6801+jitter, .4928)})
        self.assertFalse(any(t.get('aruco_id') == 47 for t in self.engine.snapshot()['towers']))
        for _ in range(4):
            self.sample([100, 47], .3, positions={100: (.6451, .4915), 47: (.6801, .4928)})
        self.assertTrue(any(t.get('aruco_id') == 47 for t in self.engine.snapshot()['towers']))

    def test_board_public_snapshot_through_game_adapter_preserves_camera_only_cover(self):
        self.now = time.time() - 2
        self.activate_first()
        self.connected["green"] = False
        placement = self.cover(ingest=False)
        tracking = {"sampled_at": self.now, "frame_at": self.now, "tags": []}
        with mock.patch.object(self.board, "_runtime", self.runtime), \
             mock.patch.object(self.board, "_placement", placement), \
             mock.patch.object(self.board, "_tracking", tracking), \
             mock.patch.object(self.game, "_hub_ctx", FakeContext({"photon-board": self.board})):
            observed, error = self.game._board_observation()
            self.assertIsNone(error)
            self.assertEqual(observed["relations"], [])
            self.engine.ingest_physical(observed)
            self.assertEqual(self.engine.core_stage, "detonating")
            placement["stacking"]["relations"][0]["lower_id"] = "100"
            observed, error = self.game._board_observation()
            self.assertIsNone(observed)
            self.assertIn("payload is invalid", error)

    def test_camera_sampler_outage_discards_cover_evidence(self):
        self.activate_first()
        self.sample([103])
        self.sample([103], status="unavailable")
        self.cover()
        self.assertEqual(self.engine.core_stage, "first_tag")

    def test_cover_is_confirmed_before_win_and_waits_for_enemy_purge(self):
        self.activate_first()
        self.cover()
        self.assertEqual(self.engine.phase, "running")
        self.engine.core_purge_target_ids = {123}
        self.engine.enemies[123] = {"id": 123}
        self.engine.sim_time = self.engine.core_detonation_started_at + 3
        self.assertFalse(self.engine._finish_core_detonation_if_ready())
        self.engine.enemies.clear()
        self.assertTrue(self.engine._finish_core_detonation_if_ready())
        self.assertEqual(self.engine.phase, "won")

    def test_reversed_team_order(self):
        self.connected = {"green": False, "purple": True}
        self.activate_first(103)
        self.connected["purple"] = False
        self.cover(100)
        self.assertEqual(self.engine.core_stage, "detonating")

    def test_follows_first_atom_when_it_moves_away_from_38(self):
        self.activate_first()
        self.sample([100], positions={100: (.7, .6)})
        self.cover(positions={103: (.7, .6)})
        self.assertEqual(self.engine.core_stage, "detonating")

    def test_same_team_cover_does_not_win(self):
        self.activate_first()
        self.cover(101)
        self.assertEqual(self.engine.core_stage, "first_tag")

    def test_physical_first_layer_overrides_manual_selection(self):
        with mock.patch('time.time', return_value=self.now):
            self.engine.operator_turret_command('operator_core', None, 103)
        self.activate_first(100)
        self.assertEqual(self.engine.core_first_source, 'physical')
        self.cover(101)
        self.assertEqual(self.engine.core_stage, 'first_tag')
        self.sample([100, 101], positions={101: (.8, .8)})
        self.cover(103)
        self.assertEqual(self.engine.core_stage, 'detonating')
        self.assertEqual(self.engine.core_second_source, 'physical')

    def test_physical_cover_can_complete_manual_first_layer(self):
        with mock.patch('time.time', return_value=self.now):
            self.engine.operator_turret_command('operator_core', None, 100)
        self.sample([100])
        self.cover(101)
        self.assertEqual(self.engine.core_stage, 'first_tag')
        self.sample([100, 101], positions={101: (.8, .8)})
        self.cover(103)
        self.assertEqual(self.engine.core_stage, 'detonating')

    def test_x_does_not_replay_stationary_physical_layer(self):
        self.activate_first()
        with mock.patch('time.time', return_value=self.now):
            self.engine.operator_turret_command('operator_core', None, None)
        for _ in range(4):
            self.sample([100], .3)
        self.assertEqual(self.engine.core_stage, 'ring_ready')
        self.sample([38], 2)
        self.activate_first()

    def test_second_atom_at_38_does_not_replace_cover_requirement(self):
        self.activate_first()
        self.connected["purple"] = True
        for _ in range(4):
            self.sample([38, 100, 103], .3, positions={100: (.8, .8)})
        self.assertEqual(self.engine.core_stage, "first_tag")

    def test_two_visible_atoms_do_not_count_as_cover(self):
        self.activate_first()
        for _ in range(4):
            p = self.sample([100, 103], .3)
        self.assertEqual(p["stacking"]["relations"], [])
        self.assertEqual(self.engine.core_stage, "first_tag")

    def test_cover_of_different_atom_does_not_win(self):
        self.activate_first()
        self.sample([100, 101], positions={101: (.8, .8)})
        for _ in range(4):
            self.sample([100, 103], .3, positions={103: (.8, .8)})
        self.assertEqual(self.engine.core_stage, "first_tag")

    def test_tracked_grace_period_does_not_hide_real_cover(self):
        self.activate_first()
        self.cover(tracked_extra=[{"id": 100, "nx": .5, "ny": .5, "missing": .2}])
        self.assertEqual(self.engine.core_stage, "detonating")

    def test_old_uncovered_location_cannot_be_used(self):
        self.activate_first()
        self.sample([], 6)
        self.cover()
        self.assertEqual(self.engine.core_stage, "first_tag")

    def test_stale_frame_and_source_change_clear_stack_evidence(self):
        for reset in ("stale", "source"):
            with self.subTest(reset=reset):
                self.setUp()
                self.activate_first()
                if reset == "stale":
                    self.sample([103], frame_at=self.now - 3)
                    self.cover()
                else:
                    self.cover(source="simulation")
                self.assertEqual(self.engine.core_stage, "first_tag")

    def test_same_frame_cannot_satisfy_cover_dwell(self):
        self.activate_first()
        frame = self.now + .2
        for _ in range(4):
            p = self.sample([103], .2, frame_at=frame)
        self.assertFalse(p["stacking"]["relations"][0]["stable"])
        self.assertEqual(self.engine.core_stage, "first_tag")

    def test_reappearance_and_departure_reset_dwell(self):
        self.activate_first()
        self.sample([103])
        self.sample([100, 103], .3)
        p = self.sample([103], .3)
        self.assertFalse(p["stacking"]["relations"][0]["stable"])
        p = self.sample([103], .3, positions={103: (.8, .8)})
        self.assertEqual(p["stacking"]["relations"], [])
        self.assertEqual(self.engine.core_stage, "first_tag")

    def test_ambiguous_cover_does_not_win(self):
        self.activate_first()
        self.sample([100, 101])
        p = self.cover()
        self.assertEqual(p["stacking"]["relations"], [])
        self.assertEqual(self.engine.core_stage, "first_tag")

    def test_cover_before_first_activation_cannot_be_replayed(self):
        self.sample([100], ingest=False)
        p = self.cover()
        self.engine.activate_core_tag(100, source="physical", team="green")
        self.engine.core_first_tag_wall_at = self.now
        self.engine.ingest_physical(p)
        self.assertEqual(self.engine.core_stage, "first_tag")

    def test_existing_tower_placements_still_require_owner_arm(self):
        for _ in range(4):
            self.sample([40, 103], .3)
        self.assertEqual(self.engine.placements, {})

    def test_reset_discards_armed_atom(self):
        self.activate_first()
        self.engine.reset()
        self.cover()
        self.assertEqual(self.engine.core_stage, "locked")
        self.assertIsNone(self.engine.core_first_tag_wall_at)

    def test_malformed_stack_contract_is_rejected(self):
        self.activate_first()
        p = self.cover()
        for field, invalid in (("version", True), ("version", 2), ("source_epoch", "wrong"),
                               ("sampled_at", self.now - 3)):
            with self.subTest(field=field, invalid=invalid):
                bad = copy.deepcopy(p["stacking"])
                bad[field] = invalid
                with self.assertRaises(ValueError):
                    self.game._validated_stacking(bad, p["sampled_at"], p["source_epoch"])
        for field, invalid in (("upper_id", True), ("upper_id", 100), ("distance", float("nan")),
                               ("stable", "true"), ("observed_since", self.now + 1)):
            with self.subTest(field=field):
                bad = copy.deepcopy(p["stacking"])
                bad["relations"][0][field] = invalid
                with self.assertRaises(ValueError):
                    self.game._validated_stacking(bad, p["sampled_at"], p["source_epoch"])


if __name__ == "__main__":
    unittest.main()
