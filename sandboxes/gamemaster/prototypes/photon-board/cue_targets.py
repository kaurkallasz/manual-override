"""Fixed board coordinates and separate live evidence; only the sampler writes."""
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
BOARD_MIN_SPAN = .15


def coherent_motion(records, observations):
    """Two separated IDs must agree on one translation/rotation/scale.

    Measured marker size must agree with that scale too. A projected decode on
    an arm is not board motion merely because its centre moved. No fitting or
    extrapolation supplies target coordinates: a confirmed move clears memory.
    """
    points = {i: t for i, t in observations.items()
              if i in records and records[i]['mapped']
              and math.hypot(t['nx']-records[i]['reference']['nx'],
                             t['ny']-records[i]['reference']['ny']) > .01}
    best = []
    for i, first in points.items():
        a = records[i]['reference']
        for j, second in points.items():
            if j <= i:
                continue
            b = records[j]['reference']
            dx, dy = b['nx']-a['nx'], b['ny']-a['ny']
            norm = dx*dx+dy*dy
            if norm < BOARD_MIN_SPAN**2:
                continue
            ux, uy = second['nx']-first['nx'], second['ny']-first['ny']
            re, im = (ux*dx+uy*dy)/norm, (uy*dx-ux*dy)/norm
            scale = math.hypot(re, im)
            if not .25 <= scale <= 4:
                continue
            group = []
            for ident, tag in points.items():
                ref = records[ident]['reference']
                x, y = ref['nx']-a['nx'], ref['ny']-a['ny']
                size_ratio = tag['geometry']['size']/(ref['size']*scale)
                if (1/MARKER_SIZE_RATIO <= size_ratio <= MARKER_SIZE_RATIO
                        and math.hypot(first['nx']+re*x-im*y-tag['nx'],
                                       first['ny']+im*x+re*y-tag['ny']) <= ACQUIRE_TOLERANCE):
                    group.append(ident)
            if i in group and j in group and len(group) > len(best):
                best = sorted(group)
    return best


