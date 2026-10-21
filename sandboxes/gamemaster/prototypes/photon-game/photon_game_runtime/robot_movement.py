"""Bounded, read-only TCP trails. The simulation owns sampling and run lifetime."""
import copy
import math
from shared.playfield_registration import registration, project

SIDES = ('green', 'purple')
MAX_POINTS = 3000
MAX_SEGMENTS = 128


def finite(value):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError('Finite movement coordinate required')
    return float(value)


def contract(value, name):
    if (not isinstance(value, dict) or value.get('contract') != name
            or type(value.get('version')) is not int or value['version'] != 1
            or value.get('status') != 'ready'):
        raise ValueError((value or {}).get('error') if isinstance(value, dict) and value.get('error') else name+' unavailable')
    return value


def solve(matrix, rhs):
    rows = [list(row)+[v] for row, v in zip(matrix, rhs)]
    n = len(rows)
    for i in range(n):
        j = max(range(i, n), key=lambda k: abs(rows[k][i]))
        rows[i], rows[j] = rows[j], rows[i]
        d = rows[i][i]
        if abs(d) < 1e-10:
            raise ValueError('Calibration points do not span the field')
        rows[i] = [v/d for v in rows[i]]
        for j in range(n):
            if j != i:
                d = rows[j][i]
                rows[j] = [a-d*b for a, b in zip(rows[j], rows[i])]
    return [r[-1] for r in rows]


def dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def inverse(matrix, u, v):
    a,b,c,d,e,f,g,h = matrix
    return solve([[a-u*g,b-u*h],[d-v*g,e-v*h]], [u-c,v-f])


class FieldFrame:
    """Fit a measured table plane to six ground samples; XYZ stays metric.

    Robot bases may oppose each other. Their own measured basis determines the
    orientation, and positive height follows each robot's upward Z direction.
    """
    def __init__(self, calibration, matrix):
        samples = calibration.get('samples')
        if not isinstance(samples, list) or len(samples) != 6:
            raise ValueError('Six measured ground positions are required')
        rows, xyz = [], []
        for sample in samples:
            if not isinstance(sample, list) or len(sample) != 5:
                raise ValueError('Invalid measured ground position')
            u,v,x,y,z = map(finite, sample)
            rows.append([1, *inverse(matrix, u, v)])
            xyz.append([x,y,z])
        normal = [[sum(r[i]*r[j] for r in rows) for j in range(3)] for i in range(3)]
        coefficients = [solve(normal, [sum(r[i]*p[axis] for r,p in zip(rows,xyz)) for i in range(3)]) for axis in range(3)]
        self.origin, self.x, self.y = [[c[i] for c in coefficients] for i in range(3)]
        self.width, self.height = math.sqrt(dot(self.x,self.x)), math.sqrt(dot(self.y,self.y))
        if not all(100 <= size <= 5000 for size in (self.width,self.height)):
            raise ValueError('Calibrated field size is invalid')
        if abs(dot(self.x,self.y)/(self.width*self.height)) > .15:
            raise ValueError('Calibrated field axes are inconsistent')
        errors = [math.dist(p, [dot(r,c) for c in coefficients]) for r,p in zip(rows,xyz)]
        if max(errors) > 20:
            raise ValueError('Ground calibration does not fit the playfield (over 20 mm error)')
        x,y = self.x,self.y
        n = [x[1]*y[2]-x[2]*y[1], x[2]*y[0]-x[0]*y[2], x[0]*y[1]-x[1]*y[0]]
        size = math.sqrt(dot(n,n))
        self.up = [v/size*(1 if n[2] >= 0 else -1) for v in n]
        if self.up[2] < .9:
            raise ValueError('Calibrated surface is too steep')
        self.matrix = list(matrix)
        self.revision = calibration['revision']
        self.device = copy.deepcopy(calibration['device'])

    def position(self, pose):
        if not isinstance(pose, list) or len(pose) < 3:
            raise ValueError('Measured XYZ feedback unavailable')
        delta = [finite(pose[i])-self.origin[i] for i in range(3)]
        return solve([[self.x[i],self.y[i],self.up[i]] for i in range(3)], delta)


def distance_to_line(p, a, b):
    # Points contain [time, x, y, z]. Simplify space only, retaining timestamps.
    d = [b[i]-a[i] for i in (1,2,3)]
    v = [p[i]-a[i] for i in (1,2,3)]
    ratio = min(1, max(0, dot(v,d)/dot(d,d))) if dot(d,d) else 0
    return math.sqrt(sum((x-ratio*y)**2 for x,y in zip(v,d)))


def simplify(points, tolerance):
    if len(points) < 3:
        return points
    keep = {0,len(points)-1}
    stack = [(0,len(points)-1)]
    while stack:
        start,end = stack.pop()
        if end-start < 2:
            continue
        index = max(range(start+1,end), key=lambda i: distance_to_line(points[i],points[start],points[end]))
        if distance_to_line(points[index],points[start],points[end]) > tolerance:
            keep.add(index)
            stack.extend(((start,index),(index,end)))
    return [points[i] for i in sorted(keep)]


