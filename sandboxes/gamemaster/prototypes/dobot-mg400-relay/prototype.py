"""
Dobot MG400 Relay — two-arm game-master relay server (a Flask blueprint).

This machine OWNS TWO MG400 connections — one per side ("purple" / "green") — and
relays each side's move/pump commands to ITS OWN arm. The two sides are fully
INDEPENDENT and drive concurrently: purple's controller drives the purple arm
while green's controller drives the green arm, with no blocking between sides.

Both arms keep Dobot's factory IP (192.168.1.6) and are told apart by which
LOCAL NETWORK INTERFACE each side's sockets are pinned to (macOS IP_BOUND_IF —
see relay_arm.py and the dualdobottest proof of concept).

Per SIDE the relay still arbitrates: a side must *acquire* its arm and gets an
opaque token + a lease; a per-side watchdog smooth-stops that side's arm if its
holder stops heartbeating. This stops two tabs of the SAME side from fighting,
but it NEVER blocks across sides.

Every command for a side passes the same safety filter (joint limits / reachable
workspace clamp mirrored from the joint and cartesian prototypes) before it
reaches that side's arm.

A single GLOBAL E-STOP latch stops BOTH arms; `clear` un-latches it and clears
both arms' errors.

Loaded by hub.py; registered under /p/dobot-mg400-relay. No app.run() of its own —
it only runs inside the hub server. It needs each arm reachable on the network to
move it; without a robot the operator GUI + every endpoint still work and
move/pump fail cleanly with "Not connected".

Put each robot in API mode first — see ../../docs/operations/dobot-api-mode.md.
Safety: keep the hardware E-stop within reach; start with a low speed.
"""
from shared import delay_trace as trace

import json
import math
import os
import sys
import threading
import time
from collections import deque
from contextlib import ExitStack
from functools import wraps

from flask import Blueprint, jsonify, request, send_from_directory

import live   # shared push helper (prototypes/live.py)

HERE = os.path.dirname(os.path.abspath(__file__))
ARM_CONTRACT = "hhh.relay.arms"
ARM_VERSION = 1
sys.path.insert(0, HERE)  # so the sibling driver imports cleanly
from relay_arm import DobotMG400, DobotError  # noqa: E402
from arm_worker import ArmWorker  # noqa: E402

MANIFEST = {
    "name": "Dobot MG400 Relay",
    "description": (
        "Two-arm relay: owns BOTH MG400 arms and forwards each side's commands "
        "to its OWN arm. Player controllers connect through its HTTP API.\n"
        "**Need to know to get it working:**\n"
        "- Both robots keep the factory IP `192.168.1.6` — do not change it.\n"
        "- Each robot needs its OWN USB Ethernet dongle on this Mac, cable "
        "straight from dongle to robot (no switch in between).\n"
        "- Purple's dongle: IP `192.168.1.50`. Green's dongle: IP `192.168.1.51`.\n"
        "- Both dongles: subnet mask `255.255.255.0`; leave router and DNS empty.\n"
        "- No interface names needed — the relay finds the right dongle by its IP.\n"
        "- Put both robots in API mode, then Connect each side below."
    ),
    "default_page": "",
    "pages": [{"path": "", "label": "Relay (operator)"}],
}
bp = Blueprint("dobot_mg400_relay", __name__)

# ---- configuration --------------------------------------------------------
# BOTH arms keep Dobot's factory IP; they are told apart by WHICH USB dongle
# (local network interface) the connection leaves through. Each side's sockets
# are pinned to its dongle's interface (macOS IP_BOUND_IF — see
# relay_arm.DobotMG400), the same trick as the dualdobottest proof of concept.
# Only the dongles' FIXED local IPs are configured here; the interface names
# (en10/en11/... — they vary by Mac and USB port) are auto-detected at connect
# time as whichever interface owns that IP. Operator-editable in the GUI / via
# /api/connect ({side, local_ip?, ip?, iface?}).
ROBOT_IP = "192.168.1.6"
DEFAULT_LINKS = {
    "purple": {"local_ip": "192.168.1.50"},
    "green": {"local_ip": "192.168.1.51"},
}

SIDES = ("purple", "green")


@bp.before_request
def _enforce_team_side():
    """Players reach this machine through the hub's shared-API door, which puts
    their authenticated roles in request.environ["hhh.roles"]. A request whose
    roles are ONLY team roles may target ONLY its own side — so a hand-edited
    green controller can never acquire/move/kick the purple arm. Operator
    (gamemaster) sessions and engine deployments without the auth layer are
    unrestricted."""
    if request.method != "POST":
        return None
    roles = request.environ.get("hhh.roles")
    if roles is None:               # engine without the auth layer
        return None
    teams = {r for r in roles if r in SIDES}
    if not teams or roles - teams:  # operator/admin role present → unrestricted
        return None
    side = (request.get_json(silent=True) or {}).get("side")
    if side is not None and side not in teams:
        return jsonify({"ok": False,
                        "error": f"side '{side}' is not your team"}), 403
    return None
MODES = ("joint", "cartesian")
LEASE_SECS = 2.0          # holder must heartbeat within this or it's dropped
WATCHDOG_HZ = 5.0         # how often the watchdog checks each side's lease
COMMAND_LOG_MAX = 160     # recent relay/operator + robot command events
COMMAND_LOG_FILE = os.path.join(HERE, "command-monitor.log")

# Per-joint angle limits (degrees) — mirrored from joint-angles-test/prototype.py.
JOINT_LIMITS = {
    "j1": [-160.0, 160.0],   # base rotation
    "j2": [-25.0, 85.0],     # arm joint 1
    "j3": [-25.0, 105.0],    # arm joint 2
    "j4": [-160.0, 160.0],   # end rotation (R)
}

# Approximate MG400 workspace — mirrored EXACTLY from cartesian-xyz-test/prototype.py.
# The reachable area is an ANNULUS, so X/Y are clamped to a min/max radius too.
WORKSPACE = {
    "x": [-450.0, 450.0],
    "y": [-450.0, 450.0],
    "z": [-150.0, 230.0],
    "r": [-160.0, 160.0],
}
RADIUS_MIN = 150.0   # mm — inside this the arm can't reach (too folded)
RADIUS_MAX = 440.0   # mm — max horizontal reach

# Global follower settings shared by both arms. The defaults preserve the former
# fixed, conservative Tag Game profile; the upper limits match the original
# standalone joint and Cartesian controller ranges.
MOTION_SETTINGS_PATH = os.path.join(HERE, "motion-settings.json")
DEFAULT_MOTION_SETTINGS = {
    "tcp_xyz": 20.0,       # mm/s
    "tcp_rotation": 9.0,   # deg/s
    "joint": 12.0,         # deg/s along the four-joint path
    "ramp_secs": 0.50,     # acceleration = velocity cap / ramp time
}
MOTION_SETTING_LIMITS = {
    "tcp_xyz": (1.0, 200.0),
    "tcp_rotation": (1.0, 90.0),
    "joint": (1.0, 120.0),
    "ramp_secs": (0.05, 0.80),
}
_motion_settings_lock = threading.Lock()
_motion_settings = dict(DEFAULT_MOTION_SETTINGS)

# Air pump box (two-line suck/blow model — see joint prototype).
SUCK_DO_INDEX = 2
BLOW_DO_INDEX = 1

# Per-side arm connections, guarded by _arm_locks[side] while reconnecting.
_robots = {s: None for s in SIDES}
_arm_locks = {s: threading.RLock() for s in SIDES}
# Last link params each side connected with, so /api/reset can rebuild the driver
# (fresh sockets) without the operator re-typing the IP.
_last_link = {s: None for s in SIDES}
# Sampled state (live feedback + lease seconds tick down), so the SSE stream
# re-snapshots on a short interval rather than on a bump. See prototypes/live.py.
_live = live.LiveState()
_command_log = deque(maxlen=COMMAND_LOG_MAX)
_command_log_lock = threading.Lock()
_command_log_seq = 0
_command_log_file_error_reported = False


# ---- arbitration state -----------------------------------------------------
# Guarded by _arb_lock. NEVER do blocking arm socket I/O while holding this lock;
# read what's needed under it, release, then talk to the arm.
_arb_lock = threading.Lock()
_token_counter = 0             # bumps on every acquire → opaque per-side tokens
# Per side: who (if anyone) holds it, the mode they acquired with, and their lease.
_sides = {
    s: {"present": False, "last_seen": 0.0, "token": None, "mode": "joint", "motion_epoch": None, "player_session": None}
    for s in SIDES
}


def _arm(side):
    return _robots.get(side)


