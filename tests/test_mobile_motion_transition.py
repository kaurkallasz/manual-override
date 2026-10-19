"""Reproduce a retained test shop after reset/restart without opening any robot."""
import ast
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from mobile_ltz_fixture import create_app
from test_photon_framework import FakeContext, ROOT


class MotionTransitionTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.app, self.game = create_app(self.folder.name)
        self.addCleanup(self.app.config['fixture_cleanup'])
        self.addCleanup(self.game.hub_stop)
        self.game._engine.stop_background()
        self.progress = self.game._module('photon-progress')
        for side in ('green', 'purple'):
            self.progress.player_command(side, {'action':'select','player_id':'ltz-test-'+side})
        source = (ROOT/'sandboxes/gamemaster/prototypes/dobot-mg400-relay/prototype.py').read_text()
        node = next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='_ltz_motion_error')
        namespace = {'_hub_ctx':FakeContext({'photon-game':self.game,'photon-progress':self.progress})}
        exec(compile(ast.Module(body=[node],type_ignores=[]),'relay-policy','exec'),namespace)
        self.relay_check = namespace['_ltz_motion_error']
        self.client = self.app.test_client()

    def shop(self):
        state = self.game.apply_command({'action':'start','virtual_play':True,'reward_enabled':False})
        self.run_id = state['run_id']
        self.game.apply_command({'action':'test_end_match','run_id':self.run_id})

    def projected(self, side):
        value = self.client.get('/s/gamemaster/p/mobile-ltz-api/api/state?side='+side).json
        self.assertEqual(value['status'], 'ready')
        return value['mobile_motion_policy']

    def test_reset_and_restart_allow_granted_setup_tier_preserving_shop_and_saved_players(self):
        self.shop()
        players = {s:self.progress.progress_snapshot({'side':s})['player'] for s in ('green','purple')}
        self.game.apply_command({'action':'reset'})
        j = self.game._journey
        self.game._journey = type(j)(j.path, j.module_reader, j.wake)
        for virtual in (True, False):
            self.game._engine.set_virtual_play(virtual)
            for tier, action in enumerate(('joint','xyz','image','cue'), 1):
                self.game.apply_command({'action':'virtual_test_loadout','levels':None,'control':tier})
                for side in ('green','purple'):
                    with self.subTest(virtual=virtual, tier=tier, side=side):
                        policy = self.projected(side)
                        self.assertEqual(policy, self.game.motion_policy(side))
                        self.assertEqual((policy['scope'],policy['tier'],policy['blocked']), ('practice',tier,False))
                        self.assertIsNone(self.relay_check(side, {'mode':'joint' if tier==1 else 'cartesian','ltz_action':action}))
                        if tier<4:
                            self.assertIn('locked', self.relay_check(side, {'mode':'cartesian','ltz_action':'cue'}))
                        self.assertEqual(self.progress.progress_snapshot({'side':side})['player'],players[side])
        self.assertTrue(self.game._journey.snapshot()['practice_shop'])
        self.assertEqual(self.game._journey.snapshot()['id'], self.run_id)
        result = self.game.apply_command({'action':'test_next_level','run_id':self.run_id})
        self.assertEqual(result['journey']['phase'],'lobby')

    def test_finished_shop_still_blocks_and_same_reason_reaches_relay_and_mobile(self):
        self.shop()
        for side in ('green','purple'):
            policy = self.projected(side)
            self.assertTrue(policy['blocked'])
            self.assertIn('Practice upgrades',policy['error'])
            self.assertEqual(self.relay_check(side,{'mode':'cartesian','ltz_action':'cue'}),policy['error'])
            with self.assertRaisesRegex(ValueError,'Practice upgrades'):
                self.game.mobile_command({'action':'connect','side':side})
        self.game.apply_command({'action':'reset'})
        self.game.apply_command({'action':'virtual_test_loadout','levels':None,'control':None})
        self.assertTrue(self.game.motion_policy('green')['blocked'], 'Setup alone cannot grant test controls')

    def test_setup_grant_cannot_override_calibration_or_unconfirmed_stop(self):
        self.shop()
        self.game.apply_command({'action':'reset'})
        for state, reason in [({'phase':'calibration'}, 'calibration'),
                              ({'phase':'lobby','motion_blocked':True,'motion_error':'Previous arm stop unconfirmed'}, 'stop unconfirmed')]:
            with patch.object(self.game,'journey_snapshot',return_value=state):
                for side in ('green','purple'):
                    policy = self.projected(side)
                    self.assertTrue(policy['blocked'])
                    self.assertIn(reason, self.relay_check(side, {'mode':'cartesian','ltz_action':'cue'}))

    def test_missing_or_invalid_motion_contract_fails_closed_in_mobile_projection(self):
        for invalid in (None, {'contract':'wrong','version':1},
                        {'contract':'photon.game.motion','version':True,'status':'ready','blocked':False,'scope':'practice'}):
            with patch.object(self.game,'motion_policy',return_value=invalid):
                for side in ('green','purple'):
                    policy = self.projected(side)
                    self.assertEqual(policy['status'],'unavailable')
                    self.assertTrue(policy['blocked'])


if __name__ == '__main__':
    unittest.main()
