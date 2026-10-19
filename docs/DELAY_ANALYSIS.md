# Delay Analysis

Game Master → Photon Engine → Mobile LTZ API → **Delay Analysis**.
Local route: `/s/gamemaster/p/mobile-ltz-api/delay-analysis`.

This is an opt-in timing recorder. It does not move an arm, change a timeout,
relax a safety check, acquire a lease, or make extra camera/robot observations.
Install by loading the updated code at the next planned hub restart, then refresh
the player pages. Restart the mobile gateway during its normal maintenance window
to obtain the additional hosted-route timings. Once loaded, recording starts and
stops live; do not use the hub's module enable/disable switch (that restarts the hub).

## Operator workflow

1. Choose both players, Green, or Purple. Shared server work is included for either team.
2. Start recording. The default duration is **Until I turn it off**, so a full game is not cut short. Optional 1, 5, 15 or 30 minute timers remain available. Recording is off after startup.
3. Play normally. Closing the analysis tab leaves recording active. Mark an incident
   when a delay is noticeable. Execution spans and browser frame/timer stalls of at least 250 ms, delivery gaps of 500 ms, feedback ages of 1,000 ms, movement holds and driver failures preserve incident windows. Hidden-page timing stalls are excluded; automatic timing incidents are spaced by 15 seconds and repeated failure labels by five seconds.
4. Inspect maximum and p95/p99 durations, then the incident timeline. Filter by
   `camera`, `simulation`, `lock`, `feedback`, `mobile`, `delivery` or `diagnostics`.
5. Stop recording, wait for the buffer and participant acknowledgements, and export
   JSONL timings or a CSV operation summary. Starting again replaces the displayed
   capture. The last three captures (each with a detail file and a summary checkpoint) remain on disk until normal rotation.

Stopping disables producers immediately. Server records already queued are drained.
A browser sends one final bounded batch with its stop acknowledgement; no periodic
uploads remain. Unsent records beyond that batch are counted as dropped. Browser
and worker capture permissions expire after four seconds without renewal, including
when a tab or connection is stranded. The UI distinguishes acknowledged stop from
an absent/unresponsive participant. An older enabled update cannot undo a newer stop.

## Reading the measurements

- **Elapsed** includes calculation, I/O, scheduling and lock waits. **CPU** measures
  the current thread's CPU time. Low thread CPU alone does not prove I/O: native
  libraries may work on other threads. Lock wait/hold spans provide direct evidence.
- **Own time** subtracts synchronous child spans. Nested total times overlap and
  must not be added together. IPC child spans carry their parent's trace identity,
  but remote execution is not subtracted from the caller's explicit IPC wait.
- Feedback age, frame/update gaps and scheduling lag are **gauges**, not execution
  spans. They are ranked separately by name and are never included in parent time.
- A lock's `lock_id` plus process ID relates a waiter to the holder of that same
  lock. Names alone can describe several instances of the same component.
- Host and arm-worker timing share the host monotonic clock. Each browser uses its
  own monotonic clock. Browser groups in the timeline have independent origins.
  Delivery sequences correlate updates; do not subtract a phone timestamp from a
  server timestamp to claim exact network transit time.
- Gateway receive gaps, local parse and queue durations ride the existing hosted
  stream. Gateway encoding, tunnel/proxy internals and network transit are not
  individually measured. They remain an unmeasured part of the delivery path.
- Browser long-task observation is optional. Timer lag and animation-frame gaps
  also work in browsers without that API. Hidden-page delays remain labelled and
  do not create automatic browser incidents.
- Statistics cover the **entire capture**. Counts, totals and maxima are exact for received records; percentiles use bounded 5% timing buckets across all received samples, rather than a sliding tail. The UI displays up to 300 records, including up to 60 decision-evidence entries, with at most 24 execution spans per clock group. The live buffer holds up to 60 seconds / 20,000 detailed records. Locks shorter than 1 ms contribute to summaries without individual records. Older saved incident windows remain selectable after the rolling buffer expires and after a server restart.
- Incidents preserve a collection-time window (10 seconds before, 5 after), limited by the available rolling buffer, capture start/stop and detail storage. Monotonic start/duration timestamps remain the authority for execution order. Nested and overlapping windows are deduplicated on disk. The detail export contains incident windows, not every routine operation. Dropped records and absent participants mean the trace is incomplete.
- Expand **decision evidence** in the timeline for board status, rejected marker IDs/reasons/sizes, pending/quarantined markers, verified anchor IDs and hull, or driver failure text, error type, process health and parent heartbeat age. Controller hold events include the board evidence used by that browser. Evidence is allowlisted and bounded; this records existing decisions without changing them.

## Instrumentation coverage

`shared/delay_trace.py` owns the recorder and its public `delay.analysis` version 1
contract. It is a shared helper, not a sibling prototype import. Mobile LTZ API
owns its lifecycle and authenticated UI/API. Module imports perform no background
work. Each producer times its existing work locally:

- Webcam: capture, resizing/grayscale, all three ArUco detector passes, tracker
  updates, JPEG encoding and state-lock waits/holds.
- Calibration: board checks, undistortion, corrected tag mapping, preview encoding
  and state access.
- Photon Board: source reads, sampling/state locks, cue targets/layouts, occupancy,
  placement, tracking and runtime/preview snapshots.
- Photon Game: level/status/assets, configuration, progress/post-match projection,
  simulation step/snapshot/ingestion, missed simulation deadlines and engine locks.
