"""Bounded, identity-preserving inverse-depth fusion for a short camera sweep.

Each feature has one fixed reference ray. New measured viewpoints contribute
separate triangulations along that ray. A robust consensus rejects conflicts;
reprojection into the current frame prevents old geometry painting over changes.
This is a local measurement window, not a persistent world map or robot controller.
"""
from collections import deque
import math
import cv2
import numpy as np
from depth_vision import seed_features, track_points


class DepthFusion:
    MAX_OBSERVATIONS = 8
    MIN_VIEW_TRAVEL_MM = 2.

    def __init__(self):
        self.generation = 0
        self.clear('Waiting for measured translation')

    def clear(self, reason='Observations reset'):
        self.generation += 1
        self.reference = None
        self.latest = None
        self.seeds = self.rays = None
        self.tracks = {}
        self.last_stamp = None
        self.reason = reason
        self.stats = dict(state='collecting', tracked_features=0, combined_points=0,
                          max_views=0, median_views=0, rejected_observations=0,
                          median_spread_mm=None, window_ms=0, reason=reason)

    def begin(self, reference, matrix, distortion, exclude):
        self.clear('Collecting repeated observations of the same features')
        self.reference = reference
        self.matrix, self.distortion, self.exclude = matrix, distortion, exclude
        self.seeds = seed_features(reference['gray'], [0, 0, 1, 1], exclude, grid_step=12)
        if len(self.seeds):
            normalized = cv2.undistortPoints(self.seeds.reshape(-1, 1, 2), matrix, distortion).reshape(-1, 2)
            self.rays = np.column_stack((normalized, np.ones(len(normalized))))
        else:
            self.rays = np.empty((0, 3))
        self.latest = dict(gray=reference['gray'], stamp=reference['stamp'], pixels=self.seeds.copy(), ids=np.arange(len(self.seeds)))

    def track(self, gray, stamp):
        if stamp == self.latest['stamp']:
            ids, found = self.latest['ids'], self.latest['pixels']
            return self.seeds[ids], found, ids
        # Small inter-frame displacement keeps LK in the right neighborhood.
        # A second, initialized match to the fixed reference checks accumulated
        # drift without attempting an unseeded large-displacement search.
        predicted, keep = track_points(self.latest['gray'], gray, self.latest['pixels'], [0,0,1,1], self.exclude)
        ids = self.latest['ids'][keep]
        found, keep = track_points(self.reference['gray'], gray, self.seeds[ids], [0,0,1,1], self.exclude, initial=predicted)
        ids = ids[keep]
        self.latest = dict(gray=gray, stamp=stamp, pixels=found, ids=ids)
        return self.seeds[ids], found, ids

    @staticmethod
    def _agrees(a, b):
        # Pixel/timing noise gives a tolerance, capped to avoid very uncertain
        # observations merging two different surfaces at an occlusion boundary.
        tolerance = min(.15*max(a['rho'], b['rho']), 3*math.hypot(a['sigma'], b['sigma']))
        return abs(a['rho']-b['rho']) <= max(1e-7, tolerance)

    @classmethod
    def _estimate(cls, observations):
        clusters = [[other for other in observations if cls._agrees(seed, other)] for seed in observations]
        cluster = max(clusters, key=lambda group: (len(group), sum(o['weight'] for o in group)))
        # Two conflicting first measurements must not become a confident map.
        if len(observations) > 1 and len(cluster) < 2:
            return None
        weight = sum(o['weight'] for o in cluster)
        rho = sum(o['rho']*o['weight'] for o in cluster)/weight
        # Keep the per-observation noise floor: shared reference pixels and
        # nominal lens/timing bias do not vanish just because N grows.
        sigma = max(o['sigma'] for o in cluster)
        spread = (math.sqrt(sum(o['weight']*(o['rho']-rho)**2 for o in cluster)/weight)/rho**2
                  if len(cluster) > 1 else None)
        return dict(rho=rho, sigma=sigma, views=len(cluster)+1, spread_mm=spread)

    def update(self, tracked_ids, pixels, geometry, residuals, *, frame_key, stamp,
               baseline, timing_motion, tracked_count, view_position):
        """Return fused coordinates in THIS camera and current-frame feature pixels.

        geometry carries input indices and the measured camera transform relative
        to the retained reference. No commanded pose or AI depth enters this path.
        """
        centre, rotation = geometry['centre'], geometry['rotation']
        ids = np.asarray(tracked_ids)[geometry['indices']]
        focal = max(self.matrix[0, 0], self.matrix[1, 1])
        output, locations, evidence = [], [], []
        rejected = 0
        for feature, pixel, z, residual in zip(ids, pixels, geometry['anchor_depths'], residuals):
            feature = int(feature)
            if not np.isfinite(z) or z <= 0:
                rejected += 1
                continue
            ray = self.rays[feature]
            transverse = float(np.linalg.norm(np.cross(ray/np.linalg.norm(ray), centre)))
            if transverse < 1e-5:
                rejected += 1
                continue
            rho = 1/float(z)
            sigma = math.hypot(max(.7, float(residual))/(focal*transverse), rho*timing_motion/baseline)
            observation = dict(rho=rho, sigma=sigma, weight=1/max(sigma**2, 1e-12),
                               view_position=np.asarray(view_position).copy(), key=frame_key)
            track = self.tracks.setdefault(feature, dict(samples=deque(maxlen=self.MAX_OBSERVATIONS), seen=stamp))
            track['seen'] = stamp
            samples = track['samples']
            novel = all(o['key'] != frame_key and np.linalg.norm(view_position-o['view_position']) >= self.MIN_VIEW_TRAVEL_MM for o in samples)
            if novel:
                samples.append(observation)
            estimate = self._estimate(samples)
            if estimate is None or not self._agrees(estimate, observation):
                rejected += 1
                continue
            current = (ray/estimate['rho']-centre)@rotation
            if not np.isfinite(current).all() or not 20 < current[2] < 1200:
                rejected += 1
                continue
            output.append(current)
            locations.append(pixel)
            evidence.append(dict(track_id=f'{self.generation}:{feature}', views=estimate['views'],
                                 spread_mm=None if estimate['spread_mm'] is None else round(estimate['spread_mm'], 3)))
        coordinates = np.asarray(output, dtype=float).reshape(-1, 3)
        locations = np.asarray(locations, dtype=float).reshape(-1, 2)
        if len(coordinates):
            projection, _ = cv2.projectPoints(coordinates, np.zeros(3), np.zeros(3), self.matrix, self.distortion)
            good = np.linalg.norm(projection.reshape(-1, 2)-locations, axis=1) < 1.5
            rejected += int((~good).sum())
            coordinates, locations = coordinates[good], locations[good]
            evidence = [row for row, keep in zip(evidence, good) if keep]
        # Lost features cannot carry evidence indefinitely or be reassigned to
        # another feature that later happens to occupy the same image cell.
        self.tracks = {feature:track for feature, track in self.tracks.items() if stamp-track['seen'] <= .6}
        self.last_stamp = stamp
        views = [row['views'] for row in evidence]
        spreads = [row['spread_mm'] for row in evidence if row['spread_mm'] is not None]
        combined = sum(v >= 3 for v in views)
        refined = combined >= 8
        self.stats = dict(state='refined' if refined else 'collecting', tracked_features=int(tracked_count),
                          combined_points=combined, max_views=max(views, default=0),
                          median_views=float(np.median(views)) if views else 0,
                          rejected_observations=rejected, median_spread_mm=float(np.median(spreads)) if spreads else None,
                          window_ms=round((stamp-self.reference['stamp'])*1000),
                          reason='Repeated viewpoints agree' if refined else 'Move farther to add another measured viewpoint')
        return coordinates, locations, evidence
