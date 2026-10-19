"""Qualified fixed coordinates shared by placement and camera-only occupancy."""
import math


def read_anchors(value, now):
    """Read the existing scoped map, never display memory or renewed sightings."""
    if (not isinstance(value, dict) or value.get('contract') != 'photon.board.cue-targets'
            or type(value.get('version')) is not int or value['version'] != 2
            or value.get('coordinate_space') != 'corrected-camera-normalized'
            or not isinstance(value.get('layout_scope'), str) or not value['layout_scope']
            or not isinstance(value.get('epoch'), str) or not value['epoch']):
        raise ValueError('Invalid fixed target map contract')
    ids = value.get('fixed_ids')
    if (not isinstance(ids, list) or not 1 <= len(ids) <= 30
            or any(type(i) is not int or not 30 <= i <= 59 for i in ids)
            or len(set(ids)) != len(ids)):
        raise ValueError('Invalid fixed target map layout')
    if (value.get('status') != 'ready' or value.get('board_motion_ids')
            or any(type(value.get(k)) not in (int, float) or not math.isfinite(value[k])
                   or not 0 <= now - value[k] <= 1.5 for k in ('sampled_at', 'frame_at'))):
        raise ValueError(value.get('error') or 'Fixed target map unavailable or stale')
    blocked, pending = value.get('blocked_fixed_ids'), value.get('pending_fixed_ids')
    if any(not isinstance(items, list) or any(type(i) is not int or i not in ids for i in items)
           for items in (blocked, pending)):
        raise ValueError('Invalid fixed target map conflicts')
    tags = value.get('tags')
    if not isinstance(tags, list) or len(tags) > 128:
        raise ValueError('Invalid fixed target map observations')
    anchors = {}
    for tag in tags:
        if not isinstance(tag, dict) or type(tag.get('id')) is not int:
            raise ValueError('Invalid fixed target identity')
        ident = tag['id']
        if ident >= 100:
            continue  # Moving Atoms retain their existing live detection rules.
        if (ident not in ids or ident in anchors or tag.get('fixed') is not True
                or any(type(tag.get(k)) not in (int, float) or not math.isfinite(tag[k])
                       or not 0 <= tag[k] <= 1 for k in ('nx', 'ny'))
                or type(tag.get('last_seen')) not in (int, float)
                or not math.isfinite(tag['last_seen']) or tag['last_seen'] > value['frame_at']):
            raise ValueError('Invalid confirmed fixed target')
        anchors[ident] = {'nx': tag['nx'], 'ny': tag['ny'], 'seen_at': tag['last_seen']}
    states = [{'marker_id': i, 'status': 'target_position_disputed' if i in blocked
               else 'ready' if i in anchors else 'target_not_learned',
               'last_seen': anchors.get(i, {}).get('seen_at')} for i in ids]
    return ({i: p for i, p in anchors.items() if i not in blocked},
            (value['layout_scope'], value['epoch']), states, set(pending))
