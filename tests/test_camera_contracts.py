"""Public camera boundaries, no capture device or physical robot commands."""
import time
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from test_photon_framework import load, FakeContext, Flask


class CameraContractTests(unittest.TestCase):
    def setUp(self):
        self.webcam = load('webcam')
        self.camera = load('camera-calibration')
        self.frame = np.zeros((8, 12, 3), dtype=np.uint8)
        self.calls = []
        self.owner = SimpleNamespace(
            camera_status_snapshot=lambda: {'contract':'hhh.webcam.camera','version':1,'status':'ready','camera':{'width':12,'height':8}},
            raw_frame_snapshot=lambda: {'contract':'hhh.webcam.frame','version':1,'status':'ready','frame_at':time.time(),'frame':self.frame.copy()},
            tag_snapshot=lambda: {'contract':'hhh.webcam.tags','version':1,'status':'ready','tags':[],'detections':[]},
            set_tag_transformer=self.transform,
            camera_command=self.command)
        self.context = FakeContext({'webcam':self.owner})
        with patch.object(self.camera,'_load_calibration'):
            self.camera.hub_init(self.context)
        self.addCleanup(self.camera.hub_stop)
        app = Flask('public-camera-contracts')
        app.register_blueprint(self.camera.bp)
        self.client = app.test_client()

    def transform(self, callback):
        self.calls.append(('transform',callback))
        return {'contract':'hhh.webcam.transformer','version':1,'status':'ready','registered':callback is not None}

    def command(self, value):
        self.calls.append(('command',value))
        return {'contract':'hhh.webcam.controls','version':1,'status':'ready','ok':True,'camera':{'index':2},'cameras':[]}

    def test_consumes_only_named_public_producer_and_unregisters_on_stop(self):
        self.assertEqual(self.camera._frame().shape,(8,12,3))
        self.assertEqual(self.client.get('/api/tags').status_code,200)
        self.assertEqual(self.client.get('/api/focus').status_code,200)
        self.assertEqual(self.client.get('/api/cameras').status_code,200)
        self.assertEqual(self.client.post('/api/camera',json={'index':2}).json['status'],{'index':2})
        self.camera.hub_stop()
        self.assertEqual(self.calls[-1],('transform',None))

    def test_disabled_stale_wrong_version_and_malformed_camera_are_unavailable(self):
        self.context.modules.clear()
        self.assertIsNone(self.camera._frame())
        self.assertEqual(self.client.get('/api/tags').status_code,503)
        self.context.modules['webcam']=self.owner
        for version,stamp in ((True,time.time()),(2,time.time()),(1,time.time()-2),(1,float('nan'))):
            self.owner.raw_frame_snapshot=lambda v=version,s=stamp: {'contract':'hhh.webcam.frame','version':v,'status':'ready','frame_at':s,'frame':self.frame}
            self.assertIsNone(self.camera._frame())
        self.owner.camera_status_snapshot=lambda: {'contract':'hhh.webcam.camera','version':1,'status':'ready','camera':{'width':'bad','height':8}}
        self.assertFalse(self.camera.corrected_tag_snapshot([],[])['corrected'])

    def test_raw_frame_copy_and_staleness_owned_by_webcam(self):
        manager=self.webcam._mgr
        with patch.object(manager,'_cap',object()),patch.object(manager,'_running',True),patch.object(manager,'_latest_raw',self.frame),patch.object(manager,'_latest_raw_at',time.time()):
            value=self.webcam.raw_frame_snapshot()
            self.assertEqual(value['status'],'ready')
            value['frame'][0,0,0]=255
            self.assertEqual(self.frame[0,0,0],0)
            with patch.object(manager,'_latest_raw_at',time.time()-2):
                self.assertIsNone(self.webcam.raw_frame_snapshot()['frame'])

    def test_owner_rejects_bad_selection_and_focus_without_touching_device(self):
        with patch.object(self.webcam._mgr,'open') as opened,patch.object(self.webcam._mgr,'set_focus_controls') as controls:
            for index in (True,2.5,-1,'2',None):
                with self.assertRaises(ValueError):self.webcam.camera_command({'action':'select','index':index})
            for value in ({'autofocus':'true'},{'exposure':float('nan')},{'focus':float('inf')}):
                with self.assertRaises(ValueError):self.webcam.camera_command({'action':'focus_set',**value})
            opened.assert_not_called();controls.assert_not_called()

    def test_selection_keeps_remembered_owned_capture_settings(self):
        remembered={'width':2560,'height':1440,'tracking_width':1920,'tracking_height':1080,'detection_fps':10}
        with patch.object(self.webcam,'_load_settings',return_value=remembered),patch.object(self.webcam._mgr,'open',return_value=(True,None)) as opened:
            self.assertTrue(self.webcam.camera_command({'action':'select','index':2})['ok'])
            opened.assert_called_once_with(2,2560,1440,1920,1080,10)

    def test_closed_camera_publishes_explicit_focus_failure(self):
        with patch.object(self.webcam._mgr,'set_focus_controls',return_value=(False,'no camera is open',None)):
            value=self.webcam.camera_command({'action':'focus_set','autofocus':False})
            self.assertEqual(value['status'],'unavailable')
            self.assertFalse(value['ok'])

    def test_atomic_camera_and_lens_writes_preserve_previous_file_on_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'saved.json';path.write_text('{"previous":true}')
            with patch.object(self.webcam,'SETTINGS_PATH',str(path)):
                with self.assertRaises(ValueError):self.webcam._write_settings({'focus':float('nan')})
                self.assertEqual(json.loads(path.read_text()),{'previous':True})
                self.webcam._write_settings({'focus':15})
                self.assertEqual(json.loads(path.read_text()),{'focus':15})
            lens={'camera_matrix':np.eye(3),'dist_coeffs':np.zeros(5),'image_size':[12,8],'rms':float('nan'),'samples':6}
            with patch.object(self.camera,'CALIBRATION_PATH',str(path)):
                with self.assertRaises(ValueError):self.camera._save_calibration(lens)
                self.assertEqual(json.loads(path.read_text()),{'focus':15})
                lens['rms']=.1;self.camera._save_calibration(lens)
                self.assertEqual(json.loads(path.read_text())['samples'],6)
            self.assertEqual([p.name for p in Path(folder).iterdir()],['saved.json'])

    def test_lens_persistence_failure_does_not_publish_new_calibration(self):
        previous={'previous':True}
        self.camera._calibration=previous
        self.camera._samples=[np.zeros((135,1,2),dtype=np.float32)]
        self.camera._image_size=(12,8)
        self.client.application.testing=True
        output=(.1,np.eye(3),np.zeros(5),[],[])
        with patch.object(self.camera.cv2,'calibrateCamera',return_value=output),patch.object(self.camera,'_save_calibration',side_effect=OSError('fixture disk failure')):
            with self.assertRaises(OSError):self.client.post('/api/calibrate')
        self.assertIs(self.camera._calibration,previous)

    def test_controller_events_share_preview_status_and_controls(self):
        with patch.object(self.camera, '_preview_jpeg', return_value=b'fixture-jpeg'), \
                patch.object(self.camera, '_status_dict', return_value={'camera_ready':True}):
            response = self.client.get('/api/events', buffered=False)
            self.assertEqual(response.mimetype, 'text/event-stream')
            event = json.loads(next(iter(response.response)).decode().removeprefix('data: '))
            response.close()
            self.assertEqual(event['preview'], 'data:image/jpeg;base64,Zml4dHVyZS1qcGVn')
            self.assertTrue(event['calibration']['camera_ready'])
            self.assertTrue(event['controls']['ok'])
            self.assertIn(('command', {'action':'focus_read'}), self.calls)


if __name__ == '__main__':unittest.main()
