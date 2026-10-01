"""Authenticated profile creation and test classification; no venue data."""
from pathlib import Path
import tempfile
import unittest
from test_photon_framework import load, Flask


class TestPlayerApiTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.progress=load('photon-progress');self.progress.DATA_DIR=Path(self.folder.name)
        self.progress.hub_init(None);self.addCleanup(self.progress.hub_stop)
        app=Flask('test-player-api');app.register_blueprint(self.progress.bp)
        self.client=app.test_client()

    def test_both_sides_create_and_select_atomically_with_non_uuid_receipts(self):
        for side in ('green','purple'):
            value={'action':'create','select':True,'name':side+' mobile player',
                   'operation_id':'ltz:'+side+':http-receipt','is_test':True}
            url='/api/player?side='+side
            response=self.client.post(url,json=value,environ_overrides={'hhh.roles':{side}})
            self.assertEqual(response.status_code,200,response.json)
            self.assertEqual(response.json['player']['id'],response.json['result']['player_id'])
            self.assertFalse(response.json['player']['is_test'])
            retry=self.client.post(url,json=value,environ_overrides={'hhh.roles':{side}})
            self.assertEqual(retry.json['result'],response.json['result'])
            tests={p['id'] for p in response.json['players'] if p['is_test']}
            self.assertEqual(tests,{'ltz-test-green','ltz-test-purple'})
            selected=self.client.post(url,json={'action':'select','player_id':'ltz-test-'+side},environ_overrides={'hhh.roles':{side}})
            self.assertTrue(selected.json['player']['is_test'])
            self.assertTrue(selected.json['roster'][side]['is_test'])

    def test_test_profiles_do_not_bypass_team_authorization(self):
        response=self.client.post('/api/player?side=purple',json={'action':'select','player_id':'ltz-test-purple'},environ_overrides={'hhh.roles':{'green'}})
        self.assertEqual(response.status_code,403)


if __name__=='__main__':unittest.main()
