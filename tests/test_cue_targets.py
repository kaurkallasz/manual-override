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
        self.assertEqual(value['status'], 'ready')
        self.assertEqual(value['blocked_fixed_ids'], [42])
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
        self.assertEqual(value['status'], 'ready')
        self.assertEqual(value['blocked_fixed_ids'], [42])
        self.assertEqual(value['epoch'], epoch)
        for key in ('tag', 'last_seen', 'mapped'):
            self.assertEqual(self.map.records[42][key], original[key])
        self.assertEqual(value['pending_fixed_ids'], [42])
        # Merely losing the suspect fixed tag does not prove the map unchanged.
        self.now += .3
        value = self.frame(ids=())
        self.assertEqual(value['status'], 'ready')
        self.assertEqual(value['blocked_fixed_ids'], [42])
        self.assertEqual(value['epoch'], epoch)
        # Its normal position recovers the same map with Atom 100 still hidden.
        self.now += .3
        value = self.frame(ids=(42,))
        self.assertEqual(value['status'], 'ready')
        self.assertEqual(value['epoch'], epoch)
        self.assertFalse(next(t for t in value['tags'] if t['id'] == 100)['visible'])

    def test_repeated_single_marker_conflict_never_relearns_unrelated_coordinates(self):
        self.learn(); epoch = self.map.epoch
        for n in range(6):
            value = self.frame(ids=(42,), detections=[dict(id=42,nx=.7,ny=.5,missing=0)])
            self.assertEqual(value['status'], 'ready')
            self.assertEqual(value['epoch'], epoch)
            self.assertEqual(value['blocked_fixed_ids'], [42])
            self.assertAlmostEqual(value['fixed_tags'][0]['nx'], .342)
            self.now += .3

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
                self.assertEqual(value['status'], 'ready')
                self.assertEqual(value['blocked_fixed_ids'], [42])

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

    def test_mobile_route_uses_owner_scope_and_keeps_positions_learned_before_reader(self):
        mobile=load('mobile-ltz-api')
        game={'contract':'photon.game','version':2,'run_id':'one','level':{'id':'one','layout_revision':1,
              'sockets':[{'aruco_id':42}], 'core':{'marker_x':100,'marker_y':100}}}
        calls=[]
        def snapshot(**kwargs):
            calls.append(kwargs)
            tags=[dict(id=42,last_seen=100.,fixed=True)] if len(calls)==1 or kwargs['scope']==calls[0]['scope'] else []
            return dict(contract='photon.board.cue-targets',version=2,status='ready',tags=tags,fixed_tags=copy.deepcopy(tags),
                        layout_scope=kwargs['scope'],fixed_ids=sorted(kwargs['fixed_ids']))
        mobile.hub_init(FakeContext({'photon-game':SimpleNamespace(game_snapshot=lambda:copy.deepcopy(game)),
                                     'photon-board':SimpleNamespace(cue_targets_snapshot=snapshot)}))
        app=Flask('cue-map-test');app.register_blueprint(mobile.bp)
        def get():return app.test_client().get('/api/cue-targets?side=green',environ_overrides={'hhh.roles':{'green'}})
        with patch.object(mobile.time,'time',return_value=101.):
            self.assertEqual(get().json['tags'][0]['last_seen'],100.,'Reading later does not remove fixed memory')
            game['level']['layout_revision']=2
            self.assertEqual(get().json['tags'],[])
        self.assertEqual(calls[0]['fixed_ids'],[42,38]);self.assertNotEqual(calls[0]['scope'],calls[-1]['scope'])
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

    def test_cue_snapshot_carries_cached_stack_evidence_without_aliasing_or_retiming(self):
        stack = dict(contract='photon.board.stacking', version=1, status='ready',
                     sampled_at=99.5, source_epoch='camera',
                     relations=[dict(lower_id=103, upper_id=100, stable=True)])
        observation = dict(status='ready', placement=dict(stacking=stack))
        with patch.object(self.board, 'runtime_observation', return_value=observation):
            value = self.board.cue_targets_snapshot()
        self.assertEqual(value['stacking'], stack)
        value['stacking']['relations'][0]['lower_id'] = 104
        self.assertEqual(stack['relations'][0]['lower_id'], 103)
        with patch.object(self.board, 'runtime_observation', return_value=dict(status='unavailable')):
            value = self.board.cue_targets_snapshot()
        self.assertEqual(value['status'], 'unavailable')
        self.assertEqual(value['stacking']['status'], 'unavailable')

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

    def test_bad_geometry_and_total_occlusion_keep_all_fixed_positions(self):
        for bad in ({'nx':.65,'size':90}, {'ncorners':None},
                    {'ncorners':[[.1,.1],[.2,.2],[.1,.2],[.2,.1]]}):
            with self.subTest(bad=bad):
                self.setUp(); initial=self.learn(); epoch=initial['epoch']
                original={t['id']:(t['nx'],t['ny']) for t in initial['fixed_tags']}
                self.frame(changes={49:bad})
                for _ in range(200):
                    value=self.frame(hidden=tuple(self.positions))
                    self.assertEqual(value['status'],'ready')
                    self.assertEqual(value['epoch'],epoch)
                    self.assertEqual(value['blocked_fixed_ids'],[])
                    self.assertEqual({t['id']:(t['nx'],t['ny']) for t in value['tags']},original)
                    self.assertTrue(all(t['cached'] and not t['visible'] for t in value['tags']))
                self.assertEqual(value['quarantined_tags'][0]['reason'],'marker_geometry')

    def test_fixed_pose_and_corners_are_immutable_but_live_timestamps_advance(self):
        initial=self.learn(); original=copy.deepcopy(self.map.records[40]['tag'])
        for delta in (.002,-.002,.003,0):
            value=self.frame(changes={40:{'nx':.2+delta}})
            target=next(t for t in value['tags'] if t['id']==40)
            self.assertEqual(target['nx'],original['nx'])
            self.assertEqual(target['ncorners'],original['ncorners'])
            self.assertGreater(target['last_seen'],initial['frame_at'])
            self.assertTrue(target['visible'])
        value['fixed_tags'][0]['nx']=999
        self.assertEqual(self.map.snapshot(self.now)['fixed_tags'][0]['nx'],.2)

    def test_late_identification_adds_to_same_board_without_waiting_for_every_tag(self):
        for _ in range(3):value=self.frame(hidden=(49,))
        epoch=value['epoch'];self.assertEqual(value['status'],'ready')
        self.assertNotIn(49,[t['id'] for t in value['tags']])
        for _ in range(3):value=self.frame()
        self.assertEqual(value['epoch'],epoch)
        self.assertIn(49,[t['id'] for t in value['tags']])

    def test_single_geometry_valid_conflict_blocks_only_that_id_and_recovers(self):
        epoch=self.learn()['epoch']
        for _ in range(6):
            value=self.frame(changes={49:{'nx':.65}})
            self.assertEqual(value['status'],'ready')
            self.assertEqual(value['blocked_fixed_ids'],[49])
            self.assertEqual(value['epoch'],epoch)
            self.assertEqual(next(t for t in value['tags'] if t['id']==49)['nx'],.5)
        self.assertEqual(self.frame(hidden=(49,))['blocked_fixed_ids'],[49])
        self.assertEqual(self.frame()['blocked_fixed_ids'],[])

    def test_coherent_translation_rotation_and_resize_hold_then_relearn(self):
        import math
        for angle,scale in ((0,1),(.1,1),(0,.8)):
            with self.subTest(angle=angle,scale=scale):
                self.setUp(); epoch=self.learn()['epoch']
                changes={i:dict(nx=.53+scale*((x-.5)*math.cos(angle)-(y-.5)*math.sin(angle)),
                                ny=.53+scale*((x-.5)*math.sin(angle)+(y-.5)*math.cos(angle)),size=40*scale)
                         for i,(x,y) in self.positions.items()}
                for n in range(3):
                    value=self.frame(changes=changes)
                    if n<2:
                        self.assertEqual(value['status'],'unavailable')
                        self.assertGreaterEqual(len(value['board_motion_ids']),2)
                        self.assertEqual(value['tags'],[])
                        self.assertEqual(value['epoch'],epoch)
                self.assertNotEqual(value['epoch'],epoch)
                self.assertEqual(value['epoch_reason'],'board_moved')
                self.assertEqual(value['fixed_tags'],[])
                for _ in range(3):value=self.frame(changes=changes)
                self.assertEqual(value['status'],'ready')
                self.assertAlmostEqual(next(t for t in value['tags'] if t['id']==40)['nx'],changes[40]['nx'])

    def test_two_separated_markers_detect_board_movement_without_all_targets(self):
        self.learn();epoch=self.map.epoch
        for _ in range(3):
            value=self.frame(hidden=(43,44,49),changes={40:{'nx':.25},42:{'nx':.85}})
        self.assertNotEqual(value['epoch'],epoch)

    def test_board_motion_confirms_when_extra_anchors_flicker(self):
        self.learn();epoch=self.map.epoch
        change={i:{'nx':x+.04} for i,(x,y) in self.positions.items()}
        for hidden in ((43,), (44,), (49,)):
            value=self.frame(hidden=hidden,changes=change)
        self.assertNotEqual(value['epoch'],epoch)
        self.assertEqual(value['epoch_reason'],'board_moved')
        self.assertEqual(value['fixed_tags'],[])

    def test_tightly_clustered_or_wrong_scale_decodes_cannot_confirm_board_motion(self):
        self.positions={40:(.4,.4),42:(.45,.4)};self.learn_pair()
        epoch=self.map.epoch
        for _ in range(4):self.frame(changes={40:{'nx':.5},42:{'nx':.55}})
        self.assertEqual(self.map.epoch,epoch)
        self.setUp();self.learn();epoch=self.map.epoch
        for _ in range(4):
            value=self.frame(changes={i:{'nx':x+.05,'size':90} for i,(x,y) in self.positions.items()})
        self.assertEqual(value['epoch'],epoch)
        self.assertEqual(value['status'],'ready','Wrong-sized projected detections do not move the board')

    def learn_pair(self):
        for _ in range(3):self.frame()

    def test_board_motion_hold_does_not_clear_on_occlusion_or_repeat_frames(self):
        self.learn();epoch=self.map.epoch
        change={i:{'nx':x+.04} for i,(x,y) in self.positions.items()}
        first=self.frame(changes=change)
        for _ in range(3):
            value=self.frame(changes=change,frame_at=first['frame_at'])
            self.assertEqual(value['status'],'unavailable')
            self.assertEqual(value['epoch'],epoch)
        for _ in range(4):
            value=self.frame(hidden=tuple(self.positions))
            self.assertEqual(value['status'],'unavailable')
        for _ in range(4):value=self.frame()
        self.assertEqual(value['status'],'ready')
        self.assertEqual(value['epoch'],epoch)

    def test_gradual_board_drift_uses_original_reference_not_last_detection(self):
        self.learn();original=copy.deepcopy(self.map.records[40]['reference'])
        for delta in (.003,.006,.009,.012):
            value=self.frame(changes={i:{'nx':x+delta} for i,(x,y) in self.positions.items()})
        self.assertEqual(value['status'],'unavailable')
        self.assertEqual(self.map.records[40]['reference'],original)

    def test_camera_staleness_stops_motion_but_retains_display_only_memory(self):
        self.learn();stamp=self.now
        value=self.map.snapshot(stamp+1.6)
        self.assertEqual(value['status'],'unavailable');self.assertEqual(value['tags'],[])
        self.assertEqual(len(value['fixed_tags']),5)
        value=self.frame(status='unavailable')
        self.assertEqual(value['tags'],[]);self.assertEqual(len(value['fixed_tags']),5)
        value=self.frame(camera_identity='new')
        self.assertEqual(value['fixed_tags'],[])

    def test_fixed_marker_uses_its_own_size_including_larger_core(self):
        self.positions[38]=(.5,.3)
        for _ in range(4):value=self.frame(changes={38:{'size':65}})
        self.assertIn(38,[t['id'] for t in value['tags']]);self.assertEqual(value['pending_fixed_ids'],[])

    def test_occupancy_survives_bad_geometry_and_atom_battery_loss(self):
        self.learn();self.frame(changes={49:{'size':90}})
        atom=CueTargetTests.sized(dict(id=103,nx=.5,ny=.5,missing=0))
        value=self.frame(detections=[atom],visible_ids=[103])
        target=next(t for t in value['tags'] if t['id']==49)
        self.assertEqual(target['covered_by'],[103])
        self.now+=60;value=self.frame(hidden=tuple(self.positions))
        self.assertEqual(next(t for t in value['tags'] if t['id']==49)['covered_by'],[103])

    def test_invalid_geometry_never_establishes_a_new_fixed_position(self):
        for _ in range(4):value=self.frame(changes={49:{'ncorners':None}})
        self.assertNotIn(49,[t['id'] for t in value['tags']]);self.assertNotIn(49,self.map.records)

