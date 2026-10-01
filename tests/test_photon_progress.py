"""Transactional progress tests use temporary databases; never venue players."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('ltz_test_store', ROOT / 'sandboxes/gamemaster/prototypes/photon-progress/store.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ProgressTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = module.ProgressStore(Path(self.temp.name) / 'progress.sqlite3')
        self.store.initialize()
        self.green = self.store.create_player('Same name', uuid.uuid4().hex)['player_id']
        self.purple = self.store.create_player('Same name', uuid.uuid4().hex)['player_id']
        self.store.select_player('green', self.green)
        self.store.select_player('purple', self.purple)

    def start(self, scored=True):
        run_id = uuid.uuid4().hex
        return self.store.begin({'run_id': run_id, 'reward_enabled': scored, 'metadata': {'level_id': 'test', 'settings_hash': 'unchanged'}})

    def finish(self, attempt, kills=87, outcome='won', sequence=1):
        result = {'run_id': attempt['run_id'], 'kills': kills, 'sequence': sequence, 'outcome': outcome,
                  'active_seconds': 15, 'finished_at': 100 + len(self.store.history(self.green, {})['rows']), 'released_orcs': kills}
        self.store.record(result, final=True)
        return result

    def player(self):
        return self.store.snapshot('green')['player']

    def test_three_nonconsecutive_wins_unlock_without_spending(self):
        for outcome in ('won', 'overrun', 'won'):
            self.finish(self.start(), outcome=outcome)
        self.assertEqual(self.player()['unlocked_control'], 1)
        result = self.finish(self.start())
        self.store.record(result, final=True)
        p = self.player()
        self.assertEqual((p['unlocked_control'], p['wins_by_tier']), (2, [3, 0, 0, 0]))
        self.assertEqual(p['credits'], 348)
        self.assertEqual(self.store.snapshot('purple')['player']['credits'], 348)
        self.assertNotEqual(self.green, self.purple)

    def test_checkpoints_and_retry_award_only_delta(self):
        a = self.start()
        checkpoint = {'run_id': a['run_id'], 'kills': 50, 'sequence': 1}
        self.store.record(checkpoint)
        self.store.record(checkpoint)
        self.finish(a, sequence=2)
        self.assertEqual(self.player()['credits'], 87)
        self.assertEqual(self.player()['lifetime_score'], 87)

    def test_practice_aborts_and_recovery(self):
        self.finish(self.start(False), kills=1000)
        self.finish(self.start(), kills=3, outcome='aborted')
        a = self.start()
        self.store.record({'run_id': a['run_id'], 'kills': 12, 'sequence': 1})
        self.store.recover()
        self.store.recover()
        p = self.player()
        self.assertEqual((p['credits'], p['wins'], p['attempts']), (15, 0, 2))
        self.assertEqual(self.store.history(self.green, {'dataset': 'practice'})['total'], 1)

    def test_newer_durable_final_supersedes_recovery_once(self):
        a=self.start()
        self.store.record({'run_id':a['run_id'],'kills':12,'sequence':62})
        self.store.recover()
        recovered=self.store.attempt(a['run_id'])
        final={'run_id':a['run_id'],'kills':30,'sequence':75,'outcome':'won',
               'active_seconds':1500,'finished_at':recovered['finished_at']+1,'released_orcs':60}
        result=self.store.record(final,final=True)
        self.store.record(final,final=True)
        self.assertEqual(result['interrupted_result']['outcome'],'interrupted')
        self.assertEqual((self.player()['credits'],self.player()['wins'],self.player()['attempts']),(30,1,1))
        self.assertEqual(self.store.history(self.green,{'combined':True})['total'],1)
        with self.assertRaisesRegex(ValueError,'conflicting'):
            self.store.record({**final,'sequence':76,'kills':31},final=True)

    def test_legacy_recovery_race_does_not_block_practice_history(self):
        a=self.start(False)
        legacy={'run_id':a['run_id'],'kills':0,'sequence':63,'outcome':'interrupted',
                'active_seconds':0,'finished_at':1789502196.214591,'released_orcs':0}
        self.store.record(legacy,final=True)
        final={**legacy,'outcome':'aborted','sequence':75,'active_seconds':10.15270279161632,
               'finished_at':1789502581.55021,'released_orcs':32}
        self.store.record(final,final=True)
        self.store.record(final,final=True)
        self.assertEqual(self.store.attempt(a['run_id'])['result'],final)
        self.assertEqual((self.player()['credits'],self.player()['wins'],self.player()['attempts']),(0,0,0))
        self.assertEqual(self.store.history(self.green,{'dataset':'practice'})['total'],1)

    def test_purchase_concurrency_and_idempotency(self):
        self.finish(self.start(), kills=300)
        p = self.player()
        def buy(track):
            try:
                return self.store.mutate_player('green', {'action': 'purchase', 'track': track, 'level': 2,
                    'revision': p['revision'], 'operation_id': uuid.uuid4().hex})
            except ValueError:
                return None
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(buy, ['damage-machine-gun', 'damage-mortar']))
        self.assertEqual(sum(r is not None for r in results), 1)
        self.assertEqual(self.player()['credits'], 50)
        self.assertEqual(self.player()['lifetime_score'], 300)

    def test_profile_and_control_are_locked_during_attempt(self):
        a = self.start()
        with self.assertRaises(ValueError):
            self.store.select_player('green', None)
        with self.assertRaises(ValueError):
            self.store.begin({'run_id': uuid.uuid4().hex, 'reward_enabled': True, 'metadata': {}})
        self.finish(a)
        p = self.player()
        with self.assertRaises(ValueError):
            self.store.mutate_player('green', {'action': 'control', 'level': 4, 'revision': p['revision'], 'operation_id': uuid.uuid4().hex})

    def test_backup_roundtrip_preview_conflict_and_restart(self):
        self.finish(self.start())
        backup = self.store.export()
        other = module.ProgressStore(Path(self.temp.name) / 'other.sqlite3')
        other.initialize()
        self.assertGreater(other.import_backup(backup, preview=True)['new_records'], 0)
        self.assertEqual({p['id'] for p in other.snapshot()['players']}, set(module.TEST_PLAYERS))
        other.import_backup(backup)
        self.assertEqual(other.import_backup(backup)['new_records'], 0)
        other.select_player('green', self.green)
        other = module.ProgressStore(other.path)
        other.initialize()
        self.assertEqual(other.snapshot('green')['player']['credits'], 87)
        broken = json.loads(json.dumps(backup))
        p = json.loads(broken['tables']['players'][0]['data'])
        p['credits'] += 1
        broken['tables']['players'][0]['data'] = json.dumps(p)
        with self.assertRaises(ValueError):
            other.import_backup(broken)
        self.assertEqual(other.snapshot('green')['player']['credits'], 87)

    def test_history_comparable_six_nonoverlapping_results(self):
        # Normal advancement stays immediate. Continued Cue play can supply six
        # successful comparable runs without replaying an earlier tier.
        for tier in range(1,4):
            for _ in range(3): self.finish(self.start(),kills=5)
            if tier==2:
                for side in ('green','purple'):
                    p=self.store.snapshot(side)['player']
                    self.store.complete_lesson({'player_id':p['id'],'operation_id':uuid.uuid4().hex,
                        'milestone_id':p['calibration_milestone'],'lesson_version':1,'calibration_revision':2,'evidence_id':'fixture'})
        for kills in (10,20,30,20,30): self.finish(self.start(),kills=kills)
        self.assertIsNone(self.store.history(self.green,{'tier':4})['summary']['score_change'])
        self.finish(self.start(),kills=40)
        summary=self.store.history(self.green,{'tier':4,'limit':'1'})['summary']
        self.assertEqual(summary['attempts'],6)
        self.assertEqual(summary['score_change']['percent'],50)
        self.assertFalse(self.store.history(self.green,{})['summary']['comparable'])

    def test_twelve_wins_master_all_four_tiers(self):
        for tier in range(1, 5):
            if tier > 1:
                p = self.player()
                self.store.mutate_player('green', {'action':'control', 'level':tier, 'revision':p['revision'], 'operation_id':uuid.uuid4().hex})
            for _ in range(3):
                self.finish(self.start(), kills=5)
            self.assertEqual(self.player()['unlocked_control'], min(4, tier + 1))
            if tier==2:
                for side in ('green','purple'):
                    p=self.store.snapshot(side)['player']
                    self.store.complete_lesson({'player_id':p['id'],'operation_id':uuid.uuid4().hex,
                        'milestone_id':p['calibration_milestone'],'lesson_version':1,'calibration_revision':2,'evidence_id':'fixture-placement'})
        self.assertEqual(self.player()['wins_by_tier'], [3,3,3,3])
        self.assertEqual(self.player()['credits'], 60)

    def test_backup_rejects_inconsistent_balance_and_migrates_tesla_alias(self):
        self.finish(self.start(), kills=300)
        backup = self.store.export()
        other = module.ProgressStore(Path(self.temp.name) / 'import.sqlite3'); other.initialize()
        corrupt = json.loads(json.dumps(backup))
        player = json.loads(corrupt['tables']['players'][0]['data']); player['credits'] -= 1
        corrupt['tables']['players'][0]['data'] = json.dumps(player)
        with self.assertRaisesRegex(ValueError, 'ledger'):
            other.import_backup(corrupt)
        legacy = json.loads(json.dumps(backup).replace('damage-tesla-coil', 'damage-photon'))
        other.import_backup(legacy)
        other.select_player('green', self.green)
        self.assertIn('damage-tesla-coil', other.snapshot('green')['player']['levels'])
        self.assertNotIn('damage-photon', other.snapshot('green')['player']['levels'])

    def test_builtin_test_profiles_are_selectable_and_stable_after_restart(self):
        for side in ('green', 'purple'):
            self.store.select_player(side, 'ltz-test-'+side)
            self.assertTrue(self.store.snapshot(side)['player']['is_test'])
        before = self.store.export()['tables']['players']
        self.store.initialize()
        self.assertEqual(before, self.store.export()['tables']['players'])
        self.assertEqual(len(self.store.snapshot()['players']), 4)

    def test_mixed_test_roster_never_rewards_either_player_or_scored_history(self):
        self.finish(self.start(), kills=10)
        real_before = self.store.snapshot('purple')['player']
        self.store.select_player('green', 'ltz-test-green')
        test_before = self.player()
        for _ in range(3):
            attempt = self.start(scored=True)
            self.assertFalse(attempt['reward_enabled'])
            self.assertEqual(attempt['test_player_ids'], ['ltz-test-green'])
            self.assertEqual(attempt['practice_reason'], 'test_player')
            self.assertEqual(self.store.begin({'run_id': attempt['run_id'], 'reward_enabled': True,
                'metadata': attempt['metadata']}), attempt)
            self.store.record({'run_id': attempt['run_id'], 'kills': 100, 'sequence': 1})
            result = self.finish(attempt, kills=300, sequence=2)
            self.store.record(result, final=True)
        self.assertEqual(self.player(), test_before)
        self.assertEqual(self.store.snapshot('purple')['player'], real_before)
        scored = self.store.history(None, {'combined': True})
        practice = self.store.history(None, {'combined': True, 'dataset': 'practice'})
        self.assertEqual((scored['total'], scored['summary']['best_score']), (1, 10))
        self.assertEqual(practice['total'], 3)
        self.assertTrue(all(not row['completion_awarded'] for row in practice['rows']))
        self.assertEqual(self.store.history('ltz-test-green', {})['total'], 0)
        with self.assertRaisesRegex(ValueError, 'test profiles'):
            self.store.mutate_player('green', {'action': 'control', 'level': 1,
                'revision': test_before['revision'], 'operation_id': uuid.uuid4().hex})

    def test_two_test_profiles_and_interrupted_test_results_are_practice(self):
        for side in ('green', 'purple'):
            self.store.select_player(side, 'ltz-test-'+side)
        attempt = self.start()
        self.assertEqual(set(attempt['test_player_ids']), set(module.TEST_PLAYERS))
        self.store.record({'run_id': attempt['run_id'], 'kills': 99, 'sequence': 1})
        self.store.recover()
        self.assertEqual((self.player()['attempts'], self.player()['credits']), (0, 0))
        self.assertEqual(self.store.history(None, {'combined': True})['total'], 0)
        self.assertEqual(self.store.history(None, {'combined': True, 'dataset': 'practice'})['total'], 1)

    def test_test_names_do_not_classify_real_profiles_and_legacy_profiles_default_to_real(self):
        p = self.store.create_player('Test player · Green', uuid.uuid4().hex)['player_id']
        self.store.select_player('green', p)
        self.assertFalse(self.player()['is_test'])
        with self.store.transaction(write=True) as db:
            saved = json.loads(db.execute('SELECT data FROM players WHERE id=?', (p,)).fetchone()[0])
            saved.pop('is_test')
            db.execute('UPDATE players SET data=? WHERE id=?', (json.dumps(saved), p))
        self.store.initialize()
        self.assertFalse(self.player()['is_test'])
        self.finish(self.start())
        self.assertEqual(self.player()['credits'], 87)

    def test_atomic_create_and_select_retries_once_and_rolls_back_if_locked(self):
        operation_id = uuid.uuid4().hex
        result = self.store.create_player('New green', operation_id, side='green')
        self.assertEqual(self.player()['id'], result['player_id'])
        self.assertEqual(self.store.create_player('New green', operation_id, side='green'), result)
        attempt = self.start()
        before = self.store.snapshot()['players']
        with self.assertRaisesRegex(ValueError, 'active attempt'):
            self.store.create_player('Blocked', uuid.uuid4().hex, side='green')
        self.assertEqual(self.store.snapshot()['players'], before)
        self.finish(attempt)

    def test_test_classification_survives_backup_and_cannot_be_relabelled_scored(self):
        self.store.select_player('green', 'ltz-test-green')
        self.finish(self.start())
        backup = self.store.export()
        other = module.ProgressStore(Path(self.temp.name)/'test-backup.sqlite3')
        other.initialize(); other.import_backup(backup)
        self.assertEqual(other.history(None, {'combined': True})['total'], 0)
        self.assertEqual(other.history(None, {'combined': True, 'dataset': 'practice'})['total'], 1)
        corrupt = json.loads(json.dumps(backup))
        row = corrupt['tables']['attempts'][0]
        attempt = json.loads(row['data']); attempt['reward_enabled'] = True; row['data'] = json.dumps(attempt)
        with self.assertRaisesRegex(ValueError, 'cannot be scored'):
            other.import_backup(corrupt)
        corrupt = json.loads(json.dumps(backup))
        row = next(row for row in corrupt['tables']['players'] if row['id'] == 'ltz-test-green')
        p = json.loads(row['data']); p['is_test'] = False; row['data'] = json.dumps(p)
        with self.assertRaisesRegex(ValueError, 'classification'):
            other.import_backup(corrupt)



if __name__ == '__main__':
    unittest.main()
