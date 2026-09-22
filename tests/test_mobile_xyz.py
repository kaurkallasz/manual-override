"""Cartesian intent stays in the authoritative virtual-arm session."""
import math
import random
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from test_photon_framework import load, FakeContext


class XYZTests(unittest.TestCase):
    def setUp(self):
        self.game = load('photon-game')
        bundle = load('photon-level').runtime_bundle()
        self.engine = self.game.DefenseEngine(bundle['runtime'], bundle['waves'])
        self.engine.set_virtual_play(True)
        self.arm = self.engine.mobile_arm
        self.token = self.arm.command({'action': 'connect'}, self.engine)['session']
        self.seq = 0

    def command(self, action, **fields):
        self.seq += 1
        return self.arm.command({'action': action, 'session': self.token, 'sequence': self.seq, **fields}, self.engine)

    def unlock(self, tier=2):
        self.engine.set_virtual_test_loadout(None, tier)

    def xyz(self, point):
        return self.command('xyz', xyz=point, control_revision=self.arm.control_revision)

    def test_unlock_and_preview_enforcement(self):
        with self.assertRaisesRegex(ValueError, 'locked'):
            self.command('control_mode', mode='xyz')
        self.unlock(4)
        for mode in ('unknown', True, None):
            with self.assertRaisesRegex(ValueError, 'preview'):
                self.command('control_mode', mode=mode)
        self.command('control_mode', mode='xyz')
        self.assertEqual(self.arm.control_mode, 'xyz')
        with self.assertRaisesRegex(ValueError, 'Joint mode'):
            self.command('joints', joints=[0, 0, 0])

    def test_targeting_uses_xyz_validation_and_mode_revisions(self):
        self.unlock(2)
        with self.assertRaisesRegex(ValueError, 'locked'):
            self.command('control_mode', mode='targeting')
        self.unlock(3)
        self.assertEqual(self.arm.control_mode, 'targeting')
        point = self.arm.pose()['tip']
        point['x'] -= 40
        result = self.xyz(point)
        for axis in ('x', 'y', 'z'):
            self.assertAlmostEqual(result['xyz_target'][axis], point[axis])
        with self.assertRaisesRegex(ValueError, 'Joint mode'):
            self.command('joints', joints=[0, 0, 0])
        before = self.arm.targets[:]
        with self.assertRaises(ValueError):
            self.xyz({'x': float('nan'), 'y': 0, 'z': 60})
        self.assertEqual(self.arm.targets, before)
        revision = self.arm.control_revision
        self.unlock(2)
        self.assertEqual(self.arm.control_mode, 'xyz')
        self.assertEqual(self.arm.targets, self.arm.joints)
        with self.assertRaisesRegex(ValueError, 'mode changed'):
            self.command('xyz', xyz=point, control_revision=revision)

    def test_inverse_round_trip_and_nearest_branch(self):
        randomizer = random.Random(72)
        points = [{'x': x, 'y': y, 'z': z} for x in (0, self.arm.width)
                  for y in (0, self.arm.height) for z in (0, 400)]
        points += [{'x': randomizer.uniform(0, self.arm.width),
                    'y': randomizer.uniform(0, self.arm.height), 'z': randomizer.uniform(0, 400)} for _ in range(150)]
        points.append({'x': self.arm.width*.075, 'y': self.arm.height*.9, 'z': 60})
        for point in points:
            solved = self.arm.solve_xyz(point)
            actual = self.arm.pose(solved)['tip']
            for key in ('x', 'y', 'z'):
                self.assertAlmostEqual(point[key], actual[key], places=5)
            self.arm.joints = solved
            for a, b in zip(self.arm.solve_xyz(point), solved):
                self.assertAlmostEqual(a, b, places=4)

    def test_motion_actual_target_separation_and_convergence(self):
        self.unlock(); self.command('control_mode', mode='xyz')
        destination = {**self.arm.pose()['tip'], 'x': self.arm.width*.7, 'z': 80}
        original = self.arm.pose()['tip']
        state = self.xyz(destination)
        self.assertEqual(state['tip'], original)
        for axis in ('x', 'y', 'z'):
            self.assertAlmostEqual(state['xyz_target'][axis], destination[axis])
        travel_seconds = max(abs(a-b) for a,b in zip(self.arm.targets,self.arm.joints)) / 12
        for _ in range(math.ceil(travel_seconds/.05)+1):
            self.engine.step(.05)
        for axis in ('x', 'y', 'z'):
            self.assertAlmostEqual(self.arm.pose()['tip'][axis], destination[axis])

    def test_rejected_xyz_is_atomic(self):
        self.unlock(); self.command('control_mode', mode='xyz')
        valid = {'x': self.arm.width*.6, 'y': self.arm.height*.4, 'z': 120}
        self.xyz(valid)
        before = self.arm.targets[:]
        invalid = [None, [], {}, {'x': 1, 'y': 1}, {'x': True, 'y': 0, 'z': 0},
                   {'x': math.inf, 'y': 0, 'z': 0}, {'x': math.nan, 'y': 0, 'z': 0},
                   {'x': self.arm.width+1, 'y': 0, 'z': 400},
                   {'x': 0, 'y': 0, 'z': 401}]
        for point in invalid:
            with self.assertRaises(ValueError): self.xyz(point)
            self.assertEqual(self.arm.targets, before)
        self.assertTrue(self.arm.snapshot()['connected'])

    def test_mode_switch_and_relock_cancel_old_motion(self):
        self.command('pump', mode='suction')
        self.command('joints', joints=[-65, 30, 40])
        self.unlock(); self.command('control_mode', mode='xyz')
        self.assertEqual(self.arm.targets, self.arm.joints)
        self.assertEqual(self.arm.held, 100)
        revision = self.arm.control_revision
        self.xyz({'x': self.arm.width*.7, 'y': self.arm.height*.5, 'z': 80})
        self.unlock(1)
        self.assertEqual(self.arm.control_mode, 'joint')
        self.assertEqual(self.arm.targets, self.arm.joints)
        self.command('control_mode', mode='joint')
        with self.assertRaises(ValueError):
            self.command('joints', joints=[0, 0, 0], control_revision=revision)
        with self.assertRaises(ValueError):
            self.command('xyz', xyz=self.arm.pose()['tip'], control_revision=revision)

    def test_override_validation_reset_and_physical_guard(self):
        self.unlock(3)
        for tier in (0, 5, True, '2', 2.5):
            with self.assertRaises(ValueError): self.unlock(tier)
            self.assertEqual(self.engine.virtual_test_control, 3)
        self.engine.reset()
        self.assertEqual(self.engine.virtual_test_control, 3)
        with self.assertRaises(ValueError): self.unlock(2)
        self.engine.set_virtual_play(True)
        self.unlock(None)
        self.assertIsNone(self.engine.virtual_test_control)

    def test_default_follows_unlock_without_overriding_manual_choice_on_heartbeat(self):
        self.assertEqual(self.arm.control_mode, 'joint')
        self.command('joints', joints=[-65, 20, 30])
        self.unlock(2)
        self.assertEqual(self.arm.control_mode, 'xyz')
        self.assertEqual(self.arm.targets, self.arm.joints)
        self.command('control_mode', mode='joint')
        self.command('heartbeat')
        self.assertEqual(self.arm.control_mode, 'joint')
        self.unlock(2)  # Applying the same tier preserves a deliberate choice.
        self.assertEqual(self.arm.control_mode, 'joint')
        self.unlock(3)
        self.assertEqual(self.arm.control_mode, 'targeting')
        self.unlock(1)
        self.assertEqual(self.arm.control_mode, 'joint')

    def test_fresh_connection_defaults_to_highest_implemented_saved_or_test_unlock(self):
        for override, saved, expected in [(None, 1, 'joint'), (None, 2, 'xyz'),
                                           (None, 3, 'targeting'), (None, 4, 'cue'), (1, 4, 'joint'), (4, 1, 'cue')]:
            self.arm.halt()
            self.engine.set_virtual_test_loadout(None, override)
            self.arm.select_control('joint')
            result = self.arm.command({'action': 'connect'}, self.engine, saved)
            self.assertEqual(result['control_mode'], expected)
            self.assertEqual(self.arm.targets, self.arm.joints)

    def test_saved_progress_checked_server_side(self):
        fake = SimpleNamespace(progress_snapshot=lambda query: {'contract': 'photon.progress', 'version': 1, 'status': 'ready', 'player': {'unlocked_control': 2}})
        self.game._hub_ctx = FakeContext({'photon-progress': fake})
        with patch.object(self.game, '_require_engine', return_value=(self.engine, True)):
            result = self.game.mobile_command({'action': 'control_mode', 'mode': 'xyz', 'session': self.token, 'sequence': 1})
        self.assertEqual(result['control_mode'], 'xyz')
        fake.progress_snapshot = lambda query: {'contract': 'wrong', 'version': 1, 'player': {'unlocked_control': 4}}
        self.assertEqual(self.game._mobile_saved_control(), 1)


if __name__ == '__main__': unittest.main()
