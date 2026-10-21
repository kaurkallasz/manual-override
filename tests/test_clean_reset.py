"""Real Hub authentication and Game/Progress reset; temporary data, fake arms.

Run: PYTHONPATH=tests .venv/bin/python -m unittest test_clean_reset
"""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import copy
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from werkzeug.test import Client
from werkzeug.wrappers import Response
from flask import jsonify
from flask import Flask, request
from types import SimpleNamespace
from unittest.mock import Mock
from test_photon_framework import load

from test_player_join import fixture_hub, PlayerJoinTests
from test_event_reset import EventResetTests
from hub import HubContext, COOKIE_NAME
from hub.player_sessions import PlayerSessions


def attach_management(hub, game):
    """Connect the real Game owner to Hub, keeping fixture hardware isolated."""
    ctx = HubContext(hub.sandboxes['gamemaster'], 'photon-game')
    game._hub_ctx.player_sessions = hub.player_sessions
    game._hub_ctx.invalidate_player_links = ctx.invalidate_player_links
    game._hub_ctx.refresh_player_links = ctx.refresh_player_links
    relay = game._module('dobot-mg400-relay')
    relay.player_control_sessions = lambda: dict(contract='hhh.relay.player-sessions', version=1,
                                                status='ready', sessions={}, leased_sides=[])
    relay.revoke_player_controls = lambda: dict(contract='hhh.relay.player-sessions', version=1,
                                               status='ready', released=True)
    ctx.register_player_management(dict(contract='photon.player-management', version=1,
                                        snapshot=game.player_connections, clean_reset=game.clean_reset_players))


