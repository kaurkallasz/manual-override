"""Replay settlement with the production hub's helper-import isolation."""
import json
import sys
from contextlib import contextmanager
from unittest.mock import patch

import test_results_replay_heatmap as results
from test_photon_framework import ROOT


@contextmanager
def isolated_helpers():
    # Match Hub._load_one: owners retain references, but helper names and their
    # temporary import directories are no longer globally importable at runtime.
    helpers={name:module for name,module in list(sys.modules.items())
             if str(getattr(module,'__file__','') or '').startswith(str(ROOT/'sandboxes')+'/')}
    paths=list(sys.path)
    for name in helpers:sys.modules.pop(name,None)
    sys.path[:]=[p for p in paths if not str(p).startswith(str(ROOT/'sandboxes'))]
    try:yield
    finally:
        sys.modules.update(helpers)
        sys.path[:]=paths


class IsolatedResultSaveTests(results.ResultChoiceTests):
    def setUp(self):
        super().setUp()
        self.enterContext(isolated_helpers())

    def test_two_replayed_l4_wins_each_save_and_return_to_game_over(self):
        run=self.l4_result()
        for _ in range(2):
            self.choose('green',run,'replay_level');self.choose('purple',run,'replay_level')
            self.assertEqual(self.g.game_snapshot()['contract_control_tier'],4)
            previous=run;run=self.finish()
            self.assertNotEqual(run,previous)
            state=self.g.game_snapshot()
            self.assertEqual(state['result_save']['status'],'saved')
            self.assertTrue(state['journey']['game_complete'])
            self.assertEqual(state['journey']['phase'],'results')
            for side in ('green','purple'):
                receipt=self.g._module('photon-progress').public_snapshot(side)['latest_result']
                self.assertEqual(receipt['run_id'],run)
                self.assertTrue(receipt['statistics']['game_complete'])
            self.assertFalse(self.g._progress.path.exists())

    def test_pending_l4_win_is_recovered_once_after_saver_restarts(self):
        run=self.l4_result()
        for side in ('green','purple'):self.choose(side,run,'replay_level')
        owner=self.g._module('photon-progress')
        before={side:owner.public_snapshot(side)['player'] for side in ('green','purple')}
        with patch.object(owner,'finalize_attempt',side_effect=ValueError('Save temporarily unavailable')):
            with self.assertRaisesRegex(ValueError,'pending save'):self.finish()
        pending=json.loads(self.g._progress.path.read_text())
        self.assertEqual((pending['outcome'],pending['run_id']),('won',self.g._run_id))
        old=self.g._progress
        self.g._progress=self.g.ProgressLink(old.module_reader,old.engine_reader,old.wake,old.path,old.result_listener,old.tick)
        self.g._progress.roster()  # Restore the durable result before recovering unfinished attempts.
        first={side:owner.public_snapshot(side) for side in ('green','purple')}
        self.assertTrue(self.g._journey.snapshot()['game_complete'])
        for side in first:
            self.assertEqual(first[side]['latest_result']['run_id'],pending['run_id'])
            self.assertEqual(first[side]['player']['wins'],before[side]['wins']+1)
        self.g._progress.roster();owner.finalize_attempt(pending)
        for side in first:self.assertEqual(owner.public_snapshot(side),first[side])
        self.assertFalse(old.path.exists())
