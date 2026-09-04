"""Forward existing input diagnostics, not hardware access or calibration data."""
import copy
import json
import time
import unittest

from test_photon_framework import FakeContext, load


class BoardReportTests(unittest.TestCase):
    def setUp(self):
        self.game = load('photon-game')
        self.value = {'contract': 'photon.board.runtime', 'version': 1, 'status': 'ready',
                      'source': 'camera', 'revision': 3, 'observed_at': time.time(),
                      'frame_at': time.time(), 'tags': [], 'arms': {},
                      'placement': {'contract': 'photon.board.placement', 'version': 1,
                                    'revision': 4, 'status': 'ready', 'source_epoch': 'fixture',
                                    'sampled_at': time.time(), 'relations': []},
                      'inputs': {'webcam': {'status': 'ready', 'contract': 'hhh.webcam.tags', 'version': 1}},
                      'tracking': {'contract': 'photon.board.tracking', 'version': 1,
                                   'status': 'ready', 'sampled_at': time.time(),
                                   'inputs': {'cal2_projection': {'status': 'unavailable', 'error': 'missing calibration'}},
                                   'tags': [{'id': 100}], 'calibration': {'private': 123}}}
        case = self

        class Board:
            calls = 0

            def runtime_observation(self):
                self.calls += 1
                return copy.deepcopy(case.value)

        self.board = Board()
        self.game._hub_ctx = FakeContext({'photon-board': self.board})

    def tearDown(self):
        self.game.hub_stop()

    def test_one_existing_read_forwards_bounded_health_without_raw_data(self):
        self.value.pop('tags')
        self.value.pop('arms')
        self.assertEqual(self.game._physical_observation()['relations'], [])
        self.assertEqual(self.board.calls, 1)
        report = self.game.game_snapshot()['inputs']['board']['upstream']
        self.assertEqual(report['inputs']['webcam']['contract'], 'hhh.webcam.tags')
        self.assertEqual(report['tracking']['inputs']['cal2_projection']['error'], 'missing calibration')
        self.assertNotIn('calibration', report['tracking'])
        self.assertNotIn('tags', report['tracking'])
        self.assertNotIn('arms', report)
        self.assertGreater(report['reported_at'], 0)
        self.game.game_snapshot()
        self.assertEqual(self.board.calls, 1, 'snapshot readers must not resample Board')
        report['inputs'].clear()
        self.assertIn('webcam', self.game.game_snapshot()['inputs']['board']['upstream']['inputs'])

    def test_failure_keeps_input_reason_but_never_physical_evidence(self):
        self.value.update(status='unavailable', errors=['camera disconnected'])
        self.value['inputs']['webcam'] = {'status': 'unavailable', 'error': 'camera disconnected'}
        self.value['tags'] = [{'id': 100, 'nx': .5, 'ny': .5}]
        self.assertEqual(self.game._physical_observation()['status'], 'unavailable')
        result = self.game.game_snapshot()['inputs']['board']
        self.assertEqual(result['status'], 'unavailable')
        self.assertEqual(result['upstream']['inputs']['webcam']['error'], 'camera disconnected')
        self.game._hub_ctx = FakeContext({})
        self.game._physical_observation()
        self.assertEqual(self.game.game_snapshot()['inputs']['board']['upstream'], {})

    def test_incompatible_contracts_do_not_forward_untrusted_reports(self):
        for version in (2, True, '1'):
            with self.subTest(version=version):
                self.value['version'] = version
                self.assertEqual(self.game._physical_observation()['status'], 'unavailable')
                self.assertEqual(self.game.game_snapshot()['inputs']['board']['upstream'], {})

    def test_malformed_optional_diagnostics_cannot_break_valid_game_input(self):
        self.value.update(inputs={'bad': {'status': [], 'error': {'a': 1}, 'version': True}}, frame_at=float('nan'))
        self.value['tracking'] = {'contract': 'photon.board.tracking', 'version': 2, 'inputs': {'hidden': {}}}
        self.game._physical_observation()
        result = self.game.game_snapshot()['inputs']['board']
        self.assertEqual(result['status'], 'ready')
        self.assertEqual(result['upstream']['tracking']['inputs'], {})
        self.assertEqual(result['upstream']['inputs']['bad']['status'], 'unavailable')
        self.assertIsNone(result['upstream']['frame_at'])
        json.dumps(result, allow_nan=False)

    def test_changed_or_malformed_placement_contract_fails_closed(self):
        self.value['placement']['version'] = 2
        self.assertEqual(self.game._physical_observation()['status'], 'unavailable')
        self.assertIn('placement contract mismatch', self.game.game_snapshot()['inputs']['board']['error'])
        self.value['placement']['version'] = 1
        self.value['placement']['relations'] = [{'relation_id': 'bad'}]
        self.assertEqual(self.game._physical_observation()['status'], 'unavailable')
        self.assertIn('placement payload is invalid', self.game.game_snapshot()['inputs']['board']['error'])


if __name__ == '__main__':
    unittest.main()
