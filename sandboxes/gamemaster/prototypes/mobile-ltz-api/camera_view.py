"""Presentation-only registration of level markers to corrected camera pixels."""
import math
import time


def project(matrix, x, y):
    d = matrix[6]*x + matrix[7]*y + 1
    if abs(d) < 1e-8:
        raise ValueError('Camera registration is degenerate.')
    return ((matrix[0]*x+matrix[1]*y+matrix[2])/d,
            (matrix[3]*x+matrix[4]*y+matrix[5])/d)


def registration(level, board):
    """Return normalized map -> normalized corrected-image homography."""
    now = time.time()
    if (board.get('contract') != 'photon.board.runtime' or type(board.get('version')) is not int
            or board['version'] != 1 or board.get('status') != 'ready'
            or not board.get('corrected') or board.get('source') == 'simulation'
            or not isinstance(board.get('frame_at'), (int, float))
            or not -1 <= now-board['frame_at'] <= 2):
        raise ValueError('Camera tracking is unavailable or stale.')
    width, height = float(level['width']), float(level['height'])
    centers = {int(s['aruco_id']): (float(s.get('marker_x', s['x']))/width,
               float(s.get('marker_y', s['y']))/height) for s in level['sockets']}
    core = level.get('core') or {}
    if 'marker_x' in core and 'marker_y' in core:
        centers[38] = (float(core['marker_x'])/width, float(core['marker_y'])/height)
    pairs = {}
    for tag in board.get('tags', []):
        ident = tag.get('id')
        if ident not in centers or not tag.get('tracked', True) or float(tag.get('missing', 0)) > .25:
            continue
        u, v = float(tag['nx']), float(tag['ny'])
        if not all(math.isfinite(n) and 0 <= n <= 1 for n in (u,v)):
            continue
        if ident in pairs:
            raise ValueError('Duplicate camera marker IDs; alignment unavailable.')
        pairs[ident] = (*centers[ident], u, v)
    if len(pairs) < 4:
        raise ValueError('Show at least four level markers to align turret controls.')
    rows = []
    for x,y,u,v in pairs.values():
        rows.extend(([x,y,1,0,0,0,-u*x,-u*y,u], [0,0,0,x,y,1,-v*x,-v*y,v]))
    # Small least-squares system, normalized inputs, pivoted elimination.
    system = [[sum(r[i]*r[j] for r in rows) for j in range(9)] for i in range(8)]
    for i in range(8):
        pivot = max(range(i,8), key=lambda k:abs(system[k][i]))
        system[i], system[pivot] = system[pivot], system[i]
        divisor = system[i][i]
        if abs(divisor) < 1e-9:
            raise ValueError('Spread the visible markers across the playfield for alignment.')
        system[i] = [v/divisor for v in system[i]]
        for j in range(8):
            if j != i:
                f = system[j][i]
                system[j] = [a-f*b for a,b in zip(system[j],system[i])]
    matrix = [row[8] for row in system]
    if any(math.hypot(project(matrix,x,y)[0]-u,project(matrix,x,y)[1]-v) > .018
           for x,y,u,v in pairs.values()):
        raise ValueError('Camera markers do not match this level layout.')
    # A projective horizon through the level would flip the overlay.
    denominators = [matrix[6]*x+matrix[7]*y+1 for x,y in ((0,0),(1,0),(1,1),(0,1))]
    if min(denominators) <= .05:
        raise ValueError('Camera alignment is unstable.')
    return matrix, sorted(pairs)
