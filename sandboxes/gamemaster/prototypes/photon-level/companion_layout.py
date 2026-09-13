"""Level-owned L4 companion geometry; no additional placement sockets."""
import math


def descriptor(props, x, y, offset_x, offset_y, rotation):
    if 'l4_companion_enabled' not in props:
        return None
    enabled = props['l4_companion_enabled']
    if type(enabled) is not bool:
        raise ValueError('l4_companion_enabled must be a boolean')
    value = {'contract': 'photon.level.companion', 'version': 1, 'eligible': enabled}
    if enabled:
        cx = x + 2 * offset_x * math.cos(rotation)
        cy = y + 2 * offset_x * math.sin(rotation)
        value.update(x=cx, y=cy, visual_x=cx - offset_y * math.sin(rotation),
                     visual_y=cy + offset_y * math.cos(rotation), pod_size=96)
    return value


def validate_clearance(sockets, width, height, primary_size, core):
    boxes = []
    companions = []
    for sid, socket in sockets.items():
        boxes.extend([
            (sid, socket['x'], socket['marker_y'], primary_size),
            (f"marker {socket['aruco_id']}", socket['marker_x'], socket['marker_y'], socket['marker_size']),
        ])
        value = socket.get('companion')
        if value and value['eligible']:
            companions.append((f'{sid} companion', value['visual_x'], value['visual_y'], value['pod_size']))
    boxes.append(('core marker', core['marker_x'], core['marker_y'], core['marker_size']))
    for i, (name, x, y, size) in enumerate(companions):
        if not all(math.isfinite(v) for v in (x, y, size)) or not (
            size / 2 <= x <= width - size / 2 and size / 2 <= y <= height - size / 2
        ):
            raise ValueError(f'{name} must fit inside the playfield')
        for other, ox, oy, os in boxes + companions[:i]:
            if abs(x - ox) < (size + os) / 2 - 1e-6 and abs(y - oy) < (size + os) / 2 - 1e-6:
                raise ValueError(f'{name} overlaps {other}')
