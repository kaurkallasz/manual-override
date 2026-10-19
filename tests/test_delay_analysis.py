"""Diagnostic capture only: fake game/driver inputs; never commands live hardware."""
import importlib.util
import json
import math
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from test_photon_framework import FakeContext, Flask, ROOT, load
from shared import delay_trace as trace


class RecorderTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.recorder = trace.install(self.folder.name)
        self.addCleanup(trace.shutdown)

    def test_disabled_fast_path_and_stop_preserves_capture(self):
        with patch.object(trace, 'Span', side_effect=AssertionError('off must not allocate spans')):
            with trace.span('unused'):
                pass
            self.assertEqual(trace.call('off', lambda: 42), 42)
        self.recorder.start(seconds=10)
        with trace.span('before_stop'):
            pass
        self.recorder.stop()
        with trace.span('after_stop'):
            pass
        self.recorder.drain()
        value = self.recorder.snapshot()
        self.assertEqual([op['name'] for op in value['operations']], ['before_stop'])
        self.assertFalse(value['recording'])
        self.assertIn('before_stop', self.recorder.summary_path.read_text())

    def test_nested_wait_cpu_and_lock_contention_are_distinguishable(self):
        self.recorder.start(seconds=10)
        lock = threading.Lock(); acquired = threading.Event()
        def holder():
            with trace.locked(lock, 'test.lock'):
                acquired.set(); time.sleep(.05)
        thread = threading.Thread(target=holder); thread.start(); acquired.wait(1)
        with trace.span('root'):
            with trace.locked(lock, 'test.lock'):
                with trace.span('cpu'):
                    until = time.thread_time() + .015
                    while time.thread_time() < until:
                        pass
            with trace.span('disk'):
                time.sleep(.025)
        thread.join(); self.recorder.drain()
        ops = {o['name']: o for o in self.recorder.snapshot()['operations']}
        self.assertGreater(ops['test.lock.wait']['max_ms'], 25)
        self.assertGreater(ops['disk']['max_ms'], 20)
        self.assertLess(ops['disk']['cpu_ms'], 10)
        self.assertGreater(ops['cpu']['cpu_ms'], 10)
        self.assertLess(ops['root']['self_ms'], ops['root']['total_ms']/2)

    def test_slow_span_marker_gauge_and_exception_do_not_change_work(self):
        self.recorder.start(seconds=10)
        with self.assertRaisesRegex(RuntimeError, 'original'):
            with trace.span('throws'):
                raise RuntimeError('original')
        with trace.span('parent'):
            trace.measure('feedback.age', 1500, side='green')
        self.recorder.drain()
        value = self.recorder.snapshot()
        self.assertEqual(value['incidents'][0]['name'], 'feedback.age')
        event = next(e for e in value['events'] if e['name'] == 'throws')
        self.assertEqual(event['error'], 'RuntimeError')
        age = next(e for e in value['events'] if e['name'] == 'feedback.age')
        self.assertEqual(age['kind'], 'gauge')
        parent = next(e for e in value['events'] if e['name'] == 'parent')
        self.assertGreater(parent['self_ms'], 0)
        with patch.object(self.recorder, 'submit', side_effect=RuntimeError('observer failure')):
            self.assertEqual(trace.call('failure', lambda: 'still delivered'), 'still delivered')
        self.assertEqual(self.recorder.observer_errors, 1)

    def test_nonblocking_backpressure_and_limits(self):
        self.recorder.start(seconds=10)
        self.recorder.queue_lock.acquire()
        try:
            started = time.perf_counter()
            with trace.span('dropped'):
                pass
            self.assertLess(time.perf_counter()-started, .02)
        finally:
            self.recorder.queue_lock.release()
        self.assertEqual(self.recorder.dropped, 1)
        with patch.object(trace, 'FILE_LIMIT', 1):
            self.recorder.mark('storage limit incident')
            self.recorder.drain()
        self.assertTrue(self.recorder.recording)
        self.assertTrue(self.recorder.snapshot()['detail_truncated'])
        with trace.span('after_detail_limit'):
            pass
        self.recorder.stop(); self.recorder.drain()
        self.assertIn('after_detail_limit', self.recorder.summary_path.read_text())
        self.assertTrue(self.recorder.snapshot()['warnings'])

    def test_whole_game_summaries_tiny_locks_and_old_incident_survive_restart(self):
        # Thirty simulated minutes, more samples than the former 2,048-sample
        # percentile tail and more event bytes than the original capture limit.
        r = self.recorder
        r._closed.set(); r._thread.join(2)
        r.start()
        capture = r.capture_id
        base = time.time()
        number = 0
        with patch.object(trace.time, 'time') as clock:
            for second in range(1800):
                clock.return_value = base+second
                for n in range(90):
                    number += 1
                    r.submit(dict(capture_id=capture, id=str(number), source='hub', kind='span',
                        name='camera.state_lock.wait' if n < 80 else 'mobile.snapshot',
                        duration_ms=.01 if n < 80 else 100 if second < 1600 else 1,
                        start_ms=second*1000, thread='fixture', clock='host-monotonic'))
                if second in (120, 1080):
                    trace.evidence('connection.cue_motion_held', {'tag_id':49,
                        'board':{'pending_fixed_ids':[48], 'verification':{'anchor_ids':[40,41,42,43],
                            'hull':[[0,0],[1,0],[0,1]]}}}, incident=True)
                r.drain()
            r.stop(); r.drain()
        value = r.snapshot()
        op = next(o for o in value['operations'] if o['name']=='mobile.snapshot')
        self.assertEqual(op['count'], 18000)
        self.assertEqual(op['percentile_samples'], 18000)
        self.assertGreaterEqual(op['p50_ms'], 100)  # Not just the final fast samples.
        self.assertEqual(value['fast_locks_aggregated'], 144000)
        self.assertEqual(value['dropped'], 0)
        self.assertFalse(value['detail_truncated'])
        self.assertLess(r.path.stat().st_size, 1024*1024)
        incident = value['incidents'][0]
        self.assertFalse(any(e['id']==incident['id'] for e in r.events))
        self.assertTrue(any(e['name']=='mobile.snapshot' for e in r.snapshot(incident=incident['id'])['events']))
        restored = trace.install(self.folder.name)
        value = restored.snapshot(incident=incident['id'])
        self.assertFalse(value['recording'])
        self.assertEqual(value['capture_id'], capture)
        self.assertEqual(value['received'], 162002)
        decision = next(e for e in value['events'] if e['kind']=='evidence')
        self.assertEqual(decision['details']['board']['verification']['anchor_ids'], [40,41,42,43])

    def test_interrupted_summary_is_restored_off_with_prominent_warning(self):
        r = self.recorder
        r._closed.set(); r._thread.join(2)
        r.start()
        with trace.span('last_saved_operation'):
            pass
        r.drain()
        with r.control_lock:
            r._checkpoint(force=True)
        # Simulate process loss, without a graceful close overwriting checkpoint.
        trace._recorder = None
        restored = trace.install(self.folder.name)
        value = restored.snapshot()
        self.assertFalse(value['recording'])
        self.assertEqual(value['stop_reason'], 'interrupted')
        self.assertTrue(any('interrupted' in w for w in value['warnings']))
        self.assertEqual(value['operations'][0]['name'], 'last_saved_operation')

    def test_checkpoint_failure_does_not_leave_start_enabled(self):
        original = Path.write_text
        def write(path, *args, **kwargs):
            if path.suffix == '.tmp':
                raise OSError('fixture disk full')
            return original(path, *args, **kwargs)
        with patch.object(Path, 'write_text', write):
            with self.assertRaisesRegex(OSError, 'fixture disk full'):
                self.recorder.start()
            self.assertFalse(trace.enabled())
            value = self.recorder.snapshot()
            self.assertEqual(value['stop_reason'], 'recorder_error')
            self.assertIn('fixture disk full', value['storage_error'])

    def test_driver_failure_evidence_preserves_cause_without_changing_state(self):
        from test_relay_worker import ArmWorker
        from unittest.mock import Mock
        worker = ArmWorker('fixture')
        worker.side = 'green'
        error_type = ArmWorker.get_state.__globals__['DobotError']
        error = error_type(-1, 'Relay driver response timed out. Reconnect.', 'get_state')
        error.__cause__ = TimeoutError('IPC timeout')
        worker._call = Mock(side_effect=error)
        self.recorder.start()
        state = worker.get_state()
        self.assertEqual(state['motion_invalidation'], 'driver_unavailable')
        self.assertFalse(state['connected'])
        self.recorder.drain()
        value = self.recorder.snapshot()
        self.assertEqual(value['incidents'][0]['details']['error_kind'], 'TimeoutError')
        self.assertIn('timed out', value['incidents'][0]['details']['driver_error'])

    def test_evidence_is_off_by_default_and_bounds_redacts_browser_payloads(self):
        with patch.object(trace, 'clean_evidence', side_effect=AssertionError('no off processing')):
            trace.evidence('off', {'reason':'unused'})
        self.recorder.start()
        trace.evidence('board.check', {'reason':'password=secret https://example.com/?token=secret',
            'command':['move',1,2,3], 'board':{'pending_fixed_ids':list(range(100)),
                'verification':{'anchor_ids':[40,41], 'hull':[[0,0],[1,1],[math.nan,0]],
                                'token':'secret'}}}, incident=True)
        self.recorder.drain()
        raw = self.recorder.path.read_text()
        self.assertNotIn('secret', raw)
        self.assertNotIn('command', raw)
        detail = self.recorder.snapshot()['incidents'][0]['details']
        self.assertEqual(len(detail['board']['pending_fixed_ids']), 64)
        self.assertEqual(detail['board']['verification']['hull'], [[0,0],[1,1]])

    def test_late_spans_cannot_leak_into_next_capture(self):
        first = self.recorder.start(seconds=10)['capture_id']
        timing = trace.span('late'); timing.__enter__()
        self.recorder.stop()
        second = self.recorder.start(seconds=10)['capture_id']
        timing.__exit__(None, None, None)
        self.recorder.drain()
        self.assertNotEqual(first, second)
        self.assertEqual(self.recorder.snapshot()['received'], 0)

    def test_client_validation_authorship_stop_ack_and_stale_capture(self):
        control = self.recorder.start(side='green', seconds=10)
        value = dict(control, client_id='a'*32, events=[dict(name='browser.apply',start_ms=100,duration_ms=12,sequence=8)])
        self.recorder.client_batch('green', value)
        self.recorder.drain()
        event = self.recorder.snapshot()['events'][0]
        self.assertEqual(event['clock'], 'client-monotonic')
        self.assertEqual(event['side'], 'green')
        self.assertIsNone(event['cpu_ms'])
        for rows in ([dict(name='anything',start_ms=0,duration_ms=1)],
                     [dict(name='browser.apply',start_ms=0,duration_ms=math.nan)], [None]):
            with self.assertRaises(ValueError):
                self.recorder.client_batch('green', dict(value, client_id='b'*32, events=rows))
        self.recorder.stop()
        self.recorder.client_batch('green', dict(value, revision=self.recorder.revision, recording=False, events=[]))
        self.assertFalse(self.recorder.snapshot()['participants'][-1]['recording'])
        self.assertFalse(self.recorder.client_batch('green', dict(value,capture_id='stale'))['recording'])

    def test_existing_worker_ipc_carries_timings_and_stop_ack_without_new_commands(self):
        from test_relay_worker import ArmWorker, FakeArm
        worker = ArmWorker(str(Path(self.folder.name)/'fake-arm.log'), _driver_factory=FakeArm, command_timeout=1)
        worker.side = 'green'
        self.addCleanup(worker.close)
        self.recorder.start(seconds=10)
        worker.connect()
        for _ in range(4):
            state = worker.get_state()
            self.assertTrue(state['feedback_ok'])
            self.assertLess(time.time()-state['last_feedback'], .25)
            time.sleep(.03)
        self.recorder.drain()
        data = self.recorder.snapshot()
        self.assertTrue(any(o['source']=='worker.green' and o['name'].startswith('driver.') for o in data['operations']))
        self.assertTrue(any(e['source']=='worker.green' and e.get('parent_id') for e in data['events']))
        self.recorder.stop(); worker.get_state()
        self.assertFalse(next(p for p in self.recorder.snapshot()['participants'] if p['source']=='worker.green')['recording'])

    def test_history_flush_delay_is_attributed_to_the_actual_file_operation(self):
        game = load('photon-game')
        self.recorder.start(seconds=10)
        with patch.object(game, 'LOG_PATH', str(Path(self.folder.name)/'history.jsonl')), \
             patch.object(game.os, 'fsync', side_effect=lambda fd: time.sleep(.035)):
            game._append_history('diagnostic-fixture', {'no_hardware': True})
        self.recorder.drain()
        ops = {o['name']: o for o in self.recorder.snapshot()['operations']}
        self.assertGreater(ops['logging.history_fsync']['max_ms'], 30)
        self.assertLess(ops['logging.history_fsync']['cpu_ms'], 10)

    def test_final_batch_drains_once_and_old_active_packet_cannot_undo_ack(self):
        control = self.recorder.start(seconds=10)
        batch = dict(control, client_id='f'*32, events=[], recording=True)
        self.recorder.client_batch('green', batch)
        self.recorder.stop()
        final = dict(batch, revision=self.recorder.revision, recording=False,
                     events=[{'name':'browser.apply','start_ms':10,'duration_ms':8}])
        self.recorder.client_batch('green', final)
        self.recorder.client_batch('green', batch)  # Old response in flight at Stop.
        self.recorder.drain()
        self.assertEqual(self.recorder.received, 1)
        self.assertFalse(self.recorder.snapshot()['participants'][0]['recording'])

    def test_worker_coverage_cannot_wait_for_dashboard_reader(self):
        entered, release = threading.Event(), threading.Event()
        def reader():
            with self.recorder.data_lock:
                entered.set(); release.wait(1)
        thread=threading.Thread(target=reader); thread.start(); entered.wait(1)
        try:
            started=time.perf_counter()
            self.recorder.worker_seen('worker.green')
            self.assertLess(time.perf_counter()-started,.02)
            self.assertEqual(self.recorder.coverage_dropped,1)
        finally:
            release.set(); thread.join()

    def test_new_worker_accepts_parent_protocol_from_before_hub_restart(self):
        from unittest.mock import Mock
        from test_relay_worker import ArmWorker
        reply = ArmWorker._call.__wrapped__.__globals__['_reply']
        connection = Mock()
        connection.recv.return_value = ('get_state', (), {}, time.monotonic()+1)
        robot = Mock(); robot.get_state.return_value = {'connected': False}
        reply(robot, connection, {'get_state'})
        connection.send.assert_called_once_with((True, {'connected': False}))


