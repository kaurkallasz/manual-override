"""Durable mobile evidence and relay expiry diagnostics; no hardware or network."""
from collections import deque
import json
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import uuid
from test_photon_framework import load, Flask


class ConnectionLogTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(); self.addCleanup(folder.cleanup)
        self.facade = load('mobile-ltz-api'); self.log = self.facade.connection_log
        self.path = Path(folder.name)/'events.jsonl'
        replacement = patch.object(self.log, 'LOG_PATH', self.path)
        replacement.start(); self.addCleanup(replacement.stop)
        self.log._seen.clear()
        for rate in self.log._rates.values(): rate.clear()
        app = Flask('connection-log-test'); app.register_blueprint(self.facade.bp)
        self.client = app.test_client()

    def event(self, **extra):
        return dict(version=1,id=uuid.uuid4().hex,source='bridge',event='feedback_stale',
                    client_at=time.time(),reason='Fresh feedback unavailable',**extra)

    def post(self, data, side='green', role='green', **kwargs):
        return self.client.post('/api/diagnostics?side='+side, json=data,
                                environ_overrides={'hhh.roles':{role}}, **kwargs)

    def test_authentication_team_and_origin_are_enforced(self):
        self.assertEqual(self.post(self.event(),side='purple').status_code,403)
        self.assertEqual(self.post(self.event(),role='').status_code,403)
        self.assertEqual(self.post(self.event(),headers={'Origin':'https://elsewhere.test'}).status_code,403)
        self.assertFalse(self.path.exists())
        self.assertEqual(self.post(self.event(),side='purple',role='purple').status_code,200)
        row=json.loads(self.path.read_text());self.assertEqual(row['side'],'purple')
        self.assertIn('received_utc',row);self.assertIn('client_at',row)
        self.assertEqual(self.client.get('/api/diagnostics',environ_overrides={'hhh.roles':{'purple'}}).status_code,403)
        exported=self.client.get('/api/diagnostics',environ_overrides={'hhh.roles':{'gamemaster'}})
        self.assertEqual(exported.data,self.path.read_bytes())

    def test_only_diagnostic_fields_persist_and_retries_deduplicate(self):
        secret='a'*32
        event=self.event(context={'feedback_age_ms':1700,'motion_epoch':5,'connected':True,
            'token':secret,'session':secret,'password':'private','pose':[1,2,3],
            'game_error':'token='+secret+' https://test/?auth=private', 'robot_age_ms':float('nan')})
        event['token']=secret;event['reason']='Session='+secret
        for _ in range(2):self.assertEqual(self.post(event).status_code,200)
        raw=self.path.read_text();self.assertEqual(len(raw.splitlines()),1)
        for sensitive in (secret,'private','https://test','password','pose','NaN'):self.assertNotIn(sensitive,raw)
        row=json.loads(raw);self.assertEqual(row['context']['feedback_age_ms'],1700)
        self.assertTrue(row['context']['connected'])

    def test_cue_calibration_layer_and_offsets_survive_export(self):
        for layer, marker, inset in [('raised-tag', 100, 10.5), ('ground', 42, 4.25), ('ground', 59, 0)]:
            context = dict(tag_id=marker, phase='source' if marker >= 100 else 'target',
                           calibration_layer=layer, calibration_revision=3,
                           placement_offset_mm=inset, tuning_offset_mm=2.5)
            event = self.event(context=context)
            event['event'] = 'cue_target_acquired'
            self.assertEqual(self.post(event).status_code, 200)
            row = json.loads(self.log.export().splitlines()[-1])
            self.assertEqual(row['context'], context)

    def test_rotation_is_bounded_and_survives_new_reader(self):
        with patch.object(self.log,'MAX_BYTES',1):
            for i in range(5):
                event=self.event();event['reason']=str(i);self.assertEqual(self.post(event).status_code,200)
        self.log._seen.clear()  # As after a process restart: disk still supplies the export.
        rows=[json.loads(row) for row in self.log.export().splitlines()]
        self.assertEqual([row['reason'] for row in rows],['2','3','4'])
        self.assertEqual(len(list(self.path.parent.iterdir())),3)

    def test_limits_and_storage_failure_keep_event_retryable(self):
        for event in ({},[],self.event(context=[]),{**self.event(),'version':True},{**self.event(),'client_at':float('inf')}):
            self.assertEqual(self.post(event).status_code,400)
        self.assertEqual(self.post(self.event(context={'ignored':'x'*5000})).status_code,413)
        event=self.event()
        with patch.object(Path,'open',side_effect=OSError('fixture disk failure')):
            with self.assertLogs('connection-log-test',level='ERROR'):
                self.assertEqual(self.post(event).status_code,503)
        self.assertEqual(self.post(event).status_code,200)
        with patch.dict(self.log._rates,green=deque([time.monotonic()]*240)):
            self.assertEqual(self.post(self.event()).status_code,429)

    def test_watchdog_records_expiry_after_stopping_and_redacts_rejected_token(self):
        relay=load('dobot-mg400-relay');relay.COMMAND_LOG_FILE=str(self.path)
        relay._sides['green'].update(token='private-lease',last_seen=time.time()-3,present=True)
        relay._sides['purple'].update(token='other-lease',last_seen=time.time()-4,present=True)
        order=[]
        robot=SimpleNamespace(is_connected=lambda:True,get_state=lambda:{'enabled':False},hold=lambda:order.append('stop'))
        with patch.object(relay,'_arm',return_value=robot), \
             patch.object(relay,'_watchdog_stop',SimpleNamespace(wait=Mock(side_effect=[False,True]))), \
             patch.object(relay,'_log_command',side_effect=lambda *a,**kw:order.append(('log',a,kw))):
            relay._watchdog_loop()
        self.assertEqual(order[:2],['stop','stop']);self.assertEqual(order[2][1][2],'lease_expired')
        self.assertGreater(order[2][1][3]['heartbeat_age_ms'],2900)
        self.assertIsNone(relay._sides['green']['token'])
        app=Flask('relay-log-test');app.register_blueprint(relay.bp)
        response=app.test_client().post('/api/heartbeat',json={'side':'green','token':'private-lease'})
        self.assertFalse(response.json['ok'])
        self.assertIn('heartbeat_rejected',self.path.read_text());self.assertNotIn('private-lease',self.path.read_text())


if __name__ == '__main__': unittest.main()