class CleanResetTests(unittest.TestCase):
    start = EventResetTests.start
    command = EventResetTests.command
    assert_lobby = EventResetTests.assert_lobby
    select = EventResetTests.select
    token = PlayerJoinTests.token

    def setUp(self):
        EventResetTests.setUp(self)
        self.hub = fixture_hub(self.folder.name)
        attach_management(self.hub, self.g)
        self.gm = Client(self.hub.wsgi, Response)
        self.gm.post('/s/gamemaster/login', data={'password': 'fixture-gamemaster'})
        self.links = self.gm.get('/s/gamemaster/api/player-join').json['links']
        self.players = []
        for team in ('green', 'green', 'purple'):
            player = Client(self.hub.wsgi, Response)
            link = next(row for row in self.links if row['team'] == team)
            self.assertEqual(player.post('/s/'+team+'/login/join', json={'token':self.token(link)},
                                        environ_overrides={'REMOTE_ADDR':'192.0.2.10'}).status_code, 200)
            self.players.append(player)
        self.sids = [self.hub._signer.loads(p.get_cookie(COOKIE_NAME).value)['sid'] for p in self.players]

    def reset(self, operation='clean-one', client=None):
        return (client or self.gm).post('/s/gamemaster/api/player-sessions/clean-reset',
                                       json={'operation_id': operation})

    def test_reset_invalidates_every_browser_old_links_and_delegated_worker(self):
        run = self.start()
        saved = self.g._progress.roster()
        self.hub.player_sessions.rows[self.sids[-1]]['last_seen'] = 0  # offline phone
        state = self.gm.get('/s/gamemaster/api/player-sessions').json
        self.assertEqual([r['player_name'] for r in state['rows']], ['green pilot','green pilot','purple pilot'])
        self.assertEqual(len({r['id'] for r in state['rows']}), 3)
        self.assertEqual({r['ip'] for r in state['rows']}, {'192.0.2.10'})
        stream = self.players[0].get('/s/green/api/player-session/events', buffered=False)
        iterator = iter(stream.response);self.assertIn(b'active', next(iterator))
        delegated = self.hub._delegate_signer.dumps({'team':'green','sid':self.sids[0]})
        worker = Client(self.hub.wsgi, Response)
        self.assertEqual(worker.get('/s/green/api/meta', headers={'X-HHH-Auth':delegated}).status_code, 200)
        response = self.reset();self.assertEqual(response.status_code, 200, response.json)
        self.assert_lobby()
        with self.assertRaises(StopIteration): next(iterator)
        stream.close()
        for player, team in zip(self.players, ('green','green','purple')):
            self.assertEqual(player.get('/s/'+team+'/api/meta').status_code, 401)
        self.assertEqual(worker.get('/s/green/api/meta', headers={'X-HHH-Auth':delegated}).status_code, 401)
        self.assertEqual(self.gm.get('/s/gamemaster/api/meta').status_code, 200)
        for link in self.links:
            self.assertEqual(worker.post('/s/'+link['team']+'/login/join', json={'token':self.token(link)}).status_code, 401)
        new = self.gm.get('/s/gamemaster/api/player-join').json['links'][0]
        self.assertEqual(worker.post('/s/'+new['team']+'/login/join', json={'token':self.token(new)}).status_code, 200)
        self.assertEqual(self.g._module('photon-progress').attempt_snapshot(run)['attempt']['outcome'], 'aborted')
        self.select(saved['roster'])
        self.assertEqual(set(self.g._progress.roster()['roster']), {'green','purple'})
        # Retrying a completed operation cannot clear those new selections.
        self.assertTrue(self.reset().json['already_completed'])
        self.assertEqual(worker.get('/s/'+new['team']+'/api/meta').status_code, 200)
        self.assertEqual(set(self.g._progress.roster()['roster']), {'green','purple'})

    def test_stop_failure_blocks_signins_commands_and_codes_until_retry(self):
        self.start()
        with patch.object(self.g, '_stop_for_saved_game', side_effect=ValueError('Stop unconfirmed')), \
             patch.object(self.hub.sandboxes['gamemaster'].app.logger, 'exception'):
            response = self.reset()
            self.assertEqual(response.status_code, 409)
            self.assertIn('Stop unconfirmed', response.json['error'])
            self.assert_lobby()
            self.assertTrue(self.g.motion_policy('green')['blocked'])
            self.assertEqual(self.gm.get('/s/gamemaster/api/player-join').status_code, 503)
        self.assertTrue(PlayerSessions(self.hub.player_sessions.path).blocked)
        self.assertEqual(self.command('start').status_code, 400)
        player = Client(self.hub.wsgi, Response)
        self.assertEqual(player.post('/s/green/login/join', json={'token':self.token(self.links[0])}).status_code, 503)
        self.assertIsNone(player.post('/s/green/login', data={'password':'fixture-green'}).headers.get('Set-Cookie'))
        self.assertEqual(self.reset().status_code, 200)
        self.assertFalse(self.hub.player_sessions.blocked)
        self.assertFalse(PlayerSessions(self.hub.player_sessions.path).blocked)

    def test_reset_save_failure_and_qr_failure_are_retryable(self):
        for failure in ('game', 'qr'):
            with self.subTest(failure=failure):
                operation = 'fail-'+failure
                target, method = (self.g._engine, 'reset') if failure == 'game' else (self.g._hub_ctx, 'refresh_player_links')
                with patch.object(target, method, side_effect=ValueError('Temporary failure')), \
                     patch.object(self.hub.sandboxes['gamemaster'].app.logger, 'exception'):
                    self.assertEqual(self.reset(operation).status_code, 409)
                self.assertTrue(self.hub.player_sessions.blocked)
                reply = self.reset(operation)
                self.assertEqual(reply.status_code, 200, reply.json)
                self.assert_lobby()

    def test_duplicate_requests_reset_once_and_no_individual_kick_route(self):
        cookie = self.gm.get_cookie(COOKIE_NAME).value
        def reset(_):
            client = Client(self.hub.wsgi, Response);client.set_cookie(COOKIE_NAME, cookie)
            return self.reset(client=client).status_code
        with patch.object(self.g, '_reset_event_game', wraps=self.g._reset_event_game) as action:
            with ThreadPoolExecutor(max_workers=3) as pool:
                self.assertEqual(list(pool.map(reset, range(3))), [200]*3)
            self.assertEqual(action.call_count, 1)
        self.assertEqual(self.gm.post('/s/gamemaster/api/player-sessions/kick', json={}).status_code, 404)

    def test_regenerate_and_create_event_do_not_disconnect_players(self):
        self.assertEqual(self.gm.post('/s/gamemaster/api/player-join', json={}).status_code, 200)
        self.g.event_command({'action':'create','name':'Next event','operation_id':'event-two'})
        self.assertTrue(all(self.hub.player_sessions.active(sid) for sid in self.sids))
        self.assertEqual(self.gm.get('/s/gamemaster/api/player-join').status_code, 200)

    def test_clean_reset_without_selected_event_does_not_create_one(self):
        empty = copy.deepcopy(self.g._progress.roster())
        empty['events']['active_id'] = None
        empty['saved_games'].update(active_id=None, active=None)
        empty['roster'] = {};empty['active_attempts'] = []
        owner = self.g._module('photon-progress')
        with patch.object(self.g._progress, 'roster', return_value=empty), patch.object(owner, 'event_command') as events:
            response = self.reset()
            self.assertEqual(response.status_code, 200, response.json)
            events.assert_not_called()
            self.assertEqual(self.g._journey.snapshot()['ready'], {})
            self.assertEqual(self.g._engine.phase, 'setup')

    def test_management_requires_admin_and_same_origin(self):
        self.assertEqual(self.reset(client=self.players[0]).status_code, 401)
        reply = self.gm.post('/s/gamemaster/api/player-sessions/clean-reset', json={'operation_id':'x'},
                             headers={'Origin':'https://unrelated.example'})
        self.assertEqual(reply.status_code, 403)
        self.assertFalse(self.hub.player_sessions.blocked)

    def test_idle_disconnected_arms_do_not_block_reset_or_qr_retry(self):
        relay = self.g._module('dobot-mg400-relay')
        snapshot = relay.arms_snapshot
        def disconnected():
            state = snapshot()
            for arm in state['arms'].values(): arm['connected'] = False
            return state
        with self.g._command_lock, patch.object(relay, 'arms_snapshot', side_effect=disconnected), \
             patch.object(relay, 'stop_side', return_value={'contract':'hhh.relay.stop',
                 'version':1, 'status':'unavailable', 'stopped':False}) as stop:
            reply = self.reset('offline-reset')
            self.assertEqual(reply.status_code, 200, reply.json)
            self.assert_lobby()
            self.assertFalse(self.hub.player_sessions.blocked)
            self.assertEqual(self.g._journey.snapshot()['reset_stop_sides'], [])
            self.assertIsNone(self.g._journey.snapshot()['reset_stop_error'])
            stop.assert_not_called()
            # A later failure after Game reset must not invent a hardware stop
            # requirement when that same operation is retried after a reload.
            with patch.object(self.g._hub_ctx, 'refresh_player_links', side_effect=ValueError('QR unavailable')), \
                 patch.object(self.hub.sandboxes['gamemaster'].app.logger, 'exception'):
                self.assertEqual(self.reset('offline-qr-retry').status_code, 409)
            old = self.g._journey
            self.g._journey = self.g.Journey(old.path, old.module_reader, old.wake)
            reply = self.reset('offline-qr-retry')
            self.assertEqual(reply.status_code, 200, reply.json)
            stop.assert_not_called()

    def test_persisted_empty_stop_scope_differs_from_unknown_or_required(self):
        relay = self.g._module('dobot-mg400-relay')
        snapshot = relay.arms_snapshot
        def disconnected():
            state = snapshot()
            for arm in state['arms'].values(): arm['connected'] = False
            return state
        with self.g._command_lock, patch.object(relay, 'arms_snapshot', side_effect=disconnected):
            for scope, expected in (([], []), (None, ['green','purple']), (['purple'], ['purple'])):
                with self.subTest(scope=scope):
                    state = self.g._journey._state()
                    state.update(reset_stop_error='Previously recorded stop', reset_stop_sides=scope)
                    self.g._journey._save(state)
                    old = self.g._journey
                    self.g._journey = self.g.Journey(old.path, old.module_reader, old.wake)
                    self.assertEqual(self.g._reset_stop_scope(), expected)