class DelayApiTests(unittest.TestCase):
    def setUp(self):
        from types import SimpleNamespace
        self.folder = tempfile.TemporaryDirectory(); self.addCleanup(self.folder.cleanup)
        self.facade = load('mobile-ltz-api')
        self.calls = 0
        def snapshot():
            self.calls += 1
            return {'contract':'photon.game','version':2,'status':'ready','virtual_play':True,
                    'run_id':'fixture','enemies':[],'journey':{}}
        self.facade.hub_init(FakeContext({'photon-game':SimpleNamespace(game_snapshot=snapshot)}))
        self.facade.delay_analysis.start(self.folder.name)
        self.addCleanup(self.facade.hub_stop)
        self.app = Flask('delay-test'); self.app.register_blueprint(self.facade.bp)
        self.client = self.app.test_client()
        self.gm = {'hhh.roles':{'gamemaster'}}
        self.green = {'hhh.roles':{'green'}}

    def post(self, value):
        return self.client.post('/api/delay',json=value,environ_overrides=self.gm)

    def test_permissions_and_no_game_sampling_from_tab(self):
        for path in ('/delay-analysis','/delay-analysis.js','/delay-analysis.css','/api/delay','/api/delay/export','/api/delay/events'):
            self.assertEqual(self.client.get(path,environ_overrides=self.green).status_code,403)
        self.assertEqual(self.client.post('/api/delay',json={'action':'start'},environ_overrides=self.green).status_code,403)
        response=self.client.get('/delay-analysis',environ_overrides=self.gm)
        self.assertEqual(response.status_code,200); response.close()
        self.assertFalse(self.client.get('/api/delay',environ_overrides=self.gm).json['recording'])
        self.assertEqual(self.calls,0)
        self.assertEqual(self.client.post('/api/delay',json={'action':'start'},headers={'Origin':'https://evil.example'},environ_overrides=self.gm).status_code,403)

    def test_capture_real_facade_stop_and_export(self):
        value = self.post({'action':'start','seconds':10}).json
        self.assertTrue(value['recording'])
        response = self.client.get('/api/state',environ_overrides=self.green)
        self.assertTrue(response.json['delay_analysis']['recording'])
        self.facade.delay_analysis._recorder.drain()
        data = self.client.get('/api/delay',environ_overrides=self.gm).json
        self.assertIn('mobile.snapshot',{o['name'] for o in data['operations']})
        self.assertIn('diagnostics.sample',{o['name'] for o in data['operations']})
        self.assertEqual(self.post({'action':'mark','label':'Test incident'}).status_code,200)
        self.post({'action':'stop'})
        self.facade.delay_analysis._recorder.drain()
        response = self.client.get('/api/delay/export',environ_overrides=self.gm)
        self.assertIn('mobile.snapshot',response.text)
        response.close()
        csv = self.client.get('/api/delay/export?format=csv',environ_overrides=self.gm)
        self.assertIn('p99_ms',csv.text)
        self.assertEqual(self.post({'action':'clear'}).status_code,200)

    def test_team_batch_bounds_and_control_validation(self):
        config = self.post({'action':'start','side':'purple','seconds':10}).json
        self.assertFalse(self.client.get('/api/state',environ_overrides=self.green).json['delay_analysis']['recording'])
        batch = dict(config,client_id='d'*32,events=[],recording=True)
        self.assertEqual(self.client.post('/api/diagnostics?side=purple',json=batch,environ_overrides=self.green).status_code,403)
        self.assertEqual(self.client.post('/api/diagnostics',data='x'*65537,content_type='application/json',environ_overrides=self.green).status_code,413)
        self.post({'action':'stop'})
        for value in (None, [], {'action':'move'}, {'action':'start','seconds':True}, {'action':'start','seconds':9999}, {'action':'start','side':'bad'}):
            response = self.client.post('/api/delay',data=json.dumps(value),content_type='application/json',environ_overrides=self.gm)
            self.assertEqual(response.status_code,400,value)


