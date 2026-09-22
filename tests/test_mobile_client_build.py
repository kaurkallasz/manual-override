import importlib.util
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch
from flask import Flask

ROOT = Path(__file__).resolve().parents[1]


class ClientBuildTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('mobile_client_test', ROOT/'sandboxes/green/prototypes/mobile-ltz/prototype.py')
        self.ui = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.ui)
        self.app = Flask(__name__)
        self.app.register_blueprint(self.ui.bp)
        self.client = self.app.test_client()
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        for name in self.ui.CLIENT_FILES:
            (self.root/name).write_text((self.ui.HERE/name).read_text())
        (self.root/'joint-rig.js').write_text((self.ui.HERE/'joint-rig.js').read_text())
        (self.root/'turret-overlay.js').write_text((self.ui.HERE/'turret-overlay.js').read_text())
        self.ui.HERE = self.root
        self.ui.hub_init(None)
        self.addCleanup(self.ui.hub_stop)

    def test_every_launch_changes_urls_and_serves_new_code(self):
        first = self.client.get('/api/client/manifest').json
        self.assertEqual((first['contract'], first['version']), ('mobile.client', 1))
        html = self.client.get('/api/client/latest/index.html')
        self.assertIn('no-store', html.headers['Cache-Control'])
        self.assertEqual(html.headers['X-Mobile-Build'], first['build'])
        self.assertIn(f'data-mobile-build="{first["build"]}"', html.text)
        urls = re.findall(r'(?:src|href)="(api.php[^\"]+)"', html.text)
        self.assertEqual(len(urls), len(self.ui.CLIENT_FILES) - 1)
        self.assertTrue(all(first['build'] in url for url in urls))
        old = self.client.get(f'/api/client/{first["build"]}/mobile.js').data
        (self.root/'mobile.js').write_text('// updated in next launch\n')
        self.assertEqual(self.client.get(f'/api/client/{first["build"]}/mobile.js').data, old)
        self.ui.hub_stop(); self.ui.hub_init(None)
        second = self.client.get('/api/client/manifest').json
        self.assertNotEqual(first['build'], second['build'])
        self.assertEqual(self.client.get(f'/api/client/{first["build"]}/mobile.js').status_code, 409)
        self.assertTrue(self.client.get(f'/api/client/{second["build"]}/mobile.js').text.endswith('// updated in next launch\n'))
        self.assertNotIn(first['build'], self.client.get('/api/client/latest/index.html').text)
        self.assertEqual(self.client.get('/mobile.js?v='+first['build']).status_code, 409)
        self.assertEqual(self.client.get('/mobile.js?v='+second['build']).status_code, 200)

    def test_local_refresh_is_versioned_and_files_are_restricted(self):
        build = self.ui.client_contract()['build']
        html = self.client.get('/').text
        self.assertIn(f'mobile.js?v={build}', html)
        self.assertIn('id="score">0</b></span><span class="fps"', html)
        for file in ['prototype.py', 'bridge-config.php', 'hub-config.json', '../mobile.js']:
            self.assertEqual(self.client.get(f'/api/client/{build}/{file}').status_code, 404)
        self.ui.hub_stop()
        self.assertEqual(self.client.get('/api/client/latest/index.html').status_code, 503)

    def test_rig_is_bundled_for_already_deployed_hosting_allowlists(self):
        build = self.ui.client_contract()['build']
        html = self.client.get(f'/api/client/{build}/index.html').text
        scripts = re.findall(r'<script src="api.php\?path=client/[^/]+/([^"]+)"', html)
        self.assertEqual(scripts, ['viewport.js', 'live-game.js', 'network.js', 'mobile.js'])
        script = self.client.get(f'/api/client/{build}/mobile.js').text
        self.assertIn('root.MobileJointRig=api', script)
        self.assertLess(script.index('root.MobileJointRig=api'), script.index('MobileJointRig.mount('))
        self.assertEqual(self.client.get(f'/api/client/{build}/joint-rig.js').status_code, 404)


if __name__ == '__main__':
    unittest.main()
