"""Atom false-positive regressions. Synthetic frames only; never open hardware."""
import unittest
from unittest import mock

import cv2
import numpy as np

from test_photon_framework import load


class ScreenDetectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.webcam = load('webcam')
        cls.dictionary = cv2.aruco.extendDictionary(6, 3)

    def frame(self, marker, width=80, height=80, blur=0):
        image = np.full((220, 520), 255, np.uint8)
        tag = cv2.resize(marker, (width, height), interpolation=cv2.INTER_NEAREST)
        image[60:60+height, 50:50+width] = tag
        if blur:
            image = cv2.GaussianBlur(image, (blur, blur), 0)
        return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)

    def test_all_real_atom_codes_survive_rotation_blur_and_moderate_tilt(self):
        for mid in range(6):
            marker = cv2.aruco.generateImageMarker(self.dictionary, mid, 100)
            for rotation in range(4):
                for width, height, blur in ((80, 80, 0), (60, 40, 3), (32, 32, 3)):
                    with self.subTest(id=mid, rotation=rotation, size=(width,height), blur=blur):
                        frame = self.frame(np.rot90(marker, rotation), width, height, blur)
                        detected = self.webcam._detect(frame, 520, 220)
                        self.assertIn(100 + mid, detected)

    def test_long_rectangles_accepted_by_legacy_detector_are_rejected(self):
        legacy = cv2.aruco.ArucoDetector(self.dictionary)
        for mid in range(6):
            marker = cv2.aruco.generateImageMarker(self.dictionary, mid, 100)
            frame = self.frame(marker, 400, 100)
            _, old_ids, _ = legacy.detectMarkers(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
            self.assertIn(mid, old_ids.flatten().tolist(), 'fixture must reproduce the old acceptance')
            self.assertNotIn(100 + mid, self.webcam._detect(frame, 520, 220))

    def test_printed_table_codes_are_unchanged(self):
        dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_100)
        for mid in [38, *range(40,56)]:
            marker = cv2.aruco.generateImageMarker(dictionary, mid, 100)
            for size in (32, 80):
                frame = self.frame(marker, size, size)
                tags = self.webcam._detect(frame, 520, 220)
                self.assertEqual(set(tags), {mid})

    def test_cross_dictionary_overlap_and_duplicate_screen_ids_fail_closed(self):
        a = np.array([[[10,10],[50,10],[50,50],[10,50]]], np.float32)
        b = a + [80,0]
        dets = {40: {'corners': a.reshape(4,2)}}
        self.webcam._collect_screens(dets, [a], np.array([[0]]), 1, 200, 100)
        self.assertEqual(set(dets), {40})
        dets = {}
        self.webcam._collect_screens(dets, [a,b], np.array([[0],[0]]), 1, 200, 100)
        self.assertEqual(dets, {})

    def detection(self, mid=100, x=100, side=40):
        return {mid: {'x':x,'y':100,'nx':x/500,'ny':.5,'rot':0,
                      'corners':np.array([[x-20,80],[x-20+side,80],
                                          [x-20+side,80+side],[x-20,80+side]], np.float32)}}

    def test_short_spatially_inconsistent_and_missing_reads_never_publish(self):
        gate = self.webcam.ScreenConfirmation()
        for time, x in ((1,100),(1.1,100),(1.2,100),(1.31,100)):
            result = gate.update(self.detection(x=x),time)
        self.assertIn(100,result)
        self.assertEqual(gate.update({},1.4),{})
        self.assertEqual(gate.update(self.detection(),1.5),{})
        for index in range(20):
            self.assertEqual(gate.update(self.detection(x=100+200*(index%2)),2+index*.1),{})
        gate.reset()
        for index in range(3):
            self.assertEqual(gate.update(self.detection(),10+index*.01),{})
        self.assertEqual(gate.update(self.detection(),11),{})
        # Printed table tags bypass only this additional screen gate.
        self.assertIn(40,gate.update(self.detection(40),11.1))

    def test_confirmed_moving_atom_and_geometry_changes(self):
        gate = self.webcam.ScreenConfirmation()
        for n in range(6):
            result = gate.update(self.detection(x=100+n*3),1+n*.11)
            self.assertEqual(100 in result, n>=3)
        self.assertEqual(gate.update(self.detection(x=118,side=80),1.7),{})
        gate.reset()
        self.assertEqual(gate.update(self.detection(),2),{})

    def test_immediate_public_snapshot_uses_the_confirmation_gate(self):
        manager = self.webcam.CameraManager()
        frame = np.zeros((200,500,3),np.uint8)
        manager._detection_fps_limit = 10
        with mock.patch.object(self.webcam,'_detect',return_value=self.detection()), \
                mock.patch.object(self.webcam.time,'monotonic') as clock:
            clock.return_value=10
            manager._process_frame(frame)
            self.assertEqual(manager.detection_snapshot(10),([],[]))
            for stamp in (10.11,10.22,10.33):
                clock.return_value=stamp
                manager._process_frame(frame)
            rows, visible = manager.detection_snapshot(10.33)
            self.assertEqual(visible,[100])
            self.assertEqual([row['id'] for row in rows],[100])
            # A missing frame removes current visibility, even though position history is held.
            with mock.patch.object(self.webcam,'_detect',return_value={}):
                clock.return_value=10.44
                manager._process_frame(frame)
                self.assertEqual(manager.detection_snapshot(10.44)[1],[])


if __name__ == '__main__':
    unittest.main()
