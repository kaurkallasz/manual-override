"""Run: .venv/bin/python -m unittest discover -s tests -p test_fixed_activation.py

Real Board sampler, scoped map, placement, occupancy and Game; fake camera/arms.
No browser, hardware connection, background thread or live commands.
"""
import copy
import time
import unittest
from unittest.mock import patch

from test_photon_framework import FakeContext, load


class FixedActivationTests(unittest.TestCase):
    def setUp(self):
        self.board = load('photon-board')
        self.game = load('photon-game')
        bundle = load('photon-level').runtime_bundle()
        self.engine = self.game.DefenseEngine(bundle['runtime'], bundle['waves'])
        self.now = time.time()
        self.engine.set_virtual_play(False)
        self.engine.start()
        self.engine.run_started_at = self.now - 10
        self.game._level_projection = self.game._simple_level(bundle['runtime'])
        self.game._run_id = 'run-a'
        self.game._hub_ctx = FakeContext({'photon-board': self.board})
        self.positions = {47: (.68, .49), 48: (.5, .5), 49: (.8, .5), 100: (.2, .3)}
        self.camera_revision = 'lens-a'

    @staticmethod
    def tag(ident, xy, size=.02):
        x, y = xy
        return dict(id=ident, nx=x, ny=y, missing=0,
                    ncorners=[[x-size,y-size],[x+size,y-size],[x+size,y+size],[x-size,y+size]])

    def sample(self, *, dt=.2, hidden=(), changes=None, connected=True, pump='off',
               enabled=True, frame_age=0, ready=True, relay_ready=True, ingest=True):
        self.now += dt
        tags = [self.tag(i, p) for i, p in self.positions.items() if i not in hidden]
        for tag in tags:
            tag.update((changes or {}).get(tag['id'], {}))
        camera = dict(status='ready' if ready else 'unavailable', source='camera', corrected=True,
                      camera_identity='camera-a', camera_revision=self.camera_revision,
                      width=1000, height=1000, frame_at=self.now-frame_age,
                      tags=tags, detections=tags, visible_ids=[t['id'] for t in tags])
        raw = dict(camera, contract='photon.board.runtime', version=1,
                   revision=1, observed_at=self.now, inputs={}, errors=[],
                   arms={side: dict(connected=connected, enabled=enabled, pump_mode=pump,
                                    feedback_at=self.now, pose=[0,0,0,0]) for side in ('green','purple')},
                   _occupancy_camera=copy.deepcopy(camera))
        if not relay_ready:
            raw.update(status='unavailable', arms={})
        with patch('time.time', return_value=self.now), patch.object(self.board, '_runtime_input', return_value=raw):
            # Game registers the map before the sampler, independently of any UI.
            self.game._physical_observation()
            self.board._sample_tracking()
            value = self.game._physical_observation()
            if ingest:
                self.engine.ingest_physical(value)
            return value

    def learn(self):
        for _ in range(4):
            value = self.sample()
        self.assertEqual(value['status'], 'ready')
        return self.board._cue_layouts[self.board._game_layout_key].snapshot(self.now)

    def hold(self, **kwargs):
        for _ in range(5):
            value = self.sample(**kwargs)
        return value

    def placed(self, marker=48):
        return self.engine.placements.get(self.engine.level.socket_by_marker[marker])

    def test_hidden_48_after_ten_minutes_activates_from_fresh_100_without_a_browser(self):
        learned = self.learn()
        seen = next(t['last_seen'] for t in learned['tags'] if t['id'] == 48)
        self.sample(dt=600, hidden=(48,))
        self.positions[100] = (.5, .5)
        first = self.sample(hidden=(48,))
        self.assertFalse(any(r['stable'] for r in first['relations']))
        self.assertIsNone(self.placed())
        value = self.hold(hidden=(48,))
        self.assertEqual(self.placed()['atom_tag_id'], 100)
        self.assertEqual(self.placed()['atom_buff_state'], 'active')
        self.assertEqual(value['occupancy']['relations'][0]['state'], 'present')
        self.assertEqual(value['relations'][0]['marker_seen_at'], seen)
        self.assertIsNone(self.board._placement['policy']['marker_memory_s'])
        scope, ids = self.board._game_layout_key
        with patch('time.time', return_value=self.now):
            shown = self.board.cue_targets_snapshot(scope=scope, fixed_ids=list(ids))
        self.assertEqual(shown['epoch'], self.board._placement['mapping_epoch'])
        self.assertEqual(next(t['last_seen'] for t in shown['tags'] if t['id']==48), seen)

    def test_stationary_100_near_47_still_rejected_at_old_radius(self):
        self.positions[47] = (.6801, .4928)
        self.learn()
        self.positions[100] = (.6301, .4915)
        self.hold(hidden=(47,))
        self.assertIsNone(self.placed(47))
        self.positions[100] = (.6451, .4915)
        self.hold(hidden=(47,))
        self.assertIsNotNone(self.placed(47))

    def test_fresh_atom_dwell_arm_and_camera_gates_still_required(self):
        for failure in ({'hidden': (48,100)}, {'pump':'suck'}, {'connected':False},
                        {'enabled':False}, {'ready':False}, {'frame_age':2}, {'relay_ready':False}):
            with self.subTest(failure=failure):
                self.setUp(); self.learn(); self.positions[100] = (.5,.5)
                self.hold(**({'hidden':(48,)} | failure))
                self.assertIsNone(self.placed())
                first = self.sample(hidden=(48,))
                self.assertFalse(any(r['stable'] for r in first.get('relations', [])))
                self.hold(hidden=(48,))
                self.assertIsNotNone(self.placed())

    def test_unlearned_target_never_uses_raw_or_display_only_coordinates(self):
        self.hold(hidden=(48,))
        self.positions[100] = (.5,.5)
        self.hold(hidden=(48,))
        self.assertIsNone(self.placed())
        states = {x['marker_id']:x['status'] for x in self.board._placement['target_states']}
        self.assertEqual(states[48], 'target_not_learned')

    def test_position_conflict_blocks_only_affected_target_and_hidden_does_not_clear_it(self):
        self.learn(); self.positions[48] = (.6,.5)
        self.positions[100] = (.5,.5)
        self.hold()
        self.hold(hidden=(48,))
        self.assertIsNone(self.placed())
        self.assertEqual(next(s['status'] for s in self.board._placement['target_states']
                              if s['marker_id']==48), 'target_position_disputed')
        self.positions[100] = (.8,.5)
        self.hold(hidden=(48,49))
        self.assertIsNotNone(self.placed(49))
        self.positions[48] = (.5,.5)
        self.sample()
        self.positions[100] = (.5,.5)
        self.hold(hidden=(48,))
        self.assertIsNotNone(self.placed())

    def test_invalid_geometry_does_not_move_anchor_or_imply_uncovering(self):
        self.learn(); self.positions[100] = (.5,.5)
        self.hold(hidden=(48,))
        tower = self.placed(); tower['hp'] *= .5
        hp = tower['hp']
        self.positions[48] = (.55,.5)
        self.hold(changes={48:{'ncorners':None}})
        self.assertEqual(tower['atom_buff_state'], 'active')
        self.assertEqual(tower['hp'], hp)
        self.assertFalse(any(e['kind']=='tower_replenished' for e in self.engine.events))

    def test_occupancy_stays_camera_only_through_relay_loss(self):
        self.learn(); self.positions[100] = (.5,.5)
        self.hold(hidden=(48,))
        value = self.hold(hidden=(48,), relay_ready=False)
        self.assertEqual(value['status'], 'unavailable')
        self.assertEqual(value['occupancy']['relations'][0]['state'], 'present')
        self.assertEqual(self.placed()['atom_buff_state'], 'active')
        # The existing cue endpoint still refuses acquisition without its runtime.
        scope, ids = self.board._game_layout_key
        with patch('time.time', return_value=self.now):
            self.assertEqual(self.board.cue_targets_snapshot(scope=scope, fixed_ids=list(ids))['status'], 'unavailable')

    def test_lift_uncover_and_return_replenishes_once_and_no_phantom_heal_after_outage(self):
        self.learn(); self.positions[100] = (.5,.5)
        self.hold(hidden=(48,))
        tower = self.placed(); tower['hp'] *= .5
        self.hold(hidden=(48,), ready=False)
        self.hold(hidden=(48,))
        self.assertFalse(any(e['kind']=='tower_replenished' for e in self.engine.events))
        self.hold()  # Ground marker visible again: Atom has lifted.
        self.assertNotEqual(tower['atom_buff_state'], 'active')
        self.hold(hidden=(48,))
        self.hold(hidden=(48,))
        self.assertEqual(sum(e['kind']=='tower_replenished' for e in self.engine.events), 1)

    def test_new_run_camera_or_layout_invalidates_previous_hidden_coordinates(self):
        for kind in ('run','camera','layout'):
            with self.subTest(kind=kind):
                self.setUp(); self.learn()
                if kind=='run': self.game._run_id = 'run-b'
                if kind=='camera': self.camera_revision = 'lens-b'
                if kind=='layout': self.game._level_projection['layout_revision'] = 999
                self.positions[100] = (.5,.5)
                self.hold(hidden=(48,))
                self.assertIsNone(self.placed())
                self.hold()  # A new camera-qualified observation can learn it again.
                self.hold(hidden=(48,))  # Placement still needs its own complete dwell.
                self.assertIsNotNone(self.placed())

    def test_coherent_board_motion_holds_then_discards_old_coordinates(self):
        self.positions[47] = (.2,.2)  # Independent anchors must be separated by >= .15.
        self.learn(); original_epoch = self.board._placement['mapping_epoch']
        self.positions[47] = (.25,.3); self.positions[49] = (.85,.6)
        self.positions[100] = (.5,.5)
        first = self.sample(hidden=(48,))
        self.assertEqual(first['status'], 'unavailable')
        self.hold(hidden=(48,))
        self.assertNotEqual(self.board._placement['mapping_epoch'], original_epoch)
        self.assertIsNone(self.placed())

    def test_active_map_pinned_and_reads_never_renew_sightings(self):
        self.learn(); key = self.board._game_layout_key
        with patch('time.time', return_value=self.now):
            before = self.board._cue_layouts[key].snapshot(self.now)
            for n in range(8): self.board.cue_targets_snapshot(scope=str(n), fixed_ids=[40])
            after = self.board._cue_layouts[key].snapshot(self.now)
        self.assertEqual(before, after)
        self.assertEqual(len(self.board._cue_layouts), 4)

    def test_game_cached_reads_do_not_wait_for_or_resample_the_camera(self):
        self.learn()
        scope, ids = self.board._game_layout_key
        # A sampler may hold this lock during a slow camera/projection read.
        with patch('time.time', return_value=self.now), \
             patch.object(self.board, '_sample_lock') as sampling, \
             patch.object(self.board, '_runtime_input') as hardware:
            sampling.acquire.side_effect = AssertionError('Game waited for the sampler')
            sampling.__enter__.side_effect = AssertionError('Game waited for the sampler')
            self.assertEqual(self.board.game_observation(scope=scope, fixed_ids=list(ids))['status'], 'ready')
            hardware.assert_not_called()
            sampling.acquire.assert_not_called()
            sampling.__enter__.assert_not_called()

    def test_scoped_core_stack_keeps_cover_radius_and_needs_neither_arm(self):
        self.positions[38] = (.35,.65)
        self.learn()
        self.engine.ring_completed_at = 0
        self.engine.ring_completed_wall_at = self.now - 5
        self.engine.core_stage = 'ring_ready'
        self.positions[100] = self.positions[38]
        self.hold(hidden=(38,))
        self.assertEqual(self.engine.core_stage, 'first_tag')
        self.sample(dt=600, hidden=(38,))
        self.positions[103] = (.395,.65)  # Outside activation radius, inside cover radius.
        self.hold(hidden=(38,100), connected=False)
        self.assertEqual(self.engine.core_stage, 'detonating')
        for _ in range(30): self.engine.step(.1)
        self.assertEqual(self.engine.phase, 'won')

    def test_disputed_existing_occupancy_cannot_restore_itself_from_its_old_anchor(self):
        self.learn(); self.positions[100] = (.5,.5)
        self.hold(hidden=(48,))
        self.assertEqual(self.placed()['atom_buff_state'], 'active')
        self.positions[48] = (.6,.5)
        value = self.hold()
        self.assertFalse(any(r['state']=='present' and r['marker_id']==48
                             for r in value['occupancy']['relations']))
        self.assertNotEqual(self.placed()['atom_buff_state'], 'active')
        self.hold(hidden=(48,))
        self.assertNotEqual(self.placed()['atom_buff_state'], 'active')

    def test_malformed_or_stale_fixed_map_fails_closed_without_raw_marker_fallback(self):
        self.learn(); self.positions[100] = (.5,.5)
        self.hold(hidden=(48,))
        key = self.board._game_layout_key
        good = dict(self.board._cue_layouts[key].snapshot(self.now), layout_scope=key[0], fixed_ids=list(key[1]))
        for field, bad in (('version',True), ('tags',None), ('status','unavailable'),
                           ('frame_at',self.now-3), ('blocked_fixed_ids',None)):
            with self.subTest(field=field):
                malformed = dict(good, **{field:bad})
                runtime = copy.deepcopy(self.board._runtime)
                runtime['tags'].append(self.tag(48,(.5,.5)))
                placement = self.board._placement_tracker.update(runtime,self.now,fixed_map=malformed)
                occupancy = self.board._occupancy_tracker.update(runtime,self.now,fixed_map=malformed)
                self.assertEqual(placement['status'],'unavailable')
                self.assertEqual(placement['relations'],[])
                self.assertEqual(occupancy['status'],'unavailable')

    def test_scoped_input_contract_does_not_fall_back_on_legacy_map(self):
        self.learn()
        with patch.object(self.board, 'game_observation', return_value={'contract':'photon.board.runtime',
                         'version':1,'status':'ready','layout_scope':'wrong','fixed_ids':[]}):
            observed, error = self.game._board_observation()
        self.assertIsNone(observed)
        self.assertIn('scope mismatch', error)


if __name__ == '__main__':
    unittest.main()
