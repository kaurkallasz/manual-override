"""Saved calibration, Relay and mobile readiness agree; no hardware is opened."""
import copy
import math
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from test_photon_framework import FakeContext, load
from saved_calibration_fixture import seed


class MobileCalibrationSafetyTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.owner = load('auto-pickup-game')
        self.owner._lessons = self.owner.LessonStore(Path(folder.name) / 'lessons.json')
        self.owner.CALIBRATION2_PATH = str(Path(folder.name) / 'calibration.json')
        seed(self.owner)
        for arm in self.owner._calibration2['arms'].values():
            arm['rig_identity'] = {'ip':'fixture'}
        self.lens = {'contract':'hhh.camera-correction', 'version':1,
                     'status':'ready', 'calibration_revision':'fixture'}
        self.devices = {side:{'device':{'ip':'fixture'}} for side in ('green','purple')}
        self.owner._hub_ctx = FakeContext({
            'camera-calibration':SimpleNamespace(corrected_tag_snapshot=lambda a,b:copy.deepcopy(self.lens)),
            'dobot-mg400-relay':SimpleNamespace(arms_snapshot=lambda:{
                'contract':'hhh.relay.arms', 'version':1, 'status':'ready', 'arms':self.devices}),
        })
        self.relay = load('dobot-mg400-relay')
        self.mobile = load('mobile-ltz-api')
        context = FakeContext({'auto-pickup-game':self.owner})
        self.relay._hub_ctx = context
        self.mobile.hub_init(context)
        self.addCleanup(self.mobile.hub_stop)

    def snapshot(self, side, virtual=False):
        with patch.object(self.mobile, '_game', return_value=(None, {'virtual_play':virtual})), \
             patch.object(self.mobile, 'camera_view', return_value={'status':'ready'}):
            return self.mobile.mobile_snapshot(side)['mobile_safety']

    def test_changed_lens_rejects_saved_fit_with_same_reason_in_mobile_and_relay(self):
        before = self.owner._calibration2_public()
        for side in ('green','purple'):
            self.assertEqual(self.snapshot(side)['status'], 'ready')
            self.assertGreaterEqual(len(self.relay._server_cal2_guard(side)['polygon']), 3)
        self.lens['calibration_revision'] = 'new-lens'
        for side in ('green','purple'):
            safety = self.snapshot(side)
            self.assertEqual(safety['status'], 'unavailable')
            self.assertIn(f'{side.title()} camera correction changed', safety['error'])
            self.assertIn('Laser Tag Y', safety['error'])
            with self.assertRaises(ValueError) as error:
                self.relay._server_cal2_guard(side)
            self.assertIn(safety['error'], str(error.exception))
        self.assertEqual(self.owner._calibration2_public(), before)
        # A matching correction restores readiness without replacing saved measurements.
        self.lens['calibration_revision'] = 'fixture'
        self.assertEqual(self.snapshot('green')['status'], 'ready')

    def test_connection_mismatch_is_side_scoped_and_preview_omits_private_guard_and_sessions(self):
        self.devices['green']['device'] = {'ip':'another-arm'}
        green, purple = self.snapshot('green'), self.snapshot('purple')
        self.assertIn('Green arm connection changed', green['error'])
        self.assertEqual(purple, {'status':'ready', 'revision':3})
        self.assertEqual(self.snapshot('green', virtual=True), {'status':'unused'})

    def test_missing_malformed_and_failed_safety_owner_stay_unavailable(self):
        values = [None, {}, {'contract':'other','version':1,'status':'ready'},
                  {'contract':'hhh.cal2.safety','version':True,'status':'ready'},
                  {'contract':'hhh.cal2.safety','version':1,'status':'unavailable','error':None}]
        for value in values:
            with self.subTest(value=value), patch.object(self.owner, 'calibration_safety_snapshot', return_value=value):
                self.assertEqual(self.snapshot('green')['status'], 'unavailable')
                with self.assertRaises(ValueError):
                    self.relay._server_cal2_guard('green')
        with patch.object(self.owner, 'calibration_safety_snapshot', side_effect=ValueError('Camera offline')):
            self.assertEqual(self.snapshot('green'), {'status':'unavailable','error':'Camera offline'})
        self.mobile._ctx = FakeContext({})
        self.assertEqual(self.snapshot('green')['status'], 'unavailable')

    def test_reach_expands_beyond_samples_but_relay_preserves_physical_margin_and_exclusions(self):
        public = self.owner._calibration2_public()['motion_envelope']
        self.assertEqual(public['contract'], 'hhh.cal2.reach')
        self.assertEqual(public['guard']['radius_max'], 439)
        self.assertEqual(public['physical_radius_max'] - public['guard']['radius_max'], 1)
        for side in ('green', 'purple'):
            guard = self.relay._server_cal2_guard(side)
            self.assertEqual(guard, public['guard'])
            # Outside the capture centres, still inside the configured reach.
            for pose in ([438,0,20], [310,-290,20], [369,-236,20]):
                self.assertIsNone(self.relay._validate_cal2_joint_pose(pose,guard))
            for pose in ([439.1,0,20], [440,0,20], [219,0,20], [-300,0,20], [300,0,231]):
                self.assertIsNotNone(self.relay._validate_cal2_joint_pose(pose,guard))
            self.assertIsNone(self.relay._validate_cal2_cartesian_path([300,0,20],[425,0,20],guard))
            # Valid endpoints cannot authorize a straight path through the base.
            a=math.radians(140)
            self.assertIsNotNone(self.relay._validate_cal2_cartesian_path(
                [300*math.cos(a),300*math.sin(a),20], [300*math.cos(a),-300*math.sin(a),20],guard))


if __name__ == '__main__':
    unittest.main()