def _serialize_arm_control(fn):
    """Keep connection replacement and validated target submission in one order."""
    @wraps(fn)
    def wrapped(*args, **kwargs):
        side = (request.get_json(silent=True) or {}).get('side')
        if side not in SIDES:
            return fn(*args, **kwargs)
        with _arm_locks[side]:
            try:
                denied = _player_access_guard()
                if denied is not None: return denied
                return fn(*args, **kwargs)
            except DobotError as exc:
                return _fail(str(exc), code='motion_resync_required')
    return wrapped


@bp.before_request
def _player_access_guard():
    access = getattr(_hub_ctx, 'player_sessions', None)
    if access is None: return None
    sid = request.environ.get('hhh.player_session')
    if sid and not access.active(sid):
        return _fail('Player session ended. Scan a current QR code.'), 401
    action = request.path.rsplit('/', 1)[-1]
    safe = action in ('stop', 'hold', 'release', 'kick', 'disconnect', 'heartbeat')
    safe = safe or action == 'connect' and _is_operator_request()
    safe = safe or action == 'pump' and (request.get_json(silent=True) or {}).get('mode') == 'off'
    if access.blocked and request.method == 'POST' and not safe:
        return _fail('Clean reset pending. Player controls are blocked.'), 409
    return None


def _redact_payload(value):
    """Return a JSON-safe, compact payload copy for the operator monitor."""
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if k == "token":
                out[k] = "..."
            else:
                out[k] = _redact_payload(v)
        return out
    if isinstance(value, (list, tuple)):
        return [_redact_payload(v) for v in value]
    if isinstance(value, float):
        return round(value, 3)
    return value


@trace.traced('relay.log_command')
def _log_command(direction, side, command, payload=None, ok=None, error=None):
    """Append one command monitor entry to memory/disk and wake the SSE stream."""
    global _command_log_seq, _command_log_file_error_reported
    with trace.locked(_command_log_lock, 'logging.command_lock'):
        _command_log_seq += 1
        entry = {
            "id": _command_log_seq,
            "ts": round(time.time(), 3),
            "time": time.strftime("%H:%M:%S"),
            "direction": direction,  # "incoming" | "robot"
            "side": side,
            "command": command,
            "payload": _redact_payload(payload or {}),
            "ok": ok,
            "error": error,
        }
        _command_log.appendleft(entry)
        try:
            with open(COMMAND_LOG_FILE, "a", encoding="utf-8") as log_file:
                log_file.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n")
        except OSError as exc:
            # Logging must never stop a robot command. Report the first failure
            # to the hub console without flooding it on every move event.
            if not _command_log_file_error_reported:
                print(f"dobot relay: cannot write {COMMAND_LOG_FILE}: {exc}", file=sys.stderr)
                _command_log_file_error_reported = True
    _live.bump()
    return entry["id"]


def _command_log_snapshot():
    with trace.locked(_command_log_lock, 'logging.command_lock'):
        return list(_command_log)


def _incoming_payload(data):
    payload = dict(data or {})
    payload["from"] = request.headers.get("X-HHH-Source") or request.remote_addr or ""
    return payload


def _log_incoming(command, data, ok=None, error=None):
    _log_command("incoming", _side_from(data), command, _incoming_payload(data), ok, error)


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _clamp_joints(j1, j2, j3, j4):
    """Clamp a joint target to each joint's limit (mirror joint-angles-test)."""
    return (
        _clamp(j1, *JOINT_LIMITS["j1"]),
        _clamp(j2, *JOINT_LIMITS["j2"]),
        _clamp(j3, *JOINT_LIMITS["j3"]),
        _clamp(j4, *JOINT_LIMITS["j4"]),
    )


def _point_in_polygon(x, y, polygon):
    """Ray-cast point containment for the robot-space Cal 2 boundary."""
    inside = False
    previous = polygon[-1]
    for current in polygon:
        x1, y1 = previous
        x2, y2 = current
        dx, dy = x2-x1, y2-y1
        fraction = max(0, min(1, ((x-x1)*dx+(y-y1)*dy)/(dx*dx+dy*dy or 1)))
        if math.hypot(x-x1-fraction*dx, y-y1-fraction*dy) <= 1e-7:
            return True
        if ((y1 > y) != (y2 > y)):
            crossing = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x <= crossing:
                inside = not inside
        previous = current
    return inside


def _validate_cal2_joint_pose(pose, guard):
    """Validate a forward-kinematics pose against an LTX Cal 2 envelope."""
    if (not isinstance(guard, dict)
            or guard.get("format") != "auto-pp-calibration-2-v1"):
        return "Auto PP Cal 2 safety limits are missing"
    try:
        polygon = [
            (float(point[0]), float(point[1]))
            for point in guard.get("polygon", [])
        ]
        radius_min = float(guard["radius_min"])
        radius_max = float(guard["radius_max"])
        z_min = float(guard["z_min"])
        z_max = float(guard["z_max"])
        x, y, z = (float(pose[0]), float(pose[1]), float(pose[2]))
    except (KeyError, TypeError, ValueError, IndexError):
        return "Auto PP Cal 2 safety limits are invalid"
    if not (3 <= len(polygon) <= 128):
        return "Auto PP Cal 2 safety boundary is incomplete"
    values = [x, y, z, radius_min, radius_max, z_min, z_max]
    values.extend(value for point in polygon for value in point)
    if not all(math.isfinite(value) for value in values):
        return "Auto PP Cal 2 safety limits contain non-finite values"
    if radius_min < 0 or radius_min >= radius_max or z_min >= z_max:
        return "Auto PP Cal 2 safety limits are invalid"
    radius = math.hypot(x, y)
    if radius < radius_min or radius > radius_max:
        return (f"joint target TCP radius {radius:.1f} mm is outside the Auto PP "
                f"Cal 2 limit {radius_min:.1f}-{radius_max:.1f} mm")
    if z < z_min or z > z_max:
        return (f"joint target TCP Z {z:.1f} mm is outside the Auto PP Cal 2 "
                f"limit {z_min:.1f}-{z_max:.1f} mm")
    if not _point_in_polygon(x, y, polygon):
        return "joint target TCP is outside the Auto PP Cal 2 arm boundary"
    return None


def _cal2_pose_violations(pose, guard):
    """Distances beyond each already-validated Cartesian safety boundary."""
    x, y, z = map(float, pose[:3])
    polygon = guard['polygon']
    outside = 0.0
    if not _point_in_polygon(x, y, polygon):
        distances = []
        for i, (x1, y1) in enumerate(polygon):
            x2, y2 = polygon[(i+1) % len(polygon)]
            dx, dy = x2-x1, y2-y1
            fraction = max(0, min(1, ((x-x1)*dx+(y-y1)*dy)/(dx*dx+dy*dy or 1)))
            distances.append(math.hypot(x-x1-fraction*dx, y-y1-fraction*dy))
        outside = min(distances)
    radius = math.hypot(x, y)
    return [max(0, value) for value in (guard['radius_min']-radius,
            radius-guard['radius_max'], guard['z_min']-z, z-guard['z_max'], outside)]


def _validate_cal2_cartesian_path(current, target, guard):
    """Allow only a bounded, monotonic retreat from a measured boundary stop.

    The destination must be safe. A start up to 10 mm outside may move inward,
    but no violated constraint may worsen and no safe constraint may be crossed.
    Once inside, the whole remaining segment must stay inside.
    """
    error = _validate_cal2_joint_pose(target, guard)
    if error:
        return error
    start_error = _validate_cal2_joint_pose(current, guard)
    if start_error and not start_error.startswith('joint target TCP '):
        return start_error
    previous = _cal2_pose_violations(current, guard)
    if any(value > 10 for value in previous):
        return start_error
    entered = not start_error
    steps = max(64, math.ceil(math.dist(current[:3], target[:3])/2))
    for index in range(1, steps+1):
        sample = [current[i]+(target[i]-current[i])*index/steps for i in range(3)]
        violations = _cal2_pose_violations(sample, guard)
        error = _validate_cal2_joint_pose(sample, guard)
        if error and (entered or any(value > previous[i]+1e-7 for i, value in enumerate(violations))):
            return error
        if not error:
            entered = True
        previous = violations
    return None if entered else start_error


def _clamp_pose(x, y, z, r):
    """Clamp a target pose into the (approximate) reachable workspace: Z and R to
    their ranges, X/Y to the reachable annulus, then to the X/Y box. Mirrored
    EXACTLY from cartesian-xyz-test/prototype.py."""
    z = _clamp(z, *WORKSPACE["z"])
    r = _clamp(r, *WORKSPACE["r"])
    radius = math.hypot(x, y)
    if radius == 0.0:
        x, y = RADIUS_MIN, 0.0  # base axis is unreachable; nudge outward
    elif radius > RADIUS_MAX:
        s = RADIUS_MAX / radius
        x, y = x * s, y * s
    elif radius < RADIUS_MIN:
        s = RADIUS_MIN / radius
        x, y = x * s, y * s
    x = _clamp(x, *WORKSPACE["x"])
    y = _clamp(y, *WORKSPACE["y"])
    return x, y, z, r


