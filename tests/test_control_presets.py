"""Real schedule arithmetic, immutable presets and safe preparation clock."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from test_control_journey import owner_file
from test_photon_framework import load


class PresetTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.game=load('photon-game');self.level=load('photon-level');self.bundle=self.level.runtime_bundle()
        from photon_game_runtime.settings import DEFAULTS
        self.base=DEFAULTS.copy();self.Presets=owner_file('photon-game','presets.py').Presets
        self.store=self.Presets(Path(self.folder.name)/'presets.json');self.map='fixture-map'
    def test_migration_preserves_venue_and_seeds_four_increasing_candidates(self):
        self.store.ensure_map(self.map,self.base);snapshot=self.store.snapshot()
        self.assertEqual(len(snapshot['presets']),20)
        archers=[p for p in snapshot['presets'] if p['family']=='breaker-archer']
        self.assertEqual([p['tier'] for p in archers],[1,2,3,4])
        self.assertTrue(all(p['settings']['breaker_attack_mode']=='ranged' for p in archers))
        event=[p for p in snapshot['presets'] if p['family']=='event-progression-v1']
        self.assertEqual([p['settings']['enemy_health_multiplier'] for p in event],[1,2,8,10])
        self.assertEqual(set(snapshot['selected'].values()),{p['id'] for p in event})
        selected=dict(snapshot['selected'])
        self.store.ensure_map(self.map,self.base)
        self.assertEqual(self.store.snapshot(),snapshot)
        self.assertTrue(all(p['id'] not in selected.values() for p in archers))
        self.assertEqual([p['settings'] for p in snapshot['presets'] if p['family']=='legacy'],[self.base]*4)
        schedules=[self.game.orc_schedule(settings,self.bundle['waves'],i+1) for i,(settings,_) in enumerate(self.store.family_for_map(self.map,self.base))]
        self.assertTrue(all(b['total']>a['total'] and b['wave_interval_s']<a['wave_interval_s'] and b['release_rate_multiplier']>a['release_rate_multiplier'] for a,b in zip(schedules,schedules[1:])))
        self.assertGreater(schedules[0]['scheduled_end_s'],1300)
        self.assertLess(schedules[0]['scheduled_end_s'],1500)
    def test_difficulty_offsets_apply_once_to_each_group(self):
        settings,_=self.store.for_run(self.map,2,self.base)
        for offset in (-.1,-.05,0,.05,.1):
            incoming={**settings,'difficulty_offset':offset}
            schedule=self.game.orc_schedule(incoming,self.bundle['waves'],2)
            expected=[[max(1,round(g['count']*.22*1.08*(1+offset))) for g in w['groups']] for w in self.bundle['waves']]
            self.assertEqual(schedule['groups'],expected)
    def test_old_presets_keep_bytes_and_selection_when_archers_are_added(self):
        self.store.ensure_map(self.map,self.base)
        old=self.store.snapshot()
        old['presets']=[p for p in old['presets'] if p['family'] not in ('breaker-archer','ltz-horde-v1')]
        for preset in old['presets']:
            preset['settings']={k:v for k,v in preset['settings'].items() if not k.startswith('breaker_')}
        self.store.path.write_text(json.dumps({'schema_version':1,**old}))
        restarted=self.Presets(self.store.path)
        settings,_=restarted.for_run(self.map,1,self.base)
        self.assertEqual(settings['breaker_attack_mode'],'melee')
        snapshot=restarted.snapshot()
        self.assertEqual(snapshot['presets'][:len(old['presets'])],old['presets'])
        self.assertEqual(snapshot['selected'],old['selected'])
        self.assertEqual(len(snapshot['presets']),20)
        self.assertEqual(self.Presets(self.store.path).snapshot(),snapshot)
    def test_save_load_rename_restart_and_frozen_run(self):
        frozen,preset=self.store.for_run(self.map,1,self.base);original=copy.deepcopy(frozen)
        def command(action,name,**extra):return self.store.command({'action':action,'map_id':self.map,'tier':1,'name':name,'revision':self.store.snapshot()['revision'],**extra})
        settings={**frozen,'difficulty_offset':.05};saved=command('save','Evening',settings=settings)
        command('rename','Evening',new_name='Evening revised');command('load','Evening')
        self.assertEqual(frozen,original)
        restarted=self.Presets(self.store.path)
        self.assertEqual(restarted.for_run(self.map,1,self.base)[0],settings)
        self.assertNotEqual(saved['selected_preset']['id'],preset['id'])
        with self.assertRaisesRegex(ValueError,'reload'):self.store.command({'revision':0})
    def test_failed_atomic_save_keeps_published_revision(self):
        self.store.ensure_map(self.map,self.base);before=self.store.snapshot()
        with patch('os.replace',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):self.store.command({'action':'save','map_id':self.map,'tier':1,'name':'Failed','revision':before['revision'],'settings':self.base})
        self.assertEqual(self.store.snapshot(),before)
    def test_initial_delay_does_not_win_early_and_pauses_stop_clock(self):
        settings,_=self.store.for_run(self.map,1,self.base)
        engine=self.game.DefenseEngine(self.bundle['runtime'],self.bundle['waves'])
        engine.set_virtual_play(True);engine.start(settings)
        for _ in range(100):engine.step(.1)
        self.assertEqual(engine.phase,'running');self.assertEqual(engine.current_wave,0);self.assertFalse(engine.enemies)
        before=engine.sim_time;engine.pause(True)
        for _ in range(100):engine.step(.1)
        self.assertEqual(engine.sim_time,before);self.assertEqual(engine.telemetry['pause_count'],1)
        engine.pause(False)
        for _ in range(2901):engine.step(.1)
        self.assertEqual(engine.current_wave,1)
        self.assertEqual(engine.phase,'running')
    def test_core_shortcut_has_distinct_terminal_telemetry(self):
        engine=self.game.DefenseEngine(self.bundle['runtime'],self.bundle['waves'])
        engine.core_stage='complete';engine._event('run_won',reason='core_tag_detonation')
        self.assertEqual(engine.telemetry['outcome_reason'],'core activation')


if __name__=='__main__':unittest.main()
