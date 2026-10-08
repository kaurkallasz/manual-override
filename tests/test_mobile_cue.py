"""Cue execution advances only on confirmed poses and authoritative placement."""
import json
import tempfile
import unittest
from pathlib import Path
from test_photon_framework import load


class CueTests(unittest.TestCase):
    def setUp(self):
        self.game = load('photon-game')
        bundle = load('photon-level').runtime_bundle()
        self.engine = self.game.DefenseEngine(bundle['runtime'], bundle['waves'])
        self.engine.set_virtual_play(True)
        self.engine.set_virtual_test_loadout(None, 4)
        self.arm = self.engine.mobile_arm
        self.token = self.arm.command({'action': 'connect', 'client_id': 'a'*32, 'request_id': 'b'*32}, self.engine)['session']
        self.seq = 0
        self.destinations = []
        for marker in self.arm.markers():
            if marker['kind'] != 'socket': continue
            try:
                for z in (60, 80): self.arm.solve_xyz({'x': marker['x'], 'y': marker['y'], 'z': z})
                self.destinations.append(marker['id'])
            except ValueError: pass
        self.assertGreaterEqual(len(self.destinations), 2)

    def command(self, action, **fields):
        self.seq += 1
        return self.arm.command({'action': action, 'session': self.token, 'sequence': self.seq,
                                 'control_revision': self.arm.control_revision, **fields}, self.engine)

    def until(self, predicate, steps=2400):
        for _ in range(steps):
            self.engine.step(.05)
            if predicate(): return
        self.fail(str(self.arm.cue.snapshot()))

    def rows(self, pieces=(100, 101)):
        return [{'piece': piece, 'destination': self.destinations[i]} for i, piece in enumerate(pieces)]

    def test_two_rows_complete_and_move_pieces(self):
        self.command('cue_set', rows=self.rows())
        self.command('cue_play', height=80)
        self.until(lambda: self.arm.cue.status != 'running')
        self.assertEqual(self.arm.cue.status, 'completed', self.arm.cue.error)
        for row in self.rows():
            sid = self.engine.level.socket_by_marker[row['destination']]
            self.assertEqual(self.engine.placements[sid]['atom_tag_id'], row['piece'])
        self.assertIsNone(self.arm.held)
        self.assertEqual(self.arm.cue.index, 1)

    def test_pause_holds_piece_and_resume_does_not_repeat_release(self):
        self.command('cue_set', rows=self.rows((100,)))
        self.command('cue_play', height=80)
        self.until(lambda: self.arm.held == 100 and self.arm.cue.stage == 'Move')
        self.engine.step(.05)
        self.command('cue_pause'); pose = list(self.arm.joints)
        for _ in range(20): self.engine.step(.05)
        self.assertEqual(self.arm.joints, pose)
        self.assertEqual(self.arm.held, 100)
        with self.assertRaises(ValueError): self.command('xyz', xyz=self.arm.pose()['tip'])
        with self.assertRaises(ValueError): self.command('pump', mode='off')
        self.command('cue_play', height=80)
        self.until(lambda: self.arm.cue.status != 'running')
        self.assertEqual(self.arm.cue.status, 'completed', self.arm.cue.error)
        self.assertEqual(len(self.engine.placements), 1)

    def test_clear_view_follows_placement_and_uses_the_selected_view_direction(self):
        for rotation in (0, 180):
            with self.subTest(rotation=rotation):
                self.setUp()
                rows = self.rows((100,)) + [{'action': 'clear_view'}]
                marker = next(m for m in self.arm.markers() if m['id'] == rows[0]['destination'])
                self.command('cue_set', rows=rows)
                self.command('cue_play', height=80, view_rotation=rotation)
                self.until(lambda: self.arm.cue.status != 'running')
                self.assertEqual(self.arm.cue.status, 'completed', self.arm.cue.error)
                self.assertAlmostEqual(self.arm.pose()['tip']['x'], marker['x'] + (50 if rotation else -50), places=3)
                self.assertAlmostEqual(self.arm.tags[100]['x'], marker['x'], places=3)
                self.assertEqual(len(self.engine.placements), 1)
                self.assertEqual(self.arm.pump, 'off')
                self.assertIsNone(self.arm.held)

    def test_clear_view_custom_direction_distance_and_canonical_receipts(self):
        for rotation in (0, 180):
            for direction in ('left', 'right'):
                with self.subTest(rotation=rotation, direction=direction):
                    self.setUp()
                    rows = self.rows((100,)) + [{'action': 'clear_view', 'direction': direction, 'distance_cm': 7.5}]
                    marker = next(m for m in self.arm.markers() if m['id'] == rows[0]['destination'])
                    self.command('cue_set', rows=rows)
                    with self.assertRaisesRegex(ValueError, 'selection changed'):
                        self.command('cue_play', rows=self.rows((100,)) + [{'action': 'clear_view'}])
                    self.command('cue_play', rows=rows, height=80, view_rotation=rotation)
                    self.until(lambda: self.arm.cue.status != 'running')
                    self.assertEqual(self.arm.cue.status, 'completed', self.arm.cue.error)
                    offset = 75 * (1 if rotation else -1) * (-1 if direction == 'right' else 1)
                    self.assertAlmostEqual(self.arm.pose()['tip']['x'], marker['x'] + offset, places=3)
                    self.assertIsNone(self.arm.held)
                    self.assertEqual(self.arm.pump, 'off')
        for distance in (0, -1, 51, float('nan'), float('inf'), '5', True, None):
            with self.assertRaises(ValueError):
                self.command('cue_set', rows=self.rows((100,)) + [{'action': 'clear_view', 'distance_cm': distance}])
        with self.assertRaises(ValueError):
            self.command('cue_set', rows=self.rows((100,)) + [{'action': 'clear_view', 'direction': 'up'}])

    def test_clear_view_requires_a_placement_and_pause_keeps_the_same_clearance_goal(self):
        for rows in ([{'action': 'clear_view'}], self.rows((100,)) + [{'action': 'clear_view'}]*2,
                     self.rows((100,)) + [{'action': 'clear_view', 'distance': 999}]):
            with self.assertRaises(ValueError): self.command('cue_set', rows=rows)
        self.command('cue_set', rows=self.rows((100,)) + [{'action': 'clear_view'}])
        self.command('cue_play', height=80)
        self.until(lambda: self.arm.cue.index == 1 and self.arm.cue.stage == 'Clear view')
        goal = list(self.arm.cue.goal)
        self.command('cue_pause');self.command('cue_play', height=80, view_rotation=180)
        self.assertEqual(self.arm.cue.goal, goal)
        self.until(lambda: self.arm.cue.status != 'running')
        self.assertEqual(self.arm.cue.status, 'completed', self.arm.cue.error)
        self.assertEqual(len(self.engine.placements), 1)

    def test_stop_and_session_loss_never_autoresume(self):
        self.command('cue_set', rows=self.rows())
        self.command('cue_play', height=80)
        self.until(lambda: self.arm.held == 100)
        self.command('cue_stop'); pose = list(self.arm.joints)
        self.engine.step(.1)
        self.assertEqual(self.arm.joints, pose)
        self.assertEqual(len(self.arm.cue.rows), 2)
        self.command('cue_play', height=80)
        self.command('suspend')
        self.assertEqual(self.arm.cue.status, 'stopped')
        self.arm.command({'action': 'connect', 'client_id': 'a'*32, 'request_id': 'c'*32}, self.engine)
        self.engine.step(.1)
        self.assertEqual(self.arm.cue.status, 'stopped')

    def test_rejected_rows_and_unreachable_pose_do_not_move(self):
        for rows in ([], self.rows()*17, [{'piece': 102, 'destination': self.destinations[0]}],
                     [{'piece': True, 'destination': 44}], [{'piece': 100, 'destination': 999}]):
            with self.assertRaises(ValueError): self.command('cue_set', rows=rows)
        self.command('cue_set', rows=self.rows())
        pose = list(self.arm.joints)
        with self.assertRaisesRegex(ValueError, 'travel height'):
            self.command('cue_play', height=10000)
        self.assertEqual(self.arm.cue.status, 'idle')
        self.assertEqual(self.arm.joints, pose)
        self.assertEqual(self.arm.targets, pose)

    def test_play_rejects_a_different_row_from_the_acknowledged_selection(self):
        self.command('cue_set', rows=self.rows())
        pose = list(self.arm.joints)
        wrong = [dict(row) for row in self.rows()]
        wrong[0]['destination'] = wrong[1]['destination']
        with self.assertRaisesRegex(ValueError, 'Cue selection changed'):
            self.command('cue_play', height=80, rows=wrong)
        self.assertEqual(self.arm.cue.status, 'idle')
        self.assertEqual(self.arm.joints, pose)

    def test_marker_disappearing_and_relock_freeze_motion(self):
        self.command('cue_set', rows=self.rows())
        self.command('cue_play', height=80)
        sid = self.engine.level.socket_by_marker[self.destinations[0]]
        del self.engine.level.sockets[sid]
        self.engine.step(.05)
        self.assertEqual(self.arm.cue.status, 'error')
        self.assertEqual(self.arm.targets, self.arm.joints)
        self.engine.set_virtual_test_loadout(None, 3)
        with self.assertRaises(ValueError): self.command('cue_play', height=80)

    def test_stale_revision_and_locked_tier_cannot_start_a_cue(self):
        self.command('cue_set', rows=self.rows())
        revision = self.arm.control_revision
        self.command('control_mode', mode='cue')
        with self.assertRaisesRegex(ValueError, 'mode changed'):
            self.command('cue_play', height=80, control_revision=revision)
        with self.assertRaisesRegex(ValueError, 'mode changed'):
            self.command('cue_play', height=80, control_revision=True)
        self.engine.set_virtual_test_loadout(None, 3)
        with self.assertRaisesRegex(ValueError, 'locked'):
            self.command('control_mode', mode='cue')
        self.assertNotEqual(self.arm.cue.status, 'running')

    def test_every_level_marker_and_height_is_reachable(self):
        for marker in self.arm.markers():
            for z in (0, 60, 80, 200, 400):
                point = {'x': marker['x'], 'y': marker['y'], 'z': z}
                solved = self.arm.solve_xyz(point)
                actual = self.arm.pose(solved)['tip']
                for axis in point: self.assertAlmostEqual(point[axis], actual[axis], places=5)
        rows = [{'piece': 100, 'destination': m['id']} for m in self.arm.markers() if m['kind'] == 'socket']
        self.command('cue_set', rows=rows)
        self.command('cue_play', height=400)
        self.until(lambda: self.arm.cue.status != 'running', steps=24000)
        self.assertEqual(self.arm.cue.status, 'completed', self.arm.cue.error)
        self.assertEqual(len(self.engine.placements), len(rows))

    def test_idle_click_moves_immediately_without_starting_or_editing_the_cue(self):
        point = {'x': self.arm.width*.2, 'y': self.arm.height*.2}
        for status in ('idle', 'stopped', 'completed', 'error'):
            self.arm.cue.status = status
            before = self.arm.cue.snapshot()
            self.command('cue_waypoint', point=point)
            self.until(lambda: max(abs(self.arm.pose()['tip'][k]-v) for k,v in {**point, 'z':80}.items()) < .001)
            self.assertEqual(self.arm.cue.snapshot(), before)
            self.assertIsNone(self.arm.held)
            point['x'] += 20
        self.command('cue_set', rows=self.rows((100,)))
        rows = self.arm.cue.snapshot()
        self.command('cue_waypoint', point=point)
        self.until(lambda: max(abs(self.arm.pose()['tip'][k]-v) for k,v in {**point, 'z':80}.items()) < .001)
        self.assertEqual(self.arm.cue.snapshot(), rows)
        self.command('cue_play', height=100)
        self.assertEqual(self.arm.cue.stage, 'Approach')
        self.until(lambda: self.arm.cue.status != 'running')
        self.assertEqual(self.arm.cue.status, 'completed', self.arm.cue.error)

    def test_height_override_preserves_xy_pump_and_cue_then_resumes(self):
        self.command('cue_set', rows=self.rows((100,)))
        before = self.arm.cue.snapshot()
        tip = self.arm.pose()['tip']
        self.command('xyz', height_only=True, xyz={'x': 0, 'y': 0, 'z': 90})
        self.assertEqual(self.arm.cue.snapshot(), before)
        goal = self.arm.pose(self.arm.targets)['tip']
        for axis in ('x', 'y'): self.assertAlmostEqual(goal[axis], tip[axis])
        self.assertAlmostEqual(goal['z'], 90)
        self.command('cue_play', height=80)
        self.until(lambda: self.arm.held == 100 and self.arm.cue.stage == 'Move')
        original_goal = list(self.arm.cue.goal)
        pump = self.arm.pump
        self.command('cue_pause')
        tip = self.arm.pose()['tip']
        self.command('xyz', height_only=True, xyz={'x': -9999, 'y': -9999, 'z': 110})
        self.assertEqual(self.arm.cue.status, 'paused')
        self.assertEqual(self.arm.cue.goal, original_goal)
        self.until(lambda: abs(self.arm.pose()['tip']['z']-110) < .001)
        for axis in ('x', 'y'): self.assertAlmostEqual(self.arm.pose()['tip'][axis], tip[axis])
        self.assertEqual(self.arm.held, 100)
        self.assertEqual(self.arm.pump, pump)
        self.command('cue_play', height=80)
        self.command('xyz', height_only=True, xyz={'z': 120})
        self.assertEqual(self.arm.cue.stage, 'Waypoint')
        self.assertEqual(self.arm.cue.index, 0)
        self.until(lambda: self.arm.cue.status != 'running')
        self.assertEqual(self.arm.cue.status, 'completed', self.arm.cue.error)
        self.assertEqual(len(self.engine.placements), 1)

    def test_invalid_height_cannot_replace_a_cue_goal_and_stop_clears_override(self):
        self.command('cue_set', rows=self.rows((100,)))
        self.command('cue_play', height=80)
        before, target = self.arm.cue.snapshot(), list(self.arm.targets)
        for z in (None, True, float('nan'), -1, 401):
            with self.assertRaises(ValueError): self.command('xyz', height_only=True, xyz={'z': z})
            self.assertEqual(self.arm.cue.snapshot(), before)
            self.assertEqual(self.arm.targets, target)
        with self.assertRaisesRegex(ValueError, 'mode changed'):
            self.command('xyz', height_only=True, xyz={'z': 90}, control_revision=-1)
        self.command('xyz', height_only=True, xyz={'z': 110})
        self.command('cue_stop')
        self.assertIsNone(self.arm.cue.waypoint)
        frozen = list(self.arm.joints)
        self.engine.step(.1)
        self.assertEqual(self.arm.joints, frozen)

    def test_waypoint_replacement_pause_cancel_and_resume_preserve_held_piece(self):
        self.command('cue_set', rows=self.rows((100,)))
        self.command('cue_play', height=80)
        self.until(lambda: self.arm.held == 100 and self.arm.cue.stage == 'Move')
        original = list(self.arm.cue.goal)
        self.command('cue_waypoint', point={'x': 100, 'y':100})
        self.assertEqual(self.arm.cue.goal, original)
        self.engine.step(.1)
        self.command('cue_pause'); frozen = list(self.arm.joints)
        point = {'x': self.arm.width-10, 'y':10}
        self.command('cue_waypoint', point=point)
        self.engine.step(.1)
        self.assertNotEqual(self.arm.joints, frozen, 'Player clicks move immediately even while the cue remains paused')
        self.assertEqual(self.arm.held, 100)
        self.assertEqual(self.arm.cue.status, 'paused')
        frozen = list(self.arm.joints)
        self.command('cue_cancel_waypoint')
        self.engine.step(.1)
        self.assertIsNone(self.arm.cue.waypoint)
        self.assertEqual(self.arm.joints, frozen)
        self.command('cue_waypoint', point=point)
        self.command('cue_play', height=80)
        previous = list(self.arm.joints)
        self.engine.step(.1)
        self.assertTrue(all(abs(a-b)<=1.200001 for a,b in zip(previous,self.arm.joints)), 'waypoint cannot teleport')
        self.until(lambda: max(abs(self.arm.pose()['tip'][k]-v) for k,v in {**point, 'z':80}.items()) < .001)
        self.assertEqual(self.arm.held, 100)
        self.assertEqual(self.arm.cue.index, 0)
        self.until(lambda: self.arm.cue.status != 'running')
        self.assertEqual(self.arm.cue.status, 'completed', self.arm.cue.error)
        self.assertIsNone(self.arm.cue.waypoint)
        self.assertEqual(len(self.engine.placements), 1)

    def test_waypoint_rejection_and_lifecycle_cleanup(self):
        self.command('cue_set', rows=self.rows((100,)))
        self.command('cue_waypoint', point={'x':100,'y':100})
        before = self.arm.cue.snapshot()
        target = list(self.arm.targets)
        with self.assertRaisesRegex(ValueError, 'travel height'):
            self.command('cue_play', height=10000)
        self.assertEqual(self.arm.cue.snapshot(), before)
        for point in (None, {}, {'x':True,'y':1}, {'x':float('nan'),'y':1}, {'x':-1,'y':1}, {'x':1,'y':self.arm.height+1}):
            with self.assertRaises(ValueError): self.command('cue_waypoint', point=point)
            self.assertEqual(self.arm.cue.snapshot(), before)
            self.assertEqual(self.arm.targets, target)
        with self.assertRaisesRegex(ValueError, 'mode changed'):
            self.command('cue_waypoint', point={'x':1,'y':1}, control_revision=-1)
        self.command('cue_stop');self.assertIsNone(self.arm.cue.waypoint)
        self.command('cue_waypoint', point={'x':100,'y':100})
        self.command('control_mode', mode='targeting');self.assertIsNone(self.arm.cue.waypoint)
        self.command('control_mode', mode='cue')
        self.command('cue_waypoint', point={'x':100,'y':100})
        self.command('suspend');self.assertIsNone(self.arm.cue.waypoint)

    def test_piece_configuration_preserves_roles_and_validates_conflicts(self):
        settings = {**self.engine.settings, 'green_piece_1': 104, 'green_piece_2': 105,
                    'purple_piece_1': 106, 'purple_piece_2': 107}
        self.engine.configure_piece_codes(settings)
        self.assertEqual(list(self.arm.tags), [104, 105])
        self.assertEqual(self.engine.atom_owners[106], 'purple')
        sid = self.engine.level.socket_by_marker[self.destinations[0]]
        self.engine.place(104, sid, source='virtual', team='green')
        self.assertEqual(self.engine.placements[sid]['tower_type'], 'machine_gun')
        with self.assertRaises(ValueError): self.engine.place(100, sid, source='virtual')
        with self.assertRaises(ValueError): self.engine.configure_piece_codes({**settings, 'green_piece_1': 38})
        with self.assertRaises(ValueError): self.engine.configure_piece_codes({**settings, 'green_piece_1': 106})
        self.engine.start(settings)
        self.assertEqual(list(self.engine.mobile_arm.tags), [104, 105])
        self.assertEqual(self.engine.atom_owners[106], 'purple')

    def test_legacy_settings_migrate_and_new_ids_persist(self):
        from photon_game_runtime.settings import DEFAULTS, validate_settings
        clean, errors = validate_settings({**DEFAULTS, 'green_piece_1': True})
        self.assertIn('green_piece_1', errors)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'settings.json'
            legacy = {k: v for k, v in DEFAULTS.items() if '_piece_' not in k}
            path.write_text(json.dumps({'schema_version': 1, 'settings': legacy}))
            store = self.game.SettingsStore(path)
            self.assertIsNone(store.error)
            self.assertEqual(store.snapshot()['green_piece_1'], 100)
            store.update({**store.snapshot(), 'green_piece_1': 104})
            self.assertEqual(self.game.SettingsStore(path).snapshot()['green_piece_1'], 104)

if __name__ == '__main__': unittest.main()
