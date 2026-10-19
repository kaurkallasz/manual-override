"""Passive Mobile LTZ diagnostics, with fake game state and no hardware."""
import copy
import json
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from test_photon_framework import FakeContext, Flask, load


class MobileMonitorTests(unittest.TestCase):
    def setUp(self):
        self.facade = load('mobile-ltz-api')
        self.calls = 0
        self.value = {'contract': 'photon.game', 'version': 2, 'status': 'ready',
                      'virtual_play': True, 'phase': 'setup', 'run_id': None, 'level_revision': 1,
                      'level': {'name': 'fixture'}, 'settings': {}, 'presentation': {},
                      'mobile_arms': {'green': {'side': 'green'}, 'purple': {'side': 'purple'}},
                      'enemies': [], 'journey': {}}
        def snapshot():
            self.calls += 1
            return copy.deepcopy(self.value)
        game = SimpleNamespace(game_snapshot=snapshot, mobile_command=lambda data: {'session': 'private-token', 'side': data['side']})
        self.facade.hub_init(FakeContext({'photon-game': game}))
        self.app = Flask('monitor-test')
        self.app.register_blueprint(self.facade.bp)
        self.client = self.app.test_client()
        self.gm = {'hhh.roles': {'gamemaster'}}
        self.green = {'hhh.roles': {'green'}}
        self.addCleanup(self.facade.hub_stop)

    def monitor(self, query=''):
        response = self.client.get('/api/monitor' + query, environ_overrides=self.gm)
        self.assertEqual(response.status_code, 200)
        return response.get_json()

    def test_dashboard_and_payloads_are_gamemaster_only(self):
        for path in ('/', '/monitor.js', '/monitor.css', '/api/monitor', '/api/monitor?side=purple&payloads=1'):
            for roles in (set(), {'green'}, {'purple'}):
                with self.subTest(path=path, roles=roles):
                    self.assertEqual(self.client.get(path, environ_overrides={'hhh.roles': roles}).status_code, 403)
            response = self.client.get(path, environ_overrides=self.gm)
            self.assertEqual(response.status_code, 200)
            response.close()
        self.assertEqual(self.calls, 0)

    def test_observer_does_not_generate_player_traffic_or_count_itself(self):
        for _ in range(3):
            data = self.monitor('?payloads=1')
        self.assertEqual(self.calls, 0)
        for side in ('green', 'purple'):
            self.assertEqual(data['teams'][side]['generated'], 0)
            self.assertEqual(data['teams'][side]['http_responses'], 0)
            self.assertEqual(data['teams'][side]['active_streams'], 0)

    def test_http_and_generation_are_separate_and_team_specific(self):
        response = self.client.get('/api/state?side=purple', environ_overrides={'hhh.roles': {'purple'}})
        raw = response.data
        data = self.monitor('?side=purple&payloads=1')['teams']['purple']
        self.assertEqual(data['generated'], 1)
        self.assertEqual(data['http_responses'], 1)
        self.assertEqual(data['http_bytes'], len(raw))
        self.assertEqual(data['sse_frames'], 0)
        self.assertIn('"mobile_team": "purple"', data['samples']['generated']['preview'])
        self.assertNotIn('mobile_arms', data['samples']['generated']['preview'])
        self.assertEqual(self.monitor()['teams']['green']['generated'], 0)
        self.assertEqual(self.calls, 1)

    def test_actual_sse_snapshots_updates_bytes_and_close(self):
        response = self.client.get('/api/events?side=green', environ_overrides=self.green, buffered=False)
        try:
            stream = iter(response.response)
            first = next(stream)
            self.facade._live.bump()
            second = next(stream)
            data = self.monitor('?side=green&channel=sse&payloads=1')['teams']['green']
            self.assertEqual(data['active_streams'], 1)
            self.assertEqual(data['sse_snapshots'], 1)
            self.assertEqual(data['sse_updates'], 1)
            self.assertEqual(data['sse_bytes'], len(first) + len(second))
            self.assertEqual(data['generated'], 2)
            payload = json.loads(data['samples']['sse']['preview'])
            self.assertEqual(payload['kind'], 'update')
            self.assertNotIn('level', payload['state'])
            self.assertIn('level', json.loads(self.monitor('?side=green&channel=generated&payloads=1')['teams']['green']['samples']['generated']['preview']))
        finally:
            response.close()
        data = self.monitor()['teams']['green']
        self.assertEqual((data['active_streams'], data['opened_streams'], data['closed_streams']), (0, 1, 1))

    def test_two_clients_share_generation_but_count_both_emissions(self):
        first = self.client.get('/api/events', environ_overrides=self.green, buffered=False)
        self.addCleanup(first.close)
        one = next(iter(first.response))
        # Hold the shared cache valid while this test creates the second client.
        cache = self.facade._live._shared
        self.facade._live._shared = (cache[0], time.monotonic() + 60, cache[2])
        second = self.client.get('/api/events', environ_overrides=self.green, buffered=False)
        self.addCleanup(second.close)
        two = next(iter(second.response))
        data = self.monitor()['teams']['green']
        self.assertEqual(data['generated'], 1)
        self.assertEqual(data['sse_snapshots'], 2)
        self.assertEqual(data['active_streams'], 2)
        self.assertEqual(data['sse_bytes'], len(one) + len(two))

    def test_shop_clock_and_profile_changes_do_not_resend_static_scene(self):
        # The shop carries a live server clock. Treating progress as static
        # forced a full level/art snapshot on every real player's SSE tick.
        value = {**self.value, 'mobile_progress': {
            'revision': 1, 'player': {'current_control_tier': 1},
            'shop': {'server_time': 100}}}
        with patch.object(self.facade, 'mobile_snapshot', side_effect=lambda: copy.deepcopy(value)):
            response = self.client.get('/api/events', environ_overrides=self.green, buffered=False)
            try:
                stream = iter(response.response)
                def state(chunk):
                    return json.loads(chunk.decode().split('data: ', 1)[1])
                self.assertEqual(state(next(stream))['kind'], 'snapshot')
                value['mobile_progress']['shop']['server_time'] += 1
                value['mobile_progress']['player']['current_control_tier'] = 2
                self.facade._live.bump()
                update = state(next(stream))
                self.assertEqual(update['kind'], 'update')
                self.assertNotIn('level', update['state'])
                self.assertEqual(update['state']['mobile_progress'], value['mobile_progress'])
                value['level'] = {'name': 'new map'}
                self.facade._live.bump()
                full = state(next(stream))
                self.assertEqual(full['kind'], 'snapshot')
                self.assertEqual(full['state']['level'], value['level'])
            finally:
                response.close()

    def test_error_responses_are_counted_without_changing_status(self):
        response = self.client.post('/api/command?side=purple', json={'action': 'connect'}, environ_overrides=self.green)
        self.assertEqual(response.status_code, 403)
        response = self.client.get('/api/events?side=purple', environ_overrides=self.green)
        self.assertEqual(response.status_code, 403)
        data = self.monitor()['teams']['purple']
        self.assertEqual(data['http_errors'], 2)
        self.assertEqual(data['generated'], 0)

    def test_hub_auth_can_return_before_blueprint_measurement(self):
        from flask import abort
        @self.app.before_request
        def hub_auth():
            abort(403)
        response = self.client.get('/api/state')
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.calls, 0)

    def test_rejected_request_body_is_not_read_for_diagnostics(self):
        with patch('flask.wrappers.Request.get_json', side_effect=AssertionError('must not parse')):
            response = self.client.post('/api/command?side=purple', json={'action': 'connect'}, environ_overrides=self.green)
        self.assertEqual(response.status_code, 403)

    def test_connection_secrets_are_redacted_only_in_monitor(self):
        response = self.client.post('/api/command', json={'action': 'connect'}, environ_overrides=self.green)
        self.assertEqual(response.get_json()['arm']['session'], 'private-token')
        value = self.monitor('?side=green&payloads=1')
        self.assertNotIn('private-token', json.dumps(value))
        self.assertIn('[redacted]', value['teams']['green']['samples']['http']['preview'])
        self.assertEqual(value['recent'][0]['action'], 'connect')

    def test_unavailable_generation_is_visible(self):
        self.facade.hub_init(FakeContext({}))
        response = self.client.get('/api/state', environ_overrides=self.green)
        self.assertEqual(response.get_json()['status'], 'unavailable')
        data = self.monitor('?side=green&payloads=1')['teams']['green']
        self.assertEqual(data['generated_unavailable'], 1)
        self.assertIn('Photon Game unavailable', data['samples']['generated']['preview'])

    def test_instrumentation_failure_never_blocks_delivery(self):
        with patch.object(self.facade._diagnostics, 'generated', side_effect=RuntimeError('test')):
            with self.assertLogs(self.facade.__name__, level='ERROR'):
                response = self.client.get('/api/state', environ_overrides=self.green)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['status'], 'ready')
        self.assertEqual(self.monitor()['observer_errors'], 1)

    def test_counter_rates_expire_and_sample_memory_is_bounded(self):
        monitor = self.facade._diagnostics
        now = monitor.started_mono
        with patch('delivery_diagnostics.time.monotonic', return_value=now + 1):
            monitor.generated('green', {'status': 'ready', 'large': ['x' * 1000] * 1000}, 2)
            for i in range(80):
                monitor.http_response('green', '/api/state', 200, 100, 'application/json', 1)
        data = monitor.snapshot(side='green', payloads=True)
        sample = data['teams']['green']['samples']['generated']
        self.assertTrue(sample['truncated'])
        self.assertLess(len(sample['preview'].encode()), 256 * 1024 + 100)
        self.assertEqual(len(data['recent']), 60)
        with patch('delivery_diagnostics.time.monotonic', return_value=now + 12):
            data = monitor.snapshot()['teams']['green']
        self.assertEqual(data['generated_hz'], 0)
        self.assertEqual(data['http_bytes_per_s'], 0)
        self.assertEqual(data['generated'], 1)

    def test_keepalive_and_stream_failure_counts(self):
        monitor = self.facade._diagnostics
        monitor.stream_open('purple')
        monitor.emitted('purple', ': ping\n\n')
        monitor.stream_close('purple', failed=True)
        data = monitor.snapshot()['teams']['purple']
        self.assertEqual(data['sse_pings'], 1)
        self.assertEqual(data['stream_errors'], 1)
        self.assertEqual(data['emitted_hz'], 0)
        self.assertEqual(data['sse_bytes'], 8)

    def test_stream_exception_releases_active_connection(self):
        def broken():
            yield 'data: {"status":"ready"}\n\n'
            raise RuntimeError('fixture stream failure')
        with patch.object(self.facade._live, 'stream', return_value=self.facade.Response(broken(), mimetype='text/event-stream')):
            response = self.client.get('/api/events', environ_overrides=self.green, buffered=False)
            stream = iter(response.response)
            next(stream)
            with self.assertRaisesRegex(RuntimeError, 'fixture stream failure'):
                next(stream)
            response.close()
        data = self.monitor()['teams']['green']
        self.assertEqual(data['active_streams'], 0)
        self.assertEqual(data['stream_errors'], 1)

    def test_recursive_redaction_preserves_source_value(self):
        source = {'nested': {'password': 'hidden-password', 'access_token': 'hidden-access',
                             'url': 'https://example.test/events?token=hidden-url&side=green'},
                  'session': 'hidden-session', 'name': 'Player'}
        before = copy.deepcopy(source)
        self.facade._diagnostics.generated('green', source, 1)
        preview = self.monitor('?side=green&payloads=1')['teams']['green']['samples']['generated']['preview']
        for secret in ('hidden-password', 'hidden-access', 'hidden-url', 'hidden-session'):
            self.assertNotIn(secret, preview)
        self.assertEqual(source, before)
        self.assertIn('Player', preview)

    def test_summary_omits_previews_and_channel_filter_limits_payloads(self):
        self.client.get('/api/state', environ_overrides=self.green)
        for sample in self.monitor()['teams']['green']['samples'].values():
            self.assertNotIn('preview', sample)
        data = self.monitor('?side=green&channel=generated&payloads=1')['teams']['green']['samples']
        self.assertIn('preview', data['generated'])
        self.assertNotIn('preview', data['http'])
        for query in ('?side=bad', '?channel=bad'):
            self.assertEqual(self.client.get('/api/monitor' + query, environ_overrides=self.gm).status_code, 400)


if __name__ == '__main__':
    unittest.main()
