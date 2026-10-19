"""Ring-only core unlocking, real camera evidence, and durable zero-kill wins."""
import copy
import unittest
from unittest.mock import patch
import test_event_game as fixture
import test_photon_core_stack as core_fixture
from test_photon_framework import load


class RingCoreCameraTests(unittest.TestCase):
    sample = core_fixture.CoreStackTests.sample
    activate_first = core_fixture.CoreStackTests.activate_first
    cover = core_fixture.CoreStackTests.cover

    def setUp(self):
        self.game=load('photon-game');self.board=load('photon-board')
        self.bundle=load('photon-level').runtime_bundle()
        self.new_engine(1)

    def new_engine(self,level):
        self.engine=self.game.DefenseEngine(self.bundle['runtime'],self.bundle['waves'])
        self.engine.set_virtual_play(False)
        self.engine.start({'first_wave_delay_s':300},event_game={
            'level':level,'atoms':{'green':{'tag':100},'purple':{'tag':102}}})
        for i,marker in enumerate((41,43,42,45,54,46,52,53)):
            tag=100 if i%2==0 else 102
            self.engine.place(tag,self.engine.level.socket_by_marker[marker],source='physical')
        self.assertIsNotNone(self.engine.ring_completed_at)
        self.engine.run_started_at=self.engine.ring_completed_wall_at=90
        self.tracker=self.board.PhysicalPlacementTracker();self.now=100
        self.connected={'green':True,'purple':True}

    def test_both_physical_orders_complete_every_level_with_zero_kills(self):
        for level in (1,2,3,4):
            for lower,upper in ((100,102),(102,100)):
                with self.subTest(level=level,lower=lower):
                    self.new_engine(level)
                    self.activate_first(lower)
                    self.cover(upper)
                    self.assertEqual(self.engine.core_stage,'detonating')
                    for _ in range(30):self.engine.step(.1)
                    self.assertEqual(self.engine.phase,'won')
                    self.assertEqual(self.engine.kills,0)
                    self.assertEqual(self.engine.rewards.victory_method,'center_stack')
                    self.cover(upper)
                    self.assertEqual(sum(e['kind']=='core_detonation_started' for e in self.engine.events),1)

    def test_rejected_evidence_retries_without_lifting_the_atom(self):
        self.sample([38,100]);self.sample([100],.3)
        with patch.object(self.engine,'activate_core_tag',side_effect=ValueError('temporary gameplay block')):
            placement=self.sample([100],.3)
        self.assertEqual(self.engine.core_stage,'ring_ready')
        self.assertNotIn(100,self.engine.physical_relation_tokens)
        self.engine.ingest_physical(copy.deepcopy(placement))
        self.assertEqual(self.engine.core_stage,'first_tag')
        self.assertEqual(self.engine.core_first_tag,100)

    def test_no_ring_still_blocks_and_locked_atom_still_rejected(self):
        self.engine.ring_completed_at=None;self.engine.core_stage='locked'
        self.sample([38,100]);self.sample([100],.3);self.sample([100],.3)
        self.assertIsNone(self.engine.core_first_tag)
        with self.assertRaisesRegex(ValueError,'ring'):
            self.engine.activate_core_tag(100,source='operator')
        self.engine.ring_completed_at=0;self.engine.core_stage='ring_ready'
        with self.assertRaisesRegex(ValueError,'L4'):
            self.engine.activate_core_tag(101,source='operator')
        self.engine.event_game['level']=4
        self.engine.activate_core_tag(100,source='operator')
        with self.assertRaisesRegex(ValueError,'opposing team'):
            self.engine.activate_core_tag(101,source='operator')


class RingCoreSettlementTests(unittest.TestCase):
    setUp=fixture.EventGameTests.setUp
    command=fixture.EventGameTests.command
    start=fixture.EventGameTests.start

    def test_manual_zero_kill_win_saves_stats_bonus_and_unlocks_once(self):
        self.g._engine.stop_background()
        self.assertEqual(self.command('configure',settings={'first_wave_delay_s':300}).status_code,200)
        self.start();engine=self.g._engine
        self.assertNotIn('stack_combat',self.g.game_snapshot())
        for i,marker in enumerate((41,43,42,45,54,46,52,53)):
            result=self.command('operator_atom',socket_id=engine.level.socket_by_marker[marker],atom_tag_id=100 if i%2==0 else 102)
            self.assertEqual(result.status_code,200,result.get_json())
        for tag in (102,102,100,100):
            result=self.command('operator_core',atom_tag_id=tag)
            self.assertEqual(result.status_code,200,result.get_json())
        for _ in range(90):engine.step(.1)
        self.assertEqual(engine.phase,'won');self.assertEqual(engine.kills,0)
        self.g._progress.flush()
        owner=self.g._module('photon-progress')
        first={side:owner.public_snapshot(side) for side in ('green','purple')}
        for side,value in first.items():
            p=value['player'];receipt=value['latest_result']
            self.assertEqual((p['current_control_tier'],p['levels']['forcefield'],p['wins']),(2,2,1))
            self.assertEqual(receipt['statistics']['total_kills'],0)
            self.assertEqual(receipt['statistics']['score'],0)
            self.assertEqual(receipt['victory_method'],'center_stack')
            self.assertGreater(receipt['stack_bonus'],0)
        self.g._progress.flush()
        for side in first:
            again=owner.public_snapshot(side)
            self.assertEqual(again['player'],first[side]['player'])
            self.assertEqual(again['latest_result'],first[side]['latest_result'])
        self.assertEqual(self.g.journey_snapshot()['phase'],'results')


if __name__=='__main__':unittest.main()