# ---- Z soft-floor guard ----------------------------------------------------
# A configurable Cartesian Z floor (mm, in the arm's base frame) the TCP may not
# drop below. Cartesian/XYZ targets are clamped directly. Joint targets are
# clamped through a learned local height model z ≈ a + b·J2 + c·J3 per side
# (J1/J4 don't change height), so a descending joint target can be stopped at the
# floor instead of crashing through it. The ceiling uses controller forward
# kinematics for joint paths and direct Cartesian target checks. Both limits
# are operator-editable from the relay screen and persisted across restarts.
Z_FLOOR_PATH = os.path.join(HERE, "z-floor.json")
DEFAULT_Z_FLOOR = -72.0
DEFAULT_Z_CEILING = 80.0
_z_lock = threading.Lock()
_z_floor = DEFAULT_Z_FLOOR
_z_floor_enabled = True
_z_ceiling = DEFAULT_Z_CEILING
_z_ceiling_enabled = True
_z_samples = {s: deque(maxlen=120) for s in SIDES}  # recent (j2, j3, z) feedback
_z_coef = {s: None for s in SIDES}                  # fitted (a, b, c) or None
_Z_MIN_SAMPLES = 6


def _load_z_floor():
    global _z_floor, _z_floor_enabled, _z_ceiling, _z_ceiling_enabled
    try:
        with open(Z_FLOOR_PATH) as f:
            data = json.load(f)
        floor, floor_enabled, ceiling, ceiling_enabled = _validate_z_settings(data)
        _z_floor, _z_floor_enabled = floor, floor_enabled
        _z_ceiling, _z_ceiling_enabled = ceiling, ceiling_enabled
    except (OSError, ValueError, TypeError):
        pass


def _validate_z_settings(data):
    if not isinstance(data, dict):raise ValueError('Z limits must be an object')
    floor, ceiling = data.get('z_floor', DEFAULT_Z_FLOOR), data.get('z_ceiling', DEFAULT_Z_CEILING)
    if any(type(v) not in (int,float) or not math.isfinite(v) for v in (floor,ceiling)):
        raise ValueError('Z limits must be finite numbers')
    if not WORKSPACE['z'][0] <= floor < ceiling <= WORKSPACE['z'][1]:
        raise ValueError('Floor must be below ceiling, within -150 to 230 mm')
    enabled, ceiling_enabled = data.get('enabled', True), data.get('ceiling_enabled', True)
    if type(enabled) is not bool or type(ceiling_enabled) is not bool:
        raise ValueError('Enforce floor/ceiling must be true or false')
    return floor, enabled, ceiling, ceiling_enabled


def _save_z_floor(data):
    temporary = Z_FLOOR_PATH + '.tmp'
    try:
        with open(temporary, 'w') as f:
            json.dump(data, f, indent=2, allow_nan=False)
        os.replace(temporary, Z_FLOOR_PATH)
    finally:
        if os.path.exists(temporary):os.unlink(temporary)


def z_limits_snapshot():
    """Shared, versioned effective Z bounds for player height controls."""
    with _z_lock:
        return {'contract':'hhh.relay.z-limits','version':1,'status':'ready',
                'minimum':_z_floor if _z_floor_enabled else WORKSPACE['z'][0],
                'maximum':_z_ceiling if _z_ceiling_enabled else WORKSPACE['z'][1]}


def _ceiling_path_error(z, previous_z):
    with _z_lock:ceiling, enabled = _z_ceiling, _z_ceiling_enabled
    if not enabled:return None
    if not all(type(v) in (int,float) and math.isfinite(v) for v in (z,previous_z)):
        return 'Cannot verify joint path against Z ceiling'
    # If manually positioned above the ceiling, only a descending recovery
    # is allowed. Never silently send a different joint/XYZ goal to get inside.
    if z > ceiling and z >= previous_z - 1e-6:
        return f'Z ceiling {ceiling:g} mm exceeded by joint path ({z:.1f} mm)'
    if previous_z <= ceiling and z > ceiling:
        return f'Z ceiling {ceiling:g} mm exceeded by joint path ({z:.1f} mm)'
    return None


def _solve3(S, rhs):
    """Solve the 3x3 system S·x = rhs by Cramer's rule. None if near-singular."""
    def det3(m):
        return (m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
                - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
                + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]))
    d = det3(S)
    if abs(d) < 1e-6:
        return None
    out = []
    for col in range(3):
        m = [row[:] for row in S]
        for row in range(3):
            m[row][col] = rhs[row]
        out.append(det3(m) / d)
    return out  # [a, b, c]


def _refit_z_model(side):
    samples = _z_samples[side]
    if len(samples) < _Z_MIN_SAMPLES:
        _z_coef[side] = None
        return
    j2s = [s[0] for s in samples]
    j3s = [s[1] for s in samples]
    zs = [s[2] for s in samples]
    n = len(samples)
    sj2, sj3, sz = sum(j2s), sum(j3s), sum(zs)
    sj2j2 = sum(a * a for a in j2s)
    sj3j3 = sum(a * a for a in j3s)
    sj2j3 = sum(j2s[i] * j3s[i] for i in range(n))
    sj2z = sum(j2s[i] * zs[i] for i in range(n))
    sj3z = sum(j3s[i] * zs[i] for i in range(n))
    # Ridge on the two SLOPE terms only (not the intercept): keeps the fit solvable
    # even when one joint barely moved (its slope shrinks toward 0 instead of making
    # the whole system singular — which previously dropped the model entirely and
    # left the floor unenforced).
    r2 = 1e-3 * sj2j2 + 1e-6
    r3 = 1e-3 * sj3j3 + 1e-6
    S = [[n, sj2, sj3], [sj2, sj2j2 + r2, sj2j3], [sj3, sj2j3, sj3j3 + r3]]
    coef = _solve3(S, [sz, sj2z, sj3z])
    _z_coef[side] = tuple(coef) if coef else None


def _sample_z_model(side, robot):
    """Feed one feedback sample (only if the arm moved enough) and refit."""
    try:
        st = robot.get_state()
        joints, pose = st.get("joints"), st.get("pose")
        j2, j3, z = float(joints[1]), float(joints[2]), float(pose[2])
    except (TypeError, ValueError, IndexError):
        return
    dq = _z_samples[side]
    if dq:
        lj2, lj3, _ = dq[-1]
        if abs(j2 - lj2) < 0.5 and abs(j3 - lj3) < 0.5:
            return
    dq.append((j2, j3, z))
    _refit_z_model(side)


def _apply_z_floor(side, j1, j2, j3, j4, robot):
    """Clamp a joint target so the TCP won't drop below the Z floor. Returns
    (j1, j2, j3, j4, note); note is a human string if anything was changed."""
    with _z_lock:
        floor, enabled = _z_floor, _z_floor_enabled
    if not enabled:
        return j1, j2, j3, j4, None
    try:
        st = robot.get_state()
        joints, pose = st.get("joints"), st.get("pose")
        aj2, aj3, az = float(joints[1]), float(joints[2]), float(pose[2])
    except (TypeError, ValueError, IndexError):
        return j1, j2, j3, j4, None
    coef = _z_coef[side]
    if coef is None:
        # No reliable height model yet — allow the move. We must NOT freeze J2/J3
        # here: freezing them stops the very motion the model is learned from, so
        # the arm could never escape (and an arm resting below the floor would be
        # locked out entirely). Jog J2/J3 around once; the model fits within a
        # second or two and the predictive clamp below takes over.
        return j1, j2, j3, j4, None
    _a, b, c = coef
    dz = b * (j2 - aj2) + c * (j3 - aj3)     # predicted Z change from here to target
    if (az + dz) >= floor or dz >= 0:
        return j1, j2, j3, j4, None           # target stays above floor (or rises)
    alpha = max(0.0, min(1.0, (floor - az) / dz))   # fraction of the descent allowed
    nj2 = aj2 + alpha * (j2 - aj2)
    nj3 = aj3 + alpha * (j3 - aj3)
    return j1, nj2, nj3, j4, f"Z floor {floor:.0f} mm reached — no room to go lower"


def _apply_pose_z_floor(x, y, z, r):
    """Clamp a Cartesian/XYZ target pose so the TCP target never goes below the
    configured Z floor. Returns (x, y, z, r, note)."""
    with _z_lock:
        floor, enabled = _z_floor, _z_floor_enabled
    if not enabled or z >= floor:
        return x, y, z, r, None
    return x, y, floor, r, f"Z floor {floor:.0f} mm reached — target Z clamped"


