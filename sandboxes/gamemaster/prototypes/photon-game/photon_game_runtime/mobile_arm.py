"""Bounded practice-only Green arm. No hardware imports or network access."""
import math
import re
import secrets
import time
from .mobile_cue import MobileCue


class MobileArm:
    LIMITS = ((-180, 180), (-180, 180), (-180, 180))
    # Virtual 10% profile: 10% of the project Dobot joint range (120 deg/s).
    # This is a simulation rate, not a calibrated physical-robot timing model.
    JOINT_SPEED_DEG_S = 12.0
    # Shared-host round trips can exceed two seconds. This lease is virtual only.
    LEASE_SECONDS = 5.0

    def __init__(self, level):
        self.cue = MobileCue()
        self.level = level
        self.width, self.height = level.width, level.height
        # This model is virtual only. Equal links and full rotations remove the
        # inner dead zone; size them for every map corner at every allowed Z.
        reach = 1.05 * math.sqrt((.925*self.width)**2 + (.9*self.height)**2 + (4*340)**2)
        self.lengths = (reach/2, reach/2)
        self.joints = [-80.0, -5.0, -5.0]
        radius = self.width * .72 * math.cos(math.radians(5))
        self.joints = self.solve_xyz({
            'x': min(self.width, .075*self.width + radius*math.cos(math.radians(10))),
            'y': max(0, .9*self.height - radius*math.sin(math.radians(10))),
            'z': max(0, 60 - .25*self.width*.72*math.sin(math.radians(5)))})
        self.targets = list(self.joints)
        self.unlocked_control = 1
        self.control_mode = 'joint'
        self.control_revision = 0
        self.token = None
        self.owner = None
        self.join_request = None
        self.controller_id = None
        self.suspended = False
        self.deadline = 0
        self.sequence = -1
        self.pump = 'off'
        self.held = None
        tip = self.pose()['tip']
        self.tags = {100: {'x': tip['x'], 'y': tip['y']},
                     101: {'x': tip['x'] - 80, 'y': tip['y'] - 65}}
        self.message = 'Connect to control the simulated Green arm.'

    def configure_pieces(self, codes):
        points = list(self.tags.values())
        self.halt('Piece codes changed. Connect to resume.')
        self.tags = {code: dict(point) for code, point in zip(codes, points)}
        self.cue.rows = []
        self.cue.stop(self)

    def markers(self, engine=None):
        level = engine.level if engine else self.level
        return [{'id': int(s['aruco_id']), 'x': s['x'], 'y': s['y'], 'kind': 'socket'} for s in level.sockets.values()] + [
            {'id': 38, 'x': level.core['x'], 'y': level.core['y'], 'kind': 'core'}]

    def pose(self, joints=None):
        joints = self.joints if joints is None else joints
        heading, shoulder, forearm = map(math.radians, (joints[0] + 90, *joints[1:]))
        base = {'x': self.width * .075, 'y': self.height * .90}
        lengths = self.lengths
        reach1, reach2 = lengths[0] * math.cos(shoulder), lengths[1] * math.cos(forearm)
        elbow = {'x': base['x'] + reach1 * math.cos(heading), 'y': base['y'] - reach1 * math.sin(heading)}
        tip = {'x': elbow['x'] + reach2 * math.cos(heading), 'y': elbow['y'] - reach2 * math.sin(heading),
               'z': 60 + .25 * (lengths[0] * math.sin(shoulder) + lengths[1] * math.sin(forearm))}
        return {'base': base, 'elbow': elbow, 'tip': tip}

    def select_control(self, mode):
        self.cue.stop(self)
        # Mode boundaries invalidate old motion, without releasing a held tag.
        self.targets = list(self.joints)
        self.control_mode = mode
        self.control_revision += 1

    def refresh_control_unlock(self, tier, *, default=False):
        # Previews cannot become movement modes. A manual choice lasts until the
        # next unlock change or fresh connection, not just the next heartbeat.
        if tier != self.unlocked_control or default:
            self.unlocked_control = tier
            mode = 'cue' if tier >= 4 else 'targeting' if tier >= 3 else 'xyz' if tier >= 2 else 'joint'
            if self.control_mode != mode:
                self.select_control(mode)

    def xyz_limits(self):
        return {'x': [0, self.width], 'y': [0, self.height], 'z': [0, 400]}

    def solve_xyz(self, point):
        """Invert the virtual arm's absolute shoulder/forearm angles, nearest branch."""
        if not isinstance(point, dict) or set(point) != {'x', 'y', 'z'}:
            raise ValueError('Three XYZ coordinates are required.')
        if any(type(point[k]) not in (int, float) or not math.isfinite(point[k]) or
               not lo - 1e-7 <= point[k] <= hi + 1e-7
               for k, (lo, hi) in self.xyz_limits().items()):
            raise ValueError('XYZ target outside configured limits.')
        dx, dy = point['x'] - self.width * .075, self.height * .90 - point['y']
        radius, vertical = math.hypot(dx, dy), (point['z'] - 60) * 4
        l1, l2 = self.lengths
        cosine = (radius**2 + vertical**2 - l1*l1 - l2*l2) / (2*l1*l2)
        if not -1 - 1e-9 <= cosine <= 1 + 1e-9:
            raise ValueError('XYZ target is unreachable. Bring the target closer to the red indicators.')
        if abs(abs(cosine) - 1) < 1e-12:
            cosine = math.copysign(1, cosine)
        delta = math.acos(max(-1, min(1, cosine)))
        candidates = []
        for sign in (1, -1):
            heading = math.degrees(math.atan2(dy * sign, dx * sign)) - 90
            for difference in (delta, -delta):
                shoulder = math.atan2(vertical, radius * sign) - math.atan2(l2 * math.sin(difference), l1 + l2 * math.cos(difference))
                for turn in (-360, 0, 360):
                    values = [heading + turn, (math.degrees(shoulder)+180)%360-180, (math.degrees(shoulder+difference)+180)%360-180]
                    if all(lo - 1e-7 <= v <= hi + 1e-7 for v, (lo, hi) in zip(values, self.LIMITS)):
                        candidates.append([max(lo, min(hi, v)) for v, (lo, hi) in zip(values, self.LIMITS)])
        if not candidates:
            raise ValueError('XYZ target is unreachable within the joint limits.')
        return min(candidates, key=lambda values: sum((a-b)**2 for a,b in zip(values,self.joints)))

    def halt(self, message='Stopped. Connect to resume.'):
        self.token = None
        self.owner = self.join_request = self.controller_id = None
        self.suspend(message)

    def suspend(self, message='Reconnecting to virtual controls…'):
        self.cue.stop(self)
        self.suspended = True
        self.targets = list(self.joints)
        self.pump = 'off'
        # A held virtual tag stays at its last location, never activates a tower.
        if self.held is not None:
            self.tags[self.held].update({k: self.pose()['tip'][k] for k in ('x', 'y')})
        self.held = None
        self.message = message

    def expire(self):
        if self.token and not self.suspended and time.monotonic() >= self.deadline:
            # Freeze movement on silence, but retain the private owner so the
            # same phone can reconnect without competing for its own session.
            self.suspend()

    def step(self, dt, engine):
        self.expire()
        if not engine.virtual_play or engine.paused or engine.phase not in ('setup', 'running'):
            if self.token:
                self.halt('Game paused or unavailable. Connect to resume.')
            return
        if not self.token or self.suspended:
            return
        self.cue.advance(self, engine)
        travel = self.JOINT_SPEED_DEG_S * dt
        for i in range(3):
            delta = self.targets[i] - self.joints[i]
            self.joints[i] += max(-travel, min(travel, delta))
        if self.held is not None:
            self.tags[self.held].update({k: self.pose()['tip'][k] for k in ('x', 'y')})

    def command(self, data, engine, saved_control=1):
        self.expire()
        action = data.get('action')
        if action in ('stop', 'disconnect'):
            if data.get('session') and data['session'] != self.token:
                raise ValueError('Obsolete controller stop.')
            self.halt()
            return self.snapshot()
        if not engine.virtual_play or engine.paused or engine.phase not in ('setup', 'running'):
            self.halt('Waiting for a virtual game.')
            raise ValueError('Green mobile control requires an unpaused virtual game.')
        unlocked = engine.virtual_test_control if engine.virtual_test_control is not None else saved_control
        if action == 'connect':
            owner, join_request = data.get('client_id'), data.get('request_id')
            if owner is not None or join_request is not None:
                if not all(isinstance(v,str) and re.fullmatch(r'[a-f0-9]{32}',v) for v in (owner,join_request)):
                    raise ValueError('Invalid virtual join identity.')
            abandoned = self.suspended and time.monotonic() >= self.deadline
            if self.token and (not owner or owner != self.owner) and not abandoned:
                raise ValueError('Green already has a controller. Stop it before reconnecting.')
            if self.token and join_request == self.join_request and not self.suspended:
                # An ambiguous join response may be retried; never issue a
                # second token or replay a movement as part of that retry.
                self.deadline = time.monotonic() + self.LEASE_SECONDS
                return {**self.snapshot(), 'session': self.token}
            self.suspend()
            self.token = secrets.token_urlsafe(32)
            self.owner, self.join_request = owner, join_request
            self.controller_id = secrets.token_hex(12)
            self.suspended = False
            self.sequence = -1
            self.deadline = time.monotonic() + self.LEASE_SECONDS
            self.targets = list(self.joints)
            self.refresh_control_unlock(unlocked, default=True)
            self.message = 'Lower the gripper over a Green tag, then tap Suction.'
            return {**self.snapshot(), 'session': self.token}
        token, sequence = data.get('session'), data.get('sequence')
        if not isinstance(token, str) or not self.token or not secrets.compare_digest(token, self.token):
            raise ValueError('Controller session expired. Connect again.')
        if action == 'suspend':
            self.suspend()
            return self.snapshot()
        if self.suspended:
            raise ValueError('Virtual control is suspended. Rejoin to resume.')
        if type(sequence) is not int or sequence <= self.sequence:
            raise ValueError('Stale controller command.')
        self.refresh_control_unlock(unlocked)
        if action in ('joints', 'xyz') and data.get('control_revision', self.control_revision) != self.control_revision:
            raise ValueError('Control mode changed. Wait for the current controls.')
        if action == 'control_mode':
            mode = data.get('mode')
            if mode not in ('joint', 'xyz', 'targeting', 'cue'):
                raise ValueError('This control is a preview and cannot move the arm.')
            if mode == 'xyz' and unlocked < 2:
                raise ValueError('Cartesian XYZ is locked. Ask Gamemaster to unlock it for this virtual test.')
            if mode == 'targeting' and unlocked < 3:
                raise ValueError('Targeting is locked. Ask Gamemaster to unlock it for this virtual test.')
            if mode == 'cue' and unlocked < 4:
                raise ValueError('Cue autonomy is locked. Ask Gamemaster to unlock it for this virtual test.')
            self.select_control(mode)
            self.message = 'Build a cue and press Play.' if mode == 'cue' else 'Drag the target to move. Use Height to raise or lower.' if mode == 'targeting' else 'Cartesian XYZ ready.' if mode == 'xyz' else 'Joint controls ready.'
        elif action in ('cue_set', 'cue_play', 'cue_pause', 'cue_stop', 'cue_waypoint', 'cue_cancel_waypoint'):
            if self.control_mode != 'cue' or unlocked < 4:
                raise ValueError('Select unlocked Cue autonomy first.')
            if type(data.get('control_revision')) is not int or data['control_revision'] != self.control_revision:
                raise ValueError('Control mode changed. Wait for the current controls.')
            if action == 'cue_set':
                self.cue.set_rows(data.get('rows'), self, engine)
            elif action == 'cue_play':
                self.cue.play(self, engine, data.get('height', 80))
            elif action == 'cue_waypoint':
                self.cue.insert_waypoint(data.get('point'), self, engine)
            elif action == 'cue_cancel_waypoint':
                self.cue.cancel_waypoint(self)
            elif action == 'cue_pause':
                self.cue.pause(self)
            else:
                self.cue.stop(self)
            if self.cue.status != 'running':
                self.message = self.cue.error or ('Cue paused.' if self.cue.status == 'paused' else 'Cue ready. Press Play to begin.')
        elif action == 'xyz':
            if self.control_mode not in ('xyz', 'targeting', 'cue') or unlocked < {'xyz': 2, 'targeting': 3, 'cue': 4}.get(self.control_mode, 4):
                raise ValueError('Select an unlocked Cartesian XYZ control first.')
            if type(data.get('control_revision')) is not int or data['control_revision'] != self.control_revision:
                raise ValueError('Control mode changed. Wait for the current controls.')
            if self.cue.busy:
                raise ValueError('Stop the cue before manual movement.')
            self.targets = self.solve_xyz(data.get('xyz'))
            self.message = 'Moving to XYZ target.'
        elif action == 'joints':
            if self.control_mode != 'joint':
                raise ValueError('Joint commands require Joint mode.')
            values = data.get('joints')
            if not isinstance(values, list) or len(values) != 3:
                raise ValueError('Three joint targets are required.')
            if any(type(v) not in (int, float) or not math.isfinite(v) or not lo <= v <= hi
                   for v, (lo, hi) in zip(values, self.LIMITS)):
                raise ValueError('Joint target outside configured limits.')
            self.targets = list(map(float, values))
        elif action == 'pump':
            if self.cue.busy:
                raise ValueError('Stop the cue before using the pump.')
            self.set_pump(data.get('mode'), engine)
        elif action != 'heartbeat':
            raise ValueError('Unsupported mobile control action.')
        self.sequence = sequence
        self.deadline = time.monotonic() + self.LEASE_SECONDS
        return self.snapshot()

    def set_pump(self, mode, engine, *, piece=None, destination=None):
        if mode not in ('suction', 'blow', 'off'):
            raise ValueError('Unknown pump action.')
        tip = self.pose()['tip']
        if mode == 'suction' and self.held is None:
            candidate = piece if piece is not None else min(self.tags, key=lambda tag: math.hypot(self.tags[tag]['x'] - tip['x'], self.tags[tag]['y'] - tip['y']))
            if candidate not in self.tags or engine.atom_owners.get(candidate) != 'green':
                raise ValueError('Movable piece is unavailable.')
            if tip['z'] > 80 or math.hypot(self.tags[candidate]['x'] - tip['x'], self.tags[candidate]['y'] - tip['y']) > 55:
                raise ValueError('Lower the gripper over a Green tag before suction.')
            self.held = candidate
            self.message = f'Tag {candidate} held. Move to a socket and lower to release.'
        if mode in ('blow', 'off') and self.held is not None:
            if tip['z'] > 80:
                raise ValueError('Lower the gripper before releasing the tag.')
            socket = next((s for s in engine.level.sockets.values() if s['aruco_id'] == destination), None) if destination is not None else min(engine.level.sockets.values(), key=lambda s: math.hypot(s['x']-tip['x'], s['y']-tip['y']))
            distance = math.hypot(socket['x']-tip['x'], socket['y']-tip['y']) if socket else math.inf
            core = engine.level.core
            if destination in (None, 38) and math.hypot(core['x']-tip['x'], core['y']-tip['y']) <= 55:
                engine.activate_core_tag(self.held, source='virtual', team='green')
                self.message = 'Green core tag confirmed. Waiting for the other team.'
            elif socket and distance <= max(45, float(socket.get('size', 112)) / 2):
                # place() owns all tower activation, loadout and field rules.
                sid = next(key for key, value in engine.level.sockets.items() if value is socket)
                engine.place(self.held, sid, source='virtual', team='green')
                self.message = f'Socket {sid} activated.'
            else:
                if destination is not None:
                    raise ValueError('Destination marker is unavailable or not reached.')
                if not (0 <= tip['x'] <= self.width and 0 <= tip['y'] <= self.height):
                    raise ValueError('Move over the battlefield before releasing the tag.')
                self.message = 'Tag released on the ground.'
            self.tags[self.held] = {k: tip[k] for k in ('x', 'y')}
            self.held = None
        self.pump = mode

    def snapshot(self):
        self.expire()
        return {'contract': 'photon.mobile-arm', 'version': 1, 'source': 'virtual', 'side': 'green',
                'connected': bool(self.token) and not self.suspended, 'suspended': self.suspended,
                'controller_id': self.controller_id, 'joints': list(self.joints), 'targets': list(self.targets),
                'limits': self.LIMITS, 'control_mode': self.control_mode,
                'control_revision': self.control_revision, 'xyz_limits': self.xyz_limits(),
                'xyz_target': self.pose(self.targets)['tip'], 'pump': self.pump, 'held_tag': self.held, 'message': self.message,
                'cue': self.cue.snapshot(), 'markers': self.markers(),
                'tags': [{'id': tag, **point} for tag, point in self.tags.items()], **self.pose()}
