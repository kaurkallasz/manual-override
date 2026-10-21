"""Sparse image tracking, attachment evidence and optional lens calibration."""
import cv2
import numpy as np


def region_mask(shape, roi, exclude=None):
    mask = np.zeros(shape[:2], np.uint8)
    h, w = shape[:2]
    def bounds(r):
        x, y, rw, rh = r
        return int(x*w), int(y*h), min(w, int((x+rw)*w)), min(h, int((y+rh)*h))
    if roi:
        x, y, right, bottom = bounds(roi)
        mask[y:bottom, x:right] = 255
    if exclude:
        x, y, right, bottom = bounds(exclude)
        mask[y:bottom, x:right] = 0
    return mask


def seed_features(gray, roi, exclude=None, *, grid_step=None):
    mask = region_mask(gray.shape, roi, exclude)
    if grid_step:
        # One textured feature per image cell gives spatial coverage without
        # inventing correspondences in smooth regions or across object edges.
        strength = cv2.cornerMinEigenVal(gray, blockSize=5)
        strength[mask == 0] = 0
        strength[:5] = strength[-5:] = 0
        strength[:, :5] = strength[:, -5:] = 0
        threshold = max(.0001, float(strength.max())*.01)
        seeds = []
        for y in range(0, gray.shape[0], grid_step):
            for x in range(0, gray.shape[1], grid_step):
                cell = strength[y:y+grid_step, x:x+grid_step]
                cy, cx = np.unravel_index(cell.argmax(), cell.shape)
                if cell[cy, cx] >= threshold:
                    seeds.append([x+cx, y+cy])
        corners = np.asarray(seeds, np.float32).reshape(-1, 1, 2)
    else:
        corners = cv2.goodFeaturesToTrack(gray, 180, .015, 6, mask=mask, blockSize=5)
    return corners.reshape(-1, 2) if corners is not None else np.empty((0, 2), np.float32)


def track_points(before, after, points, roi, exclude=None, *, initial=None):
    """Track fixed feature identities from a reference image, with reverse checks."""
    if len(points) < 6:
        return np.empty((0, 2)), np.empty(0, dtype=int)
    mask = region_mask(after.shape, roi, exclude)
    corners = np.asarray(points, np.float32).reshape(-1, 1, 2)
    options = dict(winSize=(25, 25), maxLevel=4,
                   criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, .01))
    if initial is not None:
        options['flags'] = cv2.OPTFLOW_USE_INITIAL_FLOW
        initial = np.asarray(initial, np.float32).reshape(-1, 1, 2).copy()
    forward, status, _ = cv2.calcOpticalFlowPyrLK(before, after, corners, initial, **options)
    if forward is None:
        return np.empty((0, 2)), np.empty(0, dtype=int)
    backward, reverse, _ = cv2.calcOpticalFlowPyrLK(after, before, forward, corners.copy() if initial is not None else None, **options)
    if backward is None:
        return np.empty((0, 2)), np.empty(0, dtype=int)
    a, b = corners.reshape(-1, 2), forward.reshape(-1, 2)
    valid = (status.ravel() == 1) & (reverse.ravel() == 1)
    valid &= np.linalg.norm(a-backward.reshape(-1, 2), axis=1) < .8
    valid &= np.isfinite(b).all(axis=1)
    safe = np.where(np.isfinite(b), b, 0)
    x, y = np.clip(safe[:, 0], 0, after.shape[1]-1).astype(int), np.clip(safe[:, 1], 0, after.shape[0]-1).astype(int)
    valid &= (b[:, 0] >= 0) & (b[:, 0] < after.shape[1]) & (b[:, 1] >= 0) & (b[:, 1] < after.shape[0])
    valid &= mask[y, x] > 0
    return b[valid], np.flatnonzero(valid)


def track(before, after, roi, exclude=None, *, grid_step=None):
    points = seed_features(before, roi, exclude, grid_step=grid_step)
    found, ids = track_points(before, after, points, roi, exclude)
    return points[ids], found


def attachment(before, after, roi, background_shift, pump):
    if roi is None:
        return dict(state='unknown', reason='Select the visible Atom body, excluding the vacuum head')
    a, b = track(before, after, roi)
    if len(a) < 8 or background_shift < 3:
        return dict(state='unknown', reason='Need Atom texture and visible movement of the background')
    shifts = np.linalg.norm(b-a, axis=1)
    stable = float(np.mean(shifts < 1.2))
    median = float(np.median(shifts))
    state = ('moves_with_head' if stable >= .8 and pump == 'suck' else
             'relative_motion' if median > 2.5 else 'unknown')
    return dict(state=state, features=len(a), stable_fraction=round(stable, 3),
                median_shift_px=round(median, 2),
                reason={'moves_with_head':'Visual evidence during suction; grip is not pressure-verified',
                        'relative_motion':'Atom-region features moved relative to the head',
                        'unknown':'Attachment is not established'}[state])


class LensCalibration:
    def __init__(self):
        self.samples = []
        self.size = None
        self.pattern = None

    def capture(self, gray, columns, rows, square):
        pattern = (columns, rows, square)
        size = (gray.shape[1], gray.shape[0])
        if self.samples and (self.size != size or self.pattern != pattern):
            raise ValueError('Clear lens samples before changing board or video mode')
        if len(self.samples) >= 30:
            raise ValueError('30 samples collected; solve or clear the calibration')
        found, corners = cv2.findChessboardCornersSB(gray, (columns, rows), cv2.CALIB_CB_NORMALIZE_IMAGE)
        if not found:
            raise ValueError('Checkerboard not found; all inner corners must be visible and sharp')
        if any(np.sqrt(np.mean((corners-old)**2)) < 5 for old in self.samples):
            raise ValueError('View too similar; change board position, distance or tilt')
        self.samples.append(corners)
        self.size, self.pattern = size, pattern
        return len(self.samples)

    def solve(self):
        if len(self.samples) < 10:
            raise ValueError('Collect at least 10 varied checkerboard views, including tilted views')
        columns, rows, square = self.pattern
        board = np.zeros((columns*rows, 3), np.float32)
        board[:, :2] = np.mgrid[0:columns, 0:rows].T.reshape(-1, 2)*square
        rms, matrix, distortion, rotations, _ = cv2.calibrateCamera([board]*len(self.samples), self.samples, self.size, None, None)
        if not np.isfinite(matrix).all() or not np.isfinite(distortion).all() or rms > 1.:
            raise ValueError('Calibration error exceeds 1 px; collect sharper, more varied views')
        normals = np.array([cv2.Rodrigues(r)[0][:, 2] for r in rotations])
        spread = np.degrees(np.arccos(np.clip(normals@normals.T, -1, 1))).max()
        if spread < 12 or not .2*self.size[0] < matrix[0, 0] < 4*self.size[0]:
            raise ValueError('Lens calibration needs more tilt diversity; include clearly tilted board views')
        return dict(width=self.size[0], height=self.size[1], matrix=matrix.tolist(),
                    distortion=distortion.ravel()[:5].tolist(), rms=float(rms))