def _is_operator_request():
    """True for gamemaster/admin sessions (or engine runs without the auth layer)."""
    roles = request.environ.get("hhh.roles")
    if roles is None:
        return True
    return bool(roles - set(SIDES))


def _motion_settings_snapshot():
    with _motion_settings_lock:
        return dict(_motion_settings)


def _load_motion_settings():
    """Load persisted global follower settings, ignoring invalid individual keys."""
    try:
        with open(MOTION_SETTINGS_PATH) as settings_file:
            data = json.load(settings_file)
    except (OSError, ValueError, TypeError):
        return
    loaded = {}
    for key, (minimum, maximum) in MOTION_SETTING_LIMITS.items():
        try:
            value = float(data[key])
        except (KeyError, TypeError, ValueError):
            continue
        if math.isfinite(value) and minimum <= value <= maximum:
            loaded[key] = value
    with _motion_settings_lock:
        _motion_settings.update(loaded)


def _save_motion_settings():
    try:
        with open(MOTION_SETTINGS_PATH, "w") as settings_file:
            json.dump(_motion_settings, settings_file, indent=2)
    except OSError:
        pass


_load_z_floor()
_load_motion_settings()


def _apply_motion(robot):
    """Push the shared operator settings to both follower modes on one arm."""
    settings = _motion_settings_snapshot()
    secs = settings["ramp_secs"]
    robot.set_max_velocity_cartesian(
        settings["tcp_xyz"], settings["tcp_rotation"]
    )
    robot.set_max_accel_cartesian(
        settings["tcp_xyz"] / secs, settings["tcp_rotation"] / secs
    )
    robot.set_max_velocity_joint(settings["joint"])
    robot.set_max_accel_joint(settings["joint"] / secs)


def _ensure_follower(robot, mode, motion_epoch):
    """Make sure the arm is running the follower for `mode` (switching followers if
    a different one is active). Keeps the connection + enabled state intact. No
    arbitration lock is held here — this does blocking arm I/O."""
    if robot is None or not robot.is_connected():
        return
    if not robot.get_state().get("enabled"):
        return
    if robot.control_mode() != mode or not robot.get_state().get('servo_active'):
        _apply_motion(robot)
        robot.start_servo(mode, expected_epoch=motion_epoch)


# ---- lease / arbitration helpers (call with _arb_lock held) ----------------
def _lease_secs_left_locked(side):
    if _sides[side]["token"] is None:
        return 0.0
    left = LEASE_SECS - (time.time() - _sides[side]["last_seen"])
    return max(0.0, left)


def _touch_locked(side):
    """Refresh a side's presence + lease (call with _arb_lock held)."""
    _sides[side]["present"] = True
    _sides[side]["last_seen"] = time.time()


# ---- programmatic API (for other machines via the hub) ---------------------
def arm_state(side):
    """That side's arm sub-object (same shape as state['arms'][side])."""
    if side not in SIDES:
        raise ValueError(f"side must be one of {SIDES}")
    return _arm_dict(side)


def arms_snapshot():
    """Versioned read-only arm output; this function never issues a command."""
    return {
        "contract": ARM_CONTRACT,
        "version": ARM_VERSION,
        "status": "ready",
        "error": None,
        "observed_at": time.time(),
        "arms": {side: _arm_dict(side) for side in SIDES},
    }


def player_control_sessions():
    """Read-only ownership for Hub presence; never expose relay lease tokens."""
    with _arb_lock:
        return {'contract': 'hhh.relay.player-sessions', 'version': 1, 'status': 'ready',
                'sessions': {side: state['player_session'] for side, state in _sides.items()
                             if state['token'] is not None and state.get('player_session')},
                'leased_sides': [side for side, state in _sides.items() if state['token'] is not None]}


def revoke_player_controls():
    """Invalidate both leases after queued arm commands finish; Game owns Stop."""
    for side in SIDES:
        with _arm_locks[side], _arb_lock:
            _sides[side].update(token=None, present=False, player_session=None)
    _live.bump()
    return {'contract': 'hhh.relay.player-sessions', 'version': 1, 'status': 'ready', 'released': True}


def stop_side(side):
    """Owner-public stop and measured settling; never grants a new motion lease."""
    if side not in SIDES:
        raise ValueError('invalid side')
    robot = _arm(side)
    if robot is None or not robot.is_connected():
        return {'contract':'hhh.relay.stop','version':1,'status':'unavailable','stopped':False,'error':'fresh connected arm feedback required to confirm Stop'}
    try:
        robot.hold()
        first = robot.get_state()
        time.sleep(.12)
        second = robot.get_state()
        fresh = time.time()-second.get('last_feedback',0) <= 1.5
        joints = (first.get('joints'),second.get('joints'))
        valid = all(isinstance(j,list) and len(j)==4 and all(type(v) in (int,float) and math.isfinite(v) for v in j) for j in joints)
        settled = fresh and valid and all(abs(a-b)<.2 for a,b in zip(*joints))
        if settled:
            kick_side(side)
        return {'contract':'hhh.relay.stop','version':1,'status':'ready','stopped':settled}
    except Exception as exc:
        return {'contract':'hhh.relay.stop','version':1,'status':'unavailable','error':str(exc),'stopped':False}


def disable_side(side):
    """Revoke control and keep a waiting calibration arm disabled; never connect it."""
    if side not in SIDES:raise ValueError('invalid side')
    with _arb_lock:
        _sides[side].update(present=False,token=None)
    robot=_arm(side)
    result={'contract':'hhh.relay.disabled','version':1,'status':'ready',
            'inhibited':True,'connected':bool(robot and robot.is_connected()),'disabled':False}
    if not result['connected']:
        # Offline means no command access, not evidence of a physical stop.
        return result
    try:
        state=robot.get_state()
        if state.get('enabled') is not False or state.get('servo_active'):
            stopped=stop_side(side)
            if stopped.get('stopped') is not True:raise ValueError('Waiting arm has not stopped')
            robot.stop_servo()
            errid,response=robot.disable()
            if errid!=0:raise ValueError('Waiting arm disable failed: '+str(response))
            state=robot.get_state()
        stamp=state.get('last_feedback')
        if type(stamp) not in (int,float) or not math.isfinite(stamp) or not -.25<=time.time()-stamp<=1.5:
            raise ValueError('Fresh waiting-arm feedback required to confirm disabled servos')
        if state.get('enabled') is not False or state.get('servo_active'):
            raise ValueError('Waiting for arm servos to switch off')
        result['disabled']=True
    except Exception as exc:
        result.update(status='unavailable',error=str(exc))
    _live.bump()
    return result


def side_holder(side):
    """The opaque token currently holding `side`, or None if free."""
    if side not in SIDES:
        raise ValueError(f"side must be one of {SIDES}")
    with _arb_lock:
        return _sides[side]["token"]


def full_state():
    """The relay's full state object (same shape as GET /api/state)."""
    return _state_dict()


# ---- watchdog --------------------------------------------------------------
def _watchdog_loop():
    """~5 Hz: for EACH side, if its holder's lease expired, smooth-stop THAT side's
    arm and free that side (mark not present). The other side is unaffected. Arm
    I/O happens outside the lock."""
    period = 1.0 / WATCHDOG_HZ
    while not _watchdog_stop.wait(period):
        # Learn each connected+enabled arm's height model from live feedback so the
        # Z floor can clamp descending joint targets smoothly.
        for s in SIDES:
            robot = _arm(s)
            if robot is not None and robot.is_connected() and robot.get_state().get("enabled"):
                _sample_z_model(s, robot)
        expired = []
        with _arb_lock:
            for s in SIDES:
                if _sides[s]["token"] is not None and _lease_secs_left_locked(s) <= 0.0:
                    expired.append((s, round((time.time()-_sides[s]['last_seen'])*1000, 1)))
                    _sides[s]["present"] = False
                    _sides[s]["token"] = None
        expiry_results = []
        for s, heartbeat_age in expired:
            robot = _arm(s)
            stop_error = None
            if robot is not None and robot.is_connected():
                try:
                    robot.hold()      # smooth stop; keep servos enabled
                except Exception as exc:     # pragma: no cover - defensive
                    stop_error = str(exc)
            expiry_results.append((s, heartbeat_age, stop_error))
        # Finish both safety actions before disk I/O for either team's record.
        for s, heartbeat_age, stop_error in expiry_results:
            _log_command('robot', s, 'lease_expired', {'heartbeat_age_ms':heartbeat_age,
                         'lease_limit_ms':LEASE_SECS*1000}, ok=stop_error is None,
                         error=stop_error or 'Player heartbeat lease expired')
        if expired:
            _live.bump()


_watchdog_stop = threading.Event()
_watchdog_thread = None


# ---- response helpers ------------------------------------------------------
def _ok(**kw):
    return jsonify({"ok": True, **kw})


