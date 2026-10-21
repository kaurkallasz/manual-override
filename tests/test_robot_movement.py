"""Measured geometry, missing data, bounded recording, and saved result recovery."""
import copy
import json
import math
from pathlib import Path
import time
import unittest
from unittest.mock import patch
from test_photon_framework import load
import test_player_continue as continuation
from robot_movement_fixture import observation, seed


class MovementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.game=load('photon-game');cls.bundle=load('photon-level').runtime_bundle()
    def setUp(self):
        self.engine=self.game.DefenseEngine(self.bundle['runtime'],self.bundle['waves'])
        self.recorder=self.engine.robot_movement
        self.now=10000.0
    def sample(self,elapsed=0,change=None):
        value=observation(self.engine.level,self.now,elapsed)
        if change:change(value)
        with patch('time.time',return_value=self.now):self.recorder.observe(value,self.now,elapsed)
        self.now+=.1
        return value
    def test_opposing_arms_share_metric_axes_and_ground_plane(self):
        self.sample(change=lambda v:v['relay']['arms'].update({
            'green':{**v['relay']['arms']['green'],'pose':[350,-60,-20,0]},
            'purple':{**v['relay']['arms']['purple'],'pose':[850,60,-15,0]}}))
        result=self.recorder.snapshot()
        self.assertAlmostEqual(result['field']['width_mm'],1000,places=2)
        self.assertAlmostEqual(result['field']['height_mm'],600,places=2)
        for side in ('green','purple'):
            point=result['arms'][side]['segments'][0][0]
            for got,want in zip(point[1:],[250,240,80]):self.assertAlmostEqual(got,want,places=2)
    def test_stale_feedback_disconnect_and_epoch_do_not_bridge(self):
        self.sample()
        self.sample(.1,lambda v:v['relay']['arms']['green'].update(feedback_at=9990))
        self.sample(.2)
        self.sample(.3,lambda v:v['relay']['arms']['green'].update(connected=False))
        self.sample(.4)
        self.sample(.5,lambda v:v['relay']['arms']['green'].update(motion_epoch=2))
        result=self.recorder.snapshot()
        self.assertEqual(len(result['arms']['green']['segments']),4)
        self.assertEqual(len(result['arms']['purple']['segments']),1)
        self.assertEqual(result['arms']['green']['status'],'partial')
    def test_bad_geometry_and_identity_are_unavailable(self):
        self.sample(change=lambda v:v['calibration']['arms']['green'].update(samples=[[.5,.5,100,0,-100]]*6))
        self.assertEqual(self.recorder.snapshot()['arms']['green']['status'],'unavailable')
        self.sample(.1,lambda v:v['relay']['arms']['green'].update(device={'ip':'different'}))
        self.assertEqual(self.recorder.snapshot()['arms']['green']['segments'],[])
        self.sample(.2)
        self.sample(.3,lambda v:v['calibration']['arms']['green'].update(revision='changed'))
        self.assertIn('changed',self.recorder.snapshot()['arms']['green']['error'])
    def test_nan_and_camera_motion_break_recording(self):
        self.sample()
        self.sample(.1,lambda v:v['relay']['arms']['green'].update(pose=[math.nan,0,0,0]))
        self.assertEqual(self.recorder.snapshot()['arms']['green']['gaps'],1)
        def moved(v):
            for t in v['camera']['tags']:t['camera'][0]+=.05
        self.sample(.2,moved)
        self.assertIn('moved',self.recorder.snapshot()['arms']['purple']['error'])
    def test_bounded_paths_keep_first_last_and_segment_gaps(self):
        arm=self.recorder.arms['green']
        # Exercise the compactor with a path whose corners cannot be discarded by
        # the cheap collinearity filter. Timestamps survive geometry simplification.
        arm['segments']=[[[i*.01,i%2*100,math.sin(i)*200,40] for i in range(4500)]]
        self.recorder._bound('green')
        self.assertLessEqual(sum(map(len,arm['segments'])),3000)
        self.assertEqual(arm['segments'][0][0],[0,0,0,40])
        self.assertEqual(arm['segments'][0][-1][0],44.99)
        self.assertTrue(arm['simplified'])
    def test_engine_samples_only_active_play_and_resets_per_run(self):
        e=self.engine;e.phase='running';e.sim_time=1
        e.set_movement_source(lambda:observation(e.level,self.now,1))
        with patch('time.time',return_value=self.now):e.sample_movement(self.now)
        self.assertTrue(e.robot_movement.snapshot()['arms']['green']['segments'])
        e.paused=True;e.sample_movement(self.now+.1)
        self.assertTrue(e.robot_movement.broken['green'])
        e.reset();self.assertIsNot(e.robot_movement,self.recorder)
        e.phase='running';e.start_countdown_remaining_s=5;e.sample_movement(self.now+.2)
        self.assertFalse(e.robot_movement.snapshot()['arms']['green']['segments'])

    def test_calibration_owner_publishes_only_valid_bound_measurements(self):
        owner=load('auto-pickup-game')
        data=observation(self.engine.level,self.now)
        cal={'camera_revision':'camera','arms':{}}
        for side in ('green','purple'):
            evidence=data['calibration']['arms'][side]
            cal['arms'][side]={'camera_revision':'camera','rig_identity':evidence['device'],
                'points':{str(i):{'camera':{'u':u,'v':v},'pose':{'x':x,'y':y,'z':z,'set':True}}
                          for i,(u,v,x,y,z) in enumerate(evidence['samples'])}}
        with patch.object(owner,'_calibration2_public',return_value=cal),patch.object(owner,'_current_camera_revision',return_value='camera'):
            result=owner.movement_calibration_snapshot()
            self.assertEqual(result['contract'],'hhh.cal2.movement')
            self.assertEqual(result['arms']['green']['samples'],data['calibration']['arms']['green']['samples'])
            revision=result['arms']['green']['revision']
            cal['arms']['green']['points']['0']['pose']['z']+=1
            self.assertNotEqual(owner.movement_calibration_snapshot()['arms']['green']['revision'],revision)
            cal['arms']['purple']['camera_revision']='old-camera'
            self.assertEqual(owner.movement_calibration_snapshot()['arms']['purple']['status'],'unavailable')