- Mobile facade: complete snapshot including existing diagnostic observation,
  camera/safety/cues/calibration/progress/assets and generation gaps.
- Delivery: shared preparation lock, JSON encoding; existing diagnostic redaction,
  field sizes, preview encoding and response processing. Existing delivery previews
  and ordinary safety/connection logging retain their previous behavior when this
  new recorder is off; their costs can now be measured while recording.
- Arm relay: command logging/lock, feedback snapshots, worker IPC lock/response
  waits, driver command/reply and feedback publication/lock timings. Worker config
  and bounded records ride the existing request/reply channel. No extra commands,
  polling loop or control channel is introduced. Coverage updates are nonblocking.
- Player: stream parse/receive gaps, presentation wait/application, frame/timer
  stalls, feedback age and same-origin arm iframe status request/application,
  snapshot and message delivery.

## API for operators and AI

All control and export endpoints below require the existing **gamemaster** role.
POST requests use the existing origin/JSON protections. Paths are relative to
`/s/gamemaster/p/mobile-ltz-api/`:

| Request | Purpose |
| --- | --- |
| `GET api/delay` | State, timings, coverage, limits, errors and incident list |
| `POST api/delay` with `{"action":"start","side":"both","seconds":0}` | Start; 0 means until stopped (default), or 10–1,800 seconds |
| `POST api/delay` with `{"action":"stop"}` | Stop live, retain evidence |
| `POST api/delay` with `{"action":"mark","label":"Green paused"}` | Mark an incident; label ≤160 characters |
| `POST api/delay` with `{"action":"clear"}` | Clear displayed capture after recording/buffer drain |
| `GET api/delay/events` | Existing SSE helper, one-second dashboard updates |
| `GET api/delay?incident=<id>` | Retained incident detail |
| `GET api/delay/export` | JSONL metadata + detailed records |
| `GET api/delay/export?format=csv` | Operation summary |

Player pages receive a small `delay_analysis` control descriptor in existing state
updates. They submit allowlisted timing batches through the already-authorized
team-specific `POST api/diagnostics` route (`delay.analysis` v1); a player cannot
start/stop captures or read another team's diagnostics. This reuses existing
hosting allowlists. No credentials, command arguments, images or full game payloads
are written by the timing recorder.

## Bounds and failure behavior

- Producer queue: 8,192 records, nonblocking admission with drop counts.
- Rolling records: 20,000; operation keys: 1,024; histogram buckets/key: at most 401; incidents: 256;
  remote participants: 32; worker ring: 512, at most 128 records per existing reply.
- Browser ring: 512; batches: 100 / 64 KiB maximum; normally two uploads per second.
- Detail writer: 650 MiB per capture (681,574,400 bytes). The display reads the active server's limit; the increased limit takes effect when the hub loads the updated code. Reaching this budget **does not turn recording off**: whole-session summaries continue, saved incident details remain, and a prominent warning reports omitted later detail. An optional duration limit or storage error stops recording and displays an explicit coverage warning. Dropped timings and observer errors are also visible. Capture duration depends on incident volume: the October 12 Green game filled 64 MiB in about 113 seconds, which extrapolates to about 19 minutes at 650 MiB, rather than a guaranteed 30 minutes.
- Summaries are separate atomic checkpoints every five seconds and after stop/drain. They contain bounded per-operation histograms, counters, incidents and coverage, so filling the detail budget cannot consume summary capacity. Three capture pairs are retained. Actual filesystem write failures remain possible and stop recording with an error.
- Files live in the ignored, module-owned `data/delay-analysis/` directory. They
  are append-written by the collector, without per-event disk writes or fsync in
  game/robot paths. A crash may lose the buffered tail. Existing application logs
  have their own behavior and retention.
- The UI reopens the latest saved summary after a server restart, with recording **off**. An unclean interruption is flagged; up to the last five seconds of statistics and queued records can be lost. Stop preserves results; Clear removes only the displayed capture. Export before starting another capture to keep a convenient copy. Existing captures made by the older recorder remain as raw JSONL files; they have no new summary checkpoint to restore.

## Verification

Run using the repository virtual environment:

```sh
PYTHONPATH=tests .venv/bin/python -m unittest test_delay_analysis test_mobile_api_monitor test_mobile_client_build test_relay_worker test_relay_feedback test_relay_reconnect test_mobile_connection_log test_webcam_lifecycle test_camera_contracts -q
node --test tests/mobile_delay_trace.test.js
.venv/bin/python tests/benchmark_delay_analysis.py
```

The injected-delay tests distinguish CPU work, lock contention and blocking waits;
cover bounds, stale capture rejection, role/origin checks, final acknowledgement,
export, observer failure isolation, and timing transport through a real worker
process using a fake driver. Existing camera, relay, game and delivery tests cover
behavioral regressions.

For UI verification, start `tests/mobile_ltz_fixture.py --port 8137` and run
`tests/delay_analysis_browser.cjs` with Playwright available. It checks desktop and
390-pixel layouts, an injected 320 ms browser stall, start/stop acknowledgements,
export and retained results after reload, with zero game control commands. It uses
temporary data and simulated hardware only.

The benchmark compares capture off/on using the real mobile projection over the
isolated fixture at 20 builds/second. This measures recorder overhead, not a bound
on real-game latency or proof of the previous stall's cause. A live capture is the
next diagnostic step after deployment.
