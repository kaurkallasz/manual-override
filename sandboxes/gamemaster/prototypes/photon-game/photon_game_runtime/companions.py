"""Parent-owned companion weapon state and validated Level input."""
import math

POLICY = {'version': 1, 'pod_size': 96, 'shared_health': True, 'damage_scale': 1.0}
SHARED = ('atom_tag_id', 'owner', 'socket_id', 'aruco_id', 'tower_type', 'source',
          'upgrade_level', 'upgrade_multiplier', 'aim_angle', 'aim_spread', 'aim_revision',
          'hp', 'max_hp', 'base_max_hp', 'destroyed', 'destroyed_at', 'last_damage_at',
          'last_damage_amount', 'replenished_at', 'linked_turret_count', 'link_multiplier')


def validate_geometry(sockets, width, height, core=None):
    boxes = [(sid, float(s['x']), float(s.get('marker_y', s['y'])), 112)
             for sid, s in sockets.items()]
    boxes += [(f'marker {sid}', float(s.get('marker_x', s['x'])), float(s.get('marker_y', s['y'])),
               float(s.get('marker_size', 77))) for sid, s in sockets.items()]
    if core:
        boxes.append(('core marker', float(core['marker_x']), float(core['marker_y']), float(core['marker_size'])))
    for sid, socket in sockets.items():
        if 'companion' not in socket:
            continue
        value = socket['companion']
        if (not isinstance(value, dict) or value.get('contract') != 'photon.level.companion'
                or type(value.get('version')) is not int or value['version'] != 1
                or type(value.get('eligible')) is not bool):
            raise ValueError('invalid Level companion descriptor')
        if not value['eligible']:
            continue
        if any(type(value.get(k)) not in (int, float) or not math.isfinite(value[k])
               for k in ('x', 'y', 'visual_x', 'visual_y', 'pod_size')) or value['pod_size'] != 96:
            raise ValueError('invalid Level companion geometry')
        x, y, size = value['visual_x'], value['visual_y'], value['pod_size']
        mx, my = float(socket.get('marker_x', socket['x'])), float(socket.get('marker_y', socket['y']))
        if (x-mx)*(float(socket['x'])-mx) + (y-my)*(float(socket.get('marker_y', socket['y']))-my) >= 0:
            raise ValueError('Level companion must be across its marker')
        if not (0 <= value['x'] <= width and 0 <= value['y'] <= height
                and size/2 <= x <= width-size/2 and size/2 <= y <= height-size/2):
            raise ValueError('Level companion is outside playfield')
        for other, ox, oy, os in boxes:
            if abs(x-ox) < (size+os)/2 - 1e-6 and abs(y-oy) < (size+os)/2 - 1e-6:
                raise ValueError(f'Level companion {sid} overlaps {other}')
        boxes.append((f'companion {sid}', x, y, size))


def synchronize(parent, descriptor, now, activation_duration, fire_interval, *, create=False, installed=False):
    eligible = descriptor and descriptor.get('eligible') and parent.get('upgrade_level') == 4
    if not eligible:
        parent.pop('companion', None)
        return None
    unit = parent.get('companion')
    if unit is None and create and not parent.get('destroyed'):
        started = parent['activation_started_at'] if installed else now
        unit = {'placement_id': f"{parent['placement_id']}:companion",
                'parent_placement_id': parent['placement_id'], 'is_companion': True,
                'x': descriptor['x'], 'y': descriptor['y'],
                'visual_x': descriptor['visual_x'], 'visual_y': descriptor['visual_y'],
                'pod_size': descriptor['pod_size'], 'cooldown': fire_interval,
                'activation_started_at': started, 'activation_complete_at': started + activation_duration,
                'facing_angle': parent['aim_angle'], 'last_fire_at': None,
                'last_fire_target': None, 'last_fire_chain': []}
        parent['companion'] = unit
    if unit is not None:
        for key in SHARED:
            unit[key] = parent.get(key)
    return unit


def contact_fraction(ax, ay, bx, by, circles):
    """Union of swept enemy-contact intervals; never charge twice for the pair."""
    dx, dy = bx-ax, by-ay
    length = dx*dx + dy*dy
    intervals = []
    for x, y, radius in circles:
        sx, sy = ax-x, ay-y
        constant = sx*sx + sy*sy - radius*radius
        if length <= 1e-12:
            if constant <= 0:
                return 1.0
            continue
        linear = 2*(sx*dx + sy*dy)
        discriminant = linear*linear - 4*length*constant
        if discriminant < 0:
            continue
        root = math.sqrt(discriminant)
        lo, hi = max(0, (-linear-root)/(2*length)), min(1, (-linear+root)/(2*length))
        if lo < hi:
            intervals.append((lo, hi))
    total, end = 0.0, 0.0
    for lo, hi in sorted(intervals):
        total += max(0, hi-max(lo, end))
        end = max(end, hi)
    return total
