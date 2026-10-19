"""Horde selection, exact preview, offline audit and shared bundle regressions."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from test_photon_framework import load,ROOT

class HordeTests(unittest.TestCase):
    def test_horde_is_opt_in_and_exact_for_each_selected_tier(self):
        game=load('photon-game');bundle=load('photon-level').runtime_bundle()
        from photon_game_runtime.settings import DEFAULTS
        import presets,post_match,horde_presets
        with tempfile.TemporaryDirectory() as folder:
            p=presets.Presets(Path(folder)/'presets.json');p.ensure_map('map',DEFAULTS)
            before=copy.deepcopy(p.snapshot()['selected']);p.ensure_map('map',DEFAULTS);self.assertEqual(before,p.snapshot()['selected'])
            for tier in range(1,5):p.command({'action':'load','revision':p.snapshot()['revision'],'map_id':'map','tier':tier,'name':horde_presets.NAME})
            engine=game.DefenseEngine(bundle['runtime'],bundle['waves']);preview=post_match.preview(p,engine,'map',DEFAULTS)
            for tier,item in enumerate(preview['tiers'],1):
                settings,preset=p.for_run('map',tier,DEFAULTS);engine.set_virtual_play(True);engine.set_virtual_test_loadout(None,tier);engine.start(settings)
                self.assertEqual(item['scheduled_counts'],engine.ranged.counts['scheduled']);self.assertEqual(item['full_clear_credits'],engine.rewards.rule['scheduled_value'])
                self.assertEqual(item['max_active_enemies'],(150,350,650,1000)[tier-1]);self.assertEqual(item['breaker_mode'],'ranged')
            self.assertTrue(3000<=preview['tiers'][3]['total']<=5000)
            self.assertEqual(preview['survival_credits_before_cue'],3*sum(x['full_clear_credits'] for x in preview['tiers'][:3]))
            self.assertGreater(preview['survival_credits_before_cue'],7800)
            restored=presets.Presets(p.path);self.assertEqual(restored.snapshot(),p.snapshot())

    def test_offline_report_deduplicates_and_leaves_unknowns(self):
        spec=importlib.util.spec_from_file_location('ltz_balance_report',ROOT/'tools/ltz_balance_report.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        run={'run_id':'one','reward_enabled':True,'outcome':'won','kills':100,'metadata':{},'participants':[{'player_id':'pilot','side':'green','control_tier':1,'levels':{}}],'result':{'active_seconds':60}}
        rows=[{'data':json.dumps(run)},{'data':json.dumps(run)},{'data':json.dumps({**run,'run_id':'practice','reward_enabled':False})}]
        report=m.report({'tables':{'attempts':rows,'players':[],'ledger':[]}})
        self.assertEqual(report['unique_scored_runs'],1);self.assertEqual(report['duplicate_run_records_ignored'],1);self.assertEqual(report['practice_excluded'],1)
        cohort=report['cohorts'][0];self.assertIsNone(cohort['class_kills']['brute']['median']);self.assertIsNone(cohort['stack_health_fraction']['median']);self.assertEqual(cohort['victory_methods']['unknown'],1)

    def test_economy_endpoint_is_operator_only_and_contract_version_strict(self):
        from flask import Flask
        from types import SimpleNamespace
        game=load('photon-game');app=Flask(__name__);app.register_blueprint(game.bp)
        client=app.test_client()
        for method in (client.get,client.post):
            self.assertEqual(method('/api/economy',environ_overrides={'hhh.roles':{'green'}}).status_code,403)
        import post_match
        owner=SimpleNamespace(economy_snapshot=lambda:{'contract':'photon.progress.economy','version':True,'status':'ready'})
        with self.assertRaises(ValueError):post_match.economy(lambda slug:owner)

    def test_shared_bundle_includes_every_dependency_and_shop_asset(self):
        from shared.mobile_ltz.bundle import assemble
        from shared.ltz_ui import manifest
        files=assemble()
        for token in ('MobileConnectionLog','LTZShop','LTZScoreFeedback','MobileJourney','MobileJointRig'):
            self.assertIn(token,files['mobile.js'])
        self.assertEqual(len(files),6);self.assertEqual(len(manifest()),4)
        self.assertIn('.ltzShop',files['mobile.css'])

if __name__=='__main__':unittest.main()
