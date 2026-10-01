"""Capture validation with fake poses, temporary files, and no robot lifecycle."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from test_photon_framework import load, Flask


class Cal2CaptureTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.module=load('auto-pickup-game')
        self.module.CALIBRATION2_PATH=str(Path(self.folder.name)/'cal2.json')
        self.module._calibration2=self.module._default_calibration2()
        self.module._calibration_access={side:{'enabled':True} for side in ('green','purple')}
        app=Flask('cal2-capture');app.register_blueprint(self.module.bp)
        self.client=app.test_client()
        self.pose={'set':True,'x':325.408,'y':-24.225,'z':-99,'r':0}
        self.module._calibration2['arms']['purple']['points']['p1']['pose']=dict(self.pose)

    def capture(self,side='purple',target='p2',pose=None,camera=None):
        return self.client.post('/api/calibration2/capture',json={
            'side':side,'target':target,'pose':pose or self.pose,
            'camera':camera or {'u':.4,'v':.3}},environ_overrides={'hhh.roles':{side}})

    def test_noise_at_the_same_robot_position_cannot_replace_a_different_point(self):
        before=copy.deepcopy(self.module._calibration2)
        response=self.capture(pose={**self.pose,'x':325.402,'y':-24.230})
        self.assertEqual(response.status_code,400)
        self.assertIn('Purple capture overlaps Point 1',response.json['error'])
        self.assertEqual(self.module._calibration2,before)
        self.assertFalse(Path(self.module.CALIBRATION2_PATH).exists())

    def test_distinct_pose_is_saved_and_other_team_is_preserved(self):
        green=copy.deepcopy(self.module._calibration2['arms']['green'])
        response=self.capture(pose={**self.pose,'x':186.293,'y':-191.167})
        self.assertEqual(response.status_code,200,response.json)
        saved=json.loads(Path(self.module.CALIBRATION2_PATH).read_text())
        self.assertEqual(saved['arms']['purple']['points']['p2']['pose']['x'],186.293)
        self.assertEqual(saved['arms']['green'],green)

    def test_recapturing_one_point_and_other_team_does_not_compare_against_purple(self):
        self.assertEqual(self.capture(target='p1').status_code,200)
        self.assertEqual(self.capture(side='green').status_code,200)

    def test_nonfinite_and_out_of_image_camera_coordinates_are_not_saved(self):
        for camera in ({'u':float('nan'),'v':.3},{'u':-1,'v':.3},{'u':.4,'v':2}):
            self.assertEqual(self.capture(camera=camera).status_code,400)
        self.assertFalse(Path(self.module.CALIBRATION2_PATH).exists())


if __name__=='__main__':unittest.main()
