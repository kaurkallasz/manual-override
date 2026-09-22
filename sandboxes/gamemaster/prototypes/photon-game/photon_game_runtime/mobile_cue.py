"""Game-owned virtual pick/place sequence using MobileArm's existing motion path."""
import math


class MobileCue:
    def __init__(self):
        self.rows = []
        self.index = 0
        self.status = 'idle'
        self.stage = ''
        self.error = ''
        self.steps = []
        self.step_index = 0
        self.goal = None
        self.height = 80.0
        self.waypoint = None
        self.waypoint_goal = None

    @property
    def busy(self):
        return self.status in ('running', 'paused')

    def snapshot(self):
        return {'rows': [dict(row) for row in self.rows], 'index': self.index,
                'status': self.status, 'stage': self.stage, 'error': self.error,
                'waypoint': dict(self.waypoint) if self.waypoint else None}

    def stop(self, arm):
        arm.targets = list(arm.joints)
        self.status = 'stopped' if self.rows else 'idle'
        self.stage = self.error = ''
        self.waypoint = self.waypoint_goal = None
        self.steps = []
        self.goal = None

    def validate_rows(self, rows, arm, engine):
        if not isinstance(rows, list) or not 1 <= len(rows) <= 32:
            raise ValueError('Add between 1 and 32 cue rows.')
        destinations = {m['id'] for m in arm.markers(engine)}
        clean = []
        for i, row in enumerate(rows):
            if not isinstance(row, dict) or set(row) != {'piece', 'destination'} or any(type(v) is not int for v in row.values()):
                raise ValueError(f'Row {i+1}: select a piece and destination code.')
            if row['piece'] not in arm.tags or engine.atom_owners.get(row['piece']) != 'green':
                raise ValueError(f'Row {i+1}: piece is unavailable or belongs to another team.')
            if row['destination'] not in destinations:
                raise ValueError(f'Row {i+1}: destination marker is unavailable.')
            clean.append(dict(row))
        return clean

    def set_rows(self, rows, arm, engine):
        if self.status == 'running':
            raise ValueError('Pause or stop before editing cue rows.')
        clean = self.validate_rows(rows, arm, engine)
        self.stop(arm)
        self.rows, self.index, self.status = clean, 0, 'idle'

    def play(self, arm, engine, height):
        if self.status == 'running':
            return
        self.validate_rows(self.rows, arm, engine)
        if self.status == 'paused':
            self.status = 'running'
            if self.waypoint_goal is not None:
                arm.targets = list(self.waypoint_goal)
            elif self.goal is not None:
                arm.targets = list(self.goal)
            else:
                self.advance(arm, engine)
            return
        if type(height) not in (float, int) or not math.isfinite(height) or not 0 <= height <= 400:
            raise ValueError('Choose a travel height from 0 to 400.')
        self.height = max(80.0, float(height))
        if self.status != 'error':
            self.index = 0
        if self.waypoint is not None:
            self.waypoint['z'] = self.height
            self.waypoint_goal = arm.solve_xyz(self.waypoint)
        self.status, self.error = 'running', ''
        self.steps, self.goal = [], None
        self.advance(arm, engine)

    def pause(self, arm):
        if self.status == 'running':
            self.status = 'paused'
            arm.targets = list(arm.joints)

    def insert_waypoint(self, point, arm, engine):
        self.validate_rows(self.rows, arm, engine)
        if not isinstance(point, dict) or set(point) != {'x', 'y'}:
            raise ValueError('Waypoint requires X and Y map coordinates.')
        waypoint = {**point, 'z': self.height}
        goal = arm.solve_xyz(waypoint)
        self.waypoint, self.waypoint_goal = waypoint, goal
        if self.status == 'running':
            arm.targets = list(goal)
            self.stage = 'Waypoint'
        elif self.status not in ('paused', 'error'):
            self.index = 0
        arm.message = 'Blue waypoint inserted before the cue target.'

    def cancel_waypoint(self, arm):
        if self.waypoint is None:
            return
        self.waypoint = self.waypoint_goal = None
        if self.status == 'running':
            arm.targets = list(self.goal) if self.goal is not None else list(arm.joints)
        if self.steps:
            self.stage = self.steps[self.step_index][0]
        else:
            self.stage = ''

    def plan_row(self, arm, engine):
        row = self.rows[self.index]
        source = arm.tags[row['piece']]
        marker = next(m for m in arm.markers(engine) if m['id'] == row['destination'])
        if arm.held is not None and arm.held != row['piece']:
            raise ValueError(f'Release held piece {arm.held} before moving piece {row["piece"]}.')
        def at(point, z):
            return {'x': point['x'], 'y': point['y'], 'z': z}
        # Resolve every pose before this row starts. No timer can fake arrival.
        steps = [] if arm.held is not None else [
            ('Approach', at(source, self.height), None),
            ('Lower to pick', at(source, 60), None),
            ('Pick up', at(source, 60), 'suction'),
        ]
        steps += [('Lift', at(source, self.height), None),
                  ('Move', at(marker, self.height), None),
                  ('Lower to place', at(marker, 60), None),
                  ('Release', at(marker, 60), 'blow'),
                  ('Lift clear', at(marker, self.height), None)]
        self.steps = [(label, arm.solve_xyz(point), pump) for label, point, pump in steps]
        self.step_index = 0

    def advance(self, arm, engine):
        if self.status != 'running':
            return
        try:
            self.validate_rows([self.rows[self.index]], arm, engine)
            if not self.steps:
                self.plan_row(arm, engine)
            if self.waypoint is not None:
                self.stage = 'Waypoint'
                arm.targets = list(self.waypoint_goal)
                if any(abs(a-b) > .001 for a, b in zip(arm.joints, self.waypoint_goal)):
                    return
                # Reaching blue never executes pickup/release or advances a row.
                self.cancel_waypoint(arm)
                return
            if self.goal is not None and any(abs(a-b) > .001 for a, b in zip(arm.joints, self.goal)):
                return
            if self.goal is not None:
                _, _, pump = self.steps[self.step_index]
                if pump:
                    row = self.rows[self.index]
                    arm.set_pump(pump, engine, piece=row['piece'], destination=row['destination'])
                self.step_index += 1
                self.goal = None
            if self.step_index >= len(self.steps):
                self.index += 1
                self.steps = []
                if self.index >= len(self.rows):
                    self.index = len(self.rows)-1
                    self.status, self.stage = 'completed', 'Complete'
                    arm.message = 'Cue complete.'
                    return
                self.plan_row(arm, engine)
            self.stage, goal, _ = self.steps[self.step_index]
            self.goal = list(goal)
            arm.targets = list(goal)
            row = self.rows[self.index]
            arm.message = f'{row["piece"]} → {row["destination"]} · {self.stage}'
        except (ValueError, PermissionError, KeyError, StopIteration) as exc:
            arm.targets = list(arm.joints)
            self.status = 'error'
            self.error = f'Row {self.index+1}: {exc or "marker unavailable"}'
            self.steps, self.goal = [], None
            self.waypoint = self.waypoint_goal = None
            arm.message = self.error
