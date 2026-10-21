"""Run: .venv/bin/python -m unittest discover -s tests -p test_player_join.py"""
import base64
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

import cv2
import numpy as np
from flask import Blueprint
from werkzeug.test import Client
from werkzeug.wrappers import Response

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from hub import Hub, DEFAULT_SANDBOXES, COOKIE_NAME
from hub.player_join import LIFETIME_SECONDS, PlayerJoinLinks, network_origin


def fixture_hub(folder):
    config = {'port': 8163, 'secret': 'fixture-only-' * 4,
              'sandboxes': copy.deepcopy(DEFAULT_SANDBOXES)}
    for team, settings in config['sandboxes'].items():
        settings['password'] = 'fixture-' + team
    path = Path(folder) / 'hub-config.json'
    path.write_text(json.dumps(config))
    hub = Hub(folder)
    hub.local_base = 'http://192.168.1.50:8163'
    for team in ('green', 'purple'):
        sandbox = hub.sandboxes[team]
        bp = Blueprint('mobile_' + team, __name__)
        bp.add_url_rule('/', 'index', lambda: 'Mobile LTZ')
        sandbox.app.register_blueprint(bp, url_prefix='/p/mobile-ltz')
        sandbox._modules['mobile-ltz'] = object()
    return hub


class PlayerJoinTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.hub = fixture_hub(self.folder.name)
        self.gm = Client(self.hub.wsgi, Response)
        self.gm.post('/s/gamemaster/login', data={'password': 'fixture-gamemaster'})

    def links(self, method='get'):
        response = getattr(self.gm, method)('/s/gamemaster/api/player-join',
                                           **({'json': {}} if method == 'post' else {}))
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        return response.json

    def token(self, link):
        return urlsplit(link['url']).fragment.removeprefix('join=')

    def join(self, client, team, token, **extra):
        return client.post(f'/s/{team}/login/join', json={'token': token}, **extra)

    def test_each_qr_decodes_and_signs_into_only_its_team(self):
        data = self.links()
        self.assertEqual(data['origin'], self.hub.local_base)
        for link in data['links']:
            image = cv2.imdecode(np.frombuffer(base64.b64decode(link['qr'].split(',')[1]), np.uint8), 0)
            self.assertEqual(cv2.QRCodeDetector().detectAndDecode(image)[0], link['url'])
            for secret in ('fixture-green', 'fixture-purple', self.hub.config['secret']):
                self.assertNotIn(secret, link['url'])
            player = Client(self.hub.wsgi, Response)
            team = link['team']
            reply = self.join(player, team, self.token(link))
            self.assertEqual(reply.status_code, 200)
            self.assertEqual(reply.json['next'], f'/s/{team}/p/mobile-ltz/')
            self.assertEqual(player.get(reply.json['next']).status_code, 200)
            other = 'purple' if team == 'green' else 'green'
            self.assertEqual(player.get(f'/s/{other}/api/meta').status_code, 401)
            self.assertEqual(player.get('/s/gamemaster/api/meta').status_code, 401)
            self.assertIn('HttpOnly', reply.headers['Set-Cookie'])
            self.assertNotIn(self.token(link), reply.headers['Set-Cookie'])

    def test_invitation_management_requires_admin(self):
        outsider = Client(self.hub.wsgi, Response)
        self.assertEqual(outsider.get('/s/gamemaster/api/player-join').status_code, 401)
        outsider.post('/s/green/login', data={'password': 'fixture-green'})
        self.assertEqual(outsider.get('/s/green/api/player-join').status_code, 403)
        self.assertEqual(outsider.post('/s/green/api/player-join', json={}).status_code, 403)
        self.assertEqual(outsider.get('/s/gamemaster/api/player-join').status_code, 401)

    def test_rotation_expiry_tampering_and_team_swapping(self):
        links = self.links()['links']
        player = Client(self.hub.wsgi, Response)
        for invalid in (None, {}, [], 27, '', 'x' * 32, 'x' * 2000):
            self.assertIn(self.join(player, 'green', invalid).status_code, (400, 401))
        token = self.token(links[0])
        self.assertEqual(self.join(player, 'purple', token).status_code, 401)
        self.assertEqual(self.join(player, 'gamemaster', token).status_code, 401)
        self.assertEqual(self.join(player, 'green', token).status_code, 200)
        self.assertEqual(self.join(player, 'green', token).status_code, 200, 'reconnect is allowed')
        self.assertEqual(self.join(player, 'purple', self.token(links[1])).status_code, 200)
        self.assertEqual(player.get('/s/green/api/meta').status_code, 401, 'old team role is removed')
        self.assertEqual(player.get('/s/purple/api/meta').status_code, 200)
        new = self.links('post')
        self.assertEqual(self.join(player, 'green', token).status_code, 401)
        self.assertEqual(player.get('/s/purple/api/meta').status_code, 200, 'rotation leaves joined sessions working')
        with patch('hub.player_join.time.time', return_value=new['expires_at']):
            self.assertEqual(self.join(player, 'green', self.token(new['links'][0])).status_code, 401)
        self.assertFalse(PlayerJoinLinks().accepts('green', self.token(new['links'][0])), 'restart invalidates invites')

    def test_repeated_load_preserves_links_and_expired_load_refreshes(self):
        first = self.links()
        self.assertEqual(first, self.links())
        with patch('hub.player_join.time.time', return_value=first['expires_at'] + 1):
            fresh = self.links()
        self.assertNotEqual(first['links'][0]['url'], fresh['links'][0]['url'])
        self.assertEqual(fresh['expires_at'], first['expires_at'] + 1 + LIFETIME_SECONDS)

    def test_invalid_request_origin_and_redirect_do_not_grant_access(self):
        token = self.token(self.links()['links'][0])
        client = Client(self.hub.wsgi, Response)
        self.assertEqual(self.join(client, 'green', token, headers={'Origin': 'https://other.example'}).status_code, 403)
        self.assertEqual(client.post('/s/green/login/join', data={'token': token}).status_code, 403)
        self.assertEqual(self.gm.post('/s/gamemaster/api/player-join', json={}, headers={'Origin': 'https://other.example'}).status_code, 403)
        self.assertEqual(self.gm.post('/s/gamemaster/api/player-join', data={}).status_code, 403)
        response = client.post('/s/green/login/join?next=https://other.example', json={'token': token, 'team': 'gamemaster'})
        self.assertEqual(response.json['next'], '/s/green/p/mobile-ltz/')
        self.assertEqual(client.get('/s/gamemaster/api/meta').status_code, 401)

    def test_disabled_missing_or_admin_player_is_unavailable(self):
        token = self.token(self.links()['links'][0])
        player = Client(self.hub.wsgi, Response)
        self.hub.sandboxes['green']._disabled.add('mobile-ltz')
        self.assertEqual(self.join(player, 'green', token).status_code, 503)
        self.assertIsNone(player.get_cookie(COOKIE_NAME))
        with patch.object(self.hub.sandboxes['gamemaster'].app.logger, 'exception'):
            self.assertEqual(self.gm.get('/s/gamemaster/api/player-join').status_code, 503)
        self.hub.sandboxes['green']._disabled.clear()
        self.hub.sandboxes['green'].cfg['admin'] = True
        self.assertFalse(self.hub.mobile_player_available('green'))
        del self.hub.sandboxes['purple']._modules['mobile-ltz']
        self.assertFalse(self.hub.mobile_player_available('purple'))

    def test_password_login_and_logout_still_work(self):
        player = Client(self.hub.wsgi, Response)
        reply = player.post('/s/green/login?next=/s/green/p/mobile-ltz/', data={'password': 'fixture-green'})
        self.assertEqual(reply.status_code, 302)
        self.assertEqual(reply.location, '/s/green/p/mobile-ltz/')
        self.assertEqual(player.get(reply.location).status_code, 200)
        player.get('/s/green/logout')
        self.assertEqual(player.get('/s/green/api/meta').status_code, 401)


class OriginTests(unittest.TestCase):
    def test_network_addresses(self):
        lan = 'http://192.168.1.50:8000'
        for local in ('http://localhost:8000', 'http://127.0.0.1:8000', 'http://[::1]:8000', 'http://0.0.0.0:8000'):
            self.assertEqual(network_origin(local, lan), lan)
        self.assertEqual(network_origin('https://game.example', lan), 'https://game.example')
        self.assertEqual(network_origin('http://localhost', lan, 'https://game.example/'), 'https://game.example')
        for bad in ('file:///tmp/a', 'https://user:pass@game.example', 'http://localhost', 'https://game.example/x', 'https://game.example/?secret=1', 'https://game.example:bad', ''):
            with self.assertRaises(ValueError):
                network_origin(lan, lan, bad)
        with self.assertRaises(ValueError):
            network_origin('http://localhost', 'http://localhost:8000')


if __name__ == '__main__':
    unittest.main()
