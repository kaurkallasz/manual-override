"""Camera evidence for cues. Fixed coordinates are memory, never fresh sightings."""
import copy
import math
import uuid
from marker_quality import marker_geometry

ACQUIRE_MAX_AGE_S = .75
ACQUIRE_WINDOW_S = 1.5
ACQUIRE_MIN_SPAN_S = .5
ACQUIRE_MIN_SAMPLES = 3
ACQUIRE_TOLERANCE = .004
MARKER_SIZE_RATIO = 1.15
ANCHOR_MIN_COUNT = 4
ANCHOR_MIN_AREA = .02
ANCHOR_MIN_SPAN = .15


def _cross(a, b, c):
    return (b[0]-a[0])*(c[1]-a[1]) - (b[1]-a[1])*(c[0]-a[0])


def _anchor_hull(points):
    """Convex coverage of independent reference points, not a fitted new map."""
    points = sorted(set(points))
    halves = []
    for ordered in (points, reversed(points)):
        half = []
        for p in ordered:
            while len(half) >= 2 and _cross(half[-2], half[-1], p) <= 0:
                half.pop()
            half.append(p)
        halves.append(half[:-1])
    return halves[0] + halves[1]


class CueTargets:
    def __init__(self, fixed_ids=None):
        self.fixed_ids = frozenset(range(30, 60) if fixed_ids is None else fixed_ids)
        self.scope = None
        self.epoch = uuid.uuid4().hex
        self.epoch_reason = 'initialized'
        self.epoch_marker_id = None
        self.pending_fixed = {}
        self.pending_reasons = {}
        self.verification = None
        self.records = {}
        self.frame_at = None
        self.sampled_at = None
        self.ready = False

    def update(self, runtime, now):
        self.sampled_at = now
        frame = runtime.get('frame_at')
        self.ready = (runtime.get('status') == 'ready' and runtime.get('source') == 'camera'
                      and runtime.get('corrected') is True and type(frame) in (int, float)
                      and math.isfinite(frame) and 0 <= now-frame <= 1.5
                      and bool(runtime.get('camera_identity')) and bool(runtime.get('camera_revision'))
                      and all(type(runtime.get(k)) in (int, float) and math.isfinite(runtime[k])
                              and runtime[k] > 0 for k in ('width', 'height')))
        if not self.ready:
            self.verification = None
            # Keep the hold, but an outage cannot count toward confirmation.
            for ident in self.pending_fixed:
                self.pending_fixed[ident] = []
            for record in self.records.values():
                record['samples'] = 0
                record['observations'] = []
            return
        scope = (runtime['camera_identity'], runtime['camera_revision'], runtime['width'], runtime['height'])
        if scope != self.scope:
            self.scope, self.records = scope, {}
            self.epoch = uuid.uuid4().hex
            self.epoch_reason, self.epoch_marker_id = 'camera_changed', None
            self.pending_fixed = {}
            self.pending_reasons = {}
            self.frame_at = None
        if frame == self.frame_at:
            return
        self.frame_at = frame
        self.verification = None
        visible = set(runtime.get('visible_ids', []))
        current, geometry = {}, {}
        for tag in runtime.get('detections', []):
            ident, missing = tag.get('id'), tag.get('missing')
            if (type(ident) is not int or not (ident in self.fixed_ids or 100 <= ident <= 199)
                    or ident not in visible or type(missing) not in (int, float) or not 0 <= missing <= .35
                    or any(type(tag.get(k)) not in (int, float) or not math.isfinite(tag[k])
                           or not 0 <= tag[k] <= 1 for k in ('nx', 'ny'))):
                continue
            if ident < 100:
                shape = marker_geometry(tag, runtime['width'], runtime['height'])
                old = self.records.get(ident)
                reference = (old or {}).get('reference')
                invalid = shape is None
                if not invalid and reference:
                    before, after = [reference['size'], *reference['shape']], [shape['size'], *shape['shape']]
                    invalid = any(max(a,b)/min(a,b) > MARKER_SIZE_RATIO for a,b in zip(before,after))
                if invalid:
                    # Projected codes on an occluding arm can decode at the
                    # wrong size/shape. They are never movement evidence.
                    if old and old['mapped']:
                        self.pending_fixed[ident] = []
                        self.pending_reasons[ident] = 'marker_geometry'
                    continue
                geometry[ident] = shape
            current[ident] = tag
        # A partial/false fixed-tag detection near the arm must not erase an
        # acquired pickup. Isolate its evidence; independent surrounding anchors
        # may verify the retained map. Absence alone can never clear the hold.
        changed = []
        for ident, tag in current.items():
            old = self.records.get(ident)
            if ident >= 100 or not old or not old['mapped']:
                continue
            reference = old['reference']
            if math.hypot(tag['nx']-reference['nx'], tag['ny']-reference['ny']) <= .01:
                self.pending_fixed.pop(ident, None)
                self.pending_reasons.pop(ident, None)
                continue
            seen = min(frame, now-tag['missing'])
            observations = self.pending_fixed.get(ident, [])
            if observations and (seen-observations[-1][0] > .5
                                 or any(math.hypot(tag['nx']-p[1], tag['ny']-p[2]) > ACQUIRE_TOLERANCE
                                        for p in observations)):
                observations = []
            if not observations or seen > observations[-1][0]:
                observations.append((seen, tag['nx'], tag['ny']))
            self.pending_fixed[ident] = observations[-64:]
            self.pending_reasons[ident] = 'position_conflict'
            if len(observations) >= 3 and observations[-1][0]-observations[0][0] >= .5:
                changed.append(ident)
        if changed:
            self.records = {}
            self.epoch = uuid.uuid4().hex
            self.epoch_reason, self.epoch_marker_id = 'fixed_marker_changed', min(changed)
            self.pending_fixed = {}
            self.pending_reasons = {}
        else:
            for ident in self.pending_fixed:
                current.pop(ident, None)
        for ident, tag in current.items():
            seen = min(frame, now-tag['missing'])
            old = self.records.get(ident)
            consistent = (old and old['samples'] and seen-old['last_seen'] <= .5
                          and math.hypot(tag['nx']-old['tag']['nx'], tag['ny']-old['tag']['ny']) <= .004)
            since = old['since'] if consistent else seen
            samples = old['samples']+1 if consistent else 1
            stable = samples >= 3 and seen-since >= .5
            # Missing frames are expected occlusion, not evidence of movement.
            # Keep only distinct, recent sightings of the same position. A real
            # move, a long gap or invalid camera state requires reacquisition.
            observations = [p for p in (old or {}).get('observations', [])
                            if 0 <= seen-p[0] <= ACQUIRE_WINDOW_S]
            if observations and (seen-observations[-1][0] > ACQUIRE_MAX_AGE_S
                                 or any(math.hypot(tag['nx']-p[1], tag['ny']-p[2]) > ACQUIRE_TOLERANCE
                                        for p in observations)):
                observations = []
            if not observations or seen > observations[-1][0]:
                observations.append((seen, tag['nx'], tag['ny']))
            self.records[ident] = {'tag': copy.deepcopy(tag), 'last_seen': seen,
                                  'since': since, 'samples': samples,
                                  'observations': observations[-64:],
                                  'covered_by': list(old.get('covered_by', [])) if old else [],
                                  'mapped': ident < 100 and (stable or bool(old and old['mapped'])),
                                  'reference': ((old or {}).get('reference') or
                                                (dict(nx=tag['nx'], ny=tag['ny'], **geometry[ident])
                                                 if ident < 100 and stable else None))}
        # Remember observed occupancy independently of coordinate memory. A dark
        # Atom must not make an occupied fixed destination appear empty.
        for ident, record in self.records.items():
            if ident >= 100:
                continue
            blockers = set(record['covered_by'])
            for moving, tag in current.items():
                if moving < 100:
                    continue
                corners = tag.get('ncorners') or []
                valid = [p for p in corners if isinstance(p, (list, tuple)) and len(p) == 2
                         and all(type(v) in (int, float) and math.isfinite(v) for v in p)]
                if len(valid) != 4:
                    continue  # No invented footprint when corners are unavailable.
                x, y = record['tag']['nx'], record['tag']['ny']
                covered = min(p[0] for p in valid) <= x <= max(p[0] for p in valid) and min(p[1] for p in valid) <= y <= max(p[1] for p in valid)
                if covered:
                    blockers.add(moving)
                else:
                    blockers.discard(moving)
            if ident in current:
                # A directly observed fixed marker is no longer fully covered.
                blockers = {moving for moving in blockers if moving in current}
            record['covered_by'] = sorted(blockers)
        for ident, record in list(self.records.items()):
            if ident not in current:
                record['samples'] = 0
            if ident >= 100 and now-record['last_seen'] > 15:
                del self.records[ident]
        if self.pending_fixed:
            self._verify_retained_map(current, now)

    def _verify_retained_map(self, current, now):
        anchors = {}
        for ident, tag in current.items():
            record = self.records[ident]
            ref = record['reference']
            observations = record['observations']
            if (ident >= 100 or not ref or ident in self.pending_fixed
                    or not 0 <= now-record['last_seen'] <= ACQUIRE_MAX_AGE_S
                    or len(observations) < ACQUIRE_MIN_SAMPLES
                    or observations[-1][0]-observations[0][0] < ACQUIRE_MIN_SPAN_S
                    or math.hypot(tag['nx']-ref['nx'], tag['ny']-ref['ny']) > ACQUIRE_TOLERANCE):
                continue
            anchors[ident] = (ref['nx'], ref['ny'])
        if len(anchors) < ANCHOR_MIN_COUNT:
            return
        hull = _anchor_hull(anchors.values())
        area = abs(sum(a[0]*b[1]-a[1]*b[0] for a, b in zip(hull, hull[1:]+hull[:1]))) / 2
        if (area < ANCHOR_MIN_AREA or
                any(max(p[i] for p in hull)-min(p[i] for p in hull) < ANCHOR_MIN_SPAN for i in (0, 1))):
            return
        # Verify around every quarantined location. Distant or collinear
        # surviving markers cannot license extrapolation past an occlusion.
        for ident in self.pending_fixed:
            ref = self.records[ident]['reference']
            point = (ref['nx'], ref['ny'])
            if any(_cross(a, b, point) < -1e-9 for a, b in zip(hull, hull[1:]+hull[:1])):
                return
        self.verification = {'anchor_ids': sorted(anchors),
                             'observed_at': min(self.records[i]['last_seen'] for i in anchors),
                             'area': area}

    def snapshot(self, now):
        verified = bool(self.verification and 0 <= now-self.verification['observed_at'] <= ACQUIRE_MAX_AGE_S)
        ready = (self.ready and (not self.pending_fixed or verified) and self.sampled_at is not None and self.frame_at is not None
                 and 0 <= now-self.sampled_at <= 1.5 and 0 <= now-self.frame_at <= 1.5)
        tags = []
        if ready:
            for ident, record in sorted(self.records.items()):
                age = now-record['last_seen']
                visible = 0 <= age <= .35 and record['samples'] > 0
                stable = visible and record['samples'] >= 3 and record['last_seen']-record['since'] >= .5
                if ident in self.pending_fixed or ident < 100 and not record['mapped']:
                    continue
                tag = copy.deepcopy(record['tag'])
                observations = [p for p in record['observations'] if 0 <= now-p[0] <= ACQUIRE_WINDOW_S]
                acquirable = (ident >= 100 and 0 <= age <= ACQUIRE_MAX_AGE_S
                              and len(observations) >= ACQUIRE_MIN_SAMPLES
                              and observations[-1][0]-observations[0][0] >= ACQUIRE_MIN_SPAN_S)
                tag.update(last_seen=record['last_seen'], missing=max(0, age), visible=visible,
                           stable=stable, fixed=ident < 100, cached=ident < 100 and not visible,
                           acquirable=acquirable, evidence_samples=len(observations),
                           covered_by=list(record['covered_by']))
                tags.append(tag)
        error = None if ready else 'Waiting for fresh camera mapping.'
        if not ready and self.ready and self.pending_fixed:
            error = ('Checking fixed marker '+', '.join('#'+str(i) for i in sorted(self.pending_fixed))
                     +' after a conflicting camera detection.')
        return {'contract': 'photon.board.cue-targets', 'version': 1,
                'status': 'ready' if ready else 'unavailable', 'epoch': self.epoch,
                'epoch_reason': self.epoch_reason, 'epoch_marker_id': self.epoch_marker_id,
                'pending_fixed_ids': sorted(self.pending_fixed),
                # These IDs are withheld from acquisition. Occupancy remains
                # available to the current operation without exposing a pose.
                'quarantined_tags': [dict(id=i, reason=self.pending_reasons[i],
                                          covered_by=list(self.records[i]['covered_by']))
                                     for i in sorted(self.pending_fixed)],
                'verification': dict(status='ready' if ready and verified else 'unavailable',
                                     **(self.verification or {})),
                'coordinate_space': 'corrected-camera-normalized', 'source': 'camera',
                'frame_at': self.frame_at, 'sampled_at': self.sampled_at, 'tags': tags,
                'error': error}