def _fail(error, **kw):
    return jsonify({"ok": False, "error": error, **kw})


def _pump_mode(do_bits):
    suck = bool(do_bits & (1 << (SUCK_DO_INDEX - 1)))
    blow = bool(do_bits & (1 << (BLOW_DO_INDEX - 1)))
    if suck and blow:
        return "conflict"
    if suck:
        return "suck"
    if blow:
        return "blow"
    return "off"


def _arm_dict(side):
    """The arm sub-object for one side (works with no robot connected)."""
    robot = _arm(side)
    raw = DobotMG400._blank_state() if robot is None else robot.get_state()
    stamp = raw.get("last_feedback")
    age = (time.time() - stamp if type(stamp) in (int, float)
           and math.isfinite(stamp) and stamp > 0 else None)
    if age is not None and (not math.isfinite(age) or age < 0):
        age = None
    return {
        "device": dict(_last_link.get(side) or {}),
        "connected": raw["connected"],
        "robot_mode": raw["robot_mode"],
        "enabled": raw["enabled"],
        "mode_name": raw["mode_name"],
        "joints": raw["joints"],
        "pose": raw["pose"],
        "feedback_at": raw.get("last_feedback", 0.0),
        "feedback_ok": raw.get("feedback_ok") is True,
        "feedback_age": age,
        "motion_epoch": raw.get("motion_epoch"),
        "motion_invalidation": raw.get("motion_invalidation"),
        "motion_ready": raw.get("motion_ready", False),
        "servo_active": raw["servo_active"],
        "servo_error": raw["servo_error"],
        "error": raw.get("error", False),
        "alarm_ids": raw.get("alarm_ids", []),
        "fault_kind": raw.get("fault_kind"),
        "fault_label": raw.get("fault_label"),
        "stalled": raw.get("stalled", False),
        "stall_error": raw.get("stall_error", 0.0),
        "pump_mode": _pump_mode(raw.get("digital_out", 0)),
        "control_mode": raw.get("control_mode"),
        "target": None if robot is None else robot.get_target(),
    }


@trace.traced('relay.feedback_snapshot', side='argument')
def _feedback_snapshot(side):
    """Compact, read-only player telemetry; never waits for command-log I/O."""
    with _arb_lock:
        lease = {"present": _sides[side]["present"],
                 "lease_secs": round(_lease_secs_left_locked(side), 3)}
    return {"contract": "hhh.relay.feedback", "version": 1, "status": "ready",
            "z_limits": z_limits_snapshot(), "sides": {side: lease},
            "arms": {side: _arm_dict(side)}}


@trace.traced('relay.state_dict')
def _state_dict():
    """The full relay state (GET /api/state and the SSE stream)."""
    arms = {s: _arm_dict(s) for s in SIDES}
    with _arb_lock:
        sides = {
            s: {
                "present": _sides[s]["present"],
                "lease_secs": round(_lease_secs_left_locked(s), 3),
            }
            for s in SIDES
        }
        state = {
            "arms": arms,
            "sides": sides,
        }
    # Disk-backed monitor logging must not hold the lease/watchdog lock.
    state["command_log"] = _command_log_snapshot()
    with _z_lock:
        state["z_floor"] = {
            "value": _z_floor,
            "enabled": _z_floor_enabled,
            "models": {s: (_z_coef[s] is not None) for s in SIDES},
        }
        state['z_ceiling'] = {'value':_z_ceiling,'enabled':_z_ceiling_enabled}
    state['z_limits'] = z_limits_snapshot()
    state["motion_settings"] = _motion_settings_snapshot()
    return state


# ---- pages ----------------------------------------------------------------
@bp.route("/")
def index():
    return send_from_directory(HERE, "controller.html")


@bp.route("/api/config")
def config():
    return jsonify({
        "joint_limits": JOINT_LIMITS,
        "workspace": WORKSPACE,
        "radius_min": RADIUS_MIN,
        "radius_max": RADIUS_MAX,
        "robot_ip": ROBOT_IP,
        "default_links": DEFAULT_LINKS,
        "sides": list(SIDES),
        "modes": list(MODES),
        "lease_secs": LEASE_SECS,
        "z_floor": {"value": _z_floor, "enabled": _z_floor_enabled,
                    "default": DEFAULT_Z_FLOOR},
        "z_ceiling": {"value": _z_ceiling, "enabled": _z_ceiling_enabled,
                      "default": DEFAULT_Z_CEILING},
        "z_limits": z_limits_snapshot(),
        "motion_settings": _motion_settings_snapshot(),
        "motion_setting_limits": {
            key: list(bounds) for key, bounds in MOTION_SETTING_LIMITS.items()
        },
    })


@bp.route("/api/state")
def state():
    return jsonify(_state_dict())


@bp.route("/api/events")
def events():
    """Push the relay state (both arms' feedback, sides, leases) ~5x/s while it
    changes; the leases count down so it changes every sample."""
    return _live.stream(_state_dict, interval=0.2)


@bp.route("/api/feedback")
def feedback_events():
    """Push one side's feedback independently of its lease heartbeat."""
    side = request.args.get('side')
    if side not in SIDES:
        return _fail("side must be 'purple' or 'green'"), 400
    return _live.stream(lambda: _feedback_snapshot(side), interval=0.1)


@bp.route("/api/z-floor", methods=["GET", "POST"])
def z_floor():
    return _z_limit_request('floor')


@bp.route('/api/z-ceiling', methods=['GET','POST'])
def z_ceiling():
    return _z_limit_request('ceiling')


@bp.route('/api/z-limits')
def z_limits():
    return jsonify(z_limits_snapshot())


def _z_limit_request(bound):
    global _z_floor, _z_floor_enabled, _z_ceiling, _z_ceiling_enabled
    ceiling = bound == 'ceiling'
    if request.method == "GET":
        with _z_lock:
            return _ok(value=_z_ceiling if ceiling else _z_floor,
                       enabled=_z_ceiling_enabled if ceiling else _z_floor_enabled,
                       default=DEFAULT_Z_CEILING if ceiling else DEFAULT_Z_FLOOR,
                       models={s: (_z_coef[s] is not None) for s in SIDES})
    if not _is_operator_request():
        return _fail("gamemaster required"), 403
    data = request.get_json(silent=True)
    if not isinstance(data,dict):return _fail('Z limit must be an object'),400
    _log_incoming('z-'+bound, data)
    # Serialize against both sides' target submission. Settle and revoke old
    # movement before changing a limit, including a goal already being followed.
    with ExitStack() as locks:
        for side in SIDES:locks.enter_context(_arm_locks[side])
        with _z_lock:
            candidate={'z_floor':_z_floor,'enabled':_z_floor_enabled,
                       'z_ceiling':_z_ceiling,'ceiling_enabled':_z_ceiling_enabled}
        if 'value' in data:candidate['z_'+bound]=data['value']
        if 'enabled' in data:candidate['ceiling_enabled' if ceiling else 'enabled']=data['enabled']
        try:values=_validate_z_settings(candidate)
        except ValueError as exc:return _fail(str(exc)),400
        if values != (_z_floor,_z_floor_enabled,_z_ceiling,_z_ceiling_enabled):
            for side in SIDES:
                robot=_arm(side)
                if robot is not None and robot.is_connected():
                    stopped=stop_side(side)
                    if stopped.get('stopped') is not True:
                        return _fail('Could not confirm '+side+' stopped; Z limits were not changed'),409
            try:_save_z_floor(candidate)
            except OSError as exc:return _fail('Could not save Z limits: '+str(exc)),500
            with _z_lock:
                _z_floor,_z_floor_enabled,_z_ceiling,_z_ceiling_enabled=values
        out = {'value':_z_ceiling if ceiling else _z_floor,
               'enabled':_z_ceiling_enabled if ceiling else _z_floor_enabled}
    _live.bump()
    return _ok(**out,z_limits=z_limits_snapshot())


@bp.route("/api/motion-settings", methods=["GET", "POST"])
def motion_settings():
    """Read or set the follower caps shared live by the purple and green arms."""
    if request.method == "GET":
        return _ok(
            settings=_motion_settings_snapshot(),
            limits={key: list(bounds) for key, bounds in MOTION_SETTING_LIMITS.items()},
        )
    if not _is_operator_request():
        return _fail("gamemaster required"), 403
    data = request.get_json(silent=True) or {}
    _log_incoming("motion-settings", data)
    updates = {}
    for key, (minimum, maximum) in MOTION_SETTING_LIMITS.items():
        if key not in data:
            continue
        try:
            value = float(data[key])
        except (TypeError, ValueError):
            return _fail(f"{key} must be a number"), 400
        if not math.isfinite(value) or not minimum <= value <= maximum:
            return _fail(
                f"{key} must be between {minimum:g} and {maximum:g}"
            ), 400
        updates[key] = value
    if not updates:
        return _fail("no motion settings supplied"), 400
    with _motion_settings_lock:
        _motion_settings.update(updates)
        _save_motion_settings()
        settings = dict(_motion_settings)
    for side in SIDES:
        robot = _arm(side)
        if robot is None or not robot.is_connected():
            continue
        _apply_motion(robot)
        _log_command("robot", side, "motion_settings", settings, ok=True)
    _live.bump()
    return _ok(settings=settings)


