"""Deterministic, read-only physical diagnostics. No game or robot commands.

Only the Board sampler calls update(); HTTP readers never advance this state.
The >=100 marker family identifies raised hardware tags, not player ownership.
"""

import copy
import math
import time

STALE_S = 1.5
MARKER_MEMORY_S = 5.0
CARRY_MEMORY_S = 15.0
NEAR_XY_MM = 90.0
NEAR_Z_MM = 60.0
UNIQUE_MARGIN_MM = 20.0
PLACEMENT_MM = 18.0
PLACEMENT_DWELL_S = 0.55
GAME_PLACEMENT_DISTANCE = 0.05
GAME_MARKER_MEMORY_S = 120.0
MAX_PLACEMENT_RELATIONS = 512
DEFAULT_SETTINGS = {"near_xy_mm": NEAR_XY_MM, "near_z_mm": NEAR_Z_MM,
                    "unique_margin_mm": UNIQUE_MARGIN_MM, "stale_s": STALE_S}
SETTING_BOUNDS = {"near_xy_mm": (1, 1000), "near_z_mm": (1, 500),
                  "unique_margin_mm": (0, 500), "stale_s": (0.2, 5)}


def validate_settings(value):
    if not isinstance(value, dict) or set(value) != set(DEFAULT_SETTINGS):
        raise ValueError("All four diagnostic settings are required; unknown fields are not allowed")
    clean = {}
    for key, (minimum, maximum) in SETTING_BOUNDS.items():
        number = value[key]
        if type(number) not in (int, float) or not math.isfinite(number) or not minimum <= number <= maximum:
            raise ValueError(f"{key} must be a finite number from {minimum} to {maximum}")
        clean[key] = float(number)
    return clean


def fresh(stamp, now, limit=STALE_S):
    return isinstance(stamp, (float, int)) and not isinstance(stamp, bool) and math.isfinite(stamp) and -0.25 <= now - stamp <= limit


def distance(pose, xy, z, limits=None):
    limits = DEFAULT_SETTINGS if limits is None else limits
    horizontal = math.hypot(pose[0] - xy[0], pose[1] - xy[1])
    vertical = abs(pose[2] - z) if z is not None else None
    near = vertical is not None and horizontal <= limits["near_xy_mm"] and vertical <= limits["near_z_mm"]
    ratio = max(horizontal / limits["near_xy_mm"], vertical / limits["near_z_mm"]) if vertical is not None else math.inf
    return {"xy_mm": round(horizontal, 1), "z_mm": None if vertical is None else round(vertical, 1),
            "near": near, "fill": round(max(0, min(100, 100 * (1 - min(ratio, 3) / 3))))}


