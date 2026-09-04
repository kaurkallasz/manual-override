"""Presentation-only data-flow diagram, exercising the real JS without sensors."""

import shutil
import subprocess
import unittest
from pathlib import Path

from flask import Flask
from test_photon_framework import PROTOTYPES, load


class YDataFlowTests(unittest.TestCase):
    def test_diagnostic_window_and_resources_belong_to_y_only(self):
        module = load("laser-tag-y")
        app = Flask("y-data-flow")
        app.register_blueprint(module.bp, url_prefix="/p/laser-tag-y")
        with app.test_client() as client:
            for endpoint, needle in (("game", b'dataFlowOpen'), ("data-flow.js", b'YDataFlow'), ("data-flow.css", b'prefers-reduced-motion')):
                with client.get('/p/laser-tag-y/' + endpoint) as response:
                    self.assertEqual(response.status_code, 200)
                    self.assertIn(needle, response.data)
            with client.get('/p/laser-tag-y/screen') as response:
                self.assertNotIn(b'dataFlowOpen', response.data)

    def test_window_uses_existing_observations_not_new_network_reads(self):
        source = (PROTOTYPES / 'laser-tag-y/data-flow.js').read_text()
        for forbidden in ('fetch(', 'XMLHttpRequest', 'new EventSource', 'get_prototype', 'apply_command', 'innerHTML', 'photon-level', 'photon-board'):
            self.assertNotIn(forbidden, source)
        page = (PROTOTYPES / 'laser-tag-y/index.html').read_text()
        self.assertIn("dataFlow.snapshot(state,source)", page)
        self.assertIn("onAssetStatus:value=>dataFlow.assets(value)", page)
        self.assertEqual(page.count('new EventSource'), 1)
        self.assertIn("dataFlow.destroy()", page)

    @unittest.skipUnless(shutil.which('node'), 'Node.js required for diagram smoke test')
    def test_status_labels_animation_and_lifecycle_in_real_js(self):
        script = Path(__file__).with_name('y_data_flow.cjs')
        result = subprocess.run(['node', str(script)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