# ---- side helpers ----------------------------------------------------------
def _side_from(data):
    side = (data or {}).get("side")
    if side not in SIDES:
        return None
    return side


# ---- operator endpoints (no token) ----------------------------------------
@bp.route("/api/connect", methods=["POST"])
@_serialize_arm_control
def connect():
    """Connect THAT side's arm (replacing any existing connection for it)."""
    data = request.json or {}
    _log_incoming("connect", data)
    side = _side_from(data)
    if side is None:
        _log_incoming("connect", data, ok=False, error="side must be 'purple' or 'green'")
        return _fail("side must be 'purple' or 'green'")
    ip = (data.get("ip") or ROBOT_IP).strip()
    local_ip = (data.get("local_ip") or DEFAULT_LINKS[side]["local_ip"]).strip()
    iface = (data.get("iface") or "").strip() or None  # optional override
    link = {"ip": ip, "local_ip": local_ip, "iface": iface}
    with _arb_lock:
        _sides[side].update(token=None, present=False, motion_epoch=None)
    with _arm_locks[side]:
        if _robots[side] is not None:
            _robots[side].close()
            _robots[side] = None
        robot = ArmWorker(ip, iface=iface, local_ip=local_ip)
        robot.side = side
        try:
            robot.connect()
            _apply_motion(robot)
        except DobotError as e:
            robot.close()
            _log_command("robot", side, "connect", link, ok=False, error=str(e))
            return _fail(f"Could not connect to {ip} via {local_ip}: {e}")
        _robots[side] = robot
    link["iface"] = robot.iface  # the auto-detected (or given) interface
    _last_link[side] = dict(link)
    _log_command("robot", side, "connect", link, ok=True)
    _live.bump()
    return _ok(side=side, **link)


@bp.route("/api/disconnect", methods=["POST"])
@_serialize_arm_control
def disconnect():
    """Disconnect that side's arm."""
    data = request.json or {}
    _log_incoming("disconnect", data)
    side = _side_from(data)
    if side is None:
        _log_incoming("disconnect", data, ok=False, error="side must be 'purple' or 'green'")
        return _fail("side must be 'purple' or 'green'")
    with _arb_lock:
        _sides[side].update(token=None, present=False, motion_epoch=None)
    with _arm_locks[side]:
        if _robots[side] is not None:
            _robots[side].close()
            _robots[side] = None
            _log_command("robot", side, "close", {}, ok=True)
    _live.bump()
    return _ok(side=side)


@bp.route("/api/clear_error", methods=["POST"])
def clear_error():
    """Clear alarms/warnings on that side's arm without enabling or moving it."""
    data = request.json or {}
    _log_incoming("clear_error", data)
    side = _side_from(data)
    if side is None:
        _log_incoming("clear_error", data, ok=False, error="side must be 'purple' or 'green'")
        return _fail("side must be 'purple' or 'green'")
    robot = _arm(side)
    if robot is None or not robot.is_connected():
        _log_command("robot", side, "clear_error", {}, ok=False, error="Not connected")
        return _fail("Not connected")
    try:
        errid, resp = robot.clear_error()
    except DobotError as e:
        _log_command("robot", side, "clear_error", {}, ok=False, error=str(e))
        return _fail(str(e), errid=e.errid)
    ok = errid == 0
    _log_command("robot", side, "clear_error", {"errid": errid, "resp": resp}, ok=ok)
    _live.bump()
    return jsonify({"ok": ok, "errid": errid, "resp": resp, "side": side})


@bp.route("/api/enable", methods=["POST"])
@_serialize_arm_control
def enable():
    """Enable and synchronize without starting a servo stream or restoring targets."""
    data = request.json or {}
    _log_incoming("enable", data)
    side = _side_from(data)
    if side is None:
        _log_incoming("enable", data, ok=False, error="side must be 'purple' or 'green'")
        return _fail("side must be 'purple' or 'green'")
    robot = _arm(side)
    if robot is None or not robot.is_connected():
        _log_command("robot", side, "enable", {}, ok=False, error="Not connected")
        return _fail("Not connected")
    if data.get('token') is not None:
        _, error = _check_token(data)
        if error:
            return _fail(error)
    robot.reset_motion()
    try:
        robot.clear_error()
        _log_command("robot", side, "clear_error", {}, ok=True)
    except DobotError:
        pass
    try:
        errid, resp = robot.enable()
    except DobotError as e:
        _log_command("robot", side, "enable", {}, ok=False, error=str(e))
        return _fail(str(e), errid=e.errid)
    if errid == 0:
        state = robot.wait_for_motion_feedback()
        with _arb_lock:
            _sides[side]['motion_epoch'] = state['motion_epoch']
        _apply_motion(robot)
        _log_command("robot", side, "enable + synchronize", {}, ok=True)
    else:
        _log_command("robot", side, "enable", {"errid": errid, "resp": resp}, ok=False)
    _live.bump()
    return jsonify({"ok": errid == 0, "errid": errid, "resp": resp, "side": side,
                    "motion_epoch": robot.get_state()['motion_epoch']})


@bp.route("/api/kick", methods=["POST"])
def kick():
    """Force-release that side's controller (smooth-stop that side's arm + free its
    lease). The other side is unaffected."""
    data = request.json or {}
    _log_incoming("kick", data)
    side = _side_from(data)
    if side is None:
        _log_incoming("kick", data, ok=False, error="side must be 'purple' or 'green'")
        return _fail("side must be 'purple' or 'green'")
    kick_side(side)
    return _ok(side=side)


def kick_side(side):
    """Programmatic sibling-prototype helper for releasing one side's relay."""
    if side not in SIDES:
        return False
    with _arb_lock:
        _sides[side]["present"] = False
        _sides[side]["token"] = None
    robot = _arm(side)
    if robot is not None and robot.is_connected():
        try:
            robot.hold()
            _log_command("robot", side, "hold", {"reason": "kick"}, ok=True)
        except Exception:   # pragma: no cover - defensive
            _log_command("robot", side, "hold", {"reason": "kick"}, ok=False, error="hold failed")
    _live.bump()
    return True


# ---- client / side endpoints ----------------------------------------------
def _check_token(data):
    """Validate (side, token) against that side's holder. Returns (side, error)
    where error is None on success. Refreshes the side's lease on success.
    Acquires/releases _arb_lock internally; does no arm I/O."""
    side = _side_from(data)
    if side is None:
        return None, "side must be 'purple' or 'green'"
    token = data.get("token")
    with _arb_lock:
        if _sides[side]["token"] is None or token != _sides[side]["token"]:
            return None, "stale token"
        access = getattr(_hub_ctx, 'player_sessions', None)
        sid = _sides[side].get('player_session')
        if sid and access and not access.active(sid):
            return None, 'Player session ended'
        _touch_locked(side)
    return side, None


@bp.route("/api/acquire", methods=["POST"])
@_serialize_arm_control
def acquire():
    """Acquire THIS side's arm. Records the mode and mints a fresh token
    (invalidating any old one for that side). NEVER conflicts with the other side -
    purple and green can both hold concurrently (no 409)."""
    global _token_counter
    data = request.json or {}
    _log_incoming("acquire", data)
    side = _side_from(data)
    if side is None:
        _log_incoming("acquire", data, ok=False, error="side must be 'purple' or 'green'")
        return _fail("side must be 'purple' or 'green'"), 400
    mode = (data.get("mode") or "joint").lower()
    if mode not in MODES:
        _log_incoming("acquire", data, ok=False, error="mode must be 'joint' or 'cartesian'")
        return _fail("mode must be 'joint' or 'cartesian'"), 400
    robot = _arm(side)
    if robot is None or not robot.is_connected():
        return _fail('Not connected')
    motion_epoch = robot.reset_motion()
    with _arb_lock:
        _token_counter += 1
        token = f"{side}-{_token_counter}"
        _sides[side]["token"] = token
        _sides[side]["mode"] = mode
        _sides[side]["motion_epoch"] = motion_epoch
        _sides[side]['player_session'] = request.environ.get('hhh.player_session')
        _touch_locked(side)
    # A lease grants no movement. Only a fully validated move starts a follower.
    _live.bump()
    return _ok(token=token, lease_secs=LEASE_SECS, side=side, motion_epoch=motion_epoch)


