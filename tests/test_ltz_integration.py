"""LTZ contracts and fault injection with temporary stores and no hardware."""
import ast
import copy
import json
import math
from pathlib import Path
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import patch
import uuid

from test_photon_framework import load, FakeContext, ROOT, Flask


class LtzIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.progress = load('photon-progress')
        self.progress.DATA_DIR = self.path
        self.progress.hub_init(None)
        self.addCleanup(self.progress.hub_stop)
        self.store = self.progress._store
        self.player_id = self.store.create_player('Test player', uuid.uuid4().hex)['player_id']
        self.store.select_player('green', self.player_id)
        self.game = load('photon-game')
        self.bundle = load('photon-level').runtime_bundle()

    def engine(self, level=1, tier=1):
        engine = self.game.DefenseEngine(self.bundle['runtime'], self.bundle['waves'])
        engine.set_virtual_play(True)
        slots = list(engine.level.sockets)
        engine.place(100, slots[0], source='virtual', team='green')
        progression = {'green': {'control_tier': tier, 'levels': {track:level for track in self.store.snapshot('green')['player']['levels']}}}
        engine.start(progression=progression)
        engine.runtime_time = 20
        return engine

    def test_default_and_upgraded_unit_health_and_actual_damage(self):
        damages = []
        for level in range(1, 5):
            engine = self.engine(level)
            tower = next(iter(engine.placements.values()))
            self.assertAlmostEqual(tower['base_max_hp'], engine._tower_max_hp() * (1 + .1 * (level - 1)))
            self.assertEqual(engine.snapshot()['towers'][0]['upgrade_level'], level)
            tower['aim_angle'] = 0
            enemy = {'id':1, 'hp':1000, 'x':tower['x'] + 30, 'y':tower['y'], 'progress':0}
            engine.enemies = {1:enemy}
            engine._fire_towers(.1, set())
            damages.append(1000-enemy['hp'])
        for i, damage in enumerate(damages):
            self.assertAlmostEqual(damage, damages[0] * (1 + .1*i))

    def test_fields_use_weaker_owner_and_keep_geometry(self):
        engine = self.engine(4)
        slots = list(engine.level.sockets)
        engine.place(101, slots[1], source='virtual', team='green')
        field = engine._create_force_field(slots[0], slots[1], check_line_of_sight=False)
        self.assertEqual((field['upgrade_level'], field['visual_width_px']), (4, 12.5))
        self.assertEqual(field['capacity'], round(engine.settings['force_field_hit_capacity']*1.6))
        self.assertEqual(engine._field_upgrade({'owner':'green'}, {'owner':'purple'})['upgrade_level'], 1)
        public = next(f for f in engine.snapshot()['connections'] if f['field_id']==field['field_id'])
        self.assertEqual(public['upgrade_level'], 4)
        self.assertEqual(public['ax'], field['ax'])

    def test_orc_preview_matches_launch_and_overflow_is_retained(self):
        totals = []
        for tier in range(1, 5):
            engine = self.engine(tier=tier)
            engine.settings['enemy_count_multiplier'] = 1.7
            expected = self.game.orc_schedule(engine.settings, engine.wave_source, tier)
            engine.launched_waves = []
            for wave in range(1, len(expected['waves'])+1):
                engine._launch_wave(wave)
            actual = [[g['count'] for g in w['groups']] for w in engine.launched_waves]
            self.assertEqual(actual, expected['groups'])
            totals.append(expected['total'])
        self.assertTrue(all(b>a for a,b in zip(totals,totals[1:])))
        engine.sim_time = 999
        group = dict(engine.launched_waves[0]['groups'][0], count=4000, spawned=0)
        engine.launched_waves = [{'started_at':0, 'groups':[group]}]
        with patch.object(engine, '_spawn_enemy', return_value=False):
            engine._spawn_due()
        self.assertEqual(group['spawned'], 2000)
        self.assertEqual(engine.pressure_bank, 2000)
        self.assertEqual(group['count']-group['spawned'], 2000)

    def test_outbox_written_offline_then_replayed_exactly_once(self):
        engine = self.engine()
        modules = {'photon-progress':self.progress}
        link = self.game.ProgressLink(modules.get, lambda:engine, lambda:None, self.path/'pending.json')
        link.begin({'run_id':'offline-run','reward_enabled':True,'metadata':{}})
        engine.phase, engine.kills, engine.sim_time = 'won', 42, 15
        modules.clear()
        with self.assertRaises(ValueError): link.flush()
        self.assertTrue(link.path.exists())
        saved = json.loads(link.path.read_text())
        self.assertEqual((saved['kills'],saved['outcome']), (42,'won'))
        modules['photon-progress'] = self.progress
        # A fresh process replays the terminal result before interruption recovery.
        fresh = self.game.ProgressLink(modules.get, lambda:engine, lambda:None, link.path)
        fresh.roster()
        self.assertFalse(link.path.exists())
        self.progress.finalize_attempt(saved)
        player = self.store.snapshot('green')['player']
        self.assertEqual((player['credits'],player['wins']), (42,1))

    def test_transaction_committed_but_ack_lost_retries_without_double_award(self):
        engine = self.engine()
        link = self.game.ProgressLink(lambda _:self.progress, lambda:engine, lambda:None, self.path/'pending.json')
        link.begin({'run_id':'ack-lost','reward_enabled':True,'metadata':{}})
        engine.phase, engine.kills = 'won', 70
        finalize = self.progress.finalize_attempt
        def lost(value):
            finalize(value)
            raise OSError('response lost after commit')
        with patch.object(self.progress, 'finalize_attempt', side_effect=lost):
            with self.assertRaises(ValueError): link.flush()
        link.flush()
        self.assertEqual(self.store.snapshot('green')['player']['credits'],70)
        self.assertEqual(self.store.snapshot('green')['player']['wins'],1)

    def test_routes_bind_side_and_do_not_accept_client_rewards(self):
        app = Flask('ltz-isolated-api')
        app.register_blueprint(self.progress.bp, url_prefix='/progress')
        client = app.test_client()
        green = {'hhh.roles':{'green'}}
        self.assertEqual(client.get('/progress/api/state?side=purple',environ_overrides=green).status_code,403)
        self.assertEqual(client.post('/progress/api/player?side=green',json={'action':'award','score':999},environ_overrides=green).status_code,400)
        self.assertEqual(client.get('/progress/api/backup',environ_overrides=green).status_code,403)
        self.assertEqual(client.get('/progress/api/state?side=green',environ_overrides=green).get_json()['player']['credits'],0)
        foreign=self.store.create_player('Foreign',uuid.uuid4().hex)['player_id']
        self.store.select_player('purple',foreign)
        data=client.get('/progress/api/state?side=green',environ_overrides=green).get_json()
        self.assertNotIn('credits',data['roster']['purple'])
        history=client.get('/progress/api/history?side=green&player_id='+foreign,environ_overrides=green).get_json()
        self.assertEqual(history['history']['total'],0)

    def test_relay_checks_authoritative_active_tier_and_fails_closed(self):
        # Compile just the real policy function, without importing any arm driver.
        source=(ROOT/'sandboxes/gamemaster/prototypes/dobot-mg400-relay/prototype.py').read_text()
        node=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='_ltz_motion_error')
        context=FakeContext({'photon-progress':self.progress})
        namespace={'_hub_ctx':context}
        exec(compile(ast.Module(body=[node],type_ignores=[]),'relay-policy','exec'),namespace)
        check=namespace['_ltz_motion_error']
        self.progress.begin_attempt({'run_id':'control','reward_enabled':True,'metadata':{}})
        self.assertIsNone(check('green',{'mode':'joint'}))
        self.assertIn('locked',check('green',{'mode':'cartesian','ltz_action':'cue','tier':4}))
        self.assertIn('invalid',check('green',{'mode':'cartesian','ltz_action':'joint'}))
        self.assertIn('locked',check('purple',{'mode':'joint'}))
        with patch.object(self.progress,'control_policy',return_value={'contract':'bad','version':1}):
            self.assertIn('Cannot verify',check('green',{'mode':'joint'}))

    def test_game_start_uses_saved_loadout_and_virtual_play_cannot_score(self):
        game=self.game
        game._settings=game.SettingsStore(self.path/'settings.json')
        game.LOG_PATH=str(self.path/'runs.jsonl')
        game._progress=self.game.ProgressLink(game._module,lambda:game._engine,game._live.bump,self.path/'pending.json')
        context=FakeContext({'photon-level':load('photon-level'),'photon-progress':self.progress})
        with patch.object(game.DefenseEngine,'start_background'):
            game.hub_init(context)
        self.addCleanup(game.hub_stop)
        with self.assertRaises(game.GameError):
            game.apply_command({'action':'start','virtual_play':True,'reward_enabled':True})
        def physical():game._inputs['board']={'status':'ready','error':None}
        with patch.object(game,'_physical_observation',side_effect=physical):
            result=game.apply_command({'action':'start','virtual_play':False,'reward_enabled':True})
        self.assertEqual(result['progress']['participants'][0]['player_id'],self.player_id)
        self.assertEqual(result['contract_control_tier'],1)
        with self.assertRaises(game.GameError):game.apply_command({'action':'start'})
        with self.assertRaises(game.GameError):game.apply_command({'action':'place','atom_tag_id':100})
        game._engine.kills=12
        game.apply_command({'action':'reset'})
        self.assertEqual(self.store.snapshot('green')['player']['credits'],12)
        self.assertEqual(self.store.snapshot('green')['player']['wins'],0)


    def virtual_game(self):
        game=self.game
        game._settings=game.SettingsStore(self.path/'settings.json')
        game.LOG_PATH=str(self.path/'runs.jsonl')
        game._progress=game.ProgressLink(game._module,lambda:game._engine,game._live.bump,self.path/'pending.json')
        with patch.object(game.DefenseEngine,'start_background'):
            game.hub_init(FakeContext({'photon-level':load('photon-level'),'photon-progress':self.progress}))
        self.addCleanup(game.hub_stop)
        game.apply_command({'action':'set_virtual','virtual_play':True})
        return game

    def test_virtual_unlocks_apply_to_both_teams_and_never_change_player(self):
        game=self.virtual_game()
        before=self.store.snapshot('green')['player']
        levels={track:4 for track in before['levels']}
        game.apply_command({'action':'virtual_test_loadout','levels':levels})
        slots=list(game._engine.level.sockets)
        for atom,slot in zip(range(100,104),slots):
            state=game.apply_command({'action':'place','atom_tag_id':atom,'socket_id':slot})
        self.assertEqual({tower['upgrade_level'] for tower in state['towers']},{4})
        state=game.apply_command({'action':'start','virtual_play':True,'reward_enabled':False})
        self.assertEqual({tower['upgrade_level'] for tower in state['towers']},{4})
        self.assertEqual(state['progress']['metadata']['virtual_test_loadout'],levels)
        game._engine.kills=999
        game.apply_command({'action':'reset','virtual_play':True})
        self.assertEqual(game._engine.virtual_test_loadout,levels)
        self.assertEqual(self.store.snapshot('green')['player'],before)

    def test_virtual_live_upgrades_refresh_health_fields_and_restore_profile(self):
        game=self.virtual_game();engine=game._engine;slots=list(engine.level.sockets)
        engine.place(100,slots[0],source='virtual');engine.place(102,slots[1],source='virtual')
        field=engine._create_force_field(slots[0],slots[1],check_line_of_sight=False)
        game.apply_command({'action':'start','virtual_play':True})
        field=engine.force_fields[field['field_id']]
        tower=engine.placements[slots[0]];tower['hp']=tower['max_hp']*.4
        levels={track:4 for track in self.store.snapshot('green')['player']['levels']}
        state=game.apply_command({'action':'virtual_test_loadout','levels':levels})
        self.assertEqual(tower['upgrade_level'],4)
        self.assertAlmostEqual(tower['hp']/tower['max_hp'],.4)
        self.assertEqual((field['upgrade_level'],field['visual_width_px']),(4,12.5))
        self.assertEqual(field['capacity'],round(engine.settings['force_field_hit_capacity']*1.6))
        game.apply_command({'action':'virtual_test_loadout','levels':None})
        self.assertEqual(tower['upgrade_level'],1)
        self.assertEqual(field['upgrade_level'],1)
        self.assertAlmostEqual(tower['hp']/tower['max_hp'],.4)

    def test_virtual_locked_turrets_and_invalid_inputs(self):
        game=self.virtual_game();engine=game._engine;slot=next(iter(engine.level.sockets))
        levels={track:4 for track in self.store.snapshot('green')['player']['levels']}
        levels['damage-machine-gun']=0
        game.apply_command({'action':'virtual_test_loadout','levels':levels})
        with self.assertRaisesRegex(game.GameError,'locked'):
            game.apply_command({'action':'place','atom_tag_id':100,'socket_id':slot})
        for bad in (dict(levels,forcefield=0),dict(levels,forcefield=5),dict(levels,forcefield=True),{},[],'4'):
            with self.assertRaises(game.GameError):game.apply_command({'action':'virtual_test_loadout','levels':bad})
            self.assertEqual(engine.virtual_test_loadout,levels)
        game.apply_command({'action':'set_virtual','virtual_play':False})
        self.assertEqual(engine._unit_level('green','machine_gun'),1)
        with self.assertRaises(game.GameError):game.apply_command({'action':'virtual_test_loadout','levels':levels})
        app=Flask('test-unlock-authorization');app.register_blueprint(game.bp,url_prefix='/game')
        with app.test_client() as client:
            response=client.post('/game/api/command',json={'action':'virtual_test_loadout','levels':levels},environ_overrides={'hhh.roles':{'green'}})
            self.assertEqual(response.status_code,403)

    def test_virtual_unlocks_work_without_progress_module(self):
        game=self.virtual_game();game._hub_ctx.modules.pop('photon-progress')
        levels={track:3 for track in self.store.snapshot('green')['player']['levels']}
        game.apply_command({'action':'virtual_test_loadout','levels':levels})
        state=game.apply_command({'action':'start','virtual_play':True})
        self.assertEqual(state['virtual_test_loadout'],levels)
        self.assertFalse(game._progress.attempt)


if __name__=='__main__':unittest.main()
