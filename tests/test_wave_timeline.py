"""Timeline predictions follow actual wave clocks, including live practice retiming."""
import copy
import unittest
from unittest.mock import patch
import test_practice_intensity as practice


class WaveTimelineTests(unittest.TestCase):
    setUp = practice.PracticeIntensityTests.setUp
    virtual_game = practice.PracticeIntensityTests.virtual_game
    prepare = practice.PracticeIntensityTests.prepare
    select = practice.PracticeIntensityTests.select

    def test_setup_preview_uses_selected_saved_preset_and_start_matches_it(self):
        game=self.prepare()
        for tier in (1,2,3,4):
            state=self.select(game,tier)
            expected=game.orc_schedule(self.settings[tier],game._engine.wave_source,tier)['timings']
            actual=state['wave_timeline']
            self.assertEqual(actual['time_s'],0)
            self.assertEqual(len(actual['waves']),len(expected))
            for wave,timing in zip(actual['waves'],expected):
                self.assertAlmostEqual(wave['start_s'],timing['start_s'],places=2)
                self.assertAlmostEqual(wave['duration_s'],timing['duration_s'],places=2)
            started=game.apply_command({'action':'start','virtual_play':True})
            self.assertEqual(started['wave_timeline'],actual)
            game.apply_command({'action':'reset','virtual_play':True})

    def test_running_and_paused_clocks_preserve_actual_launched_windows(self):
        game=self.prepare();self.select(game,1)
        game.apply_command({'action':'start','virtual_play':True});e=game._engine
        e.sim_time=e.next_wave_at;e._launch_wave(1);e.sim_time+=5
        with patch.object(e,'_spawn_enemy',return_value=True):e._spawn_due()
        before=e.snapshot()['wave_timeline'];self.assertEqual(before['waves'][0]['state'],'spawning')
        e.pause(True);e.step(.1)
        self.assertEqual(e.snapshot()['wave_timeline'],before)
        now=e.sim_time;state=self.select(game,4);timeline=state['wave_timeline']
        self.assertEqual(timeline['time_s'],now)
        self.assertEqual(timeline['waves'][0]['start_s'],before['waves'][0]['start_s'])
        self.assertAlmostEqual(timeline['waves'][1]['start_s'],e.next_wave_at,places=2)
        end=max(g['release_at']+g['release_duration_s'] for g in e.launched_waves[0]['groups'])
        self.assertAlmostEqual(timeline['waves'][0]['end_s'],end,places=2)
        e.sim_time=end+.001  # First simulation tick past the floating-point deadline.
        with patch.object(e,'_spawn_enemy',return_value=True):e._spawn_due()
        wave=e.snapshot()['wave_timeline']['waves'][0]
        self.assertEqual(wave['state'],'released')
        self.assertAlmostEqual(wave['end_s'],end,places=2)
        self.select(game,2)
        self.assertEqual(e.snapshot()['wave_timeline']['waves'][0],wave)

    def test_congestion_and_overtime_are_visible_without_advancing_simulation(self):
        game=self.prepare();self.select(game,1)
        game.apply_command({'action':'start','virtual_play':True});e=game._engine
        e.sim_time=e.next_wave_at;e._launch_wave(1)
        e.sim_time=1000;e.pressure_bank=2000
        before=copy.deepcopy(e.launched_waves)
        timeline=e.snapshot()['wave_timeline']
        self.assertEqual(e.launched_waves,before)
        self.assertGreaterEqual(timeline['waves'][0]['end_s'],1000)
        self.assertGreaterEqual(timeline['end_s'],1000)
        self.assertEqual(timeline['queued_orcs'],2000)


if __name__=='__main__':unittest.main()