@bp.route("/api/release", methods=["POST"])
@_serialize_arm_control
def release():
    """Release this side's arm. Requires a valid (side, token)."""
    data = request.json or {}
    _log_incoming("release", data)
    side = _side_from(data)
    if side is None:
        _log_incoming("release", data, ok=False, error="side must be 'purple' or 'green'")
        return _fail("side must be 'purple' or 'green'")
    token = data.get("token")
    with _arb_lock:
        if _sides[side]["token"] is None or token != _sides[side]["token"]:
            _log_incoming("release", data, ok=False, error="stale token")
            return _fail("stale token")
        _sides[side]["token"] = None
        _sides[side]["present"] = False
    robot = _arm(side)
    if robot is not None and robot.is_connected():
        try:
            robot.hold()
            _log_command("robot", side, "hold", {"reason": "release"}, ok=True)
        except Exception:   # pragma: no cover - defensive
            _log_command("robot", side, "hold", {"reason": "release"}, ok=False, error="hold failed")
    _live.bump()
    return _ok(side=side)


@bp.route("/api/heartbeat", methods=["POST"])
def heartbeat():
    """Refresh this side's lease; returns the full state object. Stale token ->
    {ok:false, error:"stale token"}."""
    side, err = _check_token(request.json or {})
    if err:
        _log_incoming('heartbeat_rejected', request.json or {}, ok=False, error=err)
        return _fail(err)
    return _ok(state=_feedback_snapshot(side) if (request.json or {}).get('feedback_only') is True
               else _state_dict())


@bp.route("/api/move", methods=["POST"])
@_serialize_arm_control
def move():
    """Set this side's follower target after safety-clamping. Requires a valid
    (side, token), and that side's arm connected + enabled."""
    data = request.json or {}
    _log_incoming("move", data)
    side, err = _check_token(data)
    if err:
        _log_incoming("move", data, ok=False, error=err)
        return _fail(err)
    capability_error = _ltz_motion_error(side, data)
    if capability_error:
        return _fail(capability_error), 403
    robot = _arm(side)
    if robot is None or not robot.is_connected():
        _log_command("robot", side, "move", {}, ok=False, error="Not connected")
        return _fail("Not connected")
    if not robot.get_state().get("enabled"):
        _log_command("robot", side, "move", {}, ok=False, error="Arm not enabled")
        return _fail("Arm not enabled")
    state = robot.get_state()
    with _arb_lock:
        lease_epoch = _sides[side].get('motion_epoch')
    motion_epoch = data.get('motion_epoch', lease_epoch)
    if (type(motion_epoch) is not int or motion_epoch != lease_epoch
            or motion_epoch != state.get('motion_epoch') or not state.get('motion_ready')):
        return _fail('Arm position or feedback changed. Reconnect to synchronize controls.', code='motion_resync_required')
    mode = (data.get("mode") or "joint").lower()
    if mode not in MODES:
        _log_command("robot", side, "move", {"mode": mode}, ok=False, error="bad mode")
        return _fail("mode must be 'joint' or 'cartesian'")
    if mode == "joint":
        j = data.get("joints")
        if not (isinstance(j, (list, tuple)) and len(j) >= 3):
            return _fail("Expected joints [j1, j2, j3, j4]")
        try:
            j1, j2, j3 = float(j[0]), float(j[1]), float(j[2])
            j4 = float(j[3]) if len(j) > 3 else robot.get_state()["joints"][3]
        except (ValueError, TypeError, IndexError):
            return _fail("joints must be numeric")
        if not all(math.isfinite(v) for v in (j1,j2,j3,j4)): return _fail('finite joints required'),400
        j1, j2, j3, j4 = _clamp_joints(j1, j2, j3, j4)
        _sample_z_model(side, robot)   # learn the height model from live jogging too
        j1, j2, j3, j4, znote = _apply_z_floor(side, j1, j2, j3, j4, robot)
        predicted_pose = None
        try:
            guard = _server_cal2_guard(side)
        except (ValueError,AttributeError) as exc:
            return _fail(str(exc)),403
        with _z_lock:check_ceiling = _z_ceiling_enabled
        if guard is not None or check_ceiling:
            try:
                target_joints = [j1, j2, j3, j4]
                current_joints = [float(value) for value in robot.get_state()["joints"][:4]]
                sample_count = max(
                    1,
                    min(64, int(math.ceil(max(
                        abs(target_joints[index] - current_joints[index])
                        for index in range(4)
                    ) / 5.0))),
                )
                previous_z = float(robot.get_state()['pose'][2])
                for sample_index in range(1, sample_count + 1):
                    amount = sample_index / sample_count
                    sample_joints = [
                        current_joints[index]
                        + (target_joints[index] - current_joints[index]) * amount
                        for index in range(4)
                    ]
                    predicted_pose = robot.positive_solution(*sample_joints)
                    error = _ceiling_path_error(predicted_pose[2], previous_z)
                    if not error and guard is not None:
                        error = _validate_cal2_joint_pose(predicted_pose, guard)
                    previous_z = predicted_pose[2]
                    if error:
                        error = (f"Auto PP Cal 2 blocked joint path at "
                                 f"{amount * 100:.0f}%: {error}")
                        _log_command(
                            "robot", side, "joint_cal2_guard",
                            {"joints": sample_joints,
                             "predicted_pose": predicted_pose},
                            ok=False, error=error,
                        )
                        return _fail(error, predicted_pose=predicted_pose, code='motion_limit')
            except (DobotError, AttributeError, KeyError, IndexError, TypeError, ValueError) as exc:
                error = f"could not verify joint target against Auto PP Cal 2: {exc}"
                _log_command("robot", side, "joint_cal2_guard", {}, ok=False,
                             error=error)
                return _fail(error)
        _ensure_follower(robot, mode, motion_epoch)
        robot.set_target_joints(j1, j2, j3, j4, expected_epoch=motion_epoch)
        clamped = {"j1": round(j1, 2), "j2": round(j2, 2),
                   "j3": round(j3, 2), "j4": round(j4, 2)}
        if znote:
            clamped["z_floor"] = znote
        if predicted_pose is not None:
            clamped["predicted_pose"] = [round(value, 3) for value in predicted_pose]
        _log_command("robot", side, "set_target_joints", clamped, ok=True)
    else:
        p = data.get("pose")
        if not (isinstance(p, (list, tuple)) and len(p) >= 3):
            return _fail("Expected pose [x, y, z, r]")
        try:
            x, y, z = float(p[0]), float(p[1]), float(p[2])
            r = float(p[3]) if len(p) > 3 else robot.get_state()["pose"][3]
        except (ValueError, TypeError, IndexError):
            return _fail("pose must be numeric")
        if not all(math.isfinite(v) for v in (x,y,z,r)): return _fail('finite pose required'),400
        with _z_lock:ceiling, ceiling_enabled = _z_ceiling, _z_ceiling_enabled
        if ceiling_enabled and z > ceiling:
            return _fail(f'Z ceiling {ceiling:g} mm exceeded; choose a lower target',code='motion_limit'),403
        x, y, z, r = _clamp_pose(x, y, z, r)
        x, y, z, r, znote = _apply_pose_z_floor(x, y, z, r)
        try:
            guard = _server_cal2_guard(side)
            current=robot.get_state()['pose']
            error = _validate_cal2_cartesian_path(current, [x,y,z,r], guard)
            if error:
                return _fail(error),403
        except (ValueError,AttributeError,KeyError,TypeError) as exc:
            return _fail(f'Cannot validate Cartesian path: {exc}'),403
        _ensure_follower(robot, mode, motion_epoch)
        robot.set_target_pose(x, y, z, r, expected_epoch=motion_epoch)
        clamped = {"x": round(x, 2), "y": round(y, 2),
                   "z": round(z, 2), "r": round(r, 2)}
        if znote:
            clamped["z_floor"] = znote
        _log_command("robot", side, "set_target_pose", clamped, ok=True)
    _live.bump()
    return _ok(clamped=clamped, side=side)


