"""Ranged breaker gameplay/regression tests with isolated engines and stores."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from test_photon_framework import load


class RangedBreakerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.game = load('photon-game')
        cls.bundle = load('photon-level').runtime_bundle()

    def engine(self, **settings):
        # Synthetic archer/target layouts deliberately have no home defenses.
        # Production home targeting is covered by test_starter_defenses.
        e = self.game.DefenseEngine({**self.bundle['runtime'], 'atom_homes': []}, self.bundle['waves'])
        e.set_virtual_play(True)
        e.start({'breaker_attack_mode': 'ranged', 'first_wave_delay_s': 1500,
                 'enemy_tower_damage_multiplier': 1, 'enemy_core_damage_multiplier': 1, **settings})
        return e

    def enemy(self, e, x=100, y=100, kind='breaker'):
        self.assertTrue(e._spawn_enemy(kind, {}))
        enemy = e.enemies[e.next_enemy_id-1]
        enemy.update(x=x, y=y, next_scan_at=0, vx=0, vy=0)
        return enemy

    def tower(self, e, x=300, y=100, index=0):
        sid = list(e.level.sockets)[index]
        tower = e._new_tower(100, sid, 'machine_gun', 'green', 'virtual')
        tower.update(x=x, y=y, hp=1000, max_hp=1000)
        e.placements[sid] = tower
        return tower

    def advance(self, e, enemies, seconds, step=.05):
        for _ in range(round(seconds/step)):
            e.sim_time += step
            e.ranged.advance_arrows()
            e.ranged.prepare(enemies, step)
            e.ranged.fire(enemies)

    def shot(self, e, enemy):
        e.ranged.prepare([enemy], .05)
        e.sim_time += .5
        e.ranged.fire([enemy])
        self.assertEqual(len(e.ranged.arrows), 1)
        return e.ranged.arrows[0]

    def test_tower_first_even_when_core_is_nearer_and_stopped_facing(self):
        e = self.engine()
        cx, cy = e.level.core['x'], e.level.core['y']
        enemy = self.enemy(e, cx-120, cy)
        tower = self.tower(e, cx-120, cy+180)
        e.ranged.prepare([enemy], .05)
        self.assertEqual(enemy['ranged_target']['socket_id'], tower['socket_id'])
        self.assertEqual((enemy['vx'], enemy['vy']), (0, 0))
        self.assertAlmostEqual(enemy['facing_y'], 1)
        self.assertEqual(e._enemy_motion_guide(enemy)['mode'], 'hold')
        self.assertEqual(e.snapshot(compact_enemies=True)['enemies'][0]['combat']['state'], 'aim')
        self.assertEqual(e.snapshot()['enemies'][0]['combat']['variant'], 'archer')

    def test_draw_cooldown_and_scaled_single_damage(self):
        e = self.engine(enemy_tower_damage_multiplier=.35)
        enemy = self.enemy(e);tower = self.tower(e)
        e.ranged.prepare([enemy], .05)
        self.advance(e, [enemy], .45)
        self.assertFalse(e.ranged.arrows)
        self.advance(e, [enemy], .05)
        self.assertEqual(e.ranged.stats['shots'], 1)
        self.advance(e, [enemy], 1.45)
        self.assertEqual(e.ranged.stats['shots'], 1)
        self.assertAlmostEqual(tower['hp'], 995.8)
        self.advance(e, [enemy], .05)
        self.assertEqual(e.ranged.stats['shots'], 2)

    def test_shields_prevent_acquisition_but_not_exposed_row_tower(self):
        e = self.engine();enemy = self.enemy(e);tower = self.tower(e)
        e._active_rows = [dict(ax=200, ay=0, bx=200, by=200)]
        e.ranged.prepare([enemy], .05)
        self.assertEqual(enemy['combat_state'], 'move')
        e._active_rows = [dict(ax=300, ay=0, bx=300, by=200)]
        enemy['next_scan_at'] = 0
        e.ranged.prepare([enemy], .05)
        self.assertEqual(enemy['combat_state'], 'aim', 'arrow reaches exposed pod edge before its own row')

    def test_force_field_midflight_blocks_without_wear_and_behind_does_not(self):
        for shield_x, expected in [(180, 'blocks'), (110, 'hits')]:
            e = self.engine();enemy = self.enemy(e);tower = self.tower(e)
            arrow = self.shot(e, enemy)
            e.sim_time += .15;e.ranged.advance_arrows()  # arrow now at x=163
            other = self.tower(e, 1200, 700, 1)
            e.force_fields['test'] = dict(ax=shield_x, ay=0, bx=shield_x, by=200, broken=False,
                from_socket=tower['socket_id'], to_socket=other['socket_id'], hits=3)
            e.sim_time = arrow['impact_at'];e.ranged.advance_arrows()
            self.assertEqual(e.ranged.stats[expected], 1)
            self.assertEqual(e.force_fields['test']['hits'], 3)
            self.assertEqual(tower['hp'], 1000 if expected == 'blocks' else 988)

    def test_replacement_invalidates_arrow_but_replenishment_does_not(self):
        for replace in (True, False):
            e = self.engine();enemy = self.enemy(e);tower = self.tower(e)
            arrow = self.shot(e, enemy)
            if replace:
                tower = self.tower(e)
            else:
                tower['hp'] = 1000
            e.sim_time = arrow['impact_at'];e.ranged.advance_arrows()
            self.assertEqual(tower['hp'], 1000 if replace else 988)
            self.assertEqual(e.ranged.stats['misses'], int(replace))

    def test_companion_hits_one_shared_pool(self):
        e = self.engine();enemy = self.enemy(e);tower = self.tower(e, 390)
        tower['companion'] = {'x': 260, 'y': 100, 'pod_size': 96}
        arrow = self.shot(e, enemy)
        self.assertTrue(arrow['target']['key'].endswith(':companion'))
        e.sim_time = arrow['impact_at'];e.ranged.advance_arrows()
        self.assertEqual(tower['hp'], 988)
        self.assertEqual(e.ranged.stats['hits'], 1)

    def test_removed_companion_consumes_arrow_without_parent_damage(self):
        e=self.engine();enemy=self.enemy(e);tower=self.tower(e,390)
        tower['companion']={'x':260,'y':100,'pod_size':96}
        arrow=self.shot(e,enemy);tower.pop('companion')
        e.sim_time=arrow['impact_at'];e.ranged.advance_arrows()
        self.assertEqual(tower['hp'],1000);self.assertEqual(e.ranged.stats['misses'],1)

    def test_no_contact_damage_and_death_before_after_release(self):
        e = self.engine();enemy = self.enemy(e);tower = self.tower(e, 100)
        e._damage_towers([enemy], .1)
        self.assertEqual(tower['hp'], 1000)
        e.ranged.prepare([enemy], .05)
        e.ranged.killed(enemy);del e.enemies[enemy['id']]
        self.advance(e, [], 1)
        self.assertFalse(e.ranged.arrows)
        enemy = self.enemy(e, 100, 200)
        arrow = self.shot(e, enemy)
        e.ranged.killed(enemy);del e.enemies[enemy['id']]
        e.sim_time = arrow['impact_at'];e.ranged.advance_arrows()
        self.assertEqual(tower['hp'], 988)

    def test_lost_target_resumes_and_no_extra_core_contact_damage(self):
        e = self.engine();enemy = self.enemy(e);tower = self.tower(e)
        e.ranged.prepare([enemy], .05);tower['destroyed'] = True
        e.ranged.prepare([enemy], .05)
        self.assertEqual(enemy['combat_state'], 'move')
        enemy['attacking'] = True
        enemy.update(x=e.level.core['x']-80, y=e.level.core['y'])
        hp = e.core_hp
        with patch.object(e, '_fire_towers'), patch.object(e, '_integrate_particles'):
            e.step(.1)
        self.assertEqual(e.core_hp, hp)

    def test_pause_and_reset(self):
        e = self.engine();enemy = self.enemy(e);self.tower(e)
        self.shot(e, enemy);before = copy.deepcopy(e.ranged.arrows)
        e.pause(True)
        for _ in range(10):e.step(.1)
        self.assertEqual(e.ranged.arrows, before)
        e.reset();self.assertFalse(e.ranged.arrows);self.assertFalse(e.enemies)

    def terminal_engine(self, hp):
        e = self.engine(wave_count=1, core_hp=hp)
        enemy = self.enemy(e, e.level.core['x']-150, e.level.core['y'])
        self.shot(e, enemy);e.enemies.clear()
        e.current_wave = 1;e.launched_waves = [{'wave': 1, 'started_at': 0, 'groups': []}]
        return e

    def test_last_arrow_delays_win_and_can_defeat(self):
        for hp, result in [(100, 'won'), (12, 'overrun')]:
            e = self.terminal_engine(hp)
            e.step(.05);self.assertEqual(e.phase, 'running')
            for _ in range(10):e.step(.05)
            self.assertEqual(e.phase, result)
            self.assertEqual(sum(event['kind'] in ('run_won', 'core_destroyed') for event in e.events), 1)

    def test_stack_neutralizes_flights_immediately(self):
        e = self.terminal_engine(100)
        e.core_stage='ring_ready';e.ring_completed_at=0
        e.activate_core_tag(100, source='virtual')
        e.activate_core_tag(102, source='virtual')
        self.assertFalse(e.ranged.arrows)
        for _ in range(30):e.step(.1)
        self.assertEqual(e.phase, 'won');self.assertEqual(e.core_hp, 100)
        self.assertEqual(e.telemetry['core_health_at_stack']['hp'], 100)

    def test_harmless_final_arrow_does_not_delay_or_linger_after_win(self):
        e=self.terminal_engine(100)
        e.ranged.arrows[0]['damage']=0
        e.step(.05)
        self.assertEqual(e.phase,'won');self.assertFalse(e.ranged.arrows)

    def test_actual_counts_and_legacy_behavior(self):
        e = self.engine(breaker_attack_mode='melee');enemy=self.enemy(e);tower=self.tower(e,100)
        e._damage_towers([enemy], .1)
        self.assertEqual(tower['hp'], 999)
        self.assertEqual(e.ranged.counts['released']['breaker'], 1)
        enemy['hp']=0;e.step(.1)
        self.assertEqual(e.ranged.counts['killed']['breaker'], 1)
        self.assertEqual(e.ranged.counts['combat_kills']['breaker'], 1)
        self.assertEqual(sum(e.ranged.counts['scheduled'].values()), 4584)

    def test_tower_destruction_uses_shared_reconciliation(self):
        e=self.engine();enemy=self.enemy(e);tower=self.tower(e);tower['hp']=10
        arrow=self.shot(e,enemy)
        with patch.object(e, '_after_tower_destruction', wraps=e._after_tower_destruction) as reconcile:
            e.sim_time=arrow['impact_at'];e.ranged.advance_arrows()
            self.assertEqual(reconcile.call_count,1)
        self.assertTrue(tower['destroyed']);self.assertEqual(e.ranged.stats['tower_destructions'],1)

    def test_settings_migrate_validate_and_freeze(self):
        from photon_game_runtime.settings import DEFAULTS, SettingsStore, validate_settings
        from photon_game_runtime.ranged_enemies import DEFAULTS as NEW
        for changed in ({'breaker_attack_mode':'bad'}, {'breaker_range':True}, {'breaker_draw_s':1.5,'breaker_interval_s':1}, {'breaker_arrow_speed':float('inf')}):
            self.assertTrue(validate_settings({**DEFAULTS, **changed})[1])
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'settings.json'
            old={k:v for k,v in DEFAULTS.items() if k not in NEW}
            path.write_text(json.dumps({'schema_version':1,'settings':old}))
            store=SettingsStore(path)
            self.assertIsNone(store.error);self.assertEqual(store.snapshot()['breaker_attack_mode'],'melee')
            settings={**store.snapshot(),'breaker_attack_mode':'ranged'}
            e=self.engine(**settings)
            store.update({**settings,'breaker_range':400})
            self.assertEqual(e.settings['breaker_range'],220)
            self.assertEqual(SettingsStore(path).snapshot()['breaker_range'],400)

    def test_new_tower_preempts_core_with_fresh_draw_and_existing_cooldown(self):
        e = self.engine()
        enemy = self.enemy(e, e.level.core['x']-150, e.level.core['y'])
        self.shot(e, enemy)
        tower = self.tower(e, enemy['x'], enemy['y']+100)
        e.ranged.prepare([enemy], .05)
        self.assertEqual(enemy['ranged_target']['socket_id'], tower['socket_id'])
        self.assertEqual(enemy['release_at'], 2)
        self.advance(e, [enemy], 1.4)
        self.assertEqual(e.ranged.stats['shots'], 1)
        self.advance(e, [enemy], .1)
        self.assertEqual(e.ranged.stats['shots'], 2)

    def test_supported_timesteps_have_identical_cadence_and_damage(self):
        outcomes = []
        for dt in (.025, .05, .1):
            e=self.engine();enemy=self.enemy(e);tower=self.tower(e)
            e.ranged.prepare([enemy], dt)
            self.advance(e, [enemy], 6, dt)
            outcomes.append((e.ranged.stats['shots'], e.ranged.stats['hits'], tower['hp']))
        self.assertEqual(outcomes, [(4, 4, 952)]*3)

    def test_real_step_holds_then_resumes_from_actual_position(self):
        e=self.engine();enemy=self.enemy(e)
        # Use the actual route instead of relocating this fixture's spawn.
        e.enemies.clear();e._spawn_enemy('breaker', {})
        enemy=next(iter(e.enemies.values()));enemy['next_scan_at']=0
        self.tower(e, enemy['x']+100, enemy['y'])
        start=(enemy['x'],enemy['y'])
        with patch.object(e, '_fire_towers'):
            for _ in range(20):e.step(.05)
            self.assertEqual((enemy['x'],enemy['y']),start)
            self.assertEqual(e.ranged.stats['shots'],1)
            e.placements.clear()
            for _ in range(20):e.step(.05)
        self.assertEqual(enemy['combat_state'],'move')
        self.assertGreater(__import__('math').dist(start,(enemy['x'],enemy['y'])),1)

    def test_range_hysteresis_release_recheck_and_broken_field(self):
        e=self.engine();enemy=self.enemy(e);tower=self.tower(e)
        e.ranged.prepare([enemy],.05)
        enemy['x']=60  # distance 240: retained, but outside acquisition range
        e.ranged.prepare([enemy],.05)
        self.assertEqual(enemy['combat_state'],'aim')
        enemy['x']=50
        e.sim_time=.5;e.ranged.fire([enemy])
        self.assertEqual(enemy['combat_state'],'move');self.assertFalse(e.ranged.arrows)
        enemy['x']=100;enemy['next_scan_at']=0
        other=self.tower(e,1200,700,1)
        e.force_fields['test']=dict(ax=180,ay=0,bx=180,by=200,broken=True,
            from_socket=tower['socket_id'],to_socket=other['socket_id'],hits=0)
        e.ranged.prepare([enemy],.05)
        self.assertEqual(enemy['combat_state'],'aim')

    def test_purge_and_combat_counts_are_separate(self):
        e=self.engine();a=self.enemy(e);b=self.enemy(e,200)
        a['hp']=0;b.update(hp=1,burn_until=10,burn_damage_per_s=100,purge_burn=True)
        e.step(.05)
        self.assertEqual(e.ranged.counts['killed']['breaker'],2)
        self.assertEqual(e.ranged.counts['combat_kills']['breaker'],1)
        self.assertEqual(e.ranged.counts['purge_kills']['breaker'],1)


if __name__=='__main__':unittest.main()
