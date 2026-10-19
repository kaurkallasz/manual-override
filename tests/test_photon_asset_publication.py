"""Read paths stay responsive during explicit asset publication; no hardware."""
import copy
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from test_photon_framework import Flask, load


class AssetPublicationTests(unittest.TestCase):
    def setUp(self):
        self.level = load('photon-level')

    def test_runtime_manifest_and_asset_requests_never_rescan(self):
        level = self.level
        app = Flask(__name__)
        app.register_blueprint(level.bp)
        before = level.runtime_bundle()
        with patch.object(level, 'asset_snapshot', side_effect=AssertionError('scan on read')):
            for _ in range(100):
                value = level.runtime_status()
                value['presentation']['assets'].clear()
                self.assertEqual(level.runtime_bundle(), before)
                self.assertEqual(level.presentation_assets(), before['presentation'])
            with app.test_client() as client:
                self.assertEqual(client.get('/api/assets').get_json(), before['presentation'])
                with app.test_request_context():
                    response = level.presentation_asset_response('enemy.svg')
                    self.assertEqual(response.status_code, 200)
                    response.close()

    def test_second_atom_tier_one_art_is_published_through_mobile_api(self):
        from mobile_ltz_fixture import create_app
        with tempfile.TemporaryDirectory() as folder:
            app, game = create_app(folder)
            self.addCleanup(app.config['fixture_cleanup'])
            self.addCleanup(game.hub_stop)
            with app.test_client() as client:
                state = client.get('/s/gamemaster/p/mobile-ltz-api/api/state?side=green').get_json()
                for weapon in ('machine-gun', 'flamethrower', 'mortar', 'photon-detonator'):
                    path = f'game-art/z-pixel-v2/normalized/structures/{weapon}-active-l1.png'
                    self.assertIn(path, state['presentation']['assets'])
                    url = state['presentation']['assets'][path]
                    self.assertIn('?v=', url)
                    response = client.get('/s/gamemaster/p/mobile-ltz-api/api/assets/'+url)
                    self.assertEqual(response.status_code, 200, weapon)
                    self.assertEqual(response.mimetype, 'image/png')
                    self.assertTrue(response.data.startswith(b'\x89PNG\r\n\x1a\n'))
                    response.close()
                # Registering result art must not expose the rest of the package.
                self.assertEqual(client.get('/s/gamemaster/p/mobile-ltz-api/api/assets/not-published.png').status_code, 404)

    def test_two_second_scan_does_not_block_real_mobile_or_level_reads(self):
        from mobile_ltz_fixture import create_app
        with tempfile.TemporaryDirectory() as folder:
            app, game = create_app(folder)
            self.addCleanup(app.config['fixture_cleanup'])
            self.addCleanup(game.hub_stop)
            level = game._module('photon-level')
            old = level.presentation_assets()
            entered = threading.Event()
            def slow_scan(*args):
                entered.set()
                time.sleep(2)
                return {**old, 'revision': 'refreshed'}
            with patch.object(level, 'asset_snapshot', side_effect=slow_scan) as scan, ThreadPoolExecutor(4) as pool:
                refresh = pool.submit(level.refresh_presentation_assets)
                self.assertTrue(entered.wait(1))
                reads = []
                for _ in range(12):
                    start = time.perf_counter()
                    self.assertEqual(level.runtime_status()['presentation'], old)
                    with app.test_client() as client:
                        response = client.get('/s/gamemaster/p/mobile-ltz-api/api/state?side=green')
                        self.assertEqual(response.status_code, 200)
                        presentation = response.get_json()['presentation']
                        self.assertEqual(presentation['revision'], old['revision'])
                        for key, value in old['assets'].items():
                            self.assertEqual(presentation['assets'][key], value)
                    reads.append((time.perf_counter()-start)*1000)
                self.assertLess(max(reads), 500, reads)
                self.assertFalse(refresh.done(), 'reads waited for the scan')
                self.assertEqual(refresh.result(3)['revision'], 'refreshed')
                scan.assert_called_once()
            self.assertEqual(level.runtime_status()['presentation']['revision'], 'refreshed')

    def test_concurrent_refreshes_coalesce_and_publish_isolated_output(self):
        level = self.level
        old = level.presentation_assets()
        entered, release, waiting = threading.Event(), threading.Event(), threading.Event()
        real_lock = level._publish_lock
        class ObservedLock:
            def __enter__(self):
                if entered.is_set():
                    waiting.set()
                return real_lock.__enter__()
            def __exit__(self, *args):
                return real_lock.__exit__(*args)
        def scan(*args):
            entered.set()
            if not release.wait(3):
                raise AssertionError('test did not release scan')
            return {**old, 'revision': 'new-art'}
        with patch.object(level, '_publish_lock', ObservedLock()), patch.object(level, 'asset_snapshot', side_effect=scan) as scanner, ThreadPoolExecutor(2) as pool:
            first = pool.submit(level.refresh_presentation_assets)
            try:
                self.assertTrue(entered.wait(1))
                second = pool.submit(level.refresh_presentation_assets)
                self.assertTrue(waiting.wait(1))
                self.assertEqual(level.presentation_assets(), old)
            finally:
                release.set()
            a, b = first.result(2), second.result(2)
            self.assertEqual(a, b)
            scanner.assert_called_once()
            a['assets'].clear()
            self.assertTrue(level.presentation_assets()['assets'])

    def test_file_changes_missing_files_and_recovery_publish_on_refresh(self):
        import level_assets
        level = self.level
        with tempfile.TemporaryDirectory() as folder, patch.object(level, 'ASSET_ROOT', folder), patch.object(level, '_map_asset_paths', {}), patch.object(level_assets, 'runtime_asset_paths', return_value={'image': 'image.svg'}):
            image = Path(folder)/'image.svg'
            image.write_text('first')
            first = level.refresh_presentation_assets()
            image.write_text('replacement')
            self.assertEqual(level.presentation_assets(), first)
            second = level.refresh_presentation_assets()
            self.assertNotEqual(first['revision'], second['revision'])
            image.unlink()
            missing = level.refresh_presentation_assets()
            self.assertEqual(missing['status'], 'unavailable')
            self.assertIn('image', missing['error'])
            self.assertNotIn('image', missing['assets'])
            self.assertEqual(level.runtime_status()['presentation'], missing)
            image.write_text('first')
            self.assertEqual(level.refresh_presentation_assets(), first)

    def test_layout_and_manifest_publish_together_without_holding_reader_lock(self):
        level = self.level
        before = level.runtime_bundle()
        raw, runtime, waves = copy.deepcopy((level._raw_map, level._runtime, level._waves))
        runtime['layout_revision'] += 1
        entered, release = threading.Event(), threading.Event()
        def scan(*args):
            entered.set()
            if not release.wait(3):
                raise AssertionError('test did not release scan')
            return {**before['presentation'], 'revision': 'new-layout-art'}
        with patch.object(level, '_load_source', return_value=(raw, runtime, waves)), patch.object(level, '_scene_asset_paths', return_value={}), patch.object(level, 'asset_snapshot', side_effect=scan), ThreadPoolExecutor(2) as pool:
            reload = pool.submit(level._reload_source)
            try:
                self.assertTrue(entered.wait(1))
                self.assertEqual(pool.submit(level.runtime_bundle).result(.5), before)
            finally:
                release.set()
            self.assertTrue(reload.result(2))
        after = level.runtime_bundle()
        self.assertEqual(after['revision'], runtime['layout_revision'])
        self.assertEqual(after['presentation']['revision'], 'new-layout-art')
        with patch.object(level, '_load_source', side_effect=ValueError('invalid source')):
            self.assertFalse(level._reload_source())
        status = level.runtime_status()
        self.assertEqual(status['status'], 'unavailable')
        self.assertEqual(status['presentation']['error'], 'invalid source')

    def test_editor_validation_does_not_hold_reader_lock(self):
        level = self.level
        entered, release = threading.Event(), threading.Event()
        scene = level._scene_asset_paths
        def slow_scene(*args):
            entered.set()
            if not release.wait(3):
                raise AssertionError('test did not release editor')
            return scene(*args)
        with patch.object(level, '_scene_asset_paths', side_effect=slow_scene), ThreadPoolExecutor(2) as pool:
            editor = pool.submit(level.editor_snapshot)
            try:
                self.assertTrue(entered.wait(1))
                self.assertEqual(pool.submit(level.runtime_status).result(.5)['status'], 'ready')
            finally:
                release.set()
            self.assertEqual(editor.result(2)['status'], 'ready')

    def test_refresh_api_requires_operator_and_reports_validation_failure(self):
        level = self.level
        app = Flask(__name__)
        app.register_blueprint(level.bp)
        with app.test_client() as client, patch.object(level, 'asset_snapshot', side_effect=OSError('disk unavailable')) as scan:
            self.assertEqual(client.post('/api/assets/refresh').status_code, 403)
            scan.assert_not_called()
            response = client.post('/api/assets/refresh', environ_overrides={'hhh.roles': {'gamemaster'}})
            self.assertEqual(response.status_code, 503)
            self.assertIn('disk unavailable', response.get_json()['error'])
            self.assertEqual(client.get('/api/assets').get_json()['status'], 'unavailable')
            scan.assert_called_once()


if __name__ == '__main__':
    unittest.main()
