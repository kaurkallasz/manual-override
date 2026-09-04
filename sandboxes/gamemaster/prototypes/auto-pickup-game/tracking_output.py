"""Read-only Cal 2 projection and controller intent, independent of any game.

The TPS formula matches the existing LTX display. Coordinates here are always
unrotated, lens-corrected camera coordinates; rotation is a viewer concern.
"""

import copy
import math
import threading
import time


def number(value):
    if isinstance(value, bool) or value is None:
        raise ValueError("finite number required")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("finite number required")
    return value


def solve(matrix, values):
    rows = [list(row) + [value] for row, value in zip(matrix, values)]
    n = len(rows)
    for col in range(n):
        pivot = max(range(col, n), key=lambda i: abs(rows[i][col]))
        if abs(rows[pivot][col]) < 1e-12:
            raise ValueError("Cal 2 points do not span a stable 2D field")
        rows[col], rows[pivot] = rows[pivot], rows[col]
        divisor = rows[col][col]
        rows[col] = [v / divisor for v in rows[col]]
        for row in range(n):
            if row != col:
                factor = rows[row][col]
                rows[row] = [v - factor * p for v, p in zip(rows[row], rows[col])]
    return [row[-1] for row in rows]


def kernel(r2):
    return r2 * math.log(r2) / 2 if r2 > 1e-16 else 0


class Transform:
    def __init__(self, points):
        # Each sample is (input u, input v, output x, output y).
        self.points = points
        n = len(points)
        matrix = [[0.0] * (n + 3) for _ in range(n + 3)]
        for i, (u, v, *_rest) in enumerate(points):
            for j, (cu, cv, *_other) in enumerate(points):
                matrix[i][j] = kernel((u - cu) ** 2 + (v - cv) ** 2)
            matrix[i][i] += 1e-7
            for j, value in enumerate((1, u, v), n):
                matrix[i][j] = matrix[j][i] = value
        self.coefficients = [solve(matrix, [p[axis] for p in points] + [0, 0, 0])
                             for axis in (2, 3)]

    def __call__(self, u, v):
        u, v = number(u), number(v)
        basis = [kernel((u - p[0]) ** 2 + (v - p[1]) ** 2) for p in self.points]
        return [number(sum(a * b for a, b in zip(basis + [1, u, v], coeff)))
                for coeff in self.coefficients]


class CalibrationProjection:
    def __init__(self, calibration):
        self.models = {}
        for side in ("green", "purple"):
            try:
                arm = calibration["arms"][side]
                samples = [tuple(number(v) for v in (
                    p["camera"]["u"], p["camera"]["v"], p["pose"]["x"], p["pose"]["y"]))
                    for p in arm["points"].values() if p.get("camera") and p.get("pose", {}).get("set")]
                if len(samples) != 6:
                    raise ValueError("six Cal 2 camera/robot points required")
                forward = Transform(samples)
                reverse = Transform([(x / 500, y / 500, u, v) for u, v, x, y in samples])
                parallax = [tuple(number(v) for v in (
                    p["raised"]["u"], p["raised"]["v"], p["ground"]["u"], p["ground"]["v"]))
                    for p in arm.get("parallax_points", {}).values() if p and p.get("raised") and p.get("ground")]
                raised = Transform(parallax) if len(parallax) == 4 else None
                pickup = arm.get("pickup_height")
                pickup = number(pickup) if pickup is not None else None
                stack = number(arm.get("stack_drop_offset", 31.5))
                self.models[side] = (forward, reverse, raised, pickup, stack)
            except (KeyError, TypeError, ValueError, OverflowError) as exc:
                self.models[side] = str(exc)

    def project(self, tags, arms):
        result = {}
        for side, model in self.models.items():
            if isinstance(model, str):
                result[side] = {"status": "unavailable", "error": model, "tags": []}
                continue
            forward, reverse, raised, pickup, stack = model
            output = {"status": "ready", "error": None, "tags": [],
                      "base_camera": reverse(0, 0), "tcp_camera": None, "target_camera": None,
                      "height_basis": "Cal 2 estimate; excludes player-local fine tuning"}
            arm = arms.get(side) or {}
            for key, pose in (("tcp_camera", arm.get("pose")), ("target_camera", arm.get("target")
                              if arm.get("control_mode") == "cartesian" else None)):
                if pose and arm.get("connected"):
                    output[key] = reverse(number(pose[0]) / 500, number(pose[1]) / 500)
            for tag in tags:
                tag_id = int(tag["id"])
                physical = tag_id >= 100  # Existing hardware family, not game ownership.
                item = {"id": tag_id, "status": "ready", "error": None}
                if physical and raised is None:
                    item.update(status="unavailable", error="four raised-tag parallax samples required")
                else:
                    uv = raised(tag["nx"], tag["ny"]) if physical else [tag["nx"], tag["ny"]]
                    item.update(ground_camera=uv, robot_xy=forward(*uv), pickup_z=pickup,
                                drop_z=None if pickup is None else pickup + 1 + (stack if physical else 0))
                output["tags"].append(item)
            result[side] = output
        return {"contract": "hhh.cal2.projection", "version": 1, "status": "ready",
                "coordinate_space": "corrected-camera-normalized", "units": "mm", "arms": result}


class IntentStore:
    """Last authenticated controller report, never physical truth or commands."""
    STAGES = frozenset(("operation_started", "source_hover", "source_pickup", "suction_start",
        "suction_completed", "lift", "target_hover", "target_descent_started", "target_pose_reached",
        "release_started", "release_completed", "blow_started", "blow_completed", "return_hover",
        "operation_completed", "operation_failed", "script_paused", "script_resumed", "script_stopped"))

    def __init__(self):
        self.lock = threading.Lock()
        self.arms = {}

    def record(self, side, kind, detail, now=None):
        if side not in ("green", "purple") or kind not in self.STAGES:
            return
        now = time.time() if now is None else now
        with self.lock:
            old = self.arms.get(side, {})
            operation = str(detail.get("operation_id") or "")[:128]
            if not operation and not kind.startswith("script_"):
                return
            if operation and kind != "operation_started" and old and old.get("operation_id") != operation:
                return  # A delayed report must not overwrite a newer operation.
            item = dict(old) if old.get("operation_id") == operation or not operation else {}
            item.update(stage=kind, reported_at=now, source="controller_report")
            if operation:
                item["operation_id"] = operation
            for key in ("physical_tag", "target_marker"):
                value = detail.get(key)
                if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 999:
                    item[key] = value
            self.arms[side] = item

    def snapshot(self):
        with self.lock:
            return {"contract": "hhh.controller.intent", "version": 1, "status": "ready",
                    "observed_at": time.time(), "arms": copy.deepcopy(self.arms)}
