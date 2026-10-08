"""Run: .venv/bin/python -m unittest discover -s tests -p test_atom_tower_buff.py

Real Board/Game code with isolated observations; never connects to hardware.
"""
import copy
import time
import unittest
from unittest import mock
from test_photon_framework import load, FakeContext


class AtomBuffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.board = load('photon-board')
        cls.game = load('photon-game')
        cls.bundle = load('photon-level').runtime_bundle()

    def setUp(self):
        self.engine = self.game.DefenseEngine(self.bundle['runtime'], self.bundle['waves'])
        self.engine.set_virtual_play(True)
        self.tracker = self.board.OccupancyTracker()
        self.placement = self.board.PhysicalPlacementTracker()
        self.now = time.time()

    def sample(self, positions=None, *, delta=.2, ready=True, frame=None, connected=True,
               pump='off', geometry=1, ingest=False):
        self.now += delta
        positions = {40: (.4, .4), 100: (.4, .4)} if positions is None else positions
        tags = [{'id': tag, 'nx': xy[0], 'ny': xy[1], 'missing': 0} for tag, xy in positions.items()]
        raw = {'status': 'ready' if ready else 'unavailable', 'corrected': True,
               'source': 'camera', 'camera_revision': geometry, 'width': 1000, 'height': 1000,
               'observed_at': self.now, 'frame_at': self.now if frame is None else frame,
               'tags': tags, 'detections': tags, 'visible_ids': list(positions),
               'arms': {side: {'connected': connected, 'enabled': True,
                       'pump_mode': pump, 'feedback_at': self.now} for side in ('green', 'purple')}}
        result = self.tracker.update(raw, self.now)
        clean = self.game._validated_occupancy(result, self.now)
        if ready:
            self.assertEqual(clean['status'], 'ready', clean.get('error'))
        if ingest:
            placement = self.placement.update(raw, self.now)
            self.engine.ingest_physical({**placement, 'occupancy': clean})
        return result

    def acquire(self, **kwargs):
        for _ in range(4):
            result = self.sample(**kwargs)
        return result

    def physical(self):
        self.engine.set_virtual_play(False)
        self.engine.start()
        self.engine.run_started_at = self.now - 10

    def test_health_removal_and_one_heal_per_real_return(self):
        e = self.engine
        e.settings.update(core_hp=100, defense_unit_health_percent=100,
                          tower_link_start_multiplier=1, tower_link_step=0)
        e.core_max_hp = 100
        e.place(100, 'socket_01', source='virtual')
        t = e.placements['socket_01']
        self.assertEqual((t['hp'], t['max_hp']), (200, 200))
        t['hp'] -= 50
        e.place(100, 'socket_01', source='virtual')
        self.assertEqual(t['hp'], 150)
        e.place(100, None, source='virtual')
        self.assertEqual((t['hp'], t['max_hp']), (75, 100))
        self.assertEqual(t['atom_damage_multiplier'], 1)
        e.place(100, 'socket_01', source='virtual')
        self.assertEqual((t['hp'], t['max_hp']), (200, 200))
        self.assertEqual(sum(x['kind'] == 'tower_replenished' for x in e.events), 1)

    def test_one_atom_transfers_buff_without_removing_previous_turret(self):
        e = self.engine
        e.place(100, 'socket_01', source='virtual')
        e.place(100, 'socket_03', source='virtual')
        self.assertEqual(len(e.placements), 2)
        self.assertEqual(e.placements['socket_01']['atom_damage_multiplier'], 1)
        self.assertEqual(e.placements['socket_03']['atom_damage_multiplier'], 2)
        e.place(103, 'socket_03', source='virtual')
        t = e.placements['socket_03']
        self.assertEqual((t['owner'], t['tower_type'], t['occupying_atom_id']), ('green', 'machine_gun', 103))
        self.assertEqual(t['max_hp'], t['normal_max_hp'] * 2)
        e.place(100, 'socket_03', source='virtual')
        self.assertEqual(t['occupying_atom_id'], 100)

    def test_mobile_pickup_release_and_wrong_team(self):
        e = self.engine
        e.place(100, 'socket_01', source='virtual')
        t, arm = e.placements['socket_01'], e.mobile_arm
        with self.assertRaises(PermissionError):
            e.remove_atom(100, source='virtual', team='purple')
        self.assertEqual(t['atom_damage_multiplier'], 2)
        with mock.patch.object(arm, 'pose', return_value={'tip': {'x': t['x'], 'y': t['y'], 'z': 0}}):
            arm.set_pump('suction', e, piece=100)
            self.assertEqual(t['atom_damage_multiplier'], 1)
            arm.set_pump('off', e, destination=t['aruco_id'])
            self.assertEqual(t['atom_damage_multiplier'], 2)
        self.assertIsNone(arm.held)

    def test_connected_fields_repair_only_on_new_visit(self):
        e = self.engine
        e.place(100, 'socket_01', source='virtual')
        e.place(101, 'socket_03', source='virtual')
        field = next(iter(e.force_fields.values()))
        field.update(hits=7, broken=True)
        e.placements['socket_03']['hp'] *= .5
        e.place(101, 'socket_03', source='virtual')
        self.assertEqual(field['hits'], 7)
        self.assertTrue(field['broken'])
        e.remove_atom(101, source='virtual')
        self.assertEqual(field['hits'], 7)
        e.place(101, 'socket_03', source='virtual')
        self.assertEqual(field['hits'], 0)
        self.assertFalse(field['broken'])
        self.assertEqual(e.placements['socket_03']['hp'], e.placements['socket_03']['max_hp'])

    def test_virtual_core_placement_ends_tower_buff(self):
        e = self.engine
        e.place(100, 'socket_01', source='virtual')
        e.start()
        e.ring_completed_at = 0
        e.core_stage = 'ring_ready'
        e.activate_core_tag(100, source='virtual')
        self.assertEqual(e.placements['socket_01']['atom_damage_multiplier'], 1)
        self.assertEqual(e.core_stage, 'first_tag')

    def test_continuity_beyond_marker_memory_and_unrelated_arm_activity(self):
        self.physical()
        self.acquire(ingest=True)
        t = self.engine.placements['socket_01']
        t['hp'] *= .5
        for _ in range(610):
            result = self.sample({100: (.4, .4)}, connected=False, pump='suck', ingest=True)
        self.assertNotIn(40, self.placement.marker_cache)
        self.assertEqual(result['relations'][0]['state'], 'present')
        self.assertEqual(t['atom_buff_state'], 'active')
        self.assertAlmostEqual(t['hp'] / t['max_hp'], .5)
        self.assertFalse(any(x['kind'] == 'tower_replenished' for x in self.engine.events))
        self.sample({}, delta=.4, ingest=True)
        self.assertNotEqual(t['atom_buff_state'], 'active')
        self.acquire(positions={100: (.4, .4)}, connected=False, ingest=True)
        self.assertEqual(t['atom_buff_state'], 'active')
        self.assertAlmostEqual(t['hp'] / t['max_hp'], .5)

    def test_dropout_pump_toggle_and_geometry_recovery_do_not_heal(self):
        self.physical()
        self.acquire(ingest=True)
        t = self.engine.placements['socket_01']
        t['hp'] *= .75
        for _ in range(4):
            self.sample(pump='suck', ingest=True)
        self.acquire(ingest=True)
        self.assertAlmostEqual(t['hp']/t['max_hp'], .75)
        self.sample(ready=False, ingest=True)
        self.assertEqual(t['atom_buff_state'], 'unavailable')
        self.assertEqual(t['atom_damage_multiplier'], 1)
        t['hp'] *= .5  # Damage during tracking loss must survive recovery.
        self.acquire(ingest=True)
        self.assertAlmostEqual(t['hp']/t['max_hp'], .375)
        self.acquire(geometry=2, ingest=True)
        self.assertAlmostEqual(t['hp']/t['max_hp'], .375)
        self.assertFalse(any(x['kind'] == 'tower_replenished' for x in self.engine.events))
        self.sample({40: (.4, .4), 100: (.7, .7)}, geometry=2, ingest=True)
        self.assertEqual(t['atom_damage_multiplier'], 1)
        self.acquire(geometry=2, ingest=True)
        self.assertEqual(t['hp'], t['max_hp'])
        self.assertEqual(sum(x['kind'] == 'tower_replenished' for x in self.engine.events), 1)

    def test_unknown_is_not_departure_and_new_frames_are_required(self):
        self.acquire()
        result = self.sample({40: (.4, .4)}, delta=.4)
        self.assertEqual(result['relations'][0]['state'], 'unavailable')
        self.assertIsNone(result['relations'][0]['departed_at'])
        frame = self.now + .2
        for _ in range(5):
            result = self.sample(frame=frame)
        self.assertNotEqual(result['relations'][0]['state'], 'present')
        self.assertEqual(self.acquire()['relations'][0]['state'], 'present')

    def test_ambiguous_candidates_never_buff(self):
        for positions in ({40: (.4, .4), 100: (.4, .4), 101: (.4, .4)},
                          {40: (.4, .4), 42: (.41, .4), 100: (.4, .4)}):
            self.tracker = self.board.OccupancyTracker()
            result = self.acquire(positions=positions)
            self.assertFalse(any(r['state'] == 'present' for r in result['relations']))

    def test_validator_rejects_malformed_and_stale_contracts(self):
        result = self.acquire()
        for field, value in [('version', True), ('version', 2), ('sampled_at', self.now-3),
                             ('source_epoch', ''), ('frame_at', float('nan'))]:
            bad = {**result, field: value}
            self.assertEqual(self.game._validated_occupancy(bad, self.now)['status'], 'unavailable')
        bad = copy.deepcopy(result)
        bad['relations'].append(copy.deepcopy(bad['relations'][0]))
        self.assertEqual(self.game._validated_occupancy(bad, self.now)['status'], 'unavailable')

    def test_paused_departure_and_destroyed_turret_do_not_resurrect(self):
        self.physical()
        self.acquire(ingest=True)
        t = self.engine.placements['socket_01']
        self.engine.paused = True
        self.sample({40: (.4, .4), 100: (.7, .7)}, ingest=True)
        self.assertEqual(t['atom_damage_multiplier'], 1)
        self.acquire(ingest=True)
        t['destroyed'] = True
        t['hp'] = 0
        self.sample(ready=False, ingest=True)
        self.acquire(ingest=True)
        self.assertIs(self.engine.placements['socket_01'], t)
        self.assertEqual(t['hp'], 0)
        self.assertEqual(t['atom_buff_state'], 'inactive')
        self.sample({40: (.4, .4), 100: (.7, .7)}, ingest=True)
        self.acquire(ingest=True)
        self.assertIsNot(self.engine.placements['socket_01'], t)

    def test_start_reset_mode_and_l4_share_health(self):
        e = self.engine
        e.set_virtual_test_loadout(dict.fromkeys(('damage-machine-gun', 'damage-flamethrower',
                                      'damage-mortar', 'damage-tesla-coil', 'forcefield'), 4))
        e.place(100, 'socket_01', source='virtual')
        e.start()
        t = e.placements['socket_01']
        self.assertEqual(t['max_hp'], t['normal_max_hp'] * 2)
        t['hp'] *= .4
        e.set_virtual_test_loadout(dict.fromkeys(e.virtual_test_loadout, 3))
        self.assertAlmostEqual(t['hp']/t['max_hp'], .4)
        e.set_virtual_test_loadout(dict.fromkeys(e.virtual_test_loadout, 4))
        state = e.snapshot()
        self.assertEqual(state['companions'][0]['hp'], state['towers'][0]['hp'])
        self.assertEqual(state['companions'][0]['atom_damage_multiplier'], 2)
        e.set_virtual_play(False)
        self.assertEqual(t['atom_damage_multiplier'], 1)
        e.reset()
        self.assertEqual(e.atom_presence, {})
        self.assertEqual(e.atom_visits, {})

    def attack(self, atom, buff, *, companion=False):
        e = self.game.DefenseEngine(self.bundle['runtime'], self.bundle['waves'])
        e.set_virtual_play(True)
        if companion:
            e.set_virtual_test_loadout(dict.fromkeys(('damage-machine-gun', 'damage-flamethrower',
                                          'damage-mortar', 'damage-tesla-coil', 'forcefield'), 4))
        e.place(atom, 'socket_01', source='virtual')
        if not buff:
            e.remove_atom(atom, source='virtual')
        e.runtime_time = e.sim_time = 10
        t = e.placements['socket_01']
        t.update(aim_angle=0, aim_spread=.5)
        units = [t, *e._sync_companions()]
        for i, unit in enumerate(units, 1):
            targeting = e._tower_targeting(unit)
            if atom == 102:
                x, y = targeting['target_x'], targeting['target_y']
            elif atom == 101:
                x, y = e._flamethrower_path(unit, targeting)[4]
            else:
                x, y = unit['x']+25, unit['y']
            e.enemies[i] = {'id': i, 'x': x, 'y': y, 'hp': 10000., 'progress': i}
        # Tesla exercises multiple chain hits as well as the initial target.
        if atom == 103:
            e.enemies[20] = {**e.enemies[1], 'id': 20, 'x': e.enemies[1]['x']+10, 'progress': 20}
        e._fire_towers(2, set())
        if atom == 102:
            committed = [p['damage'] for p in e.pending_mortar_rounds]
            e.remove_atom(atom, source='virtual')
            self.assertEqual([p['damage'] for p in e.pending_mortar_rounds], committed)
            e.sim_time = 12
            e._resolve_mortar_rounds(set())
        return e, [10000-enemy['hp'] for enemy in e.enemies.values()]

    def test_all_weapon_damage_paths_and_companions_double_once(self):
        for companion in (False, True):
            for atom in range(100, 104):
                with self.subTest(companion=companion, atom=atom):
                    normal, base = self.attack(atom, False, companion=companion)
                    boosted, damage = self.attack(atom, True, companion=companion)
                    self.assertTrue(any(v > 0 for v in base))
                    for actual, expected in zip(damage, base):
                        self.assertAlmostEqual(actual, expected * 2)
                    self.assertEqual(normal.placements['socket_01']['cooldown'], boosted.placements['socket_01']['cooldown'])
                    if atom == 101:
                        for enemy_id, enemy in boosted.enemies.items():
                            self.assertEqual(enemy.get('burn_damage_per_s', 0), normal.enemies[enemy_id].get('burn_damage_per_s', 0)*2)
                        burn = copy.deepcopy(boosted.enemies)
                        boosted.remove_atom(atom, source='virtual')
                        self.assertEqual(boosted.enemies, burn)

    def test_camera_projection_survives_relay_failure_without_relaxing_placement(self):
        now = time.time()
        tags = [{'id': i, 'nx': .4, 'ny': .4, 'missing': 0} for i in (40, 100)]
        def producer(slug, *args):
            if slug == 'webcam':
                return {'tags': tags, 'detections': tags, 'visible_ids': [40, 100],
                        'frame_at': now, 'observed_at': now}, None
            if slug == 'camera-calibration':
                return {'corrected': True, 'tags': tags, 'detections': tags,
                        'observed_at': now, 'width': 1000, 'height': 1000}, None
            return None, 'relay disabled'
        with mock.patch.object(self.board, '_read_input', side_effect=producer), \
             mock.patch.object(self.board, '_simulation', {'enabled': False}):
            raw = self.board._runtime_input()
        self.assertEqual(raw['status'], 'unavailable')
        self.assertEqual(raw['tags'], [])
        self.assertEqual(raw['_occupancy_camera']['status'], 'ready')
        self.assertEqual([t['id'] for t in raw['_occupancy_camera']['detections']], [40, 100])
        self.assertNotIn('_occupancy_camera', self.board._fresh_runtime(raw, now, 1.5))

    def test_game_adapter_keeps_valid_occupancy_when_placement_unavailable(self):
        result = self.acquire()
        board = type('Board', (), {'occupancy_snapshot': lambda _: result})()
        with mock.patch.object(self.game, '_hub_ctx', FakeContext({'photon-board': board})), \
             mock.patch.object(self.game, '_board_observation', return_value=(None, 'Relay unavailable')), \
             mock.patch.object(self.game, '_set_input'), \
             mock.patch('time.time', return_value=self.now):
            value = self.game._physical_observation()
        self.assertEqual(value['status'], 'unavailable')
        self.assertEqual(value['occupancy']['status'], 'ready')
        self.assertEqual(value['occupancy']['relations'][0]['state'], 'present')


if __name__ == '__main__':
    unittest.main()
