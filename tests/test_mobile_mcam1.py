"""Optional MCAM1 player preview: contract, freshness, isolation and auth."""
import copy
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from test_photon_framework import FakeContext, Flask, load


class MobileMcam1Tests(unittest.TestCase):
    def setUp(self):
        self.facade = load('mobile-ltz-api')
        self.frame = dict(contract='hhh.camera.still', version=1, status='ready',
                          width=480, height=320, captured_at=time.time(), mime_type='image/jpeg',
                          image=b'\xff\xd8fixture\xff\xd9')
        self.camera = SimpleNamespace(still_snapshot=Mock(side_effect=lambda:dict(self.frame)))
        self.context = FakeContext({'mcam1':self.camera})
        self.facade.hub_init(self.context)
        self.addCleanup(self.facade.hub_stop)
        app = Flask(__name__)
        app.register_blueprint(self.facade.bp)
        self.client = app.test_client()

    def get(self, path='assets/mcam1.jpg', side='green', role=None):
        return self.client.get('/api/'+path+'?side='+side, environ_overrides={'hhh.roles':{role or side}})

    def test_green_receives_read_only_uncached_frames(self):
        response = self.get(side='green')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, self.frame['image'])
        self.assertEqual(response.mimetype, 'image/jpeg')
        self.assertIn('no-store', response.headers['Cache-Control'])
        self.assertEqual(self.get(side='purple', role='green').status_code, 403)
        self.assertEqual(self.client.get('/api/assets/mcam1.jpg').status_code, 403)
        self.assertEqual(self.client.post('/api/assets/mcam1.jpg').status_code, 405)
        self.assertEqual(self.camera.still_snapshot.call_count, 1)

    def test_purple_waits_for_mcam2_without_reading_mcam1(self):
        self.context.get_prototype = Mock(side_effect=AssertionError('Purple must not read MCAM1'))
        for role in ('purple', 'gamemaster'):
            response = self.get(side='purple', role=role)
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json['status'], 'unavailable')
            self.assertIn('MCAM2', response.json['error'])
        with patch.object(self.facade, '_game', return_value=(None, dict(status='ready', virtual_play=True))):
            response = self.get('state', 'purple')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json['status'], 'ready')
            self.assertEqual(response.json['mobile_mcam1']['status'], 'unavailable')
        self.context.get_prototype.assert_not_called()
        self.camera.still_snapshot.assert_not_called()

    def test_enabled_check_precedes_discovery_and_does_not_block_game(self):
        self.context.is_prototype_enabled = lambda slug:False
        self.context.get_prototype = Mock(side_effect=AssertionError('Disabled owner must not be read'))
        self.assertEqual(self.get().status_code, 503)
        game = dict(status='ready', virtual_play=True)
        with patch.object(self.facade, '_game', side_effect=lambda:(None, copy.deepcopy(game))):
            for side in ('green', 'purple'):
                response = self.get('state', side)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json['status'], 'ready')
                self.assertEqual(response.json['mobile_mcam1']['status'], 'unavailable')
        self.context.get_prototype.assert_not_called()

    def test_ready_projection_contains_metadata_without_image_bytes(self):
        value, image = self.facade.mcam1_view.snapshot(self.facade._module, 'green')
        self.assertEqual((value['contract'], value['version'], value['status']), ('mobile.mcam1', 1, 'ready'))
        self.assertEqual((value['width'], value['height']), (480, 320))
        self.assertNotIn('image', value)
        self.assertEqual(image, self.frame['image'])

    def test_unavailable_stale_malformed_and_failed_owner_are_optional(self):
        original = dict(self.frame)
        cases = [('status','unavailable'), ('contract','wrong'), ('version',True), ('version',2),
                 ('captured_at',time.time()-2), ('captured_at',time.time()+3), ('captured_at',float('nan')),
                 ('captured_at',True), ('width',0), ('width',True), ('height',float('inf')),
                 ('image',None), ('image',b'broken'), ('mime_type','text/html')]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                self.frame = {**original, field:value}
                response = self.get()
                self.assertEqual(response.status_code, 503)
                self.assertEqual(response.json['status'], 'unavailable')
        self.camera.still_snapshot.side_effect = RuntimeError('Camera disconnected')
        self.assertEqual(self.get().json['status'], 'unavailable')
        self.camera.still_snapshot.side_effect = lambda:None
        self.assertEqual(self.get().json['status'], 'unavailable')
        self.context.modules.clear()
        self.assertEqual(self.get().json['status'], 'unavailable')


if __name__ == '__main__':
    unittest.main()
