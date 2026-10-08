"""Y and Mobile share fresh corrected detections; fixtures never connect hardware."""
import copy
import math
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from test_photon_framework import FakeContext, load


class CameraMarkerAlignmentTests(unittest.TestCase):
    def setUp(self):
        self.board = load('photon-board')
        self.mobile = load('mobile-ltz-api')
        self.y = load('laser-tag-y')
        self.level = {'width':1000, 'height':600, 'sockets':[
            {'aruco_id':40+i, 'x':x, 'y':y, 'marker_x':x, 'marker_y':y}
            for i, (x,y) in enumerate(((100,100),(900,100),(900,500),(100,500),(500,300)))]}
        self.now = time.time()
        self.detections = [dict(id=s['aruco_id'], nx=.1+.8*s['x']/1000,
                                ny=.05+.9*s['y']/600, missing=.3, tracked=False)
                           for s in self.level['sockets']]
        for tag in self.detections:
            self.set_size(tag, 40)
        self.runtime = dict(contract='photon.board.runtime', version=1, status='ready',
                            source='camera', frame_at=self.now-.3, observed_at=self.now,
                            corrected=True, width=1280, height=720, arms={}, errors=[],
                            tags=[], detections=self.detections, visible_ids=[40,41,42,43,44])
        # Use the real cached-reader path. No sampler, webcam, relay or background work.
        self.board._runtime = self.runtime
        self.board._tracking = dict(contract='photon.board.tracking', version=1,
                                    status='ready', source='camera', sampled_at=self.now,
                                    frame_at=self.now-.3, tags=[], arms={})
        self.camera = SimpleNamespace(preview_snapshot=lambda:dict(contract='hhh.camera-preview',
            version=1, status='ready', coordinate_space='corrected-camera-normalized'))
        self.mobile.hub_init(FakeContext({'photon-board':self.board,'camera-calibration':self.camera}))
        self.y.hub_init(FakeContext({'photon-board':self.board}))
        self.addCleanup(self.y.hub_stop)
        self.game = {'level':self.level}

    @staticmethod
    def set_size(tag, size, angle=0, width=1280, height=720):
        c, s = math.cos(angle), math.sin(angle)
        tag['ncorners'] = [[tag['nx']+(x*c-y*s)/width, tag['ny']+(x*s+y*c)/height]
                           for x,y in ((-size/2,-size/2),(size/2,-size/2),(size/2,size/2),(-size/2,size/2))]

    def test_y_and_mobile_use_identical_delayed_unconfirmed_detections(self):
        with patch.object(self.board, '_runtime_input', side_effect=AssertionError('must not sample')):
            current = self.y._marker_diagnostics()['camera_markers']
            mobile = self.mobile.camera_view(self.game)
        self.assertEqual(current['status'], 'ready')
        self.assertEqual(mobile['status'], 'ready', mobile)
        self.assertEqual([t['id'] for t in current['tags']], mobile['markers'])
        self.assertEqual(mobile['alignment']['detected_count'], 5)
        self.assertEqual(mobile['alignment']['matched_count'], 5)
        self.assertEqual(mobile['tracking']['contract'], 'photon.board.camera-markers')
        self.assertEqual(mobile['tracking']['status'], 'ready')
        self.assertEqual(mobile['tracking']['frame_at'], self.runtime['frame_at'])
        # Neither path waits for Webcam's one-second tracked-tag qualification.
        self.assertEqual(self.runtime['tags'], [])
        self.assertAlmostEqual(mobile['matrix'][0], .8)
        self.assertAlmostEqual(mobile['matrix'][4], .9)

    def test_remembered_and_nonvisible_markers_do_not_complete_alignment(self):
        self.runtime['visible_ids'] = [40,41,42]
        self.runtime['tags'] = copy.deepcopy(self.detections)
        self.board._tracking['tags'] = [dict(id=i, camera=[.5,.5], visible=False,
                                             last_seen=self.now-2) for i in (43,44)]
        mobile = self.mobile.camera_view(self.game)
        self.assertEqual(mobile['status'], 'unavailable')
        self.assertEqual(mobile['alignment']['matched_ids'], [40,41,42])
        self.assertIn('3 markers detected; 3 match this level', mobile['error'])
        self.assertEqual(mobile['tracking']['status'], 'ready', 'Display detections survive an alignment hold')
        self.assertEqual([t['id'] for t in mobile['tracking']['tags']], [40,41,42])
        # A later good frame recovers directly, with no sticky alignment state.
        self.runtime['visible_ids'] = [40,41,42,43,44]
        self.assertEqual(self.mobile.camera_view(self.game)['status'], 'ready')

    def test_count_all_detections_but_only_match_level_ids(self):
        for tag in self.detections:
            tag['id'] += 60
        self.runtime['visible_ids'] = [100,101,102,103,104]
        mobile = self.mobile.camera_view(self.game)
        self.assertEqual(mobile['status'], 'unavailable')
        self.assertEqual(mobile['alignment']['detected_count'], 5)
        self.assertEqual(mobile['alignment']['matched_count'], 0)
        self.assertIn('5 markers detected; 0 match this level', mobile['error'])
        self.assertEqual([t['id'] for t in mobile['tracking']['tags']], [100,101,102,103,104])

    def test_stale_stopped_uncorrected_and_simulated_inputs_are_unavailable(self):
        for changed in ({'frame_at':self.now-2}, {'frame_at':self.now+3},
                        {'corrected':False}, {'source':'simulation'}, {'status':'unavailable'}):
            with self.subTest(changed=changed), patch.object(self.board, '_runtime', {**self.runtime, **changed}):
                current = self.board.camera_markers_snapshot()
                self.assertEqual(current['status'], 'unavailable')
                self.assertEqual(current['tags'], [])
                self.assertEqual(self.mobile.camera_view(self.game)['status'], 'unavailable')
        self.board._tracking['sampled_at'] = self.now-2
        self.assertEqual(self.board.camera_markers_snapshot()['status'], 'unavailable')

    def test_short_diagnostic_timeout_does_not_remove_fresh_camera_evidence(self):
        settings = self.board.settings_snapshot()
        settings['settings']['stale_s'] = .2
        with patch.object(self.board, 'settings_snapshot', return_value=settings):
            self.assertEqual(self.board.tracking_snapshot()['status'], 'unavailable')
            self.assertEqual(self.y._marker_diagnostics()['camera_markers']['status'], 'ready')
            self.assertEqual(self.mobile.camera_view(self.game)['status'], 'ready')

    def test_consumers_reject_missing_malformed_or_incompatible_shared_contract(self):
        current = self.board.camera_markers_snapshot()
        for changed in ({'contract':'photon.board.runtime'}, {'version':True}, {'version':2},
                        {'max_age_s':10}, {'max_age_s':float('nan')}, {'width':0},
                        {'tags':None}, {'tags':[None]}, {'tags':current['tags']*2},
                        {'tags':[{**t,'camera':[float('nan'),.5]} for t in current['tags']]},
                        {'tags':[{**t,'last_seen':self.now-2} for t in current['tags']]}):
            with self.subTest(changed=changed), patch.object(self.board, 'camera_markers_snapshot', return_value={**current,**changed}):
                self.assertEqual(self.mobile.camera_view(self.game)['status'], 'unavailable')
        with patch.object(self.board, 'camera_markers_snapshot', Mock(side_effect=RuntimeError('detector failed'))):
            self.assertEqual(self.mobile.camera_view(self.game)['status'], 'unavailable')
            self.assertEqual(self.y._marker_diagnostics()['status'], 'unavailable')

    def test_four_collinear_markers_are_rejected_with_spread_explanation(self):
        self.level['sockets'] = [dict(aruco_id=40+i,x=100+i*200,y=100) for i in range(4)]
        self.runtime.update(visible_ids=[40,41,42,43], detections=[
            dict(id=40+i,nx=.2+.2*i,ny=.2,missing=0) for i in range(4)])
        for tag in self.runtime['detections']:
            self.set_size(tag, 40)
        result = self.mobile.camera_view(self.game)
        self.assertEqual(result['status'], 'unavailable')
        self.assertEqual(result['alignment']['matched_count'], 4)
        self.assertIn('Spread', result['error'])

    def test_false_49_is_excluded_without_losing_the_valid_alignment(self):
        false = dict(id=49,nx=.8,ny=.6,missing=0)
        self.set_size(false, 90)
        self.detections.append(false)
        self.runtime['visible_ids'].append(49)
        current = self.y._marker_diagnostics()['camera_markers']
        self.assertEqual([t['id'] for t in current['tags']], [40,41,42,43,44])
        self.assertEqual(current['size_filter']['rejected'][0]['id'], 49)
        self.assertEqual(current['size_filter']['rejected'][0]['reason'], 'size_outlier')
        mobile = self.mobile.camera_view(self.game)
        self.assertEqual(mobile['status'], 'ready')
        self.assertEqual(mobile['alignment']['size_rejected_ids'], [49])
        # Correctly sized marker 49 is never blacklisted by identity.
        self.set_size(false, 41)
        self.assertIn(49, [t['id'] for t in self.board.camera_markers_snapshot()['tags']])

    def test_fifteen_percent_is_a_pairwise_span_not_plus_minus_fifteen(self):
        # 34 and 46 are each +/-15% from 40, but differ by more than 15%.
        for tag, size in zip(self.detections, (34,40,40,40,46)):
            self.set_size(tag, size)
        result = self.board.camera_markers_snapshot()
        self.assertEqual([t['id'] for t in result['tags']], [41,42,43,44])
        bounds = result['size_filter']
        self.assertLessEqual(bounds['maximum_px']/bounds['minimum_px'], 1.15+1e-12)
        self.set_size(self.detections[-1], 46.001)
        self.assertEqual([t['id'] for t in self.board.camera_markers_snapshot()['tags']], [41,42,43])

    def test_tiny_and_large_outliers_and_input_order_do_not_shift_the_reference(self):
        for tag, size in zip(self.detections, (10,40,41,42,1000)):
            self.set_size(tag, size)
        first = self.board.camera_markers_snapshot()
        self.assertEqual([t['id'] for t in first['tags']], [41,42,43])
        self.detections.reverse()
        self.assertEqual({t['id'] for t in self.board.camera_markers_snapshot()['tags']}, {41,42,43})

    def test_rotation_aspect_ratio_and_uniform_camera_resize_preserve_size_decisions(self):
        for i, tag in enumerate(self.detections):
            self.set_size(tag, 40+i, angle=i*.2)
        first = self.board.camera_markers_snapshot()
        self.assertEqual(len(first['tags']), 5)
        self.assertAlmostEqual(first['size_filter']['minimum_px'], 40)
        self.assertAlmostEqual(first['size_filter']['maximum_px'], 44)
        self.runtime.update(width=2560,height=1440)
        second = self.board.camera_markers_snapshot()
        self.assertEqual([t['id'] for t in first['tags']], [t['id'] for t in second['tags']])
        self.assertAlmostEqual(second['size_filter']['minimum_px'], 80)

    def test_missing_or_degenerate_corners_cannot_evade_size_check(self):
        for corners in (None, [], [[.1,.1]]*4, [[0,0],[1,1],[0,1],[1,0]],
                        [[0,0],[1,0],[1,float('nan')],[0,1]], [[0,0],[1,0],[1,.5]]):
            with self.subTest(corners=corners):
                self.detections[0]['ncorners'] = corners
                result = self.board.camera_markers_snapshot()
                self.assertEqual(len(result['tags']), 4)
                self.assertEqual(result['size_filter']['rejected'][0]['reason'], 'invalid_corners')

    def test_ambiguous_clusters_and_singletons_require_more_evidence(self):
        self.runtime['detections'] = self.detections[:4]
        for tag, size in zip(self.detections, (20,20,40,40)):
            self.set_size(tag, size)
        result = self.mobile.camera_view(self.game)
        self.assertEqual(result['status'], 'unavailable')
        self.assertEqual(result['alignment']['size_rejected_ids'], [40,41,42,43])
        self.assertIn('4 rejected by the 15% size check', result['error'])
        self.runtime['detections'] = self.detections[:1]
        self.assertEqual(self.board.camera_markers_snapshot()['tags'], [])
        self.runtime['detections'] = []
        self.assertEqual(self.board.camera_markers_snapshot()['tags'], [])


if __name__ == '__main__':
    unittest.main()
