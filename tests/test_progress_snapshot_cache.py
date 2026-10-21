"""Committed presentation reads stay off the persistence path; temporary DBs only."""
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from test_photon_framework import ROOT, load


class SnapshotCacheTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.module = load('photon-progress')
        self.path = Path(folder.name) / 'progress.sqlite3'
        self.store = self.module.ProgressStore(self.path)
        self.store.initialize()
        self.event = self.store.event_command({'action': 'create', 'name': 'Test', 'operation_id': 'event:1'})['event_id']
        self.ids = {side: self.store.create_player(side, side=side, event_id=self.event,
                    operation_id='player:' + side)['player_id'] for side in ('green', 'purple')}

    def test_repeated_reads_do_no_database_work_and_do_not_share_mutable_values(self):
        original = {side: self.store.snapshot(side) for side in (None, 'green', 'purple')}
        with patch.object(self.store, 'transaction', side_effect=AssertionError('Cache hit opened database')):
            for side in (None, 'green', 'purple'):
                value = self.store.snapshot(side)
                self.assertEqual(value, original[side])
                value['roster']['green']['name'] = 'Changed by caller'
                value['saved_games'].clear()
                self.assertEqual(self.store.snapshot(side), original[side])

    def test_commit_invalidates_all_sides_even_without_a_revision_bump(self):
        for side in (None, 'green', 'purple'):
            self.store.snapshot(side)
        with self.store.transaction(write=True) as db:
            player = self.store._player(db, self.ids['green'])
            player['name'] = 'Updated'
            db.execute('UPDATE players SET data=? WHERE id=?', (json.dumps(player), player['id']))
        for side in (None, 'green', 'purple'):
            self.assertEqual(self.store.snapshot(side)['roster']['green']['name'], 'Updated')

    def test_cache_serves_committed_value_during_a_pending_write_then_changes_at_commit(self):
        original = self.store.snapshot('green')
        entered, release, read_done = threading.Event(), threading.Event(), threading.Event()
        values, errors = [], []
        def writer():
            try:
                with self.store.transaction(write=True) as db:
                    player = self.store._player(db, self.ids['green'])
                    player['name'] = 'Committed later'
                    db.execute('UPDATE players SET data=? WHERE id=?', (json.dumps(player), player['id']))
                    entered.set()
                    if not release.wait(3):
                        raise AssertionError('Writer not released')
            except Exception as exc:
                errors.append(exc)
        def reader():
            try:
                values.append(self.store.snapshot('green'))
            except Exception as exc:
                errors.append(exc)
            finally:
                read_done.set()
        thread = threading.Thread(target=writer)
        thread.start()
        self.assertTrue(entered.wait(2))
        read_thread = threading.Thread(target=reader)
        read_thread.start()
        try:
            self.assertTrue(read_done.wait(.5), 'Presentation waited behind persistence')
            self.assertEqual(values, [original])
        finally:
            release.set(); thread.join(2); read_thread.join(2)
        self.assertEqual(errors, [])
        self.assertEqual(self.store.snapshot('green')['player']['name'], 'Committed later')

    def test_external_commit_and_missing_database_cannot_return_old_cache(self):
        self.store.snapshot('green')
        other = self.module.ProgressStore(self.path)
        other.create_player('Extra', event_id=self.event, operation_id='player:extra')
        self.assertEqual(len(self.store.snapshot('green')['players']), 3)
        self.path.unlink()
        with self.assertRaises(FileNotFoundError):
            self.store.snapshot('green')

    def test_rollback_does_not_publish_uncommitted_data(self):
        original = self.store.snapshot('green')
        with self.assertRaises(ValueError):
            with self.store.transaction(write=True) as db:
                db.execute('DELETE FROM sessions')
                raise ValueError('Abort')
        self.assertEqual(self.store.snapshot('green'), original)

    def test_progress_link_snapshot_does_not_wait_for_writer_and_is_detached(self):
        spec = importlib.util.spec_from_file_location('cache_test_progress_link', ROOT / 'sandboxes/gamemaster/prototypes/photon-game/progress_link.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        link = module.ProgressLink(lambda _: None, lambda: None, lambda: None, self.path.with_suffix('.json'))
        supplied = {'run_id': 'test', 'values': [1]}
        link._set(status='ready', result=supplied)
        supplied['values'].append(2)
        done = threading.Event(); values = []
        def read():
            values.append(link.snapshot()); done.set()
        with link.lock:
            thread = threading.Thread(target=read); thread.start()
            self.assertTrue(done.wait(.5), 'Read queued behind outbox lock')
        thread.join(2)
        self.assertEqual(values[0]['result']['values'], [1])
        values[0]['result']['values'].append(3)
        self.assertEqual(link.snapshot()['result']['values'], [1])


if __name__ == '__main__':
    unittest.main()