class FixedScopeTests(unittest.TestCase):
    def test_each_run_has_its_own_shared_board_scope(self):
        from shared.fixed_board import cue_layout
        game=dict(run_id='first',level=dict(id='same',sockets=[{'aruco_id':40}],core=dict(marker_x=1,marker_y=1)))
        scope,ids=cue_layout(game)
        self.assertEqual(ids,[40,38])
        self.assertEqual(cue_layout(copy.deepcopy(game))[0],scope)
        game['run_id']='second';self.assertNotEqual(cue_layout(game)[0],scope)

    def test_operator_and_mobile_register_the_same_owner_scope(self):
        game=dict(contract='photon.game',version=2,run_id='first',level=dict(id='same',sockets=[{'aruco_id':40}]))
        calls=[]
        def cue(**kw):
            calls.append(kw)
            return dict(contract='photon.board.cue-targets',version=2,layout_scope=kw['scope'],fixed_ids=kw['fixed_ids'],
                        status='ready',tags=[],fixed_tags=[])
        board=SimpleNamespace(cue_targets_snapshot=cue,
            tracking_snapshot=lambda:dict(contract='photon.board.tracking',version=1,status='ready'),
            camera_markers_snapshot=lambda:dict(contract='photon.board.camera-markers',version=1,status='ready'))
        ctx=FakeContext({'photon-game':SimpleNamespace(game_snapshot=lambda:game),'photon-board':board})
        mobile,y=load('mobile-ltz-api'),load('laser-tag-y');mobile.hub_init(ctx);y.hub_init(ctx)
        first=mobile._cue_targets_projection(game);second=y._marker_diagnostics()['fixed_board']
        self.assertEqual(first['scope'],second['scope']);self.assertEqual(calls[0],calls[1])
        self.assertEqual(first['version'],2)


if __name__ == '__main__':
    unittest.main()
