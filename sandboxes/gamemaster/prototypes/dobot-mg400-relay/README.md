# Dobot MG400 Relay (two arms)

One game-master machine that owns **both** robot arms — **purple** and **green** —
and forwards each player's commands to *their own* arm, with safety clamps in
between. Players never talk to a robot directly; they talk to this relay.
Mounted at `/p/dobot-mg400-relay`.

## Get it working ASAP

### 1. Plug in the hardware

- **2 USB Ethernet dongles**, both into the gamemaster Mac.
- **2 Ethernet cables**, each straight from a dongle to a robot —
  **no switch or router in between**.
- purple robot ↔ dongle #1, green robot ↔ dongle #2.

### 2. Give the dongles their fixed IPs

System Settings → Network → (the dongle) → Details → TCP/IP:

- Configure IPv4: **Manually**
- purple's dongle: IP **192.168.1.50**
- green's dongle: IP **192.168.1.51**
- subnet mask (both): **255.255.255.0**
- router (gateway) and DNS: leave **empty**

Do **not** touch the robots' own IP — both stay on the Dobot factory default
`192.168.1.6`. These numbers are fixed and the same everywhere in this project.

### 3. Put both robots in API mode

See `../../docs/operations/dobot-api-mode.md`. Keep each robot's hardware
E-stop within reach and start at a low speed.

### 4. Connect and drive

- Start the hub (`python hub.py` in the repo root) and open the
  **Game Master** sandbox → **Dobot MG400 Relay**.
- Press **Connect** for each side, then **Enable**.
- In **Z soft limit**, **Enforce ceiling** defaults to **80 mm**. Adjust
  **Ceiling Z (mm)** and choose **Save ceiling**, just below the floor setting.
  The effective floor/ceiling sets the player height slider range for both teams.
- Use **Following speed** below the Z soft limit to set the shared TCP path,
  TCP rotation, joint path, and ramp/braking limits for both arms.
- Players: open the controller in your own sandbox and press **Connect** —
  it links through the relay to your own color automatically.

### If something's off

- *"no local interface has IP 192.168.1.5x"* → that dongle isn't plugged in or
  isn't configured. Check with `ifconfig | grep 192.168.1.5`.
