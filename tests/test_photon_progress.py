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
        self.assertEqual(other.snapshot()['players'], [])
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
        for kills in (10, 20, 30, 20, 30):
            self.finish(self.start(), kills=kills)
        self.assertIsNone(self.store.history(self.green, {})['summary']['score_change'])

        self.finish(self.start(), kills=40)
        summary = self.store.history(self.green, {'limit': '1'})['summary']
        self.assertEqual(summary['attempts'], 6)
        self.assertEqual(summary['score_change']['percent'], 50)
        # Switching tier changes the cohort instead of fabricating skill gain.
        p = self.player()
        self.store.mutate_player('green', {'action': 'control', 'level': 2, 'revision': p['revision'], 'operation_id': uuid.uuid4().hex})
        self.finish(self.start(), kills=999)
        self.assertFalse(self.store.history(self.green, {})['summary']['comparable'])
        self.assertIsNone(self.store.history(self.green, {})['summary']['score_change'])

    def test_twelve_wins_master_all_four_tiers(self):
        for tier in range(1, 5):
            if tier > 1:
                p = self.player()
                self.store.mutate_player('green', {'action':'control', 'level':tier, 'revision':p['revision'], 'operation_id':uuid.uuid4().hex})
            for _ in range(3):
                self.finish(self.start(), kills=5)
            self.assertEqual(self.player()['unlocked_control'], min(4, tier + 1))
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



if __name__ == '__main__':
    unittest.main()
