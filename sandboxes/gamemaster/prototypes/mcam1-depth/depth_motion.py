"""Measured feedback history. Never substitute commanded targets for positions."""
from collections import deque
import math
import numpy as np


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


class PoseHistory:
    def __init__(self):
        self.samples = deque(maxlen=240)
        self.epoch = None

    def clear(self):
        self.samples.clear()
        self.epoch = None

    def add(self, arm, now):
        stamp, pose, epoch = arm.get('feedback_at'), arm.get('pose'), arm.get('motion_epoch')
        reason = None
        if arm.get('connected') is not True:
            reason = 'disconnected; connect this arm or select the connected arm'
        elif not finite(stamp):
            reason = 'measured feedback timestamp is missing or invalid'
        elif now < stamp:
            reason = 'feedback timestamp is ahead of the observation clock'
        elif now-stamp > .25:
            reason = f'measured feedback is stale ({(now-stamp)*1000:.0f} ms old; maximum 250 ms)'
        elif arm.get('feedback_ok') is not True:
            reason = 'relay reports invalid measured feedback'
        elif (not isinstance(pose, (list, tuple)) or len(pose) != 4
              or not all(finite(v) for v in pose)):
            reason = 'measured arm position is missing or invalid'
        elif type(epoch) is not int:
            reason = 'motion generation is unavailable; reconnect this arm'
        if reason:
            self.clear()
            raise ValueError(reason)
        if epoch != self.epoch or (self.samples and stamp < self.samples[-1][0]):
            self.clear()
            self.epoch = epoch
        if not self.samples or stamp > self.samples[-1][0]:
            self.samples.append((stamp, np.array(pose, dtype=float)))
        return self.motion(arm)

    def at(self, stamp):
        """Interpolate only bracketed samples; never extrapolate through arrival."""
        for (ta, a), (tb, b) in zip(self.samples, list(self.samples)[1:]):
            if ta <= stamp <= tb and tb-ta <= .12:
                fraction = (stamp-ta)/(tb-ta)
                result = a + fraction*(b-a)
                result[3] = a[3] + fraction*((b[3]-a[3]+180) % 360-180)
                return result
        return None

    def motion(self, arm):
        speed, previous, angular = 0., None, 0.
        if len(self.samples) >= 2:
            t, p = self.samples[-1]
            ta, a = next(((ta, a) for ta, a in reversed(list(self.samples)[:-1]) if t-ta >= .08), self.samples[0])
            dt = t-ta
            if dt > 0:
                speed = float(np.linalg.norm(p[:3]-a[:3])/dt)
                angular = abs((p[3]-a[3]+180) % 360-180)/dt
            earlier = [(tb, b) for tb, b in self.samples if tb <= ta-.08]
            if earlier:
                tb, b = earlier[-1]
                previous = float(np.linalg.norm(a[:3]-b[:3])/(ta-tb))
        phase = ('stopped' if speed < .5 and angular < .5 else
                 'slowing' if previous is not None and speed < previous*.8 else 'moving')
        return dict(pose=list(map(float, self.samples[-1][1])), speed_mm_s=round(speed, 2),
                    angular_speed_deg_s=round(float(angular), 2), phase=phase,
                    pump_mode=arm.get('pump_mode', 'unknown'), epoch=self.epoch,
                    feedback_at=self.samples[-1][0])