- Purple GUI moves the **green** arm? The cables are crossed — swap the two
  robot cables (or the dongles' `.50`/`.51` IPs).
- You never need the interface names (`en10`, `en11`, … vary by Mac and USB
  port) — the relay finds the right dongle by its IP at connect time.

## How it tells two identical robots apart

Both arms answer on the **same IP** (`192.168.1.6`), so plain sockets can't
tell them apart — the OS would route everything out one port (binding the
source IP alone doesn't help; routing is destination-based). The relay
therefore pins every socket (dashboard / motion / feedback) to its side's
dongle with the macOS `IP_BOUND_IF` option *before* connecting — the same
trick as the `dualdobottest` proof of concept. The interface name is
auto-detected as whichever interface owns the side's fixed dongle IP.

`relay_arm.py` is the unified MG400 driver (merging the joint ServoJ and
cartesian ServoP drivers): one class, one connection per arm, either follower.
The relay instantiates it once per side; `start_servo(mode)` picks the
follower and `control_mode()` reports which one runs.

The two sides are **independent** and drive **concurrently** — purple's
controller drives the purple arm while green's drives the green arm, with no
blocking across sides. Per side the relay arbitrates: a controller must
*acquire* its arm (opaque token + ~2 s lease, refreshed by heartbeats); a
watchdog smooth-stops a side's arm if its holder goes quiet. Everything works
with no robot connected — an arm just reports `connected:false` and that
side's `move`/`pump` fail cleanly.

## Reference — the HTTP contract (what clients depend on)

### Z soft limits

The existing `z-floor.json` also stores `z_ceiling` (default `80`) and
`ceiling_enabled` (default `true`). Older floor-only files retain their floor
and receive the default ceiling. Writes are atomic. Both bounds must be finite,
within the physical Z workspace `[-150, 230]`, and floor must be below ceiling.

`GET/POST /api/z-ceiling` mirrors `/api/z-floor`: `{value, enabled}`; edits are
operator-only. A changed limit first settles connected arms and revokes their
leases; if stopping or saving fails, the old limits stay in force. Reconnect
player controls after changing either bound. Disabling a soft bound restores
that end of the physical workspace range.

`GET /api/z-limits` and `z_limits` in config/state/heartbeat expose
`{contract:"hhh.relay.z-limits", version:1, status:"ready", minimum, maximum}`.
Green/Purple player adapters validate and relay this contract, including on
initial configuration. Shared player controls update Z ranges and cancel queued
input without issuing movement; Mobile LTZ uses the same range for its height
slider, presets and cue height. The floor continues to use its existing clamps.
Cartesian requests above the ceiling are rejected; joint paths are checked with
controller forward kinematics, even without a learned floor model. From a
manually placed position above the ceiling, only descending joint recovery is
allowed. These are software target/path limits, not a replacement for hardware
limit switches or an emergency stop.

Sides: `purple`, `green`. Modes: `joint`, `cartesian`. `LEASE_SECS = 2.0`.
Shared robot IP: `192.168.1.6` (both arms). Per-side default links (the fixed
dongle IP each side's sockets are pinned to; interface name auto-detected):
`{"purple": {"local_ip": "192.168.1.50"}, "green": {"local_ip": "192.168.1.51"}}`.

### State

`GET /api/state` (also SSE `GET /api/events`, sampled ~5x/s):

```jsonc
{
  "arms": {
    "purple": {"connected": bool, "enabled": bool, "mode_name": str,
               "joints": [j1,j2,j3,j4], "pose": [x,y,z,r],
               "feedback_at": float, "feedback_ok": bool, "feedback_age": float|null,
               "motion_epoch": int|null, "motion_ready": bool,
               "servo_active": bool, "servo_error": str|null,
               "alarm_ids": [int, ...],
               "fault_kind": "emergency_lock|joint4_positive_limit|joint4_negative_limit|workspace_limit|collision|controller_fault|unknown_fault|null",
               "fault_label": str|null,
               "pump_mode": "off|suck|blow|conflict",
               "control_mode": "joint|cartesian|null",
               "target": [..]|null},
    "green":  { ...same shape... }
  },
  "sides": {
    "purple": {"present": bool, "lease_secs": float},
    "green":  { ...same... }
  },
  "motion_settings": {
    "tcp_xyz": 20.0, "tcp_rotation": 9.0,
    "joint": 12.0, "ramp_secs": 0.5
  }
}
```

`pump_mode` is derived from each arm's digital-out bits: suck = index 2, blow =
index 1; both set = `conflict`. `control_mode` is that arm's running follower.
When `robot_mode` is ERROR, the relay reads `GetErrorID()` in a separate,
read-only background thread and uses `fault_kind` to distinguish an emergency
lock from a workspace/joint-limit stop, collision stop, or another controller
fault. A regular software hold remains enabled/idle and has no `fault_kind`.

### J4 rotation diagnosis

Each operator arm card shows the actual J4 tool-holder rotation in degrees,
including complete turns (1577.5° stays 1577.5°). The readout uses `joints[3]`,
not Cartesian `pose[3]` (TCP R) or base joint J1. It is red outside the published
MG400 J4 range of −360° to +360°, green inside. These are diagnostic reference
limits; the relay's existing, narrower command clamps remain in effect.

Alarm 70 is identified as `joint4_positive_limit`; alarm 71 as
`joint4_negative_limit`. The red status bar explains the condition, shows the
degrees beyond the reference range, and says whether the value must decrease
or increase toward that range. It also shows a measured out-of-range condition
before an alarm code is available. Emergency and collision messages retain
priority when several alarms occur together. A green angle never clears or
hides a controller alarm that remains reported.

The display requires connected feedback with `feedback_ok: true` and a finite
`feedback_age` no older than 0.5 seconds, including time elapsed in the browser.
Invalid timestamps yield a null age. Lost, malformed or silent SSE updates hide
the angle and recovery direction; disconnected default zeroes are never shown
as a valid angle. Monitoring adds no enable, reset, clear-fault or motion calls.

This ports the condition documented in the “Fix Dobot remote enable error” chat
in 3D printing Lab 1 2026. References:
[Dobot alarm definitions](https://github.com/Dobot-Arm/TCP-IP-4Axis-CSharp/blob/main/alarm_controller.json),
[MG400 motion specifications](https://www.dobot-robots.com/products/desktop-four-axis/mg400.html).

Checks: `.venv/bin/python -m unittest discover -s tests -p test_relay_rotation_diagnostics.py`
and `node tests/relay_rotation_diagnostics.cjs`. Browser layout smoke test:
`node tests/relay_rotation_browser.cjs` with Playwright on `NODE_PATH`.

### Operator endpoints (no token)

| Method | Path | Body | Effect |
|---|---|---|---|
| POST | `/api/connect` | `{side, local_ip?, ip?, iface?}` | Connect THAT side's arm via its pinned dongle, replacing any existing connection for it. Omitted fields fall back to that side's default dongle IP / the shared robot IP; `iface` overrides the auto-detection. |
| POST | `/api/disconnect` | `{side}` | Disconnect that side's arm. |
| POST | `/api/enable` | `{side}` | Enable, invalidate old movement and wait for fresh settled feedback. Returns `motion_epoch`; never starts the follower. Clears the arm's error first. Clients include their current token. |
| POST | `/api/kick` | `{side}` | Force-release that side's controller; smooth-stop that side's arm. |
| GET/POST | `/api/motion-settings` | `{tcp_xyz?, tcp_rotation?, joint?, ramp_secs?}` | Read or update the persistent follower settings shared by both arms. Updates apply immediately to connected arms and to later connects/mode switches. |

### Client / side endpoints (operate on the side's OWN arm)

| Method | Path | Body | Effect |
|---|---|---|---|
| POST | `/api/acquire` | `{side, mode}` | Acquire THIS side's connected arm; discard previous movement and mint a token with `motion_epoch`. Both sides can hold concurrently. No servo stream starts. |
| POST | `/api/release` | `{side, token}` | Release this side's arm. |
| POST | `/api/heartbeat` | `{side, token}` | Refresh this side's lease; returns the full state. Stale token → `{ok:false, error:"stale token"}`. |
| POST | `/api/move` | `{side, token, motion_epoch, mode, joints?\|pose?}` | Validate the lease generation, fresh feedback and complete path before starting the follower and setting a target. |
| POST | `/api/pump` | `{side, token, mode}` | Set that side's pump `suck\|blow\|off`. |
| POST | `/api/hold` | `{side, token}` | Smooth-stop that side's arm, keep its lease. |

Player relay clients may also call `/api/connect` for their side if the operator
has not connected that arm yet. This lets a player sandbox bring up its own arm
through the relay without first opening the operator page. Requests whose
authenticated roles are only team roles (see the hub's `shared_api` door) are
rejected with 403 unless `side` is their own team.

The operator command monitor is also persisted as newline-delimited JSON in
`command-monitor.log` in this directory. Each command is appended immediately;
the on-page monitor still keeps only the latest 160 entries.

Tokens are opaque strings (`f"{side}-{counter}"`). A new `acquire` for a side
invalidates that side's old token; any token mismatch on
`release`/`heartbeat`/`move`/`pump`/`hold` fails with `"stale token"`.

### Programmatic API (for other machines via the hub)

- `arm_state(side)` → that side's arm sub-object (same shape as `state["arms"][side]`).
- `arms_snapshot()` → the named `hhh.relay.arms` version 1 read-only output for
  both sides. It reports current connection, pose, target, enabled, and pump
  state and never issues a robot command.
- `side_holder(side)` → the opaque token currently holding `side`, or `None`.
- `full_state()` → the full relay state (same shape as `GET /api/state`).

## Safety notes

- **Per-side ownership.** Each side has its own lease + token; two tabs of the
  same side can't fight (a fresh `acquire` invalidates the old token). The two
  sides never block each other.
- **Per-side watchdog (~5 Hz).** If a side's holder lease expires (no contact
  within `LEASE_SECS`), THAT side's arm is smooth-stopped (`hold()`) and the side
  is freed. The other side is unaffected.
- **No software E-STOP.** Stopping is mechanical — use each robot's hardware
  E-stop button. The relay has no global software stop/latch to get stuck in.
- **Safety clamps** (per arm) mirror the test machines exactly:
  - joint: each angle clamped to `JOINT_LIMITS`
    (J1 ±160, J2 −25…85, J3 −25…105, J4 ±160 deg);
  - cartesian: Z clamped to −150…230 mm, R to ±160°, and X/Y to the reachable
    annulus (radius 150…440 mm) then the ±450 mm box.
- **Shared following limits.** The operator controls both arms together. Defaults
  are 20 mm/s TCP XYZ, 9 deg/s TCP rotation, 12 deg/s joint-space path, and a
  0.50 s acceleration/braking ramp. Settings persist in `motion-settings.json`.


## LTZ progression and calibration admission (2026-10-01)

The existing motion path reads `photon.game.motion` v1 first. Explicit GM
practice/tutorial grants work for both arms without selecting saved profiles.
Normal play requires `photon.progress` v2 and its mandatory tier. The relay
obtains `hhh.cal2.safety` v1 from its owner; browser calibration claims cannot
replace it. Joint FK and Cartesian paths are checked before follower creation.
During a calibration reservation, the inactive arm and expired session reject
movement. Missing or malformed reservation state, nonfinite expiry times, and
an old session epoch fail closed; Stop, release, disconnect and pump-off remain
available. `stop_side`
returns `hhh.relay.stop` v1 only after fresh finite settled feedback. The
watchdog starts in `hub_init` and stops in `hub_stop`, never at import.

`disable_side(side)` returns `hhh.relay.disabled` v1 with `inhibited`, `connected`
and `disabled`. It revokes that side's controller, confirms settled motion,
stops the follower and disables connected servos. `disabled: true` requires
fresh feedback. Offline returns `connected: false, disabled: false` with control
inhibited; it neither connects nor asserts an unobserved physical stop. Cal 2
uses this function before and throughout the other player's turn, and when a
measured calibration completes. A failed shutdown retains the durable motion
gate; saving calibration measurements can still finish while disconnected.

Operator display exit can leave Cal 2's durable `pending_stops` populated. Relay
then rejects both arms' motion/enable/acquire requests even when no target display
is reserved. Stop, disconnect, release and pump-off remain available. Operator
Connect is also available: it opens feedback sockets without enabling an arm or
starting a follower, allowing measured stop confirmation to recover the existing
gate. Screen navigation never clears this hardware requirement.

Cartesian recovery from a measured boundary stop is bounded to 10 mm outside
the owner-supplied Cal 2 envelope. The destination must be valid; sampled motion
must never worsen a violated constraint or cross another boundary, and must
remain inside after re-entry. Larger excursions and malformed geometry remain
blocked. This uses the same admission, reservation, token and follower path as
ordinary moves; reconnecting grants no additional reach. Regression:
`python -m unittest discover -s tests -p test_cartesian_boundary_recovery.py`.


Calibration connection setup permits the selected player to open its existing
Relay sockets, acquire and enable while the display has `requires_activation`.
Game then activates the lesson after fresh enabled-arm/camera evidence. Move and
pump-on still require a live same-epoch lesson grant. Setup runs owner maintenance
before acquire/enable; unresolved pending stops continue to block those actions.
A side with a pending stop may open feedback sockets solely so the stop can be
confirmed. Another side cannot use this exception to acquire or move. Player
identity and the existing per-arm lease remain authoritative.


## Reconnect and physical unlock

Connect/Enable never resumes a target. Enable waits for feedback received after
its request: finite joint and TCP coordinates, idle/running mode, age <=250 ms,
and joint measurements stable within 0.2 degrees for at least 80 ms. The first
validated movement repeats that synchronization and seeds the follower from the
measured position with zero velocity. A one-second timeout leaves it stopped.
The feedback reader latches even a single unlock/disabled/fault/paused packet by
incrementing `motion_epoch` and clearing pending targets. Feedback loss, socket
failure and unexpected follower/actual displacement also invalidate movement.
The stream checks that epoch again at the socket send boundary. A previous
follower must finish stopping before another one can start.

Each lease binds to the motion epoch established by Acquire/Enable. An old move
fails even if unlock and relock happen between browser polls or while its path
is being checked. Mobile adds a connection identity to every movement request,
so an HTTP request delayed across replacement of the player connection cannot
bind to the new arm session. Player adapters preserve the robot feedback time
and mode, reject reordered telemetry and never invent freshness from a live HTTP
connection. Green and Purple use the same behavior.

Mobile clears joint/XYZ goals, gestures and queued commands on disconnect,
unlock and resynchronization. It ignores delayed replies and old-connection
status, publishes a new control revision, and follows the measured position on
reconnect. Stop closes the player lease before the next Connect. Motion requires
a new deliberate gesture. Outside-boundary feedback remains visible; existing
path validation still controls any recovery move, and no connection operation
moves to a boundary or silently clamps an out-of-range joint/rotation goal.

Hardware-free regressions:

```sh
.venv/bin/python -B -m unittest discover -s tests -p 'test_relay_reconnect.py'
node tests/mobile_arm_bridge_smoke.cjs
MOBILE_TEST_TEAM=purple node tests/mobile_arm_bridge_smoke.cjs
```

### Player feedback delivery

Each connected arm now runs its existing `relay_arm.DobotMG400` driver in a
relay-owned spawned process (`arm_worker.py`). Camera, game, JSON and garbage
collection work in the hub can no longer starve the driver's feedback reader
or servo loop. This is still one driver/socket set per arm and one validated
relay command path. Importing the module opens no sockets or processes; Connect
starts its worker, and disconnect/replacement/`hub_stop` closes it.

Telemetry and stop/reset calls have a separate local pipe from dashboard
commands. Pending motion/pump-on requests expire after 250 ms rather than replay
after a blocked command. Original feedback timestamps and motion generations
are retained. The driver still stops on a real 250 ms feedback gap, unlock or
fault; the player still requires feedback within 1.5 s. A separate worker
watchdog cancels motion, requests StopRobot and pump-off, and exits if the hub
dies or misses its two-second parent heartbeat. Worker failure requires an
explicit new connection; there is no automatic restart or target replay.

`python -m unittest discover -s tests -p 'test_relay_worker.py'` uses fake
feedback with the real driver/follower and no robot sockets. It reproduces a
shared-process feedback failure under a 400 ms Python pause, checks continuous
feedback through repeated 600 ms hub pauses in the isolated version, and checks
real loss/unlock, stale-command rejection, parent loss, process crash, both
teams' Connect/Enable routes, and teardown. A hub restart is required to adopt
the worker transport for physical connections.

The spawn entry point is the standard-library `runpy.run_path`, loading the
relay's own `arm_worker.py` and driver in the child. The hub intentionally
removes prototype helpers from `sys.modules`; passing a cached helper function
or default driver class to `spawn` fails Python's pickle identity check after
that cleanup. No helper cache exception or second robot-control path is needed.
Startup failures are converted to the existing `DobotError` contract, so the
Connect endpoint returns a JSON diagnosis and leaves no owned worker/lease.
`tests/relay_worker_hub_smoke.py` exercises the real hub loader in a fresh Python
process, both teams' fake Connect/Enable, and the default driver's rejection of
an invalid local interface before any robot socket is opened.

`GET /api/feedback?side=green|purple` pushes full `hhh.relay.feedback` v1
snapshots through the existing SSE helper every 100 ms. Each contains `status`,
one side under `arms` and `sides`, and the versioned `z_limits`. It is read-only:
it cannot acquire/renew a lease, enable an arm, or send motion. Player adapters
consume this stream independently of the 700 ms heartbeat and retain the
original robot `feedback_at`; delayed heartbeat replies cannot replace newer
measurements. `POST /api/heartbeat` accepts `feedback_only: true` to return the
same compact state. Legacy callers still receive full monitor state.

Neither compact path reads the disk-backed command monitor or the other arm.
The full operator snapshot releases the lease lock before reading its monitor.
Feedback publication and motion-epoch validation share one lock order, so a
delayed status reader cannot revoke newer healthy feedback. The 250 ms driver
and 1.5 s player freshness limits, unlock latch, lease checks, and explicit
reconnect requirement remain unchanged. `motion_invalidation` identifies the
last epoch change (feedback gap/stale/disconnected, robot mode, reset, or servo
failure) and passes through to the mobile connection diagnostic log.

Both player adapters close their stream and heartbeat on disconnect and module
shutdown. Their read-only stream uses a one-second socket timeout so the reader
can close its own response without racing HTTP chunk parsing.

```sh
.venv/bin/python -B -m unittest discover -s tests -p 'test_relay_feedback.py'
.venv/bin/python -B tests/relay_feedback_transport_smoke.py
```
