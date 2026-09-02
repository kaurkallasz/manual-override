"""Parse the production Tiled map into Photon Level's serializable contract."""

from __future__ import annotations

import heapq
import json
import math
from pathlib import Path
from typing import Any

from level_layout import layout_revision

RING_MIN_TURRETS = 8
RING_MAX_TURRETS = 16


def properties(item: dict[str, Any]) -> dict[str, Any]:
    return {
        str(entry["name"]): entry.get("value")
        for entry in item.get("properties", [])
        if entry.get("name") is not None
    }


def _finite_positive(source: dict[str, Any], key: str, *, zero=False) -> float:
    try:
        value = float(source[key])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"level must define finite {key}") from exc
    if not math.isfinite(value) or value < 0.0 or (not zero and value == 0.0):
        raise ValueError(f"{key} must be {'non-negative' if zero else 'positive'} and finite")
    return value


def _tile_draw_offset(alignment: str, width: float, height: float) -> tuple[float, float]:
    value = (alignment or "bottomleft").lower()
    dx = 0.0 if "left" in value else -width if "right" in value else -width / 2.0
    dy = 0.0 if value.startswith("top") else -height if value.startswith("bottom") else -height / 2.0
    return dx, dy


def _tile_object_center(obj: dict[str, Any], alignments: list[tuple[int, str]]) -> tuple[float, float]:
    gid = int(obj["gid"])
    alignment = "bottomleft"
    for first_gid, candidate in alignments:
        if gid < first_gid:
            break
        alignment = candidate
    width, height = float(obj["width"]), float(obj["height"])
    dx, dy = _tile_draw_offset(alignment, width, height)
    local_x, local_y = dx + width / 2.0, dy + height / 2.0
    rotation = math.radians(float(obj.get("rotation", 0.0)))
    cosine, sine = math.cos(rotation), math.sin(rotation)
    return (
        float(obj["x"]) + local_x * cosine - local_y * sine,
        float(obj["y"]) + local_x * sine + local_y * cosine,
    )


