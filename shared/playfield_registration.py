"""Presentation-only registration of level markers to corrected camera pixels."""
import math
import time


def project(matrix, x, y):
    d = matrix[6]*x + matrix[7]*y + 1
    if abs(d) < 1e-8:
        raise ValueError('Camera registration is degenerate.')
    return ((matrix[0]*x+matrix[1]*y+matrix[2])/d,
            (matrix[3]*x+matrix[4]*y+matrix[5])/d)


def registration(level, board, *, diagnostics=None):
    """Return normalized map -> normalized corrected-image homography."""
    if diagnostics is None:
        diagnostics = {}
    diagnostics.update(required_count=4, detected_count=0, matched_count=0,
                       detected_ids=[], matched_ids=[], size_rejected_ids=[])
    now = time.time()
    if (not isinstance(board, dict) or board.get('contract') != 'photon.board.camera-markers' or type(board.get('version')) is not int
            or board['version'] != 1 or board.get('status') != 'ready'
            or board.get('coordinate_space') != 'corrected-camera-normalized' or board.get('source') != 'camera'
            or type(board.get('max_age_s')) not in (int,float) or not 0 < board['max_age_s'] <= 1.5
            or type(board.get('frame_at')) not in (int,float)
            or any(type(board.get(k)) not in (int,float) or not math.isfinite(board[k]) or board[k] <= 0 for k in ('width','height'))
            or not -.25 <= now-board['frame_at'] <= board['max_age_s']):
        raise ValueError('Camera tracking is unavailable or stale. Waiting for a fresh frame.')
    width, height = float(level['width']), float(level['height'])
    centers = {int(s['aruco_id']): (float(s.get('marker_x', s['x']))/width,
               float(s.get('marker_y', s['y']))/height) for s in level['sockets']}
    core = level.get('core') or {}
    if 'marker_x' in core and 'marker_y' in core:
        centers[38] = (float(core['marker_x'])/width, float(core['marker_y'])/height)
    diagnostics['expected_ids'] = sorted(centers)
    size_filter = board.get('size_filter') or {}
    diagnostics['size_rejected_ids'] = [t['id'] for t in size_filter.get('rejected', [])]
    pairs = {}
    detected = set()
    if not isinstance(board.get('tags'), list):
        raise ValueError('Camera marker evidence is malformed.')
    for tag in board['tags']:
        if not isinstance(tag, dict):
            raise ValueError('Camera marker evidence is malformed.')
        ident = tag.get('id')
        if type(ident) is not int or ident < 0 or ident in detected:
            raise ValueError('Duplicate or invalid camera marker IDs; alignment unavailable.')
        point = tag.get('camera')
        if (not isinstance(point, list) or len(point) != 2
                or any(type(n) not in (int,float) or not math.isfinite(n) or not 0 <= n <= 1 for n in point)):
            raise ValueError('Camera marker coordinates are invalid.')
        if type(tag.get('last_seen')) not in (int,float) or not -.25 <= now-tag['last_seen'] <= board['max_age_s']:
            continue
        detected.add(ident)
        if ident not in centers:
            continue
        u, v = point
        pairs[ident] = (*centers[ident], u, v)
    diagnostics.update(detected_count=len(detected), matched_count=len(pairs),
                       detected_ids=sorted(detected), matched_ids=sorted(pairs))
    if len(pairs) < 4:
        rejection = f" {len(diagnostics['size_rejected_ids'])} rejected by the 15% size check." if diagnostics['size_rejected_ids'] else ''
        raise ValueError(f'{len(detected)} markers detected; {len(pairs)} match this level.{rejection} At least 4 spread-out level markers are needed to align turret controls.')
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