class PhysicalPlacementTracker:
    """Publish stable camera relationships without knowing Level or game rules.

    The policy constants intentionally match the physical evidence policy that
    Photon Game used before Phase 8. Board owns only the observation that a
    movable tag remained near a fixed marker while an arm was available. Game
    still decides tag ownership, marker meaning, and whether an action is legal.
    """

    def __init__(self):
        self.source = None
        self.source_epoch = f"{time.time_ns():x}"
        self.revision = 0
        self.marker_cache = {}
        self.orders = {}
        self.generations = {}

    def reset_evidence(self, *, clear_markers=False):
        self.orders.clear()
        if clear_markers:
            self.marker_cache.clear()

    @staticmethod
    def unavailable(error, *, revision=0, source="unknown", source_epoch="unknown", sampled_at=None):
        return {
            "contract": "photon.board.placement", "version": 1,
            "revision": revision, "status": "unavailable", "error": str(error)[:500],
            "source": source, "source_epoch": source_epoch,
            "sampled_at": sampled_at, "coordinate_space": "corrected-camera-normalized",
            "relations": [],
            "policy": {
                "distance": GAME_PLACEMENT_DISTANCE,
                "stable_s": PLACEMENT_DWELL_S,
                "marker_memory_s": GAME_MARKER_MEMORY_S,
            },
        }

    def update(self, runtime, now):
        self.revision += 1
        source = str(runtime.get("source") or "unknown")
        if self.source != source:
            self.source = source
            self.source_epoch = f"{time.time_ns():x}"
            self.reset_evidence(clear_markers=True)
        if runtime.get("status") != "ready" or not fresh(runtime.get("frame_at"), now):
            self.reset_evidence()
            return self.unavailable(
                "Physical evidence unavailable or camera frame stale",
                revision=self.revision, source=source,
                source_epoch=self.source_epoch, sampled_at=now,
            )

        current = {
            int(tag["id"]): tag
            for tag in runtime.get("tags", [])
            if tag.get("id") is not None and float(tag.get("missing", 0.0)) <= 0.35
        }
        frame_at = float(runtime["frame_at"])
        for marker, tag in current.items():
            if marker >= 100:
                continue
            nx, ny = tag.get("nx"), tag.get("ny")
            if type(nx) in (int, float) and type(ny) in (int, float):
                self.marker_cache[marker] = {
                    "nx": float(nx), "ny": float(ny), "seen_at": frame_at,
                }
        self.marker_cache = {
            marker: value for marker, value in self.marker_cache.items()
            if now - value["seen_at"] <= GAME_MARKER_MEMORY_S
        }

        active_keys = set()
        relations = []
        for side in ("green", "purple"):
            arm = (runtime.get("arms") or {}).get(side) or {}
            arm_ready = (
                bool(arm.get("connected"))
                and arm.get("enabled", True) is not False
                and str(arm.get("pump_mode") or "off") == "off"
                and fresh(arm.get("feedback_at"), now)
            )
            if not arm_ready:
                continue
            for movable, tag in sorted(current.items()):
                if movable < 100:
                    continue
                nx, ny = float(tag["nx"]), float(tag["ny"])
                nearby = sorted(
                    (
                        math.hypot(nx - target["nx"], ny - target["ny"]),
                        marker,
                        target["seen_at"],
                    )
                    for marker, target in self.marker_cache.items()
                    if math.hypot(nx - target["nx"], ny - target["ny"])
                    <= GAME_PLACEMENT_DISTANCE
                )
                if not nearby:
                    continue
                key = (side, movable)
                active_keys.add(key)
                signature = tuple(marker for _distance, marker, _seen_at in nearby)
                order = self.orders.get(key)
                if order is None or order["signature"] != signature:
                    generation = self.generations.get(key, 0) + 1
                    self.generations[key] = generation
                    order = self.orders[key] = {
                        "signature": signature, "since": now,
                        "generation": generation,
                    }
                stable_at = order["since"] + PLACEMENT_DWELL_S
                stable = now >= stable_at
                for rank, (separation, marker, marker_seen_at) in enumerate(nearby):
                    relations.append({
                        "relation_id": (
                            f"{self.source_epoch}:{side}:{movable}:{marker}:"
                            f"{order['generation']}"
                        ),
                        "movable_id": movable, "marker_id": marker,
                        "arm": side, "rank": rank,
                        "distance": round(separation, 6),
                        "observed_since": order["since"],
                        "stable_at": stable_at, "stable": stable,
                        "marker_seen_at": marker_seen_at,
                    })
                    if len(relations) > MAX_PLACEMENT_RELATIONS:
                        self.reset_evidence()
                        return self.unavailable(
                            "Physical placement relation limit exceeded",
                            revision=self.revision, source=source,
                            source_epoch=self.source_epoch, sampled_at=now,
                        )
        for key in set(self.orders) - active_keys:
            self.orders.pop(key, None)
        return {
            "contract": "photon.board.placement", "version": 1,
            "revision": self.revision, "status": "ready", "error": None,
            "source": source, "source_epoch": self.source_epoch,
            "sampled_at": now, "coordinate_space": "corrected-camera-normalized",
            "relations": relations,
            "policy": {
                "distance": GAME_PLACEMENT_DISTANCE,
                "stable_s": PLACEMENT_DWELL_S,
                "marker_memory_s": GAME_MARKER_MEMORY_S,
            },
        }


