"""Read-only motion intent from the real engine, including core and barriers."""
import copy
import importlib
import json
import math
import unittest
from test_photon_framework import load, FakeContext


class MotionGuideTests(unittest.TestCase):
    def setUp(self):
        self.game = load('photon-game')
        level = load('photon-level').runtime_bundle()
        self.engine = self.game.DefenseEngine(level['runtime'], level['waves'])
        self.engine.set_virtual_play(True)
        self.engine.phase = 'running'
        weights = {lane: 1 for lane in self.engine.level.enabled_spawn_groups}
        self.assertTrue(self.engine._spawn_enemy('grunt', weights))
        self.enemy = next(iter(self.engine.enemies.values()))

    def test_road_guide_is_bounded_owned_route_and_read_only(self):
        self.enemy.update(x=0, y=0, vx=100, vy=0, speed=100,
                          path=[(0,0),(40,0),(40,200)], segment=0,
                          row_route_revision=self.engine.row_topology_revision)
        before = copy.deepcopy(self.enemy)
        guide = self.engine._enemy_motion_guide(self.enemy)
        self.assertEqual(guide['mode'], 'road')
        self.assertEqual(guide['points'], [[40,0],[40,100]])
        self.assertEqual(self.enemy, before)
        full = self.engine.snapshot()
        compact = self.engine.snapshot(compact_enemies=True)
        self.assertEqual(full['enemy_motion']['contract'], 'photon.enemy-motion')
        self.assertEqual(full['enemies'][0]['motion'], compact['enemies'][0]['motion'])
        self.assertEqual(full['enemies'][0]['hp'], self.enemy['hp'])
        self.assertLess(len(json.dumps(guide)), 500)

    def test_stalls_pause_and_stale_routes_never_invent_motion(self):
        self.enemy['blocked_steps'] = 1
        self.assertEqual(self.engine._enemy_motion_guide(self.enemy)['mode'], 'hold')
        self.enemy['blocked_steps'] = 0
        self.engine.paused = True
        self.assertEqual(self.engine._enemy_motion_guide(self.enemy)['speed'], 0)
        self.engine.paused = False
        if self.engine.level.row_barriers:
            self.enemy['row_route_revision'] = -99
            self.assertEqual(self.engine._enemy_motion_guide(self.enemy)['mode'], 'hold')

    def test_orbit_guides_do_not_cut_through_the_core(self):
        runtime = importlib.import_module(self.engine.__class__.__module__)
        cx, cy = self.engine.level.core['x'], self.engine.level.core['y']
        for direction in (-1, 1):
            for angle in range(0,360,30):
                radius = self.enemy['collision_radius']
                self.enemy.update(attacking=True, x=cx+90*math.cos(math.radians(angle)),
                                  y=cy+90*math.sin(math.radians(angle)),vx=35,vy=0,
                                  basin_direction=direction,blocked_steps=0)
                self.engine._constrain_basin_particle(self.enemy)
                guide = self.engine._enemy_motion_guide(self.enemy)
                self.assertEqual(guide['mode'], 'orbit')
                a = (self.enemy['x'], self.enemy['y'])
                for b in guide['points']:
                    for n in range(21):
                        x=a[0]+(b[0]-a[0])*n/20
                        y=a[1]+(b[1]-a[1])*n/20
                        self.assertGreaterEqual(runtime._core_octagon_face(x-cx,y-cy,radius)[3], -.06)
                    a=b

    def test_mobile_projection_retains_combat_and_reports_build_timing(self):
        facade = load('mobile-ltz-api')
        state = {'contract':'photon.game','version':2,'status':'ready',**self.engine.snapshot()}
        class Game:
            def game_snapshot(self): return copy.deepcopy(state)
        facade.hub_init(FakeContext({'photon-game':Game()}))
        self.addCleanup(facade.hub_stop)
        first, second = facade.mobile_snapshot(), facade.mobile_snapshot()
        self.assertGreater(second['delivery']['sequence'], first['delivery']['sequence'])
        self.assertGreaterEqual(second['delivery']['build_ms'], 0)
        unit = second['enemies'][0]
        self.assertIn('motion', unit)
        self.assertEqual(unit['hp'], round(self.enemy['hp'],3))
        self.assertNotIn('track', unit)
        self.assertEqual(second['kills'], self.engine.kills)


if __name__ == '__main__': unittest.main()