class GatewayTimingTests(unittest.TestCase):
    def test_gateway_timings_follow_the_existing_frame_and_capture_switch(self):
        spec=importlib.util.spec_from_file_location('delay_gateway',ROOT/'tools/mobile-ltz/gateway.py')
        gateway=importlib.util.module_from_spec(spec);spec.loader.exec_module(gateway)
        def frame(recording):
            return ('data: '+json.dumps({'contract':'hub.live','version':1,'kind':'snapshot','state':{
                'delivery':{'contract':'photon.delivery','version':1,'sequence':7},
                'delay_analysis':{'contract':'delay.analysis','version':1,'recording':recording,'capture_id':'test'}}})+'\n\n').encode()
        off=gateway.timed_frame(frame(False),50)
        self.assertNotIn(b'delay_gateway',off)
        on=gateway.delay_queue_frame(gateway.timed_frame(frame(True),50))
        state=json.loads(on.split(b'data: ',1)[1])['state']
        self.assertEqual(state['delivery']['sequence'],7)
        self.assertEqual(state['delivery']['delay_gateway']['receive_gap_ms'],50)
        self.assertGreaterEqual(state['delivery']['delay_gateway']['queue_ms'],0)
        self.assertNotIn('_received_mono',state['delivery']['delay_gateway'])


if __name__ == '__main__':
    unittest.main()
