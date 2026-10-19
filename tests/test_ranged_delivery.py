"""Capability, mobile projection and hosted-export checks, entirely offline."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from test_photon_framework import load, FakeContext, ROOT

class RangedDeliveryTests(unittest.TestCase):
    def test_matching_renderer_required_for_ranged_start(self):
        game=load('photon-game')
        game._check_enemy_renderer({'breaker_attack_mode':'melee'})
        for contract in (None,{}, {'contract':'photon.renderer','version':1,'enemy_combat_version':True}):
            game._hub_ctx=FakeContext({'laser-tag-y':SimpleNamespace(renderer_contract=lambda:contract)})
            with self.assertRaisesRegex(game.GameError,'matching'):game._check_enemy_renderer({'breaker_attack_mode':'ranged'})
        game._hub_ctx=FakeContext({'laser-tag-y':load('laser-tag-y')})
        game._check_enemy_renderer({'breaker_attack_mode':'ranged'})

    def test_mobile_projection_keeps_archer_pose_flight_and_version(self):
        api=load('mobile-ltz-api')
        combat={'variant':'archer','state':'aim','started_at':0,'release_at':.5}
        state={'status':'ready','virtual_play':True,'enemies':[{'id':1,'enemy_type':'breaker','combat':combat}],
               'enemy_combat':{'contract':'photon.enemy-combat','version':1,'breaker_mode':'ranged'},
               'enemy_arrows':[{'id':5}],'enemy_arrow_impacts':[{'id':4}]}
        with patch.object(api,'_game',return_value=(None,state)),patch.object(api,'_observe'):
            result=api.mobile_snapshot('green')
        self.assertEqual(result['enemies'][0]['combat'],combat)
        self.assertEqual(result['enemy_arrows'],[{'id':5}])
        self.assertEqual(result['enemy_arrow_impacts'],[{'id':4}])
        self.assertEqual(result['enemy_combat']['version'],1)

    def test_export_contains_owned_bundle_and_identical_versioned_atlas(self):
        level,y=load('photon-level'),load('laser-tag-y')
        presentation=level.presentation_assets()
        url=presentation['assets']['enemy/breaker/archer-atlas']
        atlas=(ROOT/'sandboxes/gamemaster/prototypes/photon-level/assets'/url.split('?')[0]).read_bytes()
        bundle=y.renderer_response().get_data()
        self.assertIn(b'function pose(enemy, time)',bundle)
        self.assertIn(b'BreakerRenderer',bundle)
        self.assertEqual(y.renderer_response().headers['Cache-Control'],'no-cache')
        spec=importlib.util.spec_from_file_location('ranged_mobile_export',ROOT/'tools/mobile-ltz/export.py')
        export=importlib.util.module_from_spec(spec);spec.loader.exec_module(export)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);runtime=root/'.mobile-ltz-runtime';runtime.mkdir()
            shutil.copytree(ROOT/'shared/mobile_ltz',root/'shared/mobile_ltz')
            shutil.copytree(ROOT/'shared/ltz_ui',root/'shared/ltz_ui')
            (root/'hub-config.json').write_text(json.dumps({'sandboxes':{'green':{'password':'fixture'}}}))
            (runtime/'tunnel.json').write_text(json.dumps({'url':'https://fixture.invalid'}))
            (runtime/'bridge-secret').write_text('fixture')
            export.ROOT=root;export.RUNTIME=runtime;export.OUT=runtime/'release/TowerDefence'
            def fetch(request,timeout=None):
                path=request.full_url.split('/api/',1)[1]
                if path=='state':data=json.dumps({'presentation':{'assets':{'enemy/breaker/archer-atlas':url}}}).encode()
                elif path=='renderer.js':data=bundle
                else:
                    self.assertEqual(path,'assets/'+url);data=atlas
                return io.BytesIO(data)
            login=SimpleNamespace(open=lambda *args:io.BytesIO(b''))
            # The exporter imports its temporary client assembly. Do not leave
            # that deleted fixture path/module cached for subsequent tests.
            with patch.object(sys,'path',list(sys.path)),patch.dict(sys.modules),patch.object(export,'build_opener',return_value=login),patch.object(export,'urlopen',side_effect=fetch),contextlib.redirect_stdout(io.StringIO()):export.export()
            mapping=json.loads((export.OUT/'assets.json').read_text())
            self.assertEqual((export.OUT/mapping[url]).read_bytes(),atlas)
            self.assertEqual((export.OUT/'renderer.js').read_bytes(),bundle)

if __name__=='__main__':unittest.main()
