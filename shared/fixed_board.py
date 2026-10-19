"""Pure scope descriptor shared by game displays; Board alone owns coordinates."""
import hashlib
import json


def cue_layout(game, calibration_display=None):
    level, journey = game.get('level') or {}, game.get('journey') or {}
    layout = {k: level.get(k) for k in ('id', 'layout_revision', 'width', 'height', 'sockets', 'core')}
    layout['run_id'] = game.get('run_id')
    fixed_ids = [s['aruco_id'] for s in level.get('sockets', [])]
    core = level.get('core') or {}
    if 'marker_x' in core and 'marker_y' in core:
        fixed_ids.append(38)
    if journey.get('phase') == 'calibration':
        field = calibration_display or {}
        if (field.get('contract') != 'hhh.playfield' or type(field.get('version')) is not int
                or field['version'] != 1 or field.get('status') != 'ready'):
            raise ValueError('Calibration display unavailable.')
        layout = {'calibration': journey.get('id'), 'areas': field.get('areas'), 'settings': field.get('settings')}
        fixed_ids = [area['marker'] for area in field['areas']]
    return hashlib.sha256(json.dumps(layout, sort_keys=True, allow_nan=False).encode()).hexdigest(), fixed_ids
