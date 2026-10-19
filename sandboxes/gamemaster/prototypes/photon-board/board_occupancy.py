"""Camera-only movable/fixed-marker occupancy; no gameplay or robot rules."""
import math
import time

from board_tracking import GAME_PLACEMENT_DISTANCE, GAME_MARKER_MEMORY_S, PLACEMENT_DWELL_S, fresh
from fixed_anchors import read_anchors

# The Board samples at 5 Hz, after camera processing. A 350 ms timeout was
# shorter than an ordinary frame's age plus the next sampling interval.
# Retain an established presence through brief missed detections, never a
# camera outage or positive departure. Keep this bounded below STALE_S.
GRACE_S = 0.9
MARKER_VISIBILITY_DWELL_S = 0.15


class OccupancyTracker:
    def __init__(self):
        self.identity = None
        self.epoch = str(time.time_ns())
        self.revision = 0
        self.markers = {}
        self.records = {}
        self.last_frame = None

    def unavailable(self, error, now=None):
        # Retain visit/departure identity, but require a new stable acquisition.
        for record in self.records.values():
            record.update(state='unavailable', frames=0, continuous=False, visibility_probe=None)
        return self.snapshot('unavailable', error, now)

    def snapshot(self, status, error, now):
        return {'contract': 'photon.board.occupancy', 'version': 1,
                'status': status, 'error': error, 'source_epoch': self.epoch,
                'revision': self.revision, 'sampled_at': now,
                'frame_at': self.last_frame,
                'relations': [{key: record[key] for key in (
                    'movable_id', 'marker_id', 'relation_id', 'state',
                    'observed_since', 'evidence_at', 'departed_at')}
                    for record in self.records.values()],
                'policy': {'distance': GAME_PLACEMENT_DISTANCE,
                           'stable_s': PLACEMENT_DWELL_S, 'grace_s': GRACE_S,
                           'marker_visibility_s': MARKER_VISIBILITY_DWELL_S}}

    def _marker_revealed(self, record, detections, point, frame, distinct, now):
        """Debounce a covered anchor becoming visible, even if its Atom is lost."""
        if not record or not record.get('established'):
            return False
        visible = record['marker_id'] in detections
        on_anchor = point is not None and math.dist(point, record['anchor']) <= GAME_PLACEMENT_DISTANCE
        kind = ('revealed' if visible and record.get('covered') else
                'covered' if not visible and on_anchor else None)
        if kind is None or now - frame > GRACE_S:
            record['visibility_probe'] = None
        elif distinct:
            probe = record.get('visibility_probe')
            if not probe or probe['kind'] != kind or frame - probe['at'] > GRACE_S:
                probe = {'kind': kind, 'since': frame, 'frames': 0}
            probe.update(at=frame, frames=probe['frames'] + 1)
            record['visibility_probe'] = probe
            if probe['frames'] >= 3 and frame - probe['since'] >= MARKER_VISIBILITY_DWELL_S:
                if kind == 'covered':
                    record.update(covered=True, revealed=False)
                else:
                    if not record.get('revealed'):
                        record['departed_at'] = frame
                    record.update(state='departed', evidence_at=frame, frames=0,
                                  continuous=False, revealed=True)
        return visible and record.get('revealed', False)

    def update(self, runtime, now, *, fixed_map=None):
        self.revision += 1
        mapped, mapping_identity, pending = None, None, set()
        if fixed_map is not None:
            try:
                mapped, mapping_identity, _, pending = read_anchors(fixed_map, now)
            except ValueError as exc:
                return self.unavailable(str(exc), now)
        identity = (runtime.get('source'), runtime.get('camera_identity'),
                    runtime.get('camera_revision'), runtime.get('width'), runtime.get('height'),
                    mapping_identity)
        if identity != self.identity:
            self.identity = identity
            self.epoch = str(time.time_ns())
            self.markers.clear()
            self.records.clear()
            self.last_frame = None
        if (runtime.get('status') != 'ready' or runtime.get('corrected') is not True
                or not fresh(runtime.get('frame_at'), now)):
            return self.unavailable('Fresh corrected camera evidence unavailable', now)
        frame = float(runtime['frame_at'])
        if self.last_frame is not None and frame < self.last_frame:
            return self.unavailable('Camera frame moved backwards', now)
        distinct = frame != self.last_frame
        self.last_frame = frame
        visible = set(runtime.get('visible_ids') or [])
        detections = {}
        for tag in runtime.get('detections') or []:
            tag_id = tag.get('id')
            coords = (tag.get('nx'), tag.get('ny'))
            if (type(tag_id) is not int or not 0 <= tag_id <= 999
                    or tag_id not in visible or tag_id in detections
                    or any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1 for v in coords)):
                return self.unavailable('Invalid or duplicate camera occupancy detection', now)
            detections[tag_id] = coords
        if mapped is not None:
            self.markers = {i: {'point': (p['nx'], p['ny']), 'seen_at': p['seen_at']}
                            for i, p in mapped.items()}
            # Bad fixed-code observations cannot imply uncovering or move anchors.
            detections = {i: p for i, p in detections.items()
                          if i >= 100 or i in mapped and i not in pending}
        else:
            # The unscoped/simulator path retains its existing reset policy.
            if any(tag_id < 100 and tag_id in self.markers
                   and math.dist(coords, self.markers[tag_id]['point']) > .01
                   for tag_id, coords in detections.items()):
                self.epoch = str(time.time_ns())
                self.markers.clear()
                self.records.clear()
            for tag_id, coords in detections.items():
                if tag_id < 100:
                    self.markers[tag_id] = {'point': coords, 'seen_at': frame}

        movable = {tag_id: point for tag_id, point in detections.items() if tag_id >= 100}
        candidates = {}
        for tag_id, point in movable.items():
            record = self.records.get(tag_id)
            anchors = {marker: data['point'] for marker, data in self.markers.items()
                       if mapped is not None or now - data['seen_at'] <= GAME_MARKER_MEMORY_S}
            # A previously established association may be reacquired by the
            # same Atom after occlusion. It cannot establish a different Atom's
            # placement, and camera/geometry changes discard it entirely.
            if mapped is None and record and record.get('established') and record['state'] != 'departed':
                anchors[record['marker_id']] = record['anchor']
            candidates[tag_id] = [(marker, anchor) for marker, anchor in anchors.items()
                                  if math.dist(point, anchor) <= GAME_PLACEMENT_DISTANCE]
        counts = {}
        for matches in candidates.values():
            for marker, _ in matches:
                counts[marker] = counts.get(marker, 0) + 1
        for tag_id in sorted(set(self.records) | set(movable)):
            record = self.records.get(tag_id)
            if mapped is not None and record and record['marker_id'] not in mapped:
                record.update(state='unavailable', frames=0, continuous=False, visibility_probe=None)
            point = movable.get(tag_id)
            revealed = self._marker_revealed(record, detections, point, frame, distinct, now)
            if point is None:
                if record and record['state'] != 'departed' and now - record['evidence_at'] > GRACE_S:
                    record.update(state='unavailable', frames=0, continuous=False)
                continue
            # A hovering/nearby Atom cannot reacquire the uncovered marker.
            # Moving to another marker can still start a new relationship.
            matches = [(marker, anchor) for marker, anchor in candidates[tag_id]
                       if not revealed or marker != record['marker_id']]
            departed_at = record['departed_at'] if record else None
            # Displacement and debounced uncovering establish departure;
            # occlusion, relay changes and missing frames alone do not.
            if (record and math.dist(point, record['anchor']) > GAME_PLACEMENT_DISTANCE
                    and record['state'] != 'departed'):
                departed_at = frame
                record.update(state='departed', departed_at=frame, evidence_at=frame,
                              frames=0, continuous=False)
            if len(matches) != 1 or counts[matches[0][0]] != 1:
                if record and record['state'] != 'departed':
                    record.update(state='unavailable', frames=0, continuous=False)
                continue
            marker, anchor = matches[0]
            if (record is None or record['marker_id'] != marker
                    or record['frames'] == 0):
                generation = (record or {}).get('generation', 0) + 1
                established = bool(record and record['marker_id'] == marker and record.get('established'))
                visibility = ({key: record.get(key) for key in ('covered', 'revealed', 'visibility_probe')}
                              if record and record['marker_id'] == marker else {})
                record = self.records[tag_id] = {
                    'movable_id': tag_id, 'marker_id': marker, 'anchor': anchor,
                    'relation_id': f'{self.epoch}:{tag_id}:{generation}',
                    'generation': generation, 'state': 'unavailable',
                    'observed_since': frame, 'evidence_at': frame,
                    'departed_at': departed_at, 'frames': 1 if distinct else 0,
                    'continuous': False, 'established': established,
                    **visibility,
                }
            elif distinct:
                if frame - record['evidence_at'] > GRACE_S:
                    record.update(frames=0, observed_since=frame, continuous=False)
                record['frames'] += 1
                record['evidence_at'] = frame
            record['state'] = ('present' if record['frames'] >= 3
                               and frame - record['observed_since'] >= PLACEMENT_DWELL_S
                               and now - frame <= GRACE_S else 'unavailable')
            record['continuous'] = record['state'] == 'present'
            record['established'] = record['established'] or record['continuous']
        self.markers = {marker: data for marker, data in self.markers.items()
                        if mapped is not None or now - data['seen_at'] <= GAME_MARKER_MEMORY_S}
        return self.snapshot('ready', None, now)
