"""Deterministic contact solver with per-iteration spatial candidate reuse."""
import math
from collections import defaultdict

def resolve_contacts(engine, living, cell_size, padding, iterations):
    population = len(living)
    solver_iterations = (
        2 if population >= 800 else
        4 if population >= 600 else
        8 if population >= 450 else
        iterations
    )
    for _ in range(solver_iterations):
        cells = defaultdict(list)
        neighbors = {}
        for enemy in living:
            cell = (
                math.floor(enemy["x"] / cell_size),
                math.floor(enemy["y"] / cell_size),
            )
            cells[cell].append(enemy)
        contacts = 0
        for enemy in living:
            cell_x = math.floor(enemy["x"] / cell_size)
            cell_y = math.floor(enemy["y"] / cell_size)
            key=(cell_x,cell_y)
            candidates=neighbors.get(key)
            if candidates is None:
                candidates=tuple(other for oy in (-1,0,1) for ox in (-1,0,1) for other in cells.get((cell_x+ox,cell_y+oy),()))
                neighbors[key]=candidates
            for other in candidates:
                other_id=other['id']
                if other_id<=enemy['id']:continue
                dx, dy = other["x"] - enemy["x"], other["y"] - enemy["y"]
                minimum = (
                    enemy["collision_radius"] + other["collision_radius"]
                    + padding
                )
                distance_sq = dx * dx + dy * dy
                if distance_sq >= (minimum - 1e-6) ** 2:
                    continue
                if distance_sq <= 1e-18:
                    angle = (enemy["id"] * 2.399963229728653 + other_id) % (math.pi * 2.0)
                    normal_x, normal_y = math.cos(angle), math.sin(angle)
                    distance = 0.0
                else:
                    distance = math.sqrt(distance_sq)
                    normal_x, normal_y = dx / distance, dy / distance
                # A small deterministic oblique component prevents
                # wall contacts from crystallizing into one-dimensional
                # rows; compression then spills into the open basin.
                jitter = math.sin(
                    enemy["id"] * 12.9898 + other_id * 78.233
                ) * 0.24
                cosine, sine = math.cos(jitter), math.sin(jitter)
                normal_x, normal_y = (
                    normal_x * cosine - normal_y * sine,
                    normal_x * sine + normal_y * cosine,
                )
                correction = (minimum - distance) * 0.74
                enemy["x"] -= normal_x * correction
                enemy["y"] -= normal_y * correction
                other["x"] += normal_x * correction
                other["y"] += normal_y * correction
                engine._constrain_particle(enemy)
                engine._constrain_particle(other)
                contacts += 1
        if contacts == 0:
            break
