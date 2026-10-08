"""Read-only J4 diagnosis and telemetry; no robot connection or motion."""
import struct
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from test_photon_framework import load


class RelayRotationDiagnosticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.relay = load('dobot-mg400-relay')
        import relay_arm
        cls.driver = relay_arm

    def test_specific_j4_alarms_and_safety_priority(self):
        classify = self.driver.classify_alarm_ids
        self.assertEqual(classify([70]), ('joint4_positive_limit', 'Joint 4 positive rotation limit'))
        self.assertEqual(classify([71]), ('joint4_negative_limit', 'Joint 4 negative rotation limit'))
        for ids, kind in [([17], 'workspace_limit'), ([85, 70], 'emergency_lock'),
                          ([112, 71], 'collision'), ([999], 'controller_fault'),
                          ([], 'unknown_fault')]:
            with self.subTest(ids=ids):
                self.assertEqual(classify(ids)[0], kind)

    def test_packet_keeps_complete_j4_turns_separate_from_tcp_rotation(self):
        driver = self.driver
        packet = bytearray(driver.FEEDBACK_SIZE)
        struct.pack_into('<Q', packet, driver.OFF_TEST_VALUE, driver.FEEDBACK_MAGIC)
        struct.pack_into('<Q', packet, driver.OFF_ROBOT_MODE, 9)
        struct.pack_into('<6d', packet, driver.OFF_Q_ACTUAL, 90, 19, 59, 1577.5, 0, 0)
        struct.pack_into('<6d', packet, driver.OFF_TOOL_VECTOR_ACTUAL, 250, 10, 60, 47.5, 0, 0)
        parsed = driver.parse_feedback(packet)
        self.assertEqual(parsed['joints'][3], 1577.5)
        self.assertEqual(parsed['pose'][3], 47.5)

    def test_state_api_carries_per_arm_freshness_without_querying_hardware(self):
        def robot(angle, stamp, alarms):
            state = dict(self.relay.DobotMG400._blank_state(), connected=True,
                         feedback_ok=True, last_feedback=stamp, joints=[0, 0, 0, angle],
                         error=bool(alarms), alarm_ids=alarms)
            state['fault_kind'], state['fault_label'] = self.driver.classify_alarm_ids(alarms)
            return SimpleNamespace(get_state=lambda: state, get_target=lambda: None)
        robots = {'purple': robot(1577.5, 99.9, [70]), 'green': robot(-250, 90, [])}
        with patch.object(self.relay, '_arm', side_effect=robots.get), patch.object(self.relay.time, 'time', return_value=100):
            state = self.relay._state_dict()
        self.assertAlmostEqual(state['arms']['purple']['feedback_age'], .1)
        self.assertTrue(state['arms']['purple']['feedback_ok'])
        self.assertEqual(state['arms']['purple']['fault_kind'], 'joint4_positive_limit')
        self.assertEqual(state['arms']['purple']['joints'][3], 1577.5)
        self.assertEqual(state['arms']['green']['feedback_age'], 10)

    def test_missing_or_invalid_feedback_cannot_supply_a_fresh_age(self):
        state = self.relay.DobotMG400._blank_state()
        robot = SimpleNamespace(get_state=lambda: state, get_target=lambda: None)
        with patch.object(self.relay, '_arm', return_value=robot), patch.object(self.relay.time, 'time', return_value=100):
            for stamp in (None, 0, -1, True, '99', float('nan'), float('inf'), 101):
                with self.subTest(stamp=stamp):
                    state['last_feedback'] = stamp
                    self.assertIsNone(self.relay._arm_dict('green')['feedback_age'])
        with patch.object(self.relay, '_arm', return_value=None):
            offline = self.relay._arm_dict('purple')
        self.assertFalse(offline['connected'])
        self.assertFalse(offline['feedback_ok'])
        self.assertIsNone(offline['feedback_age'])


if __name__ == '__main__':
    unittest.main()
