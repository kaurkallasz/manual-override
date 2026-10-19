"""Hardware-free MCAM1 boundary, lifecycle and stale-frame smoke tests."""
import time
import unittest
from unittest import mock
from flask import Flask
from test_photon_framework import load


class MCAM1Tests(unittest.TestCase):
    def setUp(self):
        self.module = load('mcam1')
        app = Flask(__name__)
        app.register_blueprint(self.module.bp)
        self.client = app.test_client()
        self.module._capture = self.module.Capture()
        self.module._controls = mock.Mock()

    def tearDown(self):
        self.module._capture.stop()

    def test_import_and_page_do_not_open_any_camera(self):
        with mock.patch('subprocess.Popen') as opened:
            with self.client.get('/') as response:
                self.assertEqual(response.status_code, 200)
            self.assertEqual(self.client.get('/api/still').status_code, 503)
            opened.assert_not_called()

    def test_unknown_camera_mode_never_starts_hardware(self):
        for mode in ('1920,1080,30', None, [], True):
            with self.subTest(mode=mode), mock.patch('subprocess.Popen') as opened:
                response = self.client.post('/api/capture',json={'action':'start','mode':mode})
                self.assertEqual(response.status_code, 400)
                opened.assert_not_called()

    def test_missing_identified_xiao_does_not_open_fallback_camera(self):
        self.module._controls.available_port.side_effect = RuntimeError('XIAO missing')
        with mock.patch.object(self.module._capture,'start') as start:
            response=self.client.post('/api/capture',json={'action':'start'})
            self.assertEqual(response.status_code,503)
            start.assert_not_called()

    def test_stale_frames_cannot_be_downloaded_or_shown(self):
        c=self.module._capture
        c.process=mock.Mock(); c.process.poll.return_value=None
        c.image=b'\xff\xd8fixture\xff\xd9'; c.stamp=time.time(); c.sequence=4
        self.assertEqual(self.client.get('/api/still').status_code,200)
        c.stamp=time.time()-2
        result=self.client.get('/api/frame')
        self.assertEqual(result.status_code,503)
        self.assertEqual(result.json['width'],0)
        self.assertIsNone(c.snapshot(True)['preview'])
        self.assertIsNone(c.still()['image'])
        c.process=None

    def test_stop_clears_frames_and_terminates_owned_process(self):
        c=self.module._capture
        process=mock.Mock();process.poll.return_value=None
        c.process=process;c.image=b'old';c.stamp=time.time()
        c.stop()
        process.terminate.assert_called_once()
        self.assertIsNone(c.image)
        self.assertFalse(c.snapshot()['running'])

    def test_cross_origin_commands_rejected(self):
        for endpoint in ('controls','ai','capture','disconnect'):
            result=self.client.post('/api/'+endpoint,json={},headers={'Origin':'https://outside.test'})
            self.assertEqual(result.status_code,403)
        self.module._controls.request.assert_not_called()

    def test_untrusted_commands_rejected_before_serial_write(self):
        controls=self.module.XiaoControls()
        for action,name,value in [('flash',None,None),('set','brightness',True),('set','quality',7),('set','hmirror',2),('set','aec', '1')]:
            with self.subTest(action=action,name=name,value=value), mock.patch.object(controls,'_exchange') as exchange:
                with self.assertRaises(ValueError): controls.request(action,name,value)
                exchange.assert_not_called()

    def test_control_transport_failure_reported_as_unavailable(self):
        self.module._controls.request.side_effect=RuntimeError('USB disconnected')
        result=self.client.post('/api/controls',json={'action':'get'})
        self.assertEqual(result.status_code,503)
        self.assertEqual(result.json['status'],'unavailable')

    def test_cached_ai_age_increases_and_stale_boxes_disappear(self):
        self.module._ai_data=dict(transport_status='ready',received_at=time.time()-2,age_ms=50,
                                 settings={'stale_ms':700},boxes=[{'x':1}],status='ready',state='ready')
        data=self.module._snapshot()['ai']
        self.assertGreater(data['age_ms'],2000)
        self.assertEqual(data['boxes'],[])
        self.assertEqual(data['status'],'unavailable')
        self.assertEqual(self.module._ai_data['boxes'],[{'x':1}])


if __name__=='__main__': unittest.main()
