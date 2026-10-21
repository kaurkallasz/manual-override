# Saved 3D robot movement

Player level results use one 3D field: the orc kill heatmap builds on the floor
over the saved gamefield artwork beneath measured gripper/TCP trails, Green in
green and Purple in purple. This is a replay of recorded game data. The floor
uses authored artwork and never a camera image or video recording. The view supports
mouse/touch rotation, pinch/wheel zoom, keyboard arrows and +/−, Reset View,
Top View, and independent side visibility. One timeline drives both the trails
and cumulative heatmap. Playback defaults to 20×, with 50× and 100× choices:
a 600-second level plays in 30, 12 or 6 seconds. Play/Pause, Replay and a seek slider
remain independent of camera rotation. Playback starts when the canvas becomes
visible and pauses while offscreen or the document is hidden. The last view,
timeline, speed and visibility choices survive results DOM replacements for that run.

## Ownership and coordinates

- Auto Pickup Game publishes `movement_calibration_snapshot()`:
  `hhh.cal2.movement` v1, read-only. It exposes each side's six measured ground
  samples `[camera_u,camera_v,robot_x_mm,robot_y_mm,robot_z_mm]`, saved device,
  camera binding and geometry revision. Invalid/missing bindings are unavailable.
- Game reads that contract, `hhh.relay.arms` v1 and
  `photon.board.camera-markers` v1 through the existing enabled-owner interface.
  There is no new motion, lease or hardware connection path.
- `shared.playfield_registration.py` is the existing phone camera registration,
  reused for the recorder. Each arm's six samples fit a metric field plane;
  opposing bases get their own orientation. Height is relative to the calibrated
  ground plane, not raw robot Z. Camera alignment and calibration are estimates.
- The per-run frames freeze after their first valid sample. Ground fit error
  over 20 mm, skew over 0.15, scale disagreement over 15%, changed calibration,
  changed device and camera/field movement over 0.025 normalized image units are
  unavailable. Geometry cannot silently change underneath an existing trail.

## Recording and persistence

The simulation samples at most 10 Hz during active physical play. Setup,
countdown, calibration and paused time do not contribute. Stale/non-finite
feedback, disconnections, changed motion epochs and long sampling gaps break
the polyline. Each sample is `[active_seconds,field_x_mm,field_y_mm,height_mm]`.
Times remain attached to samples for interpolation during accelerated playback; missing
intervals are never joined. No browser needs to be open for recording.

`robot_movement` v1 stores `units`, `height_basis`, `duration_s`, optional metric
`field` dimensions/normalized center, and `arms.green` / `arms.purple`:
`segments`, `status`, `error`, `gaps`, `simplified`, `truncated`. Each side is
limited to 3,000 points and 128 segments. Geometry simplification retains
timestamps and segment endpoints; excessive gap segments omit the oldest
segments with a visible notice. A reset or new attempt creates a new recorder.

The existing durable final-result outbox carries the recording through save
failures and retries. Progress validates bounds, finite values, time order and
availability on settlement and backup import. It exposes the same recording in
`latest_result.statistics.robot_movement` and saved history rows. Pending saves,
both phone result screens, desktop stats and history use the same viewer.
Older games explicitly show that no movement was recorded. This change does not
backfill old matches or recordings lost before a terminal outbox was written.

## Timed floor heatmap

`kill_heatmap` remains v1, with an optional `timeline` v1 containing `bin_seconds`
and sorted `[active_seconds, cell_index, count]` events. A cell index of -1 means
an unlocated kill. Game records the simulation time at the existing reward kill
hook. One-second bins combine kills in the same cell and use the latest actual
kill time, so no count appears before it happened. The recorder doubles the bin
width when needed to keep at most 8,192 sparse events without dropping kills.
Final cell and unlocated totals reconcile exactly; Progress validates that on
settlement and backup import, along with finite ordered times within the match.

Photon Level adds an optional `replay_floor` to its runtime bundle: a frozen
recipe of static sprite layers/transforms and versioned Level-owned asset paths.
Game retains it with the run's heatmap as `floor`. Progress validates its bounds,
transforms, crops and local artwork paths on settlement and import. The browser
composes that recipe into a cached image (at most 1,280 pixels on its long edge),
then projects it onto the field plane. Playback waits for this artwork to load
or explicitly fail before advancing the clock. No live state is used to reconstruct an
older map. Missing/legacy artwork falls back explicitly to recorded geometry.

The floor maps the saved playfield coordinates to the measured metric field.
Its fixed color scale uses the final hottest cell, making time comparisons stable.
Translucent cells preserve the field artwork underneath. Recent recorded kills
briefly flash at their cells using the same simulation clock as the arm paths.
Seeking backward reconstructs cumulative counts and their flashes. Missing arm recordings still
show the floor without claiming a metric height. Legacy results without kill
timing show their final heatmap and an explicit notice throughout playback.

## Verification

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tests .venv/bin/python -m unittest test_replay_floor test_robot_movement test_results_replay_heatmap test_player_continue test_level_results test_result_save_isolation test_mobile_client_build -q
node tests/robot_movement.test.js
node tests/robot_movement_browser.cjs
node tests/results_replay_browser.cjs
```

Browser tests use Playwright, a loopback fixture and temporary stores with fake
arms. They verify 600 seconds of playback in 30/12/6 seconds, speed changes, timed
floor artwork, colors and counts, kill flashes, rewind, missing artwork, legacy
results, seeking, pausing,
replaying, pointer rotation, pinch/wheel zoom, side colors, view retention,
pending-save transitions, reload and phone/desktop layout. Screenshots go to
`MOVEMENT_OUTPUT`, or `output/robot-movement` by default.

Backend changes take effect after the hub next restarts. Do not restart during
an active match merely to enable this viewer.