class SessionIsolationTests(unittest.TestCase):
    def test_delegation_captures_session_and_reset_waits_for_inflight_request(self):
        with tempfile.TemporaryDirectory() as folder:
            hub = fixture_hub(folder)
            ctx = HubContext(hub.sandboxes['green'], 'cartesian-xyz-test')
            entered, finish = threading.Event(), threading.Event()
            @hub.sandboxes['green'].app.post('/api/test-command')
            def command():
                entered.set();finish.wait(2)
                return jsonify(token=ctx.service_token)
            player = Client(hub.wsgi, Response)
            player.post('/s/green/login', data={'password':'fixture-green'})
            sid = hub._signer.loads(player.get_cookie(COOKIE_NAME).value)['sid']
            with ThreadPoolExecutor(max_workers=2) as pool:
                request = pool.submit(player.post, '/s/green/api/test-command', json={})
                self.assertTrue(entered.wait(2))
                hub.player_sessions.begin_reset('drain', None)
                drain = pool.submit(hub.player_sessions.drain)
                time.sleep(.03);self.assertFalse(drain.done())
                finish.set();response = request.result(timeout=2);drain.result(timeout=2)
            self.assertEqual(hub._delegate_signer.loads(response.json['token']), {'sid':sid,'team':'green'})
            self.assertFalse(hub.player_sessions.active(sid))
            # Restart loses all prior browser identities even after reopening.
            hub.player_sessions.finish_reset('drain')
            restarted = PlayerSessions(hub.player_sessions.path)
            self.assertFalse(restarted.active(sid))