class SavedMovementTests(unittest.TestCase):
    setUp=continuation.PlayerContinueTests.setUp
    command=continuation.PlayerContinueTests.command
    start=continuation.PlayerContinueTests.start
    finish=continuation.PlayerContinueTests.finish
    ready=continuation.PlayerContinueTests.ready
    def test_save_failure_retry_history_backup_and_replay(self):
        run=self.start();e=self.g._engine;seed(e,30)
        owner=self.g._module('photon-progress');store=owner._store
        expected=e.robot_movement.snapshot(e.sim_time)
        with patch.object(owner,'finalize_attempt',side_effect=ValueError('temporary storage failure')):
            with self.assertRaises(ValueError):self.finish()
        self.assertEqual(self.g._progress.pending['robot_movement'],expected)
        self.assertEqual(self.g.game_snapshot()['robot_movement'],expected)
        self.g._progress.flush()
        receipt=owner.public_snapshot('green')['latest_result']
        self.assertEqual(receipt['statistics']['robot_movement'],expected)
        self.assertEqual(store.history(receipt['player_id'],{})['rows'][0]['robot_movement'],expected)
        restored=owner.ProgressStore(Path(self.folder.name)/'movement-restored.db');restored.initialize()
        restored.import_backup(store.export())
        self.assertEqual(restored.attempt(run)['result']['robot_movement'],expected)
        invalid=copy.deepcopy(expected);invalid['arms']['green']['segments'][0][0][1]=math.nan
        from movement_results import validate_movement
        with self.assertRaises(ValueError):validate_movement(invalid)
        self.ready('green',run);self.ready('purple',run)
        self.assertFalse(self.g._engine.robot_movement.snapshot()['arms']['green']['segments'])
        self.assertEqual(store.attempt(run)['result']['robot_movement'],expected)