class BoardTracker:
    def __init__(self, settings=None):
        self.settings = validate_settings(DEFAULT_SETTINGS if settings is None else settings)
        self.records = {}
        self.considered = {}
        self.bound = {}
        self.pumps = {}
        self.placements = {}
        self.source = None
        self.revision = 0
        self.last_frame = None
        self.last_update = None

    def reset_evidence(self):
        self.considered.clear()
        self.bound.clear()
        self.pumps.clear()
        self.placements.clear()
        self.last_frame = None

    def update(self, runtime, projection, intents, now):
        stale_s = self.settings["stale_s"]
        self.revision += 1
        if self.last_update is not None and now - self.last_update > stale_s:
            self.reset_evidence()
        self.last_update = now
        if self.source != runtime.get("source"):
            self.records.clear()
            self.reset_evidence()
            self.source = runtime.get("source")
        valid = runtime.get("status") == "ready" and fresh(runtime.get("frame_at"), now, stale_s)
        errors = list(runtime.get("errors", []))
        if not valid:
            self.reset_evidence()
            errors.append("Physical evidence unavailable or camera frame stale; transport inference cleared")
        visible = set(runtime.get("visible_ids", [])) if valid else set()
        for tag in runtime.get("detections", []) if valid else []:
            if tag["id"] in visible and tag.get("missing", 0) <= stale_s:
                self.records[tag["id"]] = {"tag": copy.deepcopy(tag), "last_seen": runtime["frame_at"]}
        # Retain bounded, explicitly aged evidence, never forever-cached targets.
        self.records = {key: rec for key, rec in self.records.items()
                        if now - rec["last_seen"] <= (CARRY_MEMORY_S if key >= 100 else MARKER_MEMORY_S)}
        frame_new = valid and runtime.get("frame_at") != self.last_frame
        if valid:
            self.last_frame = runtime.get("frame_at")
        projected = projection.get("arms", {}) if projection else {}
        arms = {}
        choices = {}
        for side in ("green", "purple"):
            raw = runtime.get("arms", {}).get(side, {})
            calibrated = projected.get(side, {})
            pose = raw.get("pose")
            arm_ok = bool(raw.get("connected")) and pose is not None and fresh(raw.get("feedback_at"), now, stale_s)
            arm = {"status": "ready" if arm_ok else "unavailable", "pose": pose if arm_ok else None,
                   "pump_mode": raw.get("pump_mode", "unknown") if arm_ok else "unknown",
                   "feedback_age_s": round(max(0, now - raw["feedback_at"]), 2) if raw.get("feedback_at") else None,
                   "calibration_status": calibrated.get("status", "unavailable"),
                   "error": None if arm_ok else "Disconnected, missing or stale arm feedback",
                   "calibration_error": calibrated.get("error") or (None if calibrated.get("status") == "ready" else "Cal 2 projection unavailable"),
                   "candidates": [], "targets": [], "considered_tag": None, "ambiguous": False,
                   "carried_tag": None, "command_distance": None, "controller": None,
                   "base_camera": None, "tcp_camera": None, "target_camera": None}
            report = (intents or {}).get("arms", {}).get(side)
            if isinstance(report, dict):
                arm["controller"] = dict(report, stale=not fresh(report.get("reported_at"), now, 30))
            if arm_ok and raw.get("control_mode") == "cartesian" and raw.get("target"):
                arm["command_distance"] = distance(pose, raw["target"][:2], raw["target"][2], self.settings)
            elif arm_ok and raw.get("target"):
                arm["command_distance_error"] = "Target is not Cartesian; joint angles are not millimetres"
            points = {p["id"]: p for p in calibrated.get("tags", []) if p.get("status") == "ready"}
            if valid and arm_ok and calibrated.get("status") == "ready":
                for field in ("base_camera", "tcp_camera", "target_camera"):
                    arm[field] = calibrated.get(field)
                for tag_id, rec in self.records.items():
                    if tag_id not in points:
                        if tag_id >= 100:
                            arm["candidates"].append({"id": tag_id, "status": "unavailable",
                                "error": "Raised-tag calibration unavailable", "considered": False})
                        continue
                    point = points[tag_id]
                    age = max(0, now - rec["last_seen"])
                    if tag_id >= 100:
                        metric = distance(pose, point["robot_xy"], point.get("pickup_z"), self.settings)
                        metric.update(id=tag_id, visible=tag_id in visible, age_s=round(age, 2), considered=False,
                                      status="ready" if age <= stale_s else "stale")
                        arm["candidates"].append(metric)
                    if age <= MARKER_MEMORY_S:
                        metric = distance(pose, point["robot_xy"], point.get("drop_z"), self.settings)
                        metric.update(id=tag_id, visible=tag_id in visible, age_s=round(age, 2),
                                      camera=[rec["tag"]["nx"], rec["tag"]["ny"]],
                                      requested=bool(report and not arm["controller"]["stale"] and report.get("target_marker") == tag_id))
                        arm["targets"].append(metric)
                arm["candidates"].sort(key=lambda c: c.get("xy_mm", math.inf))
                arm["targets"].sort(key=lambda c: (not c["requested"], c["xy_mm"]))
                candidates = [c for c in arm["candidates"] if c.get("status") == "ready"]
                if candidates and candidates[0]["near"]:
                    gap = candidates[1]["xy_mm"] - candidates[0]["xy_mm"] if len(candidates) > 1 else math.inf
                    ambiguous = gap <= 0 or gap < self.settings["unique_margin_mm"]
                    arm["ambiguous"] = ambiguous
                    if not ambiguous:
                        choices[side] = candidates[0]["id"]
            else:
                self.bound.pop(side, None)
                self.considered.pop(side, None)
                self.pumps.pop(side, None)
            arms[side] = arm
        if len(choices) == 2 and len(set(choices.values())) == 1:
            choices.clear()
            for arm in arms.values():
                arm["ambiguous"] = True
                arm["error"] = "Both arms consider the same tag; no unique association"

        stages = {}
        for side, arm in arms.items():
            if arm["ambiguous"]:
                self.considered.pop(side, None)
                self.bound.pop(side, None)
            choice = choices.get(side)
            arm["considered_tag"] = choice
            for item in arm["candidates"]:
                item["considered"] = item["id"] == choice
            pump = arm["pump_mode"]
            old = self.considered.get(side)
            binding = self.bound.get(side)
            if not binding and old and old["id"] not in visible and pump == "suck" and valid:
                competitor = choices.get("purple" if side == "green" else "green")
                if now - old["at"] <= stale_s and not arm["ambiguous"] and choice in (None, old["id"]) and competitor != old["id"] and arm["tcp_camera"]:
                    binding = self.bound[side] = {"id": old["id"], "at": now, "release_at": None}
            if binding:
                tag_id = binding["id"]
                if not valid or arm["status"] != "ready" or pump in ("unknown", "conflict") or now - binding["at"] > CARRY_MEMORY_S:
                    self.bound.pop(side, None)
                elif tag_id in visible and pump == "suck":
                    # Reappearance contradicts the alleged occluded carry.
                    self.bound.pop(side, None)
                else:
                    if self.pumps.get(side) == "suck" and pump in ("off", "blow"):
                        binding["release_at"] = now
                    released = binding["release_at"] is not None
                    stage = "release_observed" if released else ("likely_carried" if now - binding["at"] >= 0.3 else "pickup_suspected")
                    stages[tag_id] = {"stage": stage, "arm": side, "since": binding["release_at"] if released else binding["at"],
                                      "evidence": "Pump release signal; awaiting camera placement" if released else "Tag disappeared near this arm with suction; carry is inferred",
                                      "confidence": "inferred"}
                    arm["carried_tag"] = tag_id if not released else None
                    if released and now - binding["release_at"] > 3:
                        self.bound.pop(side, None)
                        stages.pop(tag_id, None)
            if choice is not None and choice in visible:
                self.considered[side] = {"id": choice, "at": now}
            elif old and now - old["at"] > stale_s:
                self.considered.pop(side, None)
            self.pumps[side] = pump
            excluded = {arm["considered_tag"], arm["carried_tag"]}
            report = arm["controller"]
            if report and not report["stale"]:
                excluded.add(report.get("physical_tag"))
            arm["targets"] = [target for target in arm["targets"] if target["id"] not in excluded]

        rows = []
        for tag_id, rec in sorted(self.records.items()):
            is_visible = tag_id in visible
            row = {"id": tag_id, "kind": "movable" if tag_id >= 100 else "marker", "visible": is_visible,
                   "last_seen": rec["last_seen"], "age_s": round(max(0, now - rec["last_seen"]), 2),
                   "camera": [rec["tag"]["nx"], rec["tag"]["ny"]], "corners": rec["tag"].get("ncorners", []),
                   "stage": "visible" if is_visible else "unknown", "arm": None, "target_id": None,
                   "confidence": "observed" if is_visible else "unknown",
                   "evidence": "Current corrected camera detection" if is_visible else "Not currently visible; last position only"}
            if tag_id in stages:
                row.update(stages[tag_id])
            elif is_visible and tag_id in choices.values():
                row.update(stage="near_arm", arm=next(side for side, value in choices.items() if value == tag_id),
                           confidence="inferred", evidence="Uniquely closest within diagnostic proximity limits")
            if valid and tag_id >= 100 and is_visible:
                association = row.get("arm")
                # Physical overlap in calibrated mm, never a game-valid target decision.
                for side in ([association] if association else ["green", "purple"]):
                    if arms[side]["status"] != "ready" or arms[side]["pump_mode"] not in ("off", "blow"):
                        continue
                    points = {p["id"]: p for p in projected.get(side, {}).get("tags", []) if p.get("status") == "ready"}
                    if tag_id not in points:
                        continue
                    xy = points[tag_id]["robot_xy"]
                    targets = sorted((math.dist(xy, p["robot_xy"]), marker) for marker, p in points.items()
                                     if marker < 100 and marker in self.records and now - self.records[marker]["last_seen"] <= MARKER_MEMORY_S)
                    if targets and targets[0][0] <= PLACEMENT_MM and (len(targets) < 2 or targets[1][0] - targets[0][0] >= 8):
                        row["target_id"] = targets[0][1]
                        break
                if row["target_id"] is not None:
                    candidate = self.placements.get(tag_id)
                    if not candidate or candidate["marker"] != row["target_id"]:
                        candidate = self.placements[tag_id] = {"marker": row["target_id"], "since": now, "frames": 0}
                    if frame_new:
                        candidate["frames"] += 1
                    if candidate["frames"] >= 3 and now - candidate["since"] >= PLACEMENT_DWELL_S:
                        row.update(stage="placement_stable", confidence="observed", evidence="Sustained corrected-camera overlap; gameplay acceptance belongs to Game")
                else:
                    self.placements.pop(tag_id, None)
            else:
                self.placements.pop(tag_id, None)
            if not valid:
                row.update(stage="unknown", confidence="unknown", arm=None, target_id=None,
                           evidence="Input unavailable; historical position is not current evidence")
            rows.append(row)
        return {"contract": "photon.board.tracking", "version": 1, "revision": self.revision,
                "status": "ready" if valid else "unavailable", "source": self.source, "sampled_at": now,
                "frame_at": runtime.get("frame_at"), "width": runtime.get("width", 0), "height": runtime.get("height", 0),
                "coordinate_space": "corrected-camera-normalized", "arms": arms, "tags": rows,
                "errors": errors, "inputs": runtime.get("inputs", {}),
                "limits": {**self.settings,
                           "marker_memory_s": MARKER_MEMORY_S, "placement_mm": PLACEMENT_MM,
                           "placement_dwell_s": PLACEMENT_DWELL_S}}
