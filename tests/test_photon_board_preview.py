"""Corrected display pixels remain behind Board's versioned, freshness-checked API."""
import time
import unittest
from types import SimpleNamespace
from unittest import mock
from test_photon_framework import FakeContext, load


class BoardPreviewTests(unittest.TestCase):
    def setUp(self):
        self.board=load('photon-board')
        self.value={'contract':'hhh.camera-frame','version':1,'status':'ready',
                    'coordinate_space':'corrected-camera-normalized','frame_at':time.time(),
                    'width':3840,'height':2160,'jpeg':b'fixture-jpeg'}
        self.owner=SimpleNamespace(preview_frame=mock.Mock(side_effect=lambda:dict(self.value)))
        self.context=FakeContext({'camera-calibration':self.owner})
        self.board._hub_ctx=self.context

    def test_fresh_corrected_frame_passes_through_without_resizing_or_opening_hardware(self):
        result=self.board.preview_frame()
        self.assertEqual(result['contract'],'photon.board.preview')
        self.assertEqual(result['version'],1)
        self.assertEqual(result['status'],'ready')
        self.assertEqual((result['width'],result['height']),(3840,2160))
        self.assertIs(result['jpeg'],self.value['jpeg'])
        self.owner.preview_frame.assert_called_once_with()

    def test_missing_disabled_failed_malformed_or_stale_input_never_exposes_pixels(self):
        for change in ({'version':True},{'version':2},{'contract':'wrong'},
                       {'status':'unavailable'},{'coordinate_space':'raw'},
                       {'frame_at':time.time()-3},{'frame_at':time.time()+1},
                       {'frame_at':float('nan')},{'width':True},{'height':0},{'jpeg':None}):
            with self.subTest(change=change):
                value=dict(self.value,**change)
                with mock.patch.object(self.owner,'preview_frame',return_value=value):
                    result=self.board.preview_frame()
                self.assertEqual(result['status'],'unavailable')
                self.assertIsNone(result['jpeg'])
                self.assertEqual(result['width'],0)
        with mock.patch.object(self.owner,'preview_frame',side_effect=RuntimeError('camera failed')):
            self.assertIn('camera failed',self.board.preview_frame()['error'])
        self.context.modules.clear()
        self.assertEqual(self.board.preview_frame()['status'],'unavailable')

    def test_simulation_does_not_read_the_camera(self):
        self.board._simulation['enabled']=True
        self.assertEqual(self.board.preview_frame()['status'],'unavailable')
        self.owner.preview_frame.assert_not_called()


if __name__=='__main__':unittest.main()
