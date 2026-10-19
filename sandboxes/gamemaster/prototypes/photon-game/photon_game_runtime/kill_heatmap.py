"""Bounded per-run kill locations in playfield coordinates, including core purge."""
import copy
import math


class KillHeatmap:
    def __init__(self, level):
        self.value = {'version': 1, 'columns': 32, 'rows': 18,
                      'width': level.width, 'height': level.height,
                      'counts': [0] * (32 * 18), 'unlocated': 0,
                      'core': [level.core['x'], level.core['y']],
                      'roads': [[list(point) for point in edge['points']] for edge in level.edge_by_id.values()],
                      'markers': [[s['x'],s['y'],s['aruco_id']] for s in level.sockets.values()]}

    def killed(self, enemy):
        x, y = enemy.get('x'), enemy.get('y')
        v = self.value
        if not all(isinstance(n, (int, float)) and math.isfinite(n) for n in (x, y)):
            v['unlocated'] += 1
            return
        col = max(0, min(v['columns'] - 1, int(x / v['width'] * v['columns'])))
        row = max(0, min(v['rows'] - 1, int(y / v['height'] * v['rows'])))
        v['counts'][row * v['columns'] + col] += 1

    def snapshot(self):
        return copy.deepcopy(self.value)