class RelayResetTests(unittest.TestCase):
    def test_waiting_acquire_is_rechecked_and_background_lease_cannot_survive(self):
        with tempfile.TemporaryDirectory() as folder:
            access = PlayerSessions(Path(folder)/'access.json')
            sid = access.create('green', '192.0.2.10')
            relay = load('dobot-mg400-relay')
            relay._hub_ctx = SimpleNamespace(player_sessions=access, is_prototype_enabled=lambda slug:False)
            robot = Mock();robot.is_connected.return_value=True;robot.reset_motion.return_value=3
            app = Flask('clean-reset-relay');entered = threading.Event()
            @app.before_request
            def identity():
                request.environ.update({'hhh.roles':{'green'}, 'hhh.player_session':sid})
                entered.set()
            app.register_blueprint(relay.bp)
            with patch.object(relay, '_arm', return_value=robot), \
                 patch.object(relay, '_log_incoming'), patch.object(relay, '_log_command'):
                client=app.test_client()
                reply=client.post('/api/acquire',json={'side':'green','mode':'joint'})
                self.assertTrue(reply.json['ok'])
                token=reply.json['token']
                self.assertEqual(relay.player_control_sessions()['sessions'], {'green':sid})
                entered.clear()
                with ThreadPoolExecutor(max_workers=1) as pool:
                    with relay._arm_locks['green']:
                        queued=pool.submit(lambda: app.test_client().post('/api/acquire',json={'side':'green'}))
                        self.assertTrue(entered.wait(2))
                        access.begin_reset('queued-reset', None)
                    self.assertEqual(queued.result(timeout=2).status_code, 401)
                self.assertEqual(robot.reset_motion.call_count, 1)
                self.assertTrue(relay.revoke_player_controls()['released'])
                self.assertEqual(relay.player_control_sessions()['sessions'], {})
                access.finish_reset('queued-reset')
                self.assertEqual(client.post('/api/heartbeat',json={'side':'green','token':token}).status_code, 401)


if __name__ == '__main__': unittest.main()
