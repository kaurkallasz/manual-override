# Green player disconnect investigation — 2026-10-11

## Observed in the current match

The persisted Green connection events show four `motion_epoch_changed` stops
between 17:34:17 and 17:39:45 UTC, plus one `feedback_stale` stop at 17:36:16.
The epoch stops arrived with connected/enabled feedback, robot mode 5 or 7,
feedback ages of 38–484 ms, and an unpaused, ready game. The stale event reached
1,567 ms. There was also a deliberate page-away suspend, which is expected.

A read-only relay check after the reported stops found Green still physically
connected, enabled and idle, with approximately 6 ms feedback age, no robot
fault and no servo error. The final epoch was 17. The logs did not record the
specific driver invalidation reason, so they cannot prove whether every epoch
stop was a real packet gap or the reader race below. No robot command or live
game reset was sent during investigation.

## Reproduced software defects and changes

1. The driver copied feedback, checked freshness, and only then locked the
   motion epoch. Another thread could publish continuous fresh feedback between
   those steps. The delayed reader could return old feedback with a new epoch,
   or invalidate the healthy generation using its old timestamp. Two regressions
   fail against the original driver. Feedback and epoch publication/validation
   now use a consistent servo-then-state lock order.
2. Player status was refreshed only by a heartbeat that slept 700 ms after its
   HTTP reply. Request delay plus browser delivery could exhaust the 1.5 s
   freshness budget despite an active robot link. Both player adapters now read
   a 100 ms SSE stream from the existing relay, with original measurement times
   and ordering checks. Heartbeat and motion authority remain separate.
3. Full heartbeat responses included monitor history, and reading the monitor
   held the lease lock while waiting for disk-backed logging. Compact feedback
   and heartbeat snapshots omit monitor history; full monitor reads no longer
   hold the lease lock.

Driver invalidation reasons now propagate into the existing connection log to
distinguish a real feedback gap, unlock, reset and servo failure on a later run.
No freshness deadline was relaxed, and no automatic reconnection or movement
replay was added.

## Verification and activation

- 43 relay tests and 4 Cartesian boundary-recovery tests passed.
- 106 mobile Python tests and both teams' mobile arm bridge smokes passed.
- Loopback HTTP/SSE test with fake arms and 900 ms heartbeat response delays:
  both players received at least 20 distinct fresh measurements, approximately
  105 ms maximum measured age; stale feedback stopped readiness and transports
  shut down cleanly.

The backend changes require a hub restart; refreshing the player page also
loads the additional diagnostics. The active match was left running. These
results verify the software failure paths without moving hardware; repeated
physical play after activation remains the live confirmation.

## Recurrence after activation — 21:55–22:04 Tallinn time

The new client build includes the earlier diagnostics. Four later Green stops
at 21:55:04, 21:59:03, 22:02:54 and 22:03:45 now identify the driver's
`feedback_stale` invalidation, with the robot still connected/enabled. A separate
22:02:41 stop exceeded the player's 1.5-second feedback budget while game data
was also approximately 1.6 seconds old. These are timing failures, not evidence
that the robot socket disconnected. A subsequent 12-second read-only sample
received 109 relay snapshots with a maximum measured feedback age of 38 ms;
that short healthy sample cannot exclude intermittent cable/controller faults.

The driver still shared the hub's Python process with vision, simulation and
snapshot work. The live process sample showed vision and Python work, including
GIL contention and collection. A deterministic fake-arm regression reproduces
the same safety invalidation when that process is paused for 400 ms. This
reproduces a software cause of the logged symptom; it does not establish that
every live gap had the same cause.

The relay now owns one spawned `ArmWorker` per connected arm. Each worker runs
the existing driver, feedback reader and follower, with the same socket pinning,
250 ms freshness deadline, unlock latch and motion generations. Commands still
pass through the relay's existing permissions, lease and calibrated path checks.
Read-only status and Stop/reset use a separate local pipe from dashboard I/O.
Queued movement and pump-on expire after 250 ms and are never retried or replayed.

The worker also monitors its parent: EOF or a two-second heartbeat loss cancels
motion, requests StopRobot and pump-off, and closes the driver. A crashed worker
fails closed and requires explicit reconnection. Connect failure, replacement,
disconnect, module shutdown and normal interpreter exit release the worker.
The browser's 1.5-second safety budget is unchanged; longer real outages still
stop control.

Validation uses no physical robot commands: 11 new process tests cover repeated
600 ms hub pauses with live fake feedback/follower, real feedback loss, unlock,
stale-target rejection, slow command versus status/Stop, parent loss, child crash,
both teams' actual Connect/Enable routes and teardown. The existing 43 relay,
108 mobile and 4 Cartesian boundary tests also pass. The loopback transport test
still passes with 900 ms delayed heartbeat replies and a 105 ms maximum measured
feedback age.

Activation completed after explicit user approval. Both old relay connections
were closed through the existing Disconnect route before the port-8000 hub was
stopped. The replacement runs the same Conda Python runtime as the old hub
(PID 93345). At 22:22:13 Tallinn time, the authenticated relay state and both
mobile player pages returned HTTP 200, with no startup tracebacks or import
errors. Both arms reported disconnected, disabled and no active follower;
neither was reconnected or moved during verification. The updated worker will
start on the next explicit arm connection. Repeated physical play remains the
live confirmation.

## Immediate Connect failure after the 23:26 restart

Green's 23:29–23:31 connection attempts reached the relay but immediately
returned the generic `relay arm connect failed` error. Both relay arms remained
disconnected. The new worker transport had not yet succeeded on a physical
Connect after activation.

The real `Sandbox._load_one` loader removes imported prototype helpers from
`sys.modules` to isolate sandbox copies. This invalidated both the worker
entrypoint and its default driver class for Python's `spawn` pickler: each
raised `PicklingError: ... it's not the same object as ...`. Existing worker
tests used a simpler loader that retained those helpers, so they missed it.

Worker startup now uses the stable standard-library `runpy.run_path` entrypoint
to execute the relay-owned worker file in its child process. The child imports
the default driver locally; no purged driver class crosses the process boundary.
Setup failures become the existing structured `DobotError`, with pipe/process
cleanup. Player Cartesian and joint controllers now distinguish a returned
relay error from a network failure, retaining the underlying diagnosis.

Validation: 13 worker tests (including fresh-process production-loader startup
for both fake arms and a default-driver probe that rejects an invalid local
interface before opening a robot socket), 14 reconnect tests, 9 feedback tests,
and 4 Cartesian boundary tests passed. The production-loader smoke also passed
under the live hub's Conda Python runtime. No physical motion was used for testing.
The loaded backend requires a restart to activate this correction.
