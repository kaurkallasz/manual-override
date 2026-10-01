"""Pure relay geometry tests: never acquire a robot or start a follower."""
import unittest
from test_photon_framework import load


class CartesianRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.relay = load('dobot-mg400-relay')

    def setUp(self):
        self.guard = dict(format='auto-pp-calibration-2-v1', radius_min=220,
                          radius_max=440, z_min=-150, z_max=230,
                          polygon=[[-450,-450],[450,-450],[450,450],[-450,450]])

    def check(self, start, target):
        return self.relay._validate_cal2_cartesian_path(start, target, self.guard)

    def test_small_measured_overshoot_can_only_retreat_into_the_field(self):
        for start, target in [([219,0,60],[225,0,60]), ([443,0,60],[430,0,60]),
                              ([300,0,231],[300,0,229])]:
            self.assertIsNone(self.check(start, target))
        self.assertIsNotNone(self.check([209,0,60],[250,0,60]))
        self.assertIsNotNone(self.check([219,0,60],[200,120,60]))
        self.assertIsNotNone(self.check([219,0,60],[-250,0,60]))

    def test_polygon_recovery_and_concave_crossing(self):
        self.guard['polygon'] = [[240,-120],[400,-120],[400,120],[350,120],
                                 [350,-40],[290,-40],[290,120],[240,120]]
        self.assertIsNone(self.check([237,0,60],[250,0,60]))
        self.assertIsNotNone(self.check([225,0,60],[250,0,60]))
        self.assertIsNotNone(self.check([260,60,60],[380,60,60]))
        self.assertIsNone(self.check([260,-50,60],[380,-50,60]))

    def test_safe_start_must_stay_inside_and_target_must_be_safe(self):
        self.assertIsNone(self.check([300,0,60],[310,10,60]))
        self.assertIsNotNone(self.check([300,0,60],[-300,0,60]))
        self.assertIsNotNone(self.check([300,0,60],[210,0,60]))
        self.assertIsNotNone(self.check([300,0,60],[441,0,60]))
        self.assertIsNotNone(self.check([300,0,60],[300,0,231]))

    def test_bad_calibration_or_feedback_never_grants_recovery(self):
        for start in [[float('nan'),0,60], [300,0], [300,0,float('inf')]]:
            self.assertIsNotNone(self.check(start,[300,0,60]))
        for value in [None, {}, dict(self.guard,polygon=[]), dict(self.guard,radius_min=450),
                      dict(self.guard,z_min=float('nan'))]:
            self.guard=value
            self.assertIsNotNone(self.check([300,0,60],[310,0,60]))


if __name__ == '__main__':
    unittest.main()
