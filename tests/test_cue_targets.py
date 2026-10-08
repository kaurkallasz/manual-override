"""Real evidence/cache policy, isolated from cameras and robots."""
import copy
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from test_photon_framework import load, FakeContext, Flask


class CueTargetTests(unittest.TestCase):
    @staticmethod
    def sized(tag, size=40, width=1280, height=720):
        return dict(tag, ncorners=[[tag['nx']+x/width, tag['ny']+y/height]
                    for x,y in ((-size/2,-size/2),(size/2,-size/2),(size/2,size/2),(-size/2,size/2))])

    def setUp(self):
        self.board = load('photon-board')
        self.map = self.board.CueTargets()
        self.now = 100.0
        self.runtime = dict(status='ready', source='camera', corrected=True,
                            camera_identity='camera-a', camera_revision='lens-a', width=1280, height=720)

    def frame(self, ids=(42, 100), **changes):
        tags = [dict(id=i, nx=.3+i/1000, ny=.5, missing=0) for i in ids]
        runtime = dict(self.runtime, frame_at=self.now, visible_ids=list(ids), detections=tags)
        runtime.update(changes)
        runtime['detections'] = [self.sized(t) if t['id'] < 100 and 'ncorners' not in t else t
                                 for t in runtime['detections']]
        self.map.update(runtime, self.now)
        return self.map.snapshot(self.now)

    def learn(self):
        for _ in range(3):
            value = self.frame()
            self.now += .3
        return value

    def test_fixed_tags_survive_long_occlusion_without_fresh_timestamps(self):
        original = self.learn()['tags'][0]
        self.now += 60
        value = self.frame(ids=())
        self.assertEqual([t['id'] for t in value['tags']], [42])
        fixed = value['tags'][0]
        self.assertTrue(fixed['cached'])
        self.assertFalse(fixed['visible'])
        self.assertEqual(fixed['last_seen'], original['last_seen'])

    def test_inactive_calibration_marker_cannot_hold_or_reset_an_occluded_game_target(self):
        self.map = self.board.CueTargets(fixed_ids=[40, 42])
        for _ in range(3):
            value = self.frame(ids=(30, 40, 42, 100))
            self.now += .3
        epoch = value['epoch']
        target = next(t for t in value['tags'] if t['id'] == 40)
        self.assertNotIn(30, [t['id'] for t in value['tags']])
        # The hand hides 40 and produces a displaced decode of calibration ID
        # 30, then leaves both hidden. Even repeated decodes cannot reset 40.
        for n in range(240):
            tags = [dict(id=42, nx=.342, ny=.5, missing=0)]
            if n < 3:
                tags.append(dict(id=30, nx=.8, ny=.7, missing=0))
            value = self.frame(ids=tuple(t['id'] for t in tags), detections=tags)
            self.assertEqual(value['status'], 'ready')
            self.assertEqual(value['epoch'], epoch)
            hidden = next(t for t in value['tags'] if t['id'] == 40)
            self.assertEqual((hidden['nx'], hidden['ny'], hidden['last_seen']),
                             (target['nx'], target['ny'], target['last_seen']))
            self.assertTrue(hidden['cached'])
            self.now += .3

    def test_scoped_map_still_holds_on_active_marker_conflicts_and_camera_loss(self):
        self.map = self.board.CueTargets(fixed_ids=[42])
        self.learn()
        value = self.frame(detections=[dict(id=42, nx=.8, ny=.5, missing=0)])
        self.assertEqual(value['status'], 'unavailable')
        self.assertEqual(value['pending_fixed_ids'], [42])
        self.now += .3
        self.frame()
        self.assertEqual(self.frame(status='unavailable')['status'], 'unavailable')

    def test_repeated_frame_and_repeated_reads_do_not_confirm_a_tag(self):
        self.frame()
        for _ in range(5):
            value = self.frame()
            self.map.snapshot(self.now)
        self.assertEqual([t['id'] for t in value['tags']], [100])
        self.assertFalse(value['tags'][0]['stable'])

    def test_moving_tags_require_stability_and_never_become_cached(self):
        value = self.learn()
        self.assertTrue(next(t for t in value['tags'] if t['id'] == 100)['stable'])
        missing = next(t for t in self.frame(ids=(42,))['tags'] if t['id'] == 100)
        self.assertFalse(missing['stable'])
        self.assertFalse(missing['visible'])
        self.assertFalse(missing['cached'])
        self.now += .3
        returning = next(t for t in self.frame()['tags'] if t['id'] == 100)
        self.assertFalse(returning['stable'])

    def test_camera_outage_preserves_memory_but_revokes_authority(self):
        self.learn()
        epoch = self.map.epoch
        self.assertEqual(self.frame(status='unavailable')['tags'], [])
        self.assertEqual(self.map.snapshot(self.now+2)['status'], 'unavailable')
        self.now += 3
        value = self.frame(ids=())
        self.assertEqual(value['epoch'], epoch)
        self.assertTrue(value['tags'][0]['cached'])

    def test_flickering_atom_qualifies_from_distinct_recent_consistent_sightings(self):
        for present in (True, False, True, False, True):
            value = self.frame(ids=(42, 100) if present else (42,))
            self.now += .15
        atom = next(t for t in value['tags'] if t['id'] == 100)
        self.assertTrue(atom['acquirable'])
        self.assertEqual(atom['evidence_samples'], 3)
        seen = atom['last_seen']
        missing = next(t for t in self.frame(ids=(42,))['tags'] if t['id'] == 100)
        self.assertTrue(missing['acquirable'])
        self.assertFalse(missing['visible'])
        self.assertEqual(missing['last_seen'], seen)
        self.now = seen + .76
        expired = next(t for t in self.frame(ids=(42,))['tags'] if t['id'] == 100)
        self.assertFalse(expired['acquirable'])
        self.assertFalse(expired['cached'])

    def test_camera_failure_movement_and_long_gaps_revoke_acquisition_confidence(self):
        for reason in ('camera', 'movement', 'gap'):
            with self.subTest(reason=reason):
                self.setUp(); self.learn()
                if reason == 'camera':
                    self.frame(status='unavailable')
                if reason == 'gap':
                    self.now += .8
                self.now += .01
                changes = {'detections': [dict(id=100, nx=.7, ny=.5, missing=0)]} if reason == 'movement' else {}
                value = self.frame(**changes)
                self.assertFalse(next(t for t in value['tags'] if t['id'] == 100)['acquirable'])

    def test_old_sightings_and_repeated_frames_cannot_supply_three_observations(self):
        for _ in range(5):
            value = self.frame()
        atom = next(t for t in value['tags'] if t['id'] == 100)
        self.assertFalse(atom['acquirable'])
        self.assertEqual(atom['evidence_samples'], 1)
        self.now += 1.6
        self.frame()
        self.now += .3
        value = self.frame()
        self.assertFalse(next(t for t in value['tags'] if t['id'] == 100)['acquirable'])

    def test_camera_identity_correction_and_dimensions_invalidate_all_memory(self):
        for change in ({'camera_identity':'camera-b'}, {'camera_revision':'lens-b'}, {'width':1920}):
            with self.subTest(change=change):
                self.setUp()
                self.learn()
                epoch = self.map.epoch
                value = self.frame(ids=(), **change)
                self.assertNotEqual(value['epoch'], epoch)
                self.assertEqual(value['tags'], [])

    def test_one_shifted_fixed_detection_holds_without_erasing_an_acquired_map(self):
        self.learn()
        epoch = self.map.epoch
        original = copy.deepcopy(self.map.records[42])
        value = self.frame(detections=[dict(id=42,nx=.7,ny=.5,missing=0)])
        self.assertEqual(value['status'], 'unavailable')
        self.assertEqual(value['epoch'], epoch)
        for key in ('tag', 'last_seen', 'mapped'):
            self.assertEqual(self.map.records[42][key], original[key])
        self.assertEqual(value['pending_fixed_ids'], [42])
        # Merely losing the suspect fixed tag does not prove the map unchanged.
        self.now += .3
        value = self.frame(ids=())
        self.assertEqual(value['status'], 'unavailable')
        self.assertEqual(value['epoch'], epoch)
        # Its normal position recovers the same map with Atom 100 still hidden.
        self.now += .3
        value = self.frame(ids=(42,))
        self.assertEqual(value['status'], 'ready')
        self.assertEqual(value['epoch'], epoch)
        self.assertFalse(next(t for t in value['tags'] if t['id'] == 100)['visible'])

    def test_confirmed_fixed_coordinate_contradiction_relearns_the_whole_map(self):
        self.learn()
        epoch = self.map.epoch
        for n in range(3):
            value = self.frame(ids=(42,), detections=[dict(id=42,nx=.7,ny=.5,missing=0)])
            if n < 2:
                self.assertEqual(value['status'], 'unavailable')
                self.assertEqual(value['epoch'], epoch)
            self.now += .3
        self.assertNotEqual(value['epoch'], epoch)
        self.assertEqual(value['epoch_reason'], 'fixed_marker_changed')
        self.assertEqual(value['epoch_marker_id'], 42)
        self.assertEqual(value['tags'], [])

    def test_repeated_or_inconsistent_contradictions_cannot_confirm_a_map_change(self):
        for reason in ('same-frame', 'different-positions', 'outage', 'long-gap'):
            with self.subTest(reason=reason):
                self.setUp(); self.learn(); epoch = self.map.epoch
                for n in range(3):
                    if reason == 'outage' and n == 2:
                        self.frame(status='unavailable')
                    value = self.frame(ids=(42,), detections=[dict(id=42,nx=.7+(n*.02 if reason == 'different-positions' else 0),ny=.5,missing=0)])
                    if reason != 'same-frame':
                        self.now += .8 if reason == 'long-gap' else .3
                self.assertEqual(value['epoch'], epoch)
                self.assertEqual(value['status'], 'unavailable')

    def test_real_camera_change_invalidates_even_with_a_pending_fixed_outlier(self):
        self.learn(); epoch = self.map.epoch
        self.frame(ids=(42,), detections=[dict(id=42,nx=.7,ny=.5,missing=0)])
        self.now += .3
        value = self.frame(ids=(), camera_identity='camera-b')
        self.assertNotEqual(value['epoch'], epoch)
        self.assertEqual(value['tags'], [])

    def test_known_covering_remains_when_atom_battery_disappears(self):
        self.learn()
        x = self.map.records[42]['tag']['nx']
        atom = dict(id=100, nx=x, ny=.5, missing=0,
                    ncorners=[[x-.02,.48],[x+.02,.48],[x+.02,.52],[x-.02,.52]])
        self.now += .3
        covered = self.frame(ids=(100,), detections=[atom])['tags'][0]
        self.assertEqual(covered['covered_by'], [100])
        self.now += 60
        self.assertEqual(self.frame(ids=())['tags'][0]['covered_by'], [100])
        self.now += .3
        atom.update(nx=.8, ncorners=[[.78,.48],[.82,.48],[.82,.52],[.78,.52]])
        self.assertEqual(self.frame(ids=(100,), detections=[atom])['tags'][0]['covered_by'], [])

    def test_snapshot_is_a_copy_and_missing_metadata_cannot_grant_cache(self):
        value = self.learn()
        value['tags'][0]['nx'] = 999
        self.assertLess(self.map.snapshot(self.now)['tags'][0]['nx'], 1)
        self.assertEqual(self.frame(camera_identity=None)['status'], 'unavailable')

    def test_mobile_route_rejects_an_old_layouts_cached_positions(self):
        mobile = load('mobile-ltz-api')
        game = {'contract':'photon.game','version':2,'level':{'id':'one','layout_revision':1,
                'sockets':[{'aruco_id':42}], 'core':{'marker_x':100, 'marker_y':100}}}
        evidence = dict(contract='photon.board.cue-targets',version=1,status='ready',tags=[dict(id=42,last_seen=100.)])
        calls = []
        def snapshot(**kwargs):
            calls.append(kwargs)
            return dict(copy.deepcopy(evidence), layout_scope=kwargs['scope'], fixed_ids=sorted(kwargs['fixed_ids']))
        mobile.hub_init(FakeContext({
            'photon-game':SimpleNamespace(game_snapshot=lambda:copy.deepcopy(game)),
            'photon-board':SimpleNamespace(cue_targets_snapshot=snapshot)}))
        app = Flask('cue-map-test');app.register_blueprint(mobile.bp)
        def get():
            return app.test_client().get('/api/cue-targets?side=green',environ_overrides={'hhh.roles':{'green'}})
        with patch.object(mobile.time,'time',return_value=101.):
            self.assertEqual(get().json['tags'], [])
            evidence['tags'][0]['last_seen'] = 102.
            self.assertEqual(get().json['tags'][0]['id'], 42)
        with patch.object(mobile.time,'time',return_value=103.):
            game['level']['layout_revision'] = 2
            self.assertEqual(get().json['tags'], [])
        self.assertEqual(calls[0]['fixed_ids'], [42, 38])
        self.assertNotEqual(calls[0]['scope'], calls[-1]['scope'])
        self.assertEqual(app.test_client().get('/api/cue-targets?side=purple',environ_overrides={'hhh.roles':{'green'}}).status_code,403)

    def test_public_scoped_snapshot_uses_sampler_and_never_inherits_other_layouts(self):
        board = self.board
        with patch.object(board, 'runtime_observation', return_value={'status':'ready'}), \
                patch.object(board.time, 'time', side_effect=lambda:self.now):
            value = board.cue_targets_snapshot(scope='game', fixed_ids=[40, 42])
            self.assertEqual(value['status'], 'unavailable')
            for n in range(3):
                tags = [self.sized(dict(id=i, nx=.3+i/1000, ny=.5, missing=0)) for i in (30, 40, 42, 100)]
                runtime = dict(self.runtime, frame_at=self.now, visible_ids=[t['id'] for t in tags],
                               detections=tags, tags=tags, arms={}, inputs={}, errors=[])
                with patch.object(board, '_runtime_input', return_value=runtime):
                    board._sample_tracking()
                self.now += .3
            value = board.cue_targets_snapshot(scope='game', fixed_ids=[42, 40])
            self.assertEqual(value['status'], 'ready')
            self.assertEqual([t['id'] for t in value['tags']], [40, 42, 100])
            self.assertEqual(len(board._cue_layouts), 1)
            self.assertNotIn(30, value['fixed_ids'])
            epoch = value['epoch']
            # Same IDs in a different layout must learn new positions.
            value = board.cue_targets_snapshot(scope='new-game', fixed_ids=[40, 42])
            self.assertEqual(value['status'], 'unavailable')
            self.assertEqual(value['tags'], [])
            self.assertNotEqual(value['epoch'], epoch)
            for n in range(5):
                board.cue_targets_snapshot(scope=str(n), fixed_ids=[40])
            self.assertEqual(len(board._cue_layouts), 4)

    def test_scoped_snapshot_rejects_malformed_layouts(self):
        for scope, ids in ((None,[40]), ('', [40]), ('game', None), ('game', []),
                           ('game', [True]), ('game',[40,40]), ('game',[100]), ('game',[29])):
            with self.subTest(scope=scope, ids=ids), self.assertRaises(ValueError):
                self.board.cue_targets_snapshot(scope=scope, fixed_ids=ids)

    def test_mobile_projection_requires_owner_scope_acknowledgement(self):
        mobile = load('mobile-ltz-api')
        evidence = dict(contract='photon.board.cue-targets', version=1, status='ready', tags=[])
        mobile.hub_init(FakeContext({'photon-board':SimpleNamespace(cue_targets_snapshot=lambda **kw:evidence)}))
        value = mobile._cue_targets_projection({'level':{'sockets':[{'aruco_id':40}]}})
        self.assertEqual(value['status'], 'unavailable')
        self.assertIn('contract mismatch', value['error'])