class RobotMovement:
    def __init__(self, level):
        self.layout = {'width':level.width,'height':level.height,'sockets':list(level.sockets.values()),'core':level.core}
        self.frames = {}
        self.last = {}
        self.field = None
        self.duration = 0.0
        self.arms = {s:{'segments':[],'error':'No movement feedback recorded','gaps':0,'simplified':False,'truncated':False} for s in SIDES}
        self.broken = {s:True for s in SIDES}
        self.tolerance = {s:1.0 for s in SIDES}

    def gap(self, reason, side=None):
        for s in ((side,) if side else SIDES):
            if (not self.broken[s] and self.arms[s]['segments']) or (not self.arms[s]['segments'] and not self.arms[s]['gaps'] and self.duration > .2):
                self.arms[s]['gaps'] += 1
            self.broken[s] = True
            self.arms[s]['error'] = str(reason)[:240]

    def observe(self, value, now, elapsed):
        self.duration = max(self.duration, finite(elapsed))
        try:
            relay = contract(value.get('relay'), 'hhh.relay.arms')
            calibration = contract(value.get('calibration'), 'hhh.cal2.movement')
            # Fresh marker observations register the field; never stale display memory.
            matrix, _ = registration(self.layout, value.get('camera'))
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            self.gap(value.get('error') or str(exc))
            return
        for side in SIDES:
            try:
                raw = relay.get('arms',{}).get(side,{})
                cal = calibration.get('arms',{}).get(side,{})
                if cal.get('status') != 'ready':
                    raise ValueError(cal.get('error') or 'Arm calibration unavailable')
                if not raw.get('connected') or raw.get('feedback_ok') is not True:
                    raise ValueError('Arm feedback unavailable')
                stamp = finite(raw.get('feedback_at'))
                if not -.25 <= now-stamp <= 1.5:
                    raise ValueError('Arm feedback is stale')
                if raw.get('device') != cal.get('device'):
                    raise ValueError('Arm connection differs from saved calibration')
                frame = self.frames.get(side)
                if frame and frame.revision != cal.get('revision'):
                    raise ValueError('Calibration changed during this level')
                if frame:
                    # Small detection jitter should not bend a previously frozen path.
                    corners = ((0,0),(1,0),(1,1),(0,1))
                    if max(math.dist(project(matrix,*p),project(frame.matrix,*p)) for p in corners) > .025:
                        raise ValueError('Camera or playfield moved during this level')
                else:
                    frame = FieldFrame(cal,matrix)
                    if self.field and max(abs(frame.width/self.field['width_mm']-1),abs(frame.height/self.field['height_mm']-1)) > .15:
                        raise ValueError('The two arm calibrations disagree on field scale')
                    if not self.field:
                        self.field = {'width_mm':round(frame.width,3),'height_mm':round(frame.height,3),
                                      'core':[self.layout['core']['x']/self.layout['width'],self.layout['core']['y']/self.layout['height']]}
                    self.frames[side] = frame
                u,v,z = frame.position(raw.get('pose'))
                if not -2 <= u <= 3 or not -2 <= v <= 3 or not -500 <= z <= 2000:
                    raise ValueError('Measured position is outside the recording bounds')
                last = self.last.get(side)
                epoch = raw.get('motion_epoch')
                if last and (stamp < last[0] or now-last[2] > 1.5 or stamp-last[0] > 1.5 or epoch != last[1]):
                    self.gap('Feedback interrupted',side)
                if last and stamp == last[0]:
                    continue
                point = [round(elapsed,3),round(u*self.field['width_mm'],2),round(v*self.field['height_mm'],2),round(z,2)]
                self.last[side] = (stamp,epoch,now)
                arm = self.arms[side]
                if self.broken[side]:
                    arm['segments'].append([])
                    self.broken[side] = False
                arm['segments'][-1].append(point)
                arm['error'] = None
                self._bound(side)
            except (KeyError,TypeError,ValueError,OverflowError) as exc:
                self.gap(str(exc),side)

    def _bound(self, side):
        arm = self.arms[side]
        if len(arm['segments']) > MAX_SEGMENTS:
            arm['segments'] = arm['segments'][-MAX_SEGMENTS:]
            arm['truncated'] = True
        # Collinear samples are only removed if interpolation also preserves time:
        # a pause at one location must not turn into slow motion across the field.
        segment = arm['segments'][-1]
        if len(segment) >= 3:
            a,p,b = segment[-3:]
            ratio = (p[0]-a[0])/(b[0]-a[0]) if b[0]>a[0] else 0
            expected = [a[i]+ratio*(b[i]-a[i]) for i in (1,2,3)]
            if math.dist(p[1:],expected) <= .25:
                segment.pop(-2)
        while sum(map(len,arm['segments'])) > MAX_POINTS:
            # Retain timed path shape within an increasing metric tolerance.
            # Split into <=2s blocks so long stationary intervals stay visible.
            tolerance = self.tolerance[side]
            reduced = []
            for points in arm['segments']:
                keep = [points[0]]
                block = [points[0]]
                for p in points[1:]:
                    block.append(p)
                    if p[0]-block[0][0] >= 2:
                        keep.extend(simplify(block,tolerance)[1:]);block=[p]
                keep.extend(simplify(block,tolerance)[1:])
                reduced.append(keep)
            before = sum(map(len,arm['segments']))
            arm['segments'] = reduced
            arm['simplified'] = True
            self.tolerance[side] *= 2
            if sum(map(len,reduced)) >= before:
                # Very long levels still have a hard bound. Keep alternating
                # interior samples with original timestamps and every gap.
                arm['segments'] = [p if len(p)<3 else [p[0],*p[1:-1:2],p[-1]] for p in reduced]

    def snapshot(self, duration=None):
        result = {'version':1,'units':'mm','height_basis':'Calibrated ground plane',
                  'duration_s':round(max(self.duration, duration or 0),3),'field':copy.deepcopy(self.field),'arms':copy.deepcopy(self.arms)}
        for arm in result['arms'].values():
            arm['status'] = 'partial' if arm['segments'] and (arm['error'] or arm['gaps'] or arm['truncated']) else 'ready' if arm['segments'] else 'unavailable'
        return result
