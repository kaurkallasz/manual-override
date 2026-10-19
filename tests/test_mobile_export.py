"""Hosted export includes the complete progression UI; no live hub or network."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]


class MobileExportTests(unittest.TestCase):
    def test_export_bundles_calibration_and_history_before_phone_initialization(self):
        spec=importlib.util.spec_from_file_location('fixture_mobile_export',ROOT/'tools/mobile-ltz/export.py')
        export=importlib.util.module_from_spec(spec);spec.loader.exec_module(export)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);runtime=root/'.mobile-ltz-runtime'
            shutil.copytree(ROOT/'shared/mobile_ltz',root/'shared/mobile_ltz')
            shutil.copytree(ROOT/'shared/ltz_ui',root/'shared/ltz_ui')
            runtime.mkdir()
            (root/'hub-config.json').write_text(json.dumps({'sandboxes':{'green':{'password':'fixture-only'}}}))
            (runtime/'tunnel.json').write_text(json.dumps({'url':'https://fixture.invalid'}))
            (runtime/'bridge-secret').write_text('fixture-only')
            export.ROOT=root;export.RUNTIME=runtime;export.OUT=runtime/'release/TowerDefence'
            def fetch(request,timeout=None):
                path=request.full_url.split('/api/',1)[1]
                return io.BytesIO(json.dumps({'presentation':{'assets':{}}}).encode() if path=='state' else b'// renderer fixture')
            class Login:
                def open(self,*args):return io.BytesIO(b'')
            with patch.object(export,'build_opener',return_value=Login()),patch.object(export,'urlopen',side_effect=fetch),contextlib.redirect_stdout(io.StringIO()):
                export.export()
            bundle=(export.OUT/'mobile.js').read_text()
            self.assertTrue('window.MobileJourney=' in bundle)
            self.assertLess(bundle.index('root.LtzOperationId='),bundle.index('window.MobileJourney='))
            self.assertLess(bundle.index('window.MobileJourney='),bundle.index('window.MobileJourney?.update('))
            self.assertTrue('root.MobileJointRig' in bundle)
            self.assertTrue((runtime/'mobile-ltz-release.zip').exists())


if __name__=='__main__':unittest.main()
