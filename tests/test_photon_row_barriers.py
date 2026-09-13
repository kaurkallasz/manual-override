"""Smoke tests for the two-entry funnel, lifecycle, routing and swept walls."""
import copy
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from test_photon_framework import load, legacy_level_bundle, FakeContext


class RowBarrierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.level = load('photon-level')
        cls.game = load('photon-game')
        cls.bundle = cls.level.runtime_bundle()

    def engine(self, mask=0):
        e = self.game.DefenseEngine(self.bundle['runtime'], self.bundle['waves'])
        e.set_virtual_play(True)
        for i,row in enumerate(e.level.row_barriers):
            if mask & (1 << i):
                for socket in row['socket_ids']:
                    e.place(100, socket, source='virtual')
        e.runtime_time = 4
        e._refresh_row_barriers()
        return e

    def test_all_16_masks_have_two_routes_and_full_lock_winds(self):
        e = self.engine()
        self.assertEqual(self.bundle['version'], 2)
        self.assertEqual(set(e.level.spawns), {'top_outer','bottom_outer'})
        for mask in range(16):
            blocked = {edge for i,row in enumerate(e.level.row_barriers)
                       if mask & (1 << i) for edge in row['blocked_edges']}
            for spawn in e.level.spawns.values():
                route,cost = e.level._shortest_route_with_cost(e.level._node_id(spawn), blocked)
                self.assertFalse({edge['edge_id'] for edge in route} & blocked)
                if mask == 15:
                    self.assertEqual(cost, 4160)
                    points = e.level._points_for_edges(route)
                    self.assertTrue(any(a[0] > b[0] for a,b in zip(points,points[1:])))
                elif mask == 0:
                    self.assertEqual(cost, 1280)

    def test_each_turret_death_breaks_only_its_row_and_replacement_reactivates(self):
        for index, row in enumerate(self.bundle['runtime']['row_barriers']):
            for socket in row['socket_ids']:
                with self.subTest(socket=socket):
                    e = self.engine(15)
                    tower = e.placements[socket]
                    e._damage_towers([dict(x=tower['x'], y=tower['y'], tower_dps=1e9)], .1)
                    self.assertEqual(e._row_mask, 15 & ~(1 << index))
                    self.assertEqual(e._row_states[index]['active_count'], 2)
                    e.place(100, socket, source='virtual')
                    self.assertEqual(e.snapshot()['row_barriers'][index]['powered'], False)
                    e.runtime_time += 3.1
                    self.assertTrue(e.snapshot()['row_barriers'][index]['powered'])
                    self.assertEqual(e._row_mask, 15)

    def test_activation_order_and_completion_do_not_change_ordinary_links(self):
        e = self.engine()
        for socket in reversed(e.level.row_barriers[0]['socket_ids']):
            e.place(100, socket, source='virtual')
        fields = copy.deepcopy(e.force_fields)
        self.assertFalse(e.snapshot()['row_barriers'][0]['powered'])
        e.runtime_time += 2.99
        self.assertFalse(e.snapshot()['row_barriers'][0]['powered'])
        e.runtime_time += .02
        self.assertTrue(e.snapshot()['row_barriers'][0]['powered'])
        self.assertEqual(e.force_fields, fields)
        self.assertGreater(len(fields), 0)

    def test_spawn_routes_and_invalid_weight_fallback_obey_enabled_entrances(self):
        e = self.engine(15)
        e.force_fields.clear()
        for weights in ({}, {'top_inner':1}, {'bottom_inner':1}, {'top_outer':0},
                        {'top_outer':float('nan')}, {'top_outer':-1}, {'top_outer':'bad'}):
            e.enemies.clear()
            self.assertTrue(e._spawn_enemy('brute', weights))
            enemy = next(iter(e.enemies.values()))
            self.assertIn(enemy['lane'], ('top_outer','bottom_outer'))
            self.assertEqual(enemy['x'], 0)
            self.assertFalse({s['edge_id'] for s in enemy['route_steps']} & e._row_blocked_edges)
            self.assertEqual(enemy['hp'], 960)
        self.assertEqual(e.row_route_builds, 1)

    def test_congested_entrances_queue_and_resume_without_inner_spawns(self):
        e = self.engine(15)
        e.phase = 'running'
        e._launch_wave(1)
        with mock.patch.object(e, '_spawn_enemy', return_value=False):
            e._spawn_due()
        self.assertGreater(e.pressure_bank, 0)
        queued = e.pressure_bank
        e._spawn_due()
        self.assertLess(e.pressure_bank, queued)
        self.assertTrue(all(v['lane'] in e.level.spawns for v in e.enemies.values()))

    def test_closure_mid_edge_keeps_position_and_exits_on_current_side(self):
        for y in (130, 190):
            e = self.engine()
            e._spawn_enemy('grunt', {'top_outer':1})
            enemy = e.enemies[1]
            enemy.update(x=400., y=float(y), route_steps=[dict(edge_id='edge_switch_top_a_down',reverse=False)],current_route_step=0)
            for socket in e.level.row_barriers[0]['socket_ids']:
                e.place(100, socket, source='virtual')
            e.runtime_time += 4
            e.force_fields.clear()
            e._refresh_row_barriers()
            self.assertTrue(e._reroute_row_enemy(enemy))
            self.assertEqual((enemy['x'],enemy['y']), (400.,float(y)))
            self.assertTrue(e._row_prefix_clear(enemy['path']))
            self.assertEqual(enemy['route_steps'][0]['reverse'], y < 160)

    def test_break_reopens_shortcut_and_rerouting_is_bounded_and_shared(self):
        e = self.engine(15)
        e.force_fields.clear()
        e._spawn_enemy('grunt', {'top_outer':1})
        original = e.enemies[1]
        for i in range(2,1001):
            e.enemies[i] = {**copy.deepcopy(original), 'id':i}
        builds = e.row_route_builds
        for socket in [r['socket_ids'][0] for r in e.level.row_barriers]:
            e.placements[socket]['destroyed'] = True
        e._refresh_row_barriers()
        e._reroute_rows_batch()
        self.assertEqual(len(e._row_reroute_queue), 952)
        self.assertEqual(e.row_route_builds, builds+1)
        for _ in range(21): e._reroute_rows_batch()
        self.assertFalse(e._row_reroute_queue)
        self.assertTrue(all(v['row_route_revision'] == e.row_topology_revision for v in e.enemies.values()))
        self.assertIn('edge_switch_top_a_down', [s['edge_id'] for s in original['route_steps']])

    def test_swept_barriers_stop_fast_grunts_brutes_and_endpoint_leakage(self):
        e = self.engine(15)
        for radius in (2.8,20):
            for row in e._active_rows:
                y = row['ay']; x = (row['ax'] + row['bx']) / 2
                for direction in (-1,1):
                    origin = (x, y-direction*100)
                    enemy = dict(x=x,y=y+direction*100,vx=0,vy=direction*1000,collision_radius=radius,attacking=False)
                    e._clip_row_motion(enemy,origin)
                    self.assertLess((enemy['y']-y)*direction, -radius)
                gap_x = row['bx']+80 if row['opening_side']=='right' else row['ax']-80
                enemy = dict(x=gap_x,y=y+50,vx=0,vy=1000,collision_radius=radius,attacking=False)
                e._clip_row_motion(enemy,(gap_x,y-50))
                self.assertEqual(enemy['y'], y+50)
                if row['opening_side']=='left':
                    enemy = dict(x=row['ax']+100,y=y,vx=1000,vy=0,collision_radius=radius,attacking=False)
                    e._clip_row_motion(enemy,(row['ax']-100,y))
                    self.assertLess(enemy['x'],row['ax']-radius)

    def test_crowd_separation_cannot_push_through_a_row(self):
        e = self.engine(15)
        e.force_fields.clear();e._spawn_enemy('brute',{'top_outer':1})
        enemy=e.enemies[1]
        enemy.update(x=400.,y=150.,path=[(400.,80.),(400.,240.)],segment=0)
        def push(_): enemy['y']=175
        with mock.patch.object(e,'_resolve_particle_contacts',side_effect=push):
            e._integrate_particles([enemy],.05,{})
        self.assertLess(enemy['y'],160-enemy['collision_radius'])

    def test_both_streams_physically_traverse_the_full_winding_route(self):
        for lane, outer_y, inner_y in [('top_outer',160,320),('bottom_outer',800,640)]:
            e = self.engine(15)
            e.force_fields.clear();e._spawn_enemy('grunt',{lane:1})
            enemy=e.enemies[1];enemy['speed']=180
            crossings=[]
            for _ in range(1800):
                e.sim_time += .025
                old=(enemy['x'],enemy['y'])
                e._integrate_particles([enemy],.025,{})
                for y in (outer_y,inner_y):
                    if (old[1]-y)*(enemy['y']-y)<0:crossings.append((y,enemy['x']))
                e._admit_ready_particles([enemy])
                if enemy['attacking']:break
            self.assertTrue(enemy['attacking'], (lane,enemy['x'],enemy['y'],enemy['segment']))
            self.assertTrue(any(y==outer_y and x>1440 for y,x in crossings),crossings)
            self.assertTrue(any(y==inner_y and x<160 for y,x in crossings),crossings)

    def test_consumer_rejects_malformed_rows_and_accepts_legacy_v1(self):
        mutations = [lambda r:r.pop('row_barriers'),
                     lambda r:r.pop('enabled_spawn_groups'),
                     lambda r:r['row_barriers'][0].update(socket_ids=['socket_01']*3),
                     lambda r:r['row_barriers'][0].update(blocked_edges=[]),
                     lambda r:r['row_barriers'][0].update(ay=float('nan')),
                     lambda r:r['row_barriers'][0].update(opening_side='left'),
                     lambda r:r.update(enabled_spawn_groups=['top_inner','bottom_inner'])]
        for mutate in mutations:
            runtime=copy.deepcopy(self.bundle['runtime']);mutate(runtime)
            with self.assertRaises(ValueError):self.game.ContractLevelModel(runtime)
        legacy=legacy_level_bundle()
        model=self.game.ContractLevelModel(legacy['runtime'])
        self.assertEqual(len(model.spawns),4);self.assertFalse(model.row_barriers)
        waves=copy.deepcopy(self.bundle['waves'])
        waves[0]['groups'][0]['lane_weights']={'top_inner':1}
        with self.assertRaisesRegex(ValueError,'enabled spawn'):
            self.game.DefenseEngine(self.bundle['runtime'],waves)

    def test_editor_rejects_moved_row_socket_before_writing(self):
        raw=json.loads(Path(self.level.MAP_PATH).read_text())
        layer=next(l for l in raw['layers'] if 'Square Placement' in l['name'])
        socket=next(o for o in layer['objects'] if o['name']=='socket_01')
        socket['y']+=200
        # Keep relative tileset paths valid, without touching production.
        for ts in raw['tilesets']:
            ts['source']=str((Path(self.level.MAP_PATH).parent/ts['source']).resolve())
        with tempfile.TemporaryDirectory() as folder:
            candidate=Path(folder)/'candidate.tmj';candidate.write_text(json.dumps(raw))
            with self.assertRaisesRegex(ValueError,'row barrier band'):
                self.level.parse_tiled_level(candidate)

    def test_server_deadline_counts_work_time_without_extra_sleep(self):
        for work in (.04,.075):
            e=self.engine();clock=[0.0];steps=[]
            def wait(delay):
                if len(steps)==3:return True
                clock[0]+=delay
                return False
            def step(dt):
                steps.append(dt);clock[0]+=work
            with mock.patch.object(e._stop,'wait',side_effect=wait), mock.patch.object(e,'step',side_effect=step), mock.patch('photon_game_runtime.engine.time.monotonic',side_effect=lambda:clock[0]):
                e._run()
            for dt in steps[1:]:self.assertAlmostEqual(dt,max(.05,work))

    def test_active_v1_run_keeps_its_layout_until_reset(self):
        game=load('photon-game')
        game._install_level(legacy_level_bundle())
        game._engine.phase='running'
        game._hub_ctx=FakeContext({'photon-level':self.level})
        self.assertTrue(game._sync_level())
        self.assertEqual(game._engine.level.runtime_version,1)
        self.assertEqual(game._inputs['level']['pending_revision'],self.bundle['revision'])
        game._engine.reset()
        self.assertTrue(game._sync_level())
        self.assertEqual(game._engine.level.runtime_version,2)
        self.assertEqual(len(game._engine.level.row_barriers),4)

    def test_melee_broad_phase_keeps_fast_swept_hits(self):
        from photon_game_runtime.engine import TOWER_ATTACK_RADIUS
        e=self.engine()
        e.placements={'sample':dict(x=500.,y=500.,hp=10000.)}
        enemies=[dict(id=1,x=700.,y=500.,collision_radius=2.8,tower_dps=100),
                 dict(id=2,x=700.,y=900.,collision_radius=2.8,tower_dps=100)]
        e._damage_towers(enemies,.1,{1:(300.,500.),2:(300.,900.)})
        expected=100*.1*2*(TOWER_ATTACK_RADIUS+2.8)/400
        self.assertAlmostEqual(e.placements['sample']['hp'],10000-expected)


if __name__ == '__main__': unittest.main()
