"""Saved pair, wallet and upgrade persistence; temporary SQLite, no hardware."""
import copy
import tempfile
import time
import unittest
import uuid
from types import SimpleNamespace
from pathlib import Path
from test_photon_framework import load


class LinkedGameTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(); self.addCleanup(self.folder.cleanup)
        self.module = load('photon-progress')
        self.store = self.module.ProgressStore(Path(self.folder.name) / 'progress.sqlite3')
        self.store.initialize()
        self.ids = {}
        for side in ('green', 'purple'):
            self.ids[side] = self.store.create_player(side, uuid.uuid4().hex, side=side)['player_id']

    def command(self, action, **extra):
        return self.store.game_command({'action': action, 'operation_id': uuid.uuid4().hex, **extra})

    def start(self):
        self.store.prepare_game()
        return self.store.begin({'run_id': uuid.uuid4().hex, 'reward_enabled': True, 'metadata': {}})

    def finish(self, attempt, kills=800, outcome='won'):
        return self.store.record({'run_id': attempt['run_id'], 'sequence': 1, 'kills': kills,
            'outcome': outcome, 'active_seconds': 60, 'finished_at': time.time(), 'released_orcs': kills}, final=True)

    def buy(self, side, track):
        state = self.store.snapshot(side)
        return self.store.mutate_player(side, {'action': 'purchase', 'track': track, 'level': 2,
            'operation_id': uuid.uuid4().hex, 'revision': state['player']['revision'],
            'catalog_revision': state['shop']['catalog_revision']})

    def test_start_l1_lock_save_load_restart_wallets_and_purchases(self):
        # Previous Purple profile was L2; a fresh game always starts both at L1.
        with self.store.transaction(write=True) as db:
            p = self.store._player(db, self.ids['purple'])
            p.update(current_control_tier=2, selected_control=2, unlocked_control=2, wins=3, attempts=3, wins_by_tier=[3,0,0,0])
            self.store._put_player(db, p)
        attempt = self.start(); game_id = attempt['game_id']
        self.assertEqual([p['control_tier'] for p in attempt['participants']], [1, 1])
        for action in ('new', 'save', 'load'):
            with self.assertRaisesRegex(ValueError, 'finish the current match'):
                self.command(action, game_id=game_id)
        result = self.finish(attempt, 3000)
        self.store.open_shop({'id': result['run_id']})
        costs = {s: self.buy(s, track)['price'] for s, track in
                 [('green', 'damage-machine-gun'), ('purple', 'forcefield')]}
        expected = {s: (3000-costs[s], self.store.snapshot(s)['player']['levels']) for s in self.ids}
        for side in self.ids:
            with self.assertRaisesRegex(ValueError, 'pair is locked'): self.store.select_player(side, None)
            with self.assertRaisesRegex(ValueError, 'pair is locked'): self.store.create_player('intruder', uuid.uuid4().hex, side=side)
        saved = self.command('save')['game_id']; self.assertEqual(saved, game_id)
        self.command('new')
        for side in self.ids:
            other = self.store.create_player('Other '+side, uuid.uuid4().hex)['player_id']
            self.store.select_player(side, other)
        self.command('load', game_id=saved)
        self.store = self.module.ProgressStore(self.store.path); self.store.initialize()
        for side, pid in self.ids.items():
            p = self.store.snapshot(side)['player']
            self.assertEqual(p['id'], pid)
            self.assertEqual((p['credits'], p['levels']), expected[side])
            self.assertEqual(p['current_control_tier'], 1)
        self.assertTrue(self.store.snapshot()['saved_games']['pair_locked'])
        self.assertEqual(self.store.snapshot()['active_attempts'], [])

    def test_three_new_wins_and_next_tier_restore_without_rolling_back_wallet(self):
        for _ in range(3): self.finish(self.start(), 20)
        original = self.command('save')['game_id']
        self.assertEqual(self.store.snapshot('green')['player']['current_control_tier'], 2)
        self.command('new')
        p = self.store.snapshot('green')['player']
        self.assertEqual((p['current_control_tier'], p['wins_by_tier'], p['game_wins_by_tier']), (1,[3,0,0,0],[0,0,0,0]))
        self.finish(self.start(), 10)
        self.assertEqual(self.store.snapshot('green')['player']['current_control_tier'], 1)
        self.command('load', game_id=original)
        p = self.store.snapshot('green')['player']
        self.assertEqual((p['current_control_tier'], p['credits'], p['game_wins_by_tier']), (2,70,[3,0,0,0]))

    def test_retries_invalid_load_and_backup_preserve_linked_pair(self):
        self.finish(self.start())
        value = {'action':'save', 'operation_id':uuid.uuid4().hex}
        saved = self.store.game_command(value)
        before = self.store.export()
        self.assertEqual(self.store.game_command(value), saved)
        self.assertEqual(self.store.export()['tables'], before['tables'])
        with self.assertRaises(ValueError): self.command('load', game_id='missing')
        self.assertEqual(self.store.export()['tables'], before['tables'])
        restored = self.module.ProgressStore(Path(self.folder.name) / 'restored.sqlite3'); restored.initialize()
        restored.import_backup(before)
        restored.game_command({'action':'load', 'game_id':saved['game_id'], 'operation_id':uuid.uuid4().hex})
        self.assertEqual({s:p['id'] for s,p in restored.snapshot()['roster'].items()}, self.ids)
        for side in self.ids: self.assertEqual(restored.snapshot(side)['player']['credits'], 800)

    def test_checkpoint_restart_retains_credits_without_resuming_battle(self):
        a=self.start()
        self.store.record({'run_id':a['run_id'],'sequence':1,'kills':17})
        self.store=self.module.ProgressStore(self.store.path);self.store.initialize();self.store.recover()
        self.assertEqual(self.store.snapshot()['active_attempts'], [])
        self.command('load', game_id=a['game_id'])
        for side in self.ids:self.assertEqual(self.store.snapshot(side)['player']['credits'],17)

    def test_migration_preserves_previous_pair_and_wallets_without_restoring_match(self):
        before=self.store.snapshot()
        with self.store.transaction(write=True) as db: db.execute('PRAGMA user_version=3')
        self.store.initialize()
        self.assertTrue(self.store.path.with_suffix('.pre-v4.sqlite3').exists())
        state=self.store.snapshot();self.assertEqual(state['roster'],before['roster'])
        self.assertIsNone(state['saved_games']['active_id'])
        self.assertEqual(len(state['saved_games']['rows']),1)
        self.command('load',game_id=state['saved_games']['rows'][0]['id'])
        self.assertEqual({s:p['id'] for s,p in self.store.snapshot()['roster'].items()}, self.ids)

    def test_late_final_result_updates_its_saved_game_once_without_changing_new_progress(self):
        attempt=self.start()
        self.store.record({'run_id':attempt['run_id'],'sequence':1,'kills':10})
        self.store.recover()
        self.command('new')
        final={'run_id':attempt['run_id'],'sequence':3,'kills':30,'outcome':'won',
               'active_seconds':30,'finished_at':time.time()+1,'released_orcs':30}
        self.store.record(final,final=True);self.store.record(final,final=True)
        p=self.store.snapshot('green')['player']
        self.assertEqual((p['credits'],p['game_wins_by_tier']),(30,[0,0,0,0]))
        self.command('load',game_id=attempt['game_id'])
        p=self.store.snapshot('green')['player']
        self.assertEqual((p['credits'],p['game_wins_by_tier']),(30,[1,0,0,0]))

    def test_game_selection_race_aborts_start_and_failed_load_is_atomic(self):
        self.store.prepare_game();state=self.store.snapshot()
        game_id=state['saved_games']['active_id']
        self.store.select_player('green',self.ids['green'])
        with self.assertRaisesRegex(ValueError,'saved game changed'):
            self.store.begin({'run_id':uuid.uuid4().hex,'reward_enabled':True,'metadata':{},'expected_game_id':game_id})
        self.assertEqual(self.store.snapshot()['active_attempts'],[])
        before=self.store.snapshot()
        with self.store.transaction(write=True) as db:
            import json
            row=json.loads(db.execute('SELECT data FROM saved_games WHERE id=?',(game_id,)).fetchone()[0])
            row['players']['purple']['player_id']='missing-player'
            db.execute('UPDATE saved_games SET data=? WHERE id=?',(json.dumps(row),game_id))
        with self.assertRaisesRegex(ValueError,'player not found'):self.command('load',game_id=game_id)
        with self.store.transaction() as db:
            self.assertEqual(dict(db.execute('SELECT side,player_id FROM sessions')),self.ids)
            self.assertIsNone(self.store._active_game(db))


