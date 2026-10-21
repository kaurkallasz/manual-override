"""Authored Atom home geometry, independent of the sixteen construction sockets."""
import math


def parse(data, width, height, sockets):
    homes = []
    for layer in data['layers']:
        for obj in layer.get('objects', []):
            if (obj.get('class') or obj.get('type')) != 'AtomHome':
                continue
            p = {v['name']: v['value'] for v in obj.get('properties', [])}
            home = {key: p[key] for key in ('owner', 'slot', 'turret_x', 'turret_y', 'pod_size')}
            home.update(x=obj['x'] + obj['width']/2, y=obj['y'] + obj['height']/2, size=obj['width'])
            if obj['width'] != obj['height']:
                raise ValueError('Atom home platforms must be square')
            homes.append(home)
    if not homes:
        return []  # Older levels keep their original behavior.
    if len(homes) != 4 or {(h['owner'], h['slot']) for h in homes} != {
            (side, slot) for side in ('green', 'purple') for slot in (0, 1)}:
        raise ValueError('Atom homes require two slots per team')
    bounds = []
    for h in homes:
        if type(h['slot']) is not int or any(type(h[k]) not in (int, float) or not math.isfinite(h[k])
                for k in ('x', 'y', 'size', 'turret_x', 'turret_y', 'pod_size')):
            raise ValueError('Atom home geometry must be finite')
        for x, y, size in ((h['x'], h['y'], h['size']), (h['turret_x'], h['turret_y'], h['pod_size'])):
            if not 48 <= size <= 112 or not size/2 <= x <= width-size/2 or not size/2 <= y <= height-size/2:
                raise ValueError('Atom home outside the playfield')
            bounds.append((x, y, size/2))
    obstacles = [(s['marker_x'], s['marker_y'], s['marker_size']/2) for s in sockets.values()]
    obstacles += [(s['x'], s['marker_y'], 56) for s in sockets.values()]
    obstacles += [(c['visual_x'], c['visual_y'], c['pod_size']/2) for s in sockets.values()
                  if (c := s.get('companion', {})).get('eligible')]
    for i, (x, y, radius) in enumerate(bounds):
        for ox, oy, other in bounds[i+1:] + obstacles:
            if abs(x-ox) < radius+other+4 and abs(y-oy) < radius+other+4:
                raise ValueError('Atom homes overlap another platform, turret or marker')
    return sorted(homes, key=lambda h: (h['owner'], h['slot']))
