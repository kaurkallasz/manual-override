"""Shared corrected-camera marker geometry checks; no hardware or state."""
import math


def marker_size(tag, width, height):
    """Mean edge length in corrected pixels, independent of tag rotation."""
    corners = tag.get("ncorners")
    if not isinstance(corners, list) or len(corners) != 4:
        return None
    if any(not isinstance(p, (list, tuple)) or len(p) != 2
           or any(type(n) not in (int, float) or not math.isfinite(n) for n in p)
           for p in corners):
        return None
    points = [(x * width, y * height) for x, y in corners]
    edges = [(points[(i+1) % 4][0]-x, points[(i+1) % 4][1]-y)
             for i, (x, y) in enumerate(points)]
    turns = [dx * edges[(i+1) % 4][1] - dy * edges[(i+1) % 4][0]
             for i, (dx, dy) in enumerate(edges)]
    if not (all(n > 1e-9 for n in turns) or all(n < -1e-9 for n in turns)):
        return None  # Collapsed, crossed or non-convex corners cannot establish size.
    return sum(math.hypot(dx, dy) for dx, dy in edges) / 4


def marker_geometry(tag, width, height):
    """Size plus rotation-independent edge/diagonal proportions for a fixed tag."""
    size = marker_size(tag, width, height)
    if size is None or size <= 0 or any(not 0 <= n <= 1 for p in tag['ncorners'] for n in p):
        return None
    points = [(x*width, y*height) for x,y in tag['ncorners']]
    lengths = lambda step: [math.dist(p, points[(i+step) % 4])/size
                            for i,p in enumerate(points)]
    # Sorting permits rotation/corner reindexing without accepting a skinny or
    # sheared quadrilateral that happens to have the same average side length.
    return {'size': size, 'shape': sorted(lengths(1)) + sorted(lengths(2)[:2])}


def size_consistent_markers(tags, width, height):
    """A unique largest group whose maximum/minimum side length is <= 1.15."""
    ratio = 1.15
    sizes = {tag["id"]: marker_size(tag, width, height) for tag in tags}
    measured = sorted((size, ident) for ident, size in sizes.items() if size is not None)
    groups, largest = [], 0
    for start, (smallest, _) in enumerate(measured):
        group = {ident for size, ident in measured[start:] if size <= smallest * ratio + 1e-9}
        if len(group) > largest:
            groups, largest = [group], len(group)
        elif len(group) == largest:
            groups.append(group)
    # One tag cannot verify its own size. Equal competing groups are ambiguous.
    accepted = groups[0] if largest >= 2 and len(groups) == 1 else set()
    result = {"max_ratio": ratio, "status": "ready" if accepted else "unavailable",
              "minimum_px": min(sizes[i] for i in accepted) if accepted else None,
              "maximum_px": max(sizes[i] for i in accepted) if accepted else None,
              "rejected": [{"id": ident, "size_px": size,
                            "reason": "invalid_corners" if size is None else
                                      "size_outlier" if accepted else "no_size_consensus"}
                           for ident, size in sizes.items() if ident not in accepted]}
    return [tag for tag in tags if tag["id"] in accepted], result