class LinkedGameAPITests(unittest.TestCase):
    def test_game_start_and_player_load_are_serialized_and_clear_old_overrides(self):
        from mobile_ltz_fixture import create_app
        with tempfile.TemporaryDirectory() as folder:
            app, game = create_app(folder)
            try:
                game._engine.stop_background(); game._progress.stop()
                owner=game._module('photon-progress')
                game._engine.set_virtual_test_loadout(None,None)
                state=game.apply_command({'action':'start','virtual_play':True,'reward_enabled':False})
                self.assertEqual(state['contract_control_tier'],1)
                saved=owner.progress_snapshot()['saved_games']['active_id']
                client=app.test_client()
                path='/s/gamemaster/p/mobile-ltz-api/api/saved-game?side=green'
                payload={'action':'load','game_id':saved,'operation_id':uuid.uuid4().hex}
                self.assertEqual(client.post(path,json=payload).status_code,400)
                game.apply_command({'action':'reset','virtual_play':True})
                response=client.post(path,json=payload)
                self.assertEqual(response.status_code,200,response.get_json())
                self.assertEqual(game._engine.phase,'setup')
                self.assertIsNone(game._engine.virtual_test_control)
                self.assertTrue(owner.progress_snapshot()['saved_games']['pair_locked'])
                # Physical game changes revoke both previous leases before replacing the pair.
                calls=[];connected={'green':True,'purple':True};settled={'value':False}
                relay=SimpleNamespace(
                    arms_snapshot=lambda:{'contract':'hhh.relay.arms','version':1,'status':'ready','observed_at':time.time(),'arms':{s:{'connected':v} for s,v in connected.items()}},
                    stop_side=lambda side:(calls.append((side,game.motion_policy(side)['blocked'])) or {'contract':'hhh.relay.stop','version':1,'status':'ready','stopped':settled['value']}))
                game._hub_ctx.modules['dobot-mg400-relay']=relay
                game._engine.set_virtual_play(False)
                change={'action':'new','operation_id':uuid.uuid4().hex}
                before=owner.progress_snapshot()['saved_games']['active_id']
                with self.assertRaisesRegex(ValueError,'Waiting for green'):game.saved_game_command('green',change)
                self.assertEqual(owner.progress_snapshot()['saved_games']['active_id'],before)
                self.assertTrue(game.motion_policy('green')['blocked'])
                settled['value']=True;game.saved_game_command('green',change)
                self.assertEqual(calls,[('green',True),('green',True),('purple',True)])
                self.assertFalse(game.motion_policy('green')['blocked'])
            finally:game.hub_stop();app.config['fixture_cleanup']()


if __name__ == '__main__': unittest.main()