class CueTargets:
    def __init__(self, fixed_ids=None):
        self.fixed_ids = frozenset(range(30, 60) if fixed_ids is None else fixed_ids)
        self.scope = None
        self.epoch = uuid.uuid4().hex
        self.epoch_reason = 'initialized'
        self.epoch_marker_id = None
        self.pending_fixed = {}
        self.pending_reasons = {}
        self.motion_ids = []
        self.motion_samples = []
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
            self.motion_samples = []
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
            self.motion_ids = []
            self.motion_samples = []
            self.frame_at = None
        if self.frame_at is not None and frame <= self.frame_at:
            return
        self.frame_at = frame
        visible = set(runtime.get('visible_ids', []))
        current, geometry, motion = {}, {}, {}
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
                if shape and reference:
                    shape_ok = all(max(a,b)/min(a,b) <= MARKER_SIZE_RATIO
                                   for a,b in zip(reference['shape'], shape['shape']))
                    if shape_ok:
                        motion[ident] = dict(tag, geometry=shape)
                    invalid = (not shape_ok or max(reference['size'], shape['size']) /
                               min(reference['size'], shape['size']) > MARKER_SIZE_RATIO)
                if invalid:
                    # Projected codes on an occluding arm can decode at the
                    # wrong size/shape. Only independent coherent board evidence
                    # can justify relearning a changed scale.
                    if old and old['mapped']:
                        self.pending_fixed[ident] = []
                        self.pending_reasons.setdefault(ident, 'marker_geometry')
                    continue
                geometry[ident] = shape
            current[ident] = tag
        # Individual bad observations never shrink the map or erase memory.
        # A geometry-valid positional contradiction blocks only that endpoint.
        for ident, tag in current.items():
            old = self.records.get(ident)
            if ident >= 100 or not old or not old['mapped']:
                continue
            ref = old['reference']
            if math.hypot(tag['nx']-ref['nx'], tag['ny']-ref['ny']) <= .01:
                self.pending_fixed.pop(ident, None)
                self.pending_reasons.pop(ident, None)
            else:
                self.pending_fixed[ident] = []
                self.pending_reasons[ident] = 'position_conflict'
        group = coherent_motion(self.records, motion)
        if group:
            coordinates = {i: (motion[i]['nx'], motion[i]['ny']) for i in group}
            common = set(coordinates)
            for _, previous in self.motion_samples:
                common.intersection_update(previous)
            separated = any(math.dist((self.records[i]['reference']['nx'], self.records[i]['reference']['ny']),
                                      (self.records[j]['reference']['nx'], self.records[j]['reference']['ny'])) >= BOARD_MIN_SPAN
                            for i in common for j in common if i < j)
            if (self.motion_samples and (frame-self.motion_samples[-1][0] > .5 or not separated
                    or any(math.dist(previous[i], coordinates[i]) > ACQUIRE_TOLERANCE
                           for _, previous in self.motion_samples for i in common))):
                self.motion_samples = []
                common = set(coordinates)
            self.motion_ids = group
            self.motion_samples.append((frame, coordinates))
            self.motion_samples = self.motion_samples[-64:]
            if (len(self.motion_samples) >= ACQUIRE_MIN_SAMPLES
                    and frame-self.motion_samples[0][0] >= ACQUIRE_MIN_SPAN_S):
                self.records = {}
                self.epoch = uuid.uuid4().hex
                self.epoch_reason, self.epoch_marker_id = 'board_moved', min(common)
                self.pending_fixed = {}
                self.pending_reasons = {}
                self.motion_ids = []
                self.motion_samples = []
        else:
            self.motion_samples = []
            # Lost/covered anchors are not board movement. After positive motion
            # evidence, however, require two independent original positions to
            # recover; mere disappearance must not silently clear a real hold.
            anchors = [i for i, tag in current.items() if i < 100 and i not in self.pending_fixed
                       and self.records.get(i, {}).get('mapped')
                       and self.records[i]['samples'] >= ACQUIRE_MIN_SAMPLES
                       and frame-self.records[i]['last_seen'] <= ACQUIRE_MAX_AGE_S]
            if any(math.dist((self.records[i]['reference']['nx'], self.records[i]['reference']['ny']),
                             (self.records[j]['reference']['nx'], self.records[j]['reference']['ny'])) >= BOARD_MIN_SPAN
                   for i in anchors for j in anchors if i < j):
                self.motion_ids = []
        for ident in self.pending_fixed:
            current.pop(ident, None)
        for ident, tag in current.items():
            seen = min(frame, now-tag['missing'])
            old = self.records.get(ident)
            if self.motion_ids and ident < 100 and not (old and old['mapped']):
                continue
            consistent = (old and old['samples'] and seen-old['last_seen'] <= .5
                          and math.hypot(tag['nx']-old['observed_tag']['nx'], tag['ny']-old['observed_tag']['ny']) <= .004)
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
            qualified = len(observations) >= ACQUIRE_MIN_SAMPLES and observations[-1][0]-observations[0][0] >= ACQUIRE_MIN_SPAN_S
            frozen = old and old['mapped']
            self.records[ident] = {'tag': copy.deepcopy(old['tag'] if frozen else tag),
                                  'observed_tag': copy.deepcopy(tag), 'last_seen': seen,
                                  'since': since, 'samples': samples,
                                  'observations': observations[-64:],
                                  'covered_by': list(old.get('covered_by', [])) if old else [],
                                  'mapped': ident < 100 and (qualified or bool(old and old['mapped'])),
                                  'reference': ((old or {}).get('reference') or
                                                (dict(nx=tag['nx'], ny=tag['ny'], **geometry[ident])
                                                 if ident < 100 and qualified else None))}
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

    def snapshot(self, now):
        ready = (self.ready and not self.motion_ids and self.sampled_at is not None and self.frame_at is not None
                 and 0 <= now-self.sampled_at <= 1.5 and 0 <= now-self.frame_at <= 1.5)
        fixed_tags, tags = [], []
        for ident, record in sorted(self.records.items()):
            age = now-record['last_seen']
            visible = ready and ident not in self.pending_fixed and 0 <= age <= .35 and record['samples'] > 0
            stable = visible and record['samples'] >= 3 and record['last_seen']-record['since'] >= .5
            if ident < 100 and not record['mapped']:
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
            if ident < 100:
                fixed_tags.append(copy.deepcopy(tag))
            if ready:
                tags.append(tag)
        error = None if ready else ('Checking coherent board movement.' if self.motion_ids
                                     else 'Waiting for fresh camera mapping.')
        blocked = [i for i in sorted(self.pending_fixed) if self.pending_reasons[i] == 'position_conflict']
        return {'contract': 'photon.board.cue-targets', 'version': 2,
                'status': 'ready' if ready else 'unavailable', 'epoch': self.epoch,
                'epoch_reason': self.epoch_reason, 'epoch_marker_id': self.epoch_marker_id,
                'pending_fixed_ids': sorted(self.pending_fixed), 'blocked_fixed_ids': blocked,
                'board_motion_ids': list(self.motion_ids),
                'quarantined_tags': [dict(id=i, reason=self.pending_reasons[i],
                                          covered_by=list(self.records[i]['covered_by']))
                                     for i in sorted(self.pending_fixed)],
                # Display memory is explicitly separate from motion authority.
                # Fixed tags have immutable coordinates, never renewed sightings.
                'fixed_tags': fixed_tags,
                'width': self.scope[2] if self.scope else 0, 'height': self.scope[3] if self.scope else 0,
                'coordinate_space': 'corrected-camera-normalized', 'source': 'camera',
                'frame_at': self.frame_at, 'sampled_at': self.sampled_at, 'tags': tags,
                'error': error}