class CueMapVerificationTests(unittest.TestCase):
    def setUp(self):
        self.board = load('photon-board')
        self.map = self.board.CueTargets(fixed_ids=[38, 40, 42, 43, 44, 49])
        self.now = 100.
        self.positions = {40:(.2,.2), 42:(.8,.2), 43:(.8,.8), 44:(.2,.8), 49:(.5,.5)}

    def frame(self, hidden=(), changes=None, **runtime_changes):
        self.now += .3
        tags = []
        for ident, (x,y) in self.positions.items():
            if ident in hidden:
                continue
            values = dict((changes or {}).get(ident, {}))
            size = values.pop('size', 40)
            tag = dict(id=ident, nx=x, ny=y, missing=0)
            tag.update(values)
            if 'ncorners' not in tag:
                tag = CueTargetTests.sized(tag, size)
            tags.append(tag)
        runtime = dict(status='ready', source='camera', corrected=True,
                       camera_identity='camera-a', camera_revision='lens-a', width=1280, height=720,
                       frame_at=self.now, visible_ids=[t['id'] for t in tags], detections=tags)
        runtime.update(runtime_changes)
        self.map.update(runtime, self.now)
        return self.map.snapshot(self.now)

    def learn(self):
        for _ in range(3):
            value = self.frame()
        self.assertIn(49, [t['id'] for t in value['tags']])
        return value

    def test_bad_size_or_shape_then_hidden_49_retains_map_with_independent_anchors(self):
        for bad in ({'nx':.65, 'size':90}, {'nx':.65, 'ncorners':None},
                    {'nx':.65, 'ncorners':[[.65+x/1280,.5+y/720] for x,y in ((-35,-5),(35,-5),(35,5),(-35,5))]},
                    {'nx':.65, 'ncorners':[[.1,.1],[.2,.2],[.1,.2],[.2,.1]]}):
            with self.subTest(bad=bad):
                self.setUp(); epoch = self.learn()['epoch']
                saved = copy.deepcopy(self.map.records[49])
                for _ in range(3):
                    value = self.frame(changes={49:bad})
                    self.assertEqual(value['status'], 'ready')
                    self.assertEqual(value['epoch'], epoch, 'Invalid geometry cannot confirm movement')
                    self.assertEqual(value['quarantined_tags'][0]['reason'], 'marker_geometry')
                for _ in range(200):
                    value = self.frame(hidden=(49,))
                    self.assertEqual(value['status'], 'ready')
                    self.assertEqual(value['verification']['anchor_ids'], [40,42,43,44])
                    self.assertEqual(value['epoch'], epoch)
                    self.assertNotIn(49, [t['id'] for t in value['tags']], 'No new acquisition of disputed 49')
                self.assertEqual(self.map.records[49]['tag'], saved['tag'])
                self.assertEqual(self.map.records[49]['last_seen'], saved['last_seen'])

    def test_single_valid_size_position_outlier_is_isolated_but_confirmed_move_resets_map(self):
        epoch = self.learn()['epoch']
        for n in range(3):
            value = self.frame(changes={49:{'nx':.65}})
            if n < 2:
                self.assertEqual(value['status'], 'ready')
                self.assertEqual(value['quarantined_tags'][0]['reason'], 'position_conflict')
                self.assertEqual(value['epoch'], epoch)
        self.assertNotEqual(value['epoch'], epoch)
        self.assertEqual(value['epoch_marker_id'], 49)
        self.assertEqual(value['tags'], [], 'New positions must qualify again')

    def test_position_outlier_followed_by_occlusion_does_not_require_the_target_to_reappear(self):
        self.learn()
        self.frame(changes={49:{'nx':.65}})
        for _ in range(20):
            value = self.frame(hidden=(49,))
            self.assertEqual(value['status'], 'ready')
            self.assertEqual(value['pending_fixed_ids'], [49])
        value = self.frame()
        self.assertEqual(value['pending_fixed_ids'], [])
        self.assertIn(49, [t['id'] for t in value['tags']])

    def test_lost_or_shifted_anchors_revoke_retained_authority_until_verified_again(self):
        for failure in ('missing', 'shifted'):
            with self.subTest(failure=failure):
                self.setUp(); self.learn()
                self.frame(changes={49:{'size':90}})
                value = self.frame(hidden=(49,44) if failure=='missing' else (49,),
                    changes={i:{'nx':x+.006} for i,(x,y) in self.positions.items() if i!=49} if failure=='shifted' else {})
                self.assertEqual(value['status'], 'unavailable')
                for _ in range(3):
                    value = self.frame(hidden=(49,))
                self.assertEqual(value['status'], 'ready')
                self.assertEqual(value['pending_fixed_ids'], [49])

    def test_clustered_collinear_or_distant_anchors_cannot_verify_target(self):
        for positions in ({40:(.2,.2),42:(.4,.4),43:(.6,.6),44:(.8,.8)},
                          {40:(.47,.47),42:(.53,.47),43:(.53,.53),44:(.47,.53)},
                          {40:(.1,.1),42:(.35,.1),43:(.35,.35),44:(.1,.35)}):
            with self.subTest(positions=positions):
                self.setUp(); self.positions.update(positions);self.learn()
                value = self.frame(changes={49:{'size':90}})
                self.assertEqual(value['status'], 'unavailable')

    def test_frozen_reference_prevents_gradual_camera_drift_from_validating_old_target(self):
        self.learn(); ref = copy.deepcopy(self.map.records[40]['reference'])
        self.frame(changes={49:{'size':90}})
        for delta in (.002, .004, .006, .008):
            value = self.frame(hidden=(49,), changes={i:{'nx':x+delta} for i,(x,y) in self.positions.items() if i!=49})
        self.assertEqual(value['status'], 'unavailable')
        self.assertEqual(self.map.records[40]['reference'], ref)

    def test_repeated_frames_reads_and_camera_failure_cannot_renew_anchor_authority(self):
        self.learn(); self.frame(changes={49:{'size':90}})
        stamp = self.now
        for _ in range(3):
            value = self.frame(hidden=(49,), frame_at=stamp)
        self.assertEqual(value['status'], 'unavailable')
        self.assertEqual(value['verification']['observed_at'], stamp)
        self.assertEqual(self.frame(hidden=(49,), status='unavailable')['status'], 'unavailable')
        epoch = value['epoch']
        value = self.frame(hidden=(49,), camera_identity='other')
        self.assertNotEqual(value['epoch'], epoch)
        self.assertEqual(value['tags'], [])

    def test_fixed_marker_uses_its_own_learned_size_so_a_larger_core_is_valid(self):
        self.positions[38] = (.5,.3)
        for _ in range(4):
            value = self.frame(changes={38:{'size':65}})
        self.assertIn(38, [t['id'] for t in value['tags']])
        self.assertEqual(value['pending_fixed_ids'], [])

    def test_quarantine_keeps_occupancy_without_publishing_target_coordinates(self):
        self.learn(); self.frame(changes={49:{'size':90}})
        atom = CueTargetTests.sized(dict(id=103,nx=.5,ny=.5,missing=0))
        tags = [CueTargetTests.sized(dict(id=i,nx=x,ny=y,missing=0))
                for i,(x,y) in self.positions.items() if i!=49] + [atom]
        value = self.frame(hidden=(49,), detections=tags, visible_ids=[t['id'] for t in tags])
        self.assertEqual(value['status'], 'ready')
        self.assertEqual(value['quarantined_tags'][0]['covered_by'], [103])
        self.assertNotIn('nx', value['quarantined_tags'][0])

    def test_invalid_marker_geometry_cannot_establish_a_new_fixed_position(self):
        for _ in range(4):
            value = self.frame(changes={49:{'ncorners':None}})
        self.assertNotIn(49, [t['id'] for t in value['tags']])
        self.assertNotIn(49, self.map.records)


if __name__ == '__main__':
    unittest.main()
