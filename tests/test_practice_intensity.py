"""Saved per-map tiers must drive remaining practice spawns without resetting play."""
import copy
import unittest
from unittest.mock import patch
import test_ltz_integration as integration


class PracticeIntensityTests(unittest.TestCase):
    setUp = integration.LtzIntegrationTests.setUp
    virtual_game = integration.LtzIntegrationTests.virtual_game

    def prepare(self):
        game = self.virtual_game()
        self.settings = {}
        for tier in range(1, 5):
            settings = {**game._settings.snapshot(), 'wave_count': 4, 'first_wave_delay_s': 20.*tier,
                        'enemy_count_multiplier': .15*tier, 'wave_interval_s': 120./tier,
                        'release_rate_multiplier': .6+.2*tier, 'core_hp': 1000.+tier,
                        'brute_first_wave': tier}
            result = game.apply_command({'action': 'level_preset', 'preset_action': 'save',
                'map_id': game._level_projection['name'], 'tier': tier, 'name': f'Saved L{tier}',
                'revision': game._presets.snapshot()['revision'], 'settings': settings})
            self.settings[tier] = result['selected_preset']['settings']
        return game

    def select(self, game, tier, levels=None):
        return game.apply_command({'action': 'virtual_test_loadout', 'levels': levels, 'control': tier})

    def test_each_selection_uses_its_own_saved_map_preset_and_start_schedule(self):
        game = self.prepare()
        for tier in range(1, 5):
            with self.subTest(tier=tier):
                expected = game.orc_schedule(self.settings[tier], game._engine.wave_source, tier)
                selected = self.select(game, tier)
                self.assertEqual(selected['spawn_intensity']['preset'], f'Saved L{tier}')
                self.assertEqual(selected['spawn_intensity']['total'], expected['total'])
                state = game.apply_command({'action': 'start', 'virtual_play': True})
                self.assertEqual(state['contract_control_tier'], tier)
                self.assertEqual(game._engine.settings, self.settings[tier])
                self.assertEqual(state['progress']['metadata']['orc_schedule'], expected)
                self.assertEqual(state['spawn_intensity']['release_rate_multiplier'], expected['release_rate_multiplier'])
                game.apply_command({'action': 'reset', 'virtual_play': True})

    def test_live_switch_preserves_combat_and_retimes_unreleased_groups_without_burst(self):
        game = self.prepare(); self.select(game, 1)
        game.apply_command({'action': 'start', 'virtual_play': True})
        e = game._engine
        e.sim_time = e.next_wave_at; e._launch_wave(1)
        e.sim_time += 2; e._spawn_due()
        before_enemies = copy.deepcopy(e.enemies)
        before_groups = copy.deepcopy(e.launched_waves[0]['groups'])
        before_rule = copy.deepcopy(e.rewards.rule)
        old_wait = e.next_wave_at-e.sim_time
        old_interval = e.spawn_intensity['wave_interval_s']
        core = e.core_hp = e.core_max_hp*.7
        run = game._run_id; now = e.sim_time
        state = self.select(game, 4)
        expected = game.orc_schedule(self.settings[4], e.wave_source, 4)
        self.assertEqual(e.enemies, before_enemies)
        self.assertEqual((game._run_id,e.sim_time,e.core_hp),(run,now,core))
        self.assertEqual(e.settings['core_hp'], self.settings[1]['core_hp'])
        self.assertEqual(e.rewards.rule, before_rule)
        self.assertAlmostEqual(e.next_wave_at-now,old_wait/old_interval*expected['wave_interval_s'])
        for old, group, count in zip(before_groups,e.launched_waves[0]['groups'],expected['groups'][0]):
            self.assertEqual(group['spawned'],old['spawned'])
            self.assertEqual(group['count'],count)
        with patch.object(e,'_spawn_enemy',return_value=True) as spawn:
            e._spawn_due(); self.assertEqual(spawn.call_count,0)
            e.sim_time += 1; e._spawn_due(); self.assertGreater(spawn.call_count,0)
        e._launch_wave(2)
        self.assertEqual([g['count'] for g in e.launched_waves[-1]['groups']],expected['groups'][1])
        self.assertEqual(state['spawn_intensity']['tier'],4)
        self.assertFalse(e.rewards.eligible)

    def test_downgrade_keeps_queued_enemies_and_completed_groups_and_reapply_is_idempotent(self):
        game=self.prepare();self.select(game,4)
        game.apply_command({'action':'start','virtual_play':True});e=game._engine
        e.sim_time=e.next_wave_at;e._launch_wave(1);e.sim_time+=1
        with patch.object(e,'_spawn_enemy',return_value=False):e._spawn_due()
        queue=copy.deepcopy(e.pressure_queue);bank=e.pressure_bank
        group=e.launched_waves[0]['groups'][0];group['spawned']=group['count']
        finished=copy.deepcopy(group)
        e.paused=True
        state=self.select(game,2)
        self.assertTrue(state['paused']);self.assertEqual(group,finished)
        self.assertEqual((e.pressure_queue,e.pressure_bank),(queue,bank))
        schedule=copy.deepcopy(e.launched_waves);deadline=e.next_wave_at
        self.select(game,2)
        self.assertEqual((e.launched_waves,e.next_wave_at),(schedule,deadline))
        before=e.sim_time;e.step(.1);self.assertEqual(e.sim_time,before)
        self.select(game,None);self.assertEqual(e.contract_control_tier,1)

    def test_initial_delay_rescales_remaining_fraction_and_invalid_unlock_is_atomic(self):
        game=self.prepare();self.select(game,1)
        game.apply_command({'action':'start','virtual_play':True});e=game._engine
        e.sim_time=5
        self.select(game,4)
        self.assertEqual(e.next_wave_at,5+.75*80)
        before=copy.deepcopy((e.settings,e.spawn_intensity,e.virtual_test_control,e.next_wave_at))
        with self.assertRaises(game.GameError):self.select(game,2,{'invalid':4})
        self.assertEqual((e.settings,e.spawn_intensity,e.virtual_test_control,e.next_wave_at),before)
        with self.assertRaises(game.GameError):self.select(game,True)
        self.assertEqual((e.settings,e.spawn_intensity,e.virtual_test_control,e.next_wave_at),before)

    def test_retuned_practice_result_saves_all_kills_without_awarding_progress(self):
        game=self.prepare();self.select(game,1)
        before=self.store.snapshot('green')['player']
        game.apply_command({'action':'start','virtual_play':True});e=game._engine
        self.select(game,4)
        counts=e.ranged.counts['scheduled']
        self.assertGreater(sum(counts.values()),sum(e.rewards.rule['scheduled_counts'].values()))
        for kind,count in counts.items():
            for _ in range(count):e.rewards.killed({'enemy_type':kind})
        e.kills=sum(counts.values());e.phase='won';e.rewards.victory_method='waves_cleared'
        game._progress.flush()
        result=game._progress.snapshot()['result']
        self.assertEqual(result['kills'],e.kills)
        self.assertEqual(result['result']['telemetry']['practice_intensity_changes'][-1]['tier'],4)
        self.assertEqual(self.store.snapshot('green')['player'],before)


if __name__=='__main__':unittest.main()