@bp.route("/api/pump", methods=["POST"])
@_serialize_arm_control
def pump():
    """Set this side's air pump (suck|blow|off). Requires a valid (side, token)."""
    data = request.json or {}
    _log_incoming("pump", data)
    side, err = _check_token(data)
    if err:
        _log_incoming("pump", data, ok=False, error=err)
        return _fail(err)
    mode = (data.get("mode") or "off").lower()
    if mode != 'off':
        error = _ltz_motion_error(side,{'mode':'cartesian','ltz_action':'xyz','primitive':'pump'})
        if error:
            return _fail(error),403
    if mode not in ("suck", "blow", "off"):
        _log_command("robot", side, "pump", {"mode": mode}, ok=False, error="bad mode")
        return _fail("mode must be 'suck', 'blow' or 'off'")
    robot = _arm(side)
    if robot is None or not robot.is_connected():
        _log_command("robot", side, "pump", {"mode": mode}, ok=False, error="Not connected")
        return _fail("Not connected")
    try:
        errid, resp = robot.set_pump(mode, SUCK_DO_INDEX, BLOW_DO_INDEX)
    except DobotError as e:
        _log_command("robot", side, "set_pump", {"mode": mode}, ok=False, error=str(e))
        return _fail(str(e), errid=e.errid)
    state = robot.get_state()
    pose = list(state.get("pose") or [])
    operation_id = str(data.get("operation_id") or "")[:80] or None
    command_seq = _log_command(
        "robot", side, "set_pump",
        {"mode": mode, "errid": errid, "resp": resp,
         "operation_id": operation_id, "pose": pose},
        ok=(errid == 0),
    )
    _live.bump()
    return jsonify({
        "ok": errid == 0, "errid": errid, "resp": resp, "side": side,
        "operation_id": operation_id, "command_seq": command_seq, "pose": pose,
    })


@bp.route("/api/hold", methods=["POST"])
@_serialize_arm_control
def hold():
    """Smooth-stop this side's arm but keep its lease. Requires a valid (side,
    token)."""
    data = request.json or {}
    _log_incoming("hold", data)
    side, err = _check_token(data)
    if err:
        _log_incoming("hold", data, ok=False, error=err)
        return _fail(err)
    robot = _arm(side)
    if robot is not None and robot.is_connected():
        try:
            robot.hold()
            _log_command("robot", side, "hold", {}, ok=True)
        except Exception:   # pragma: no cover - defensive
            _log_command("robot", side, "hold", {}, ok=False, error="hold failed")
    _live.bump()
    return _ok(side=side)


# LTZ capability decisions belong to Photon Progress; the relay enforces them.
_hub_ctx = None


def hub_init(ctx):
    global _hub_ctx, _watchdog_thread
    _hub_ctx = ctx
    if _watchdog_thread is None or not _watchdog_thread.is_alive():
        _watchdog_stop.clear()
        _watchdog_thread = threading.Thread(target=_watchdog_loop, name='relay-watchdog', daemon=True)
        _watchdog_thread.start()


def hub_stop():
    global _hub_ctx, _watchdog_thread
    _watchdog_stop.set()
    if _watchdog_thread:
        _watchdog_thread.join(timeout=3)
        _watchdog_thread = None
    for side in SIDES:
        with _arm_locks[side]:
            robot, _robots[side] = _robots[side], None
            if robot is not None:
                robot.close()
    with _arb_lock:
        for side in SIDES:
            _sides[side].update(token=None, present=False, motion_epoch=None)
    _hub_ctx = None


def _ltz_motion_error(side, data):
    if _hub_ctx is None:
        return 'Cannot verify LTZ controls: hub context unavailable'
    try:
        game = _hub_ctx.get_prototype('photon-game') if _hub_ctx.is_prototype_enabled('photon-game') else None
        scope = game.motion_policy(side) if game and callable(getattr(game,'motion_policy',None)) else None
        if not isinstance(scope,dict) or scope.get('contract') != 'photon.game.motion' or type(scope.get('version')) is not int or scope['version'] != 1 or scope.get('status') != 'ready':
            return 'Cannot verify the current game control session'
        if scope.get('scope') == 'waiting' or scope.get('blocked'):
            return scope.get('error') or 'Wait for the other player or shared game transition'
        if scope.get('scope') == 'tutorial':
            tier = scope.get('tier')
            if type(tier) is not int or not 1<=tier<=4:
                raise ValueError('invalid calibration tier')
        elif scope.get('scope')=='player':
            module = _hub_ctx.get_prototype('photon-progress') if _hub_ctx.is_prototype_enabled('photon-progress') else None
            policy = module.control_policy(side) if module else {}
            if policy.get('contract') != 'photon.progress' or type(policy.get('version')) is not int or policy['version'] != 2 or policy.get('status') != 'ready':
                raise ValueError('Photon Progress unavailable')
            tier = policy.get('tier',0)
        else:
            raise ValueError('unknown game motion scope')
        if not tier or scope['scope']=='player' and policy.get('stage') != 'playing':
            return 'Select a player and complete the required calibration lesson'
        mode = data.get('mode', 'joint')
        action = data.get('ltz_action', 'joint' if mode == 'joint' else 'xyz')
        required = {'joint': 1, 'xyz': 2, 'image': 3, 'cue': 4}.get(action)
        if required is None or (mode == 'cartesian' and required < 2):
            return 'invalid LTZ control action'
        # XYZ is also the internal Cartesian primitive for Targeting/Cue.
        # The server tier binds the session; browser labels cannot grant another tier.
        if data.get('primitive') == 'pump': return None
        if required > tier or scope['scope']=='player' and ((tier==1 and mode!='joint') or (tier>1 and mode=='joint')):
            return 'this control method is locked for the active LTZ player'
    except Exception as exc:
        return f'Cannot verify LTZ controls: {exc}'
    return None


def _server_cal2_guard(side):
    if _hub_ctx is None or not _hub_ctx.is_prototype_enabled('auto-pickup-game'):
        raise ValueError('Cal 2 safety owner unavailable')
    owner = _hub_ctx.get_prototype('auto-pickup-game')
    value = owner.calibration_safety_snapshot(side)
    if not isinstance(value,dict) or value.get('contract') != 'hhh.cal2.safety' or type(value.get('version')) is not int or value['version'] != 1:
        raise ValueError('Validated Cal 2 safety limits unavailable')
    if value.get('status') != 'ready':
        reason = value.get('error')
        raise ValueError('Cal 2 safety unavailable: ' + (reason if isinstance(reason,str) and reason else 'validated limits unavailable'))
    return value['guard']


@bp.before_request
def _field_reservation_guard():
    action=request.path.rsplit('/',1)[-1]
    # Operator connection opens feedback sockets; it neither enables the arm nor
    # starts a follower. Keep this recovery path available to confirm a stop.
    if action=='connect' and _is_operator_request():
        return None
    if request.method != 'POST' or action in ('stop','hold','release','kick','disconnect','heartbeat') or (action=='pump' and (request.get_json(silent=True) or {}).get('mode')=='off'):
        return None
    if _hub_ctx and _hub_ctx.is_prototype_enabled('auto-pickup-game'):
        try:
            owner = _hub_ctx.get_prototype('auto-pickup-game')
            value = owner.calibration_session_snapshot()
        except Exception:
            return _fail('Calibration reservation owner unavailable'),503
        if not isinstance(value,dict) or value.get('status') != 'ready' or value.get('contract') != 'hhh.cal2.session' or type(value.get('version')) is not int or value['version'] != 1 or value.get('active_side') not in (None,'green','purple'):
            return _fail('Calibration reservation contract unavailable'),503
        side = (request.get_json(silent=True) or {}).get('side')
        # Opening feedback sockets is the recovery step, not a motion grant.
        # The player route fixes the side; allow only the selected turn or an
        # arm whose previous stop still needs measured confirmation.
        selected = side in SIDES and value.get('active_side') == side
        if action=='connect' and (selected or side in value.get('pending_stops',{})):
            return None
        if selected and action in ('acquire','enable','clear_error'):
            # Connect -> acquire -> enable is the existing player route. A
            # display reservation must allow this sequence before begin can
            # observe an enabled arm. Move/pump still require a live lesson.
            try:
                value = owner.calibration_session_maintain()
            except Exception:
                return _fail('Calibration setup owner unavailable'),503
            if not isinstance(value,dict) or value.get('contract')!='hhh.cal2.session' or type(value.get('version')) is not int or value['version']!=1 or value.get('status')!='ready':
                return _fail('Calibration setup evidence unavailable'),503
        if value.get('pending_stops'):
            return _fail(value.get('motion_error') or 'Previous calibration stop is not confirmed'),403
        if value.get('active_side') and side != value['active_side']:
            return _fail('The other player owns the unified calibration playfield'),403
        if selected and value.get('active_side')==side and value.get('requires_activation') and action in ('acquire','enable','clear_error'):
            return None
        if value.get('active_side'):
            sessions=value.get('sessions')
            session=sessions.get(value.get('active_id')) if isinstance(sessions,dict) and isinstance(value.get('active_id'),str) else None
            stamp=session.get('access_until') if isinstance(session,dict) else None
            if not isinstance(session,dict) or type(stamp) not in (int,float) or not math.isfinite(stamp) or not isinstance(value.get('epoch'),str) or session.get('epoch')!=value['epoch']:
                return _fail('Calibration reservation evidence unavailable'),503
            if session.get('paused') or stamp<=time.time():
                return _fail('Calibration connection expired; reconnect to continue'),403
