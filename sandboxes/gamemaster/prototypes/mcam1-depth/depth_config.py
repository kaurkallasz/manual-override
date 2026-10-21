"""MCAM1 Depth owns its calibration; no hardware settings are changed."""
import copy
import json
import math
import os
from pathlib import Path
import tempfile

ATOM = {'height_mm': 31.5, 'width_mm': 20.0, 'length_mm': 20.0}
DEFAULT = dict(side='green', horizontal_fov_deg=85.0, mount_rpy_deg=[180., 0., 0.],
               camera_offset_mm=[0., 0., 80.], contact_offset_mm=[0., 0., 0.],
               follows_tool_rotation=True, mounting_confirmed=False,
               frame_delay_ms=0., timing_uncertainty_ms=20., timing_confirmed=False,
               min_baseline_mm=10., surface_roi=None, atom_roi=None, intrinsics=None)


def number(value, low, high):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f'Expected a finite number between {low} and {high}')
    return float(value)


def vector(value, length, low, high):
    if not isinstance(value, list) or len(value) != length:
        raise ValueError(f'Expected {length} numbers')
    return [number(v, low, high) for v in value]


def validate(raw):
    if not isinstance(raw, dict) or set(raw) - set(DEFAULT):
        raise ValueError('Unknown calibration fields')
    c = {**copy.deepcopy(DEFAULT), **raw}
    if c['side'] not in ('green', 'purple'):
        raise ValueError('Select Green or Purple')
    for key in ('follows_tool_rotation', 'mounting_confirmed', 'timing_confirmed'):
        if type(c[key]) is not bool:
            raise ValueError(f'{key} must be true or false')
    for key, lo, hi in [('horizontal_fov_deg', 30, 130), ('frame_delay_ms', 0, 1000),
                        ('timing_uncertainty_ms', 1, 250), ('min_baseline_mm', 5, 30)]:
        c[key] = number(c[key], lo, hi)
    c['mount_rpy_deg'] = vector(c['mount_rpy_deg'], 3, -360, 360)
    for key in ('camera_offset_mm', 'contact_offset_mm'):
        c[key] = vector(c[key], 3, -300, 300)
    for key in ('surface_roi', 'atom_roi'):
        if c[key] is not None:
            x, y, w, h = vector(c[key], 4, 0, 1)
            if min(w, h) < .04 or x+w > 1.000001 or y+h > 1.000001:
                raise ValueError('Select a rectangle inside the image, at least 4% wide and high')
            c[key] = [x, y, w, h]
    lens = c['intrinsics']
    if lens is not None:
        if not isinstance(lens, dict) or set(lens) != {'width', 'height', 'matrix', 'distortion', 'rms'}:
            raise ValueError('Invalid lens calibration')
        for key in ('width', 'height'):
            if type(lens[key]) is not int or not 100 <= lens[key] <= 4096:
                raise ValueError('Invalid lens calibration dimensions')
        k = [vector(row, 3, -10000, 10000) for row in lens['matrix']] if isinstance(lens['matrix'], list) else []
        if len(k) != 3 or k[0][0] <= 0 or k[1][1] <= 0 or k[2] != [0., 0., 1.] or k[0][1] != 0 or k[1][0] != 0:
            raise ValueError('Invalid camera matrix')
        if not 0 <= k[0][2] <= lens['width'] or not 0 <= k[1][2] <= lens['height']:
            raise ValueError('Principal point must be in the calibrated image')
        distortion = vector(lens['distortion'], 5, -100, 100)
        c['intrinsics'] = dict(width=lens['width'], height=lens['height'], matrix=k,
                               distortion=distortion, rms=number(lens['rms'], 0, 2))
    return copy.deepcopy(c)


class ConfigStore:
    def __init__(self, path):
        self.path = Path(path)
        self.error = None
        try:
            self.value = validate(json.loads(self.path.read_text())) if self.path.exists() else copy.deepcopy(DEFAULT)
        except (ValueError, OSError, TypeError) as exc:
            self.value = copy.deepcopy(DEFAULT)
            self.error = f'Calibration could not be loaded: {exc}'

    def save(self, raw):
        value = validate(raw)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=self.path.parent, prefix='.depth-', suffix='.json')
        try:
            with os.fdopen(fd, 'w') as handle:
                json.dump(value, handle, allow_nan=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        self.value, self.error = value, None
        return copy.deepcopy(value)
