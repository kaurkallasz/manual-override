"""Bounded per-run kill locations in playfield coordinates, including core purge."""
import copy
import math


class KillHeatmap:
    MAX_EVENTS = 8192

    def __init__(self, level):
        self.bin_seconds = 1
        self.events = {}
        self.value = {'version': 1, 'columns': 32, 'rows': 18,
                      'width': level.width, 'height': level.height,
                      'counts': [0] * (32 * 18), 'unlocated': 0,
                      'core': [level.core['x'], level.core['y']],
                      'roads': [[list(point) for point in edge['points']] for edge in level.edge_by_id.values()],
                      'markers': [[s['x'],s['y'],s['aruco_id']] for s in level.sockets.values()]}
        self.value['floor'] = copy.deepcopy(getattr(level, 'replay_floor', None))

    def killed(self, enemy, active_seconds):
        if not isinstance(active_seconds, (int, float)) or not math.isfinite(active_seconds) or active_seconds < 0:
            raise ValueError('Invalid kill time')
        x, y = enemy.get('x'), enemy.get('y')
        v = self.value
        if not all(isinstance(n, (int, float)) and math.isfinite(n) for n in (x, y)):
            v['unlocated'] += 1
            cell = -1
        else:
            col = max(0, min(v['columns'] - 1, int(x / v['width'] * v['columns'])))
            row = max(0, min(v['rows'] - 1, int(y / v['height'] * v['rows'])))
            cell = row * v['columns'] + col
            v['counts'][cell] += 1
        key = (int(active_seconds // self.bin_seconds), cell)
        previous = self.events.get(key, [0, 0])
        self.events[key] = [max(active_seconds, previous[0]), previous[1] + 1]
        # Merge nearby times, never locations or totals. The latest real kill time
        # in each bin prevents showing kills before they happened, even at finish.
        while len(self.events) > self.MAX_EVENTS:
            self.bin_seconds *= 2
            merged = {}
            for (bucket, cell), (at, count) in self.events.items():
                key = (bucket // 2, cell)
                previous = merged.get(key, [0, 0])
                merged[key] = [max(at, previous[0]), previous[1] + count]
            self.events = merged

    def snapshot(self):
        value = copy.deepcopy(self.value)
        value['timeline'] = {'version': 1, 'bin_seconds': self.bin_seconds,
                             'events': sorted([at, cell, count] for (_, cell), (at, count) in self.events.items())}
        return value