def _segments_intersect(a, b, c, d) -> bool:
    if max(a[0], b[0]) + 1e-6 < min(c[0], d[0]) or max(c[0], d[0]) + 1e-6 < min(a[0], b[0]):
        return False
    if max(a[1], b[1]) + 1e-6 < min(c[1], d[1]) or max(c[1], d[1]) + 1e-6 < min(a[1], b[1]):
        return False

    def orientation(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    return (
        orientation(a, b, c) * orientation(a, b, d) <= 1e-6
        and orientation(c, d, a) * orientation(c, d, b) <= 1e-6
    )


def _point_in_polygon(point, points) -> bool:
    inside = False
    previous_x, previous_y = points[-1]
    for current_x, current_y in points:
        if (current_y > point[1]) != (previous_y > point[1]):
            crossing_x = (
                (previous_x - current_x) * (point[1] - current_y)
                / (previous_y - current_y) + current_x
            )
            if point[0] < crossing_x:
                inside = not inside
        previous_x, previous_y = current_x, current_y
    return inside


def _simple_polygon(points) -> bool:
    if len(points) < 3 or len({tuple(point) for point in points}) != len(points):
        return False
    count = len(points)
    for first in range(count):
        first_end = (first + 1) % count
        for second in range(first + 1, count):
            second_end = (second + 1) % count
            if first in {second, second_end} or first_end in {second, second_end}:
                continue
            if _segments_intersect(
                points[first], points[first_end], points[second], points[second_end]
            ):
                return False
    return True


def _shortest_route(edges, start_id: int, core_id: int):
    distances = {start_id: 0.0}
    previous = {}
    queue = [(0.0, start_id)]
    while queue:
        distance, node_id = heapq.heappop(queue)
        if distance != distances.get(node_id):
            continue
        if node_id == core_id:
            break
        for edge in edges.get(node_id, []):
            candidate = distance + edge["cost"]
            if candidate < distances.get(edge["to"], math.inf):
                distances[edge["to"]] = candidate
                previous[edge["to"]] = (node_id, edge)
                heapq.heappush(queue, (candidate, edge["to"]))
    if core_id not in distances:
        raise ValueError(f"spawn node {start_id} cannot reach the core")
    ordered, cursor = [], core_id
    while cursor != start_id:
        parent, edge = previous[cursor]
        ordered.append(edge)
        cursor = parent
    return list(reversed(ordered))


def _points_for_edges(edges):
    points = []
    for edge in edges:
        for point in edge["points"]:
            if not points or point != points[-1]:
                points.append(point)
    return points


def _ring_cycles(sockets, adjacency, core):
    found = set()

    def canonical(path):
        variants = []
        for candidate in (path, list(reversed(path))):
            for index in range(len(candidate)):
                variants.append(tuple(candidate[index:] + candidate[:index]))
        return min(variants)

    def visit(start, current, path):
        for neighbor in adjacency.get(current, set()):
            if neighbor == start:
                if len(path) >= RING_MIN_TURRETS:
                    found.add(canonical(path))
                continue
            if neighbor in path or len(path) >= RING_MAX_TURRETS:
                continue
            visit(start, neighbor, [*path, neighbor])

    for socket_id in sockets:
        visit(socket_id, socket_id, [socket_id])
    valid = []
    for cycle in found:
        points = [(sockets[socket_id]["x"], sockets[socket_id]["y"]) for socket_id in cycle]
        if _simple_polygon(points) and _point_in_polygon((core["x"], core["y"]), points):
            valid.append(list(cycle))
    return sorted(valid, key=lambda cycle: (len(cycle), cycle))


def parse_tiled_level(map_path: str | Path) -> dict[str, Any]:
    """Return the complete runtime geometry without leaking Tiled parsing."""
    map_path = Path(map_path)
    data = json.loads(map_path.read_text(encoding="utf-8"))
    width = int(data["width"] * data["tilewidth"])
    height = int(data["height"] * data["tileheight"])
    map_properties = properties(data)
    marker_size = _finite_positive(map_properties, "aruco_code_footprint_px")
    core_marker_size = _finite_positive(map_properties, "core_aruco_code_footprint_px")
    marker_clearance = _finite_positive(
        map_properties, "force_field_marker_clearance_px", zero=True
    )

    alignments = []
    for reference in data.get("tilesets", []):
        source = reference.get("source")
        if not source:
            continue
        tileset_path = (map_path.parent / source).resolve()
        tileset = json.loads(tileset_path.read_text(encoding="utf-8"))
        alignments.append((
            int(reference["firstgid"]),
            str(tileset.get("objectalignment") or "bottomleft"),
        ))
    alignments.sort()

    layers = {layer["name"]: layer for layer in data["layers"]}
    nodes = {}
    for obj in layers["07 Path Nodes (hidden)"]["objects"]:
        nodes[int(obj["id"])] = {
            "name": obj["name"], "x": float(obj["x"]), "y": float(obj["y"]),
            **properties(obj),
        }
    core_items = [node for node in nodes.values() if node.get("node_kind") == "core"]
    if len(core_items) != 1:
        raise ValueError("level must define exactly one core node")
    core = core_items[0]
    core_id = next(node_id for node_id, node in nodes.items() if node is core)
    spawns = {
        str(node["spawn_group"]): {**node, "object_id": node_id}
        for node_id, node in nodes.items() if node.get("node_kind") == "spawn"
    }
    if len(spawns) != 4:
        raise ValueError("level must define exactly four spawn groups")

    edges = {}
    edge_by_id = {}
    for obj in layers["06 Enemy Path Graph (hidden)"]["objects"]:
        props = properties(obj)
        points = [
            [float(obj["x"]) + float(point["x"]), float(obj["y"]) + float(point["y"])]
            for point in obj.get("polyline", [])
        ]
        if not points:
            first, second = nodes[int(props["from_node"])], nodes[int(props["to_node"])]
            points = [[first["x"], first["y"]], [second["x"], second["y"]]]
        lengths = [
            math.hypot(end[0] - start[0], end[1] - start[1])
            for start, end in zip(points, points[1:])
        ]
        edge = {
            "from": int(props["from_node"]), "to": int(props["to_node"]),
            "cost": float(props.get("base_cost", 1.0)), "points": points,
            "segment_lengths": lengths, "path_length": sum(lengths),
            "edge_id": str(props.get("edge_id", obj["name"])),
        }
        edges.setdefault(edge["from"], []).append(edge)
        if edge["edge_id"] in edge_by_id:
            raise ValueError(f"duplicate path edge: {edge['edge_id']}")
        edge_by_id[edge["edge_id"]] = edge

    route_edge_ids, paths = {}, {}
    for group, spawn in spawns.items():
        route = _shortest_route(edges, spawn["object_id"], core_id)
        route_edge_ids[group] = [edge["edge_id"] for edge in route]
        paths[group] = _points_for_edges(route)

    sockets, socket_by_marker, neighbor_markers = {}, {}, {}
    for obj in layers["09 Square Placement Spots (16)"]["objects"]:
        props = properties(obj)
        if str(obj.get("class") or obj.get("type") or "") != "TowerSocket":
            continue
        socket_id, marker = str(props["socket_id"]), int(props["aruco_id"])
        center_x, center_y = _tile_object_center(obj, alignments)
        if socket_id in sockets or marker in socket_by_marker:
            raise ValueError("socket IDs and ArUco markers must be unique")
        sockets[socket_id] = {
            "socket_id": socket_id, "aruco_id": marker,
            "owner": str(props["owner"]), "x": center_x, "y": center_y,
            "size": float(obj.get("width", 208)), "object_id": int(obj["id"]),
        }
        socket_by_marker[marker] = socket_id
        try:
            neighbor_markers[socket_id] = {
                int(value.strip())
                for value in str(props.get("ring_neighbors") or "").split(",")
                if value.strip()
            }
        except ValueError as exc:
            raise ValueError(f"socket {marker} has invalid ring_neighbors") from exc
    if sorted(socket_by_marker) != list(range(40, 56)):
        raise ValueError("level must map ArUco IDs 40-55 to exactly sixteen sockets")

    adjacency = {}
    for socket_id, markers in neighbor_markers.items():
        marker = sockets[socket_id]["aruco_id"]
        unknown = markers - set(socket_by_marker)
        if unknown or marker in markers:
            raise ValueError(f"socket {marker} has invalid ring neighbors")
        for neighbor_marker in markers:
            neighbor_id = socket_by_marker[neighbor_marker]
            if marker not in neighbor_markers.get(neighbor_id, set()):
                raise ValueError(f"ring_neighbors must be symmetric between {marker} and {neighbor_marker}")
        adjacency[socket_id] = {socket_by_marker[item] for item in markers}
    ring_cycles = _ring_cycles(sockets, adjacency, core)
    if not ring_cycles:
        raise ValueError("level must define at least one valid 8-16 socket ring")

    blockers, blocker_ids = [], set()
    pending_layers = list(data.get("layers", []))
    while pending_layers:
        layer = pending_layers.pop(0)
        pending_layers[0:0] = list(layer.get("layers", []))
        for obj in layer.get("objects", []):
            if str(obj.get("class") or obj.get("type") or "") != "ForceFieldBlocker":
                continue
            props = properties(obj)
            blocker_id = str(props.get("blocker_id") or obj.get("name") or f"blocker-{obj.get('id')}")
            if blocker_id in blocker_ids:
                raise ValueError(f"duplicate ForceFieldBlocker id: {blocker_id}")
            origin_x, origin_y = float(obj.get("x", 0)), float(obj.get("y", 0))
            if obj.get("polygon"):
                points = [
                    [origin_x + float(point["x"]), origin_y + float(point["y"])]
                    for point in obj["polygon"]
                ]
            else:
                object_width, object_height = float(obj.get("width", 0)), float(obj.get("height", 0))
                if object_width <= 0 or object_height <= 0:
                    raise ValueError(f"ForceFieldBlocker {blocker_id} must have an area")
                points = [
                    [origin_x, origin_y], [origin_x + object_width, origin_y],
                    [origin_x + object_width, origin_y + object_height],
                    [origin_x, origin_y + object_height],
                ]
            if not _simple_polygon(points):
                raise ValueError(f"ForceFieldBlocker {blocker_id} must be a simple polygon")
            blocker_ids.add(blocker_id)
            blockers.append({"blocker_id": blocker_id, "points": points})

    return {
        "layout_revision": layout_revision(data), "width": width, "height": height,
        "aruco_code_footprint_px": marker_size,
        "core_aruco_code_footprint_px": core_marker_size,
        "force_field_marker_clearance_px": marker_clearance,
        "nodes": {str(key): value for key, value in nodes.items()},
        "core": core, "spawns": spawns,
        "edges": {str(key): value for key, value in edges.items()},
        "edge_by_id": edge_by_id, "route_edge_ids": route_edge_ids,
        "paths": paths,
        "junctions": [
            [float(node["x"]), float(node["y"])] for node in nodes.values()
            if node.get("node_kind") in {"junction", "arrival", "turnaround"}
        ],
        "sockets": sockets,
        "socket_by_marker": {str(key): value for key, value in socket_by_marker.items()},
        "ring_adjacency": {key: sorted(value) for key, value in adjacency.items()},
        "ring_edges": sorted({
            tuple(sorted((first, second)))
            for first, neighbors in adjacency.items() for second in neighbors
        }),
        "ring_cycles": ring_cycles,
        "force_field_blockers": sorted(blockers, key=lambda item: item["blocker_id"]),
        "map_properties": map_properties,
    }


def simple_level(runtime: dict[str, Any]) -> dict[str, Any]:
    """Small framework projection used by generic educational games."""
    paths = runtime["paths"]
    primary_name = sorted(paths)[0]
    return {
        "name": str(runtime["map_properties"].get("level_id") or "Photon level"),
        "width": runtime["width"], "height": runtime["height"],
        "path": [{"x": point[0], "y": point[1]} for point in paths[primary_name]],
        "paths": {
            name: [{"x": point[0], "y": point[1]} for point in points]
            for name, points in paths.items()
        },
        "sockets": [
            {
                "id": socket["socket_id"], "socket_id": socket["socket_id"],
                "aruco_id": socket["aruco_id"], "owner": socket["owner"],
                "x": socket["x"], "y": socket["y"], "size": socket["size"],
                "radius": runtime["aruco_code_footprint_px"] / 2.0,
            }
            for socket in sorted(runtime["sockets"].values(), key=lambda item: item["aruco_id"])
        ],
    }
