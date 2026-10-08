Shared Mobile LTZ presentation assets for Green and Purple. Each player's
`mobile-ltz/prototype.py` freezes this same bundle at hub initialization and
supplies `data-mobile-team` in HTML. Runtime state belongs to the team-specific
module, game arm and LTX frame; these frontend files have no global Python state.

`arm-bridge.js` is served by both LTX modules and uses the existing controller's
`TEAM`, calibration, relay and guarded command path. Camera-normalized points
remain in the original camera frame. `Viewport` alone applies the selected
0°/180° presentation and inverse input transform. XYZ sliders, arrows and
measured-position markers follow that viewport direction; height stays upright.
Their readouts and command payloads retain canonical coordinates.

LTZ camera selection allows a bounded 25 mm band beyond the outer calibrated
arc. Pickups, drops, image taps, and the displayed arc share the same inward
edge correction. Raised Atom perspective correction runs first for tagged
pickups. The commanded robot pose still must satisfy the owner’s 439 mm guard,
base/rear exclusions, and relay path checks; physical reach is not expanded.
The inward offset remains in cue candidate metadata. Camera error can still affect
gripper alignment; the range check alone does not verify a physical pickup.

The inner exclusion display and cue endpoint checks use the same 220–439 mm
robot envelope. A 10 mm inner / 4 mm outer planning margin only chooses
interior detour waypoints; it cannot reject an otherwise valid pickup, drop,
or measured starting position. All executed segments still pass full motion
validation. A camera-visibility hint makes repositioning optional, distinct
from a rejected target or unsafe path.

Regression checks:

- `python -m unittest discover -s tests -p 'test_mobile_*.py'`
- `node --test tests/cal2_boundary.test.js tests/cal2_motion.test.js tests/cue_recovery.test.js tests/cue_selection.test.js`
- `node --test tests/cue_start_feedback.test.js`
- `node tests/mobile_viewport.test.js`
- `node tests/mobile_arm_bridge_smoke.cjs`
- `MOBILE_TEST_TEAM=purple node tests/mobile_arm_bridge_smoke.cjs`
- Against `python tests/mobile_ltz_fixture.py --port 8138`, run
  `node tests/mobile_relock_browser.cjs` for both teams' calibration exit,
  manual unlock/relock, Connect, and fresh height movement without target replay.
- `node tests/mobile_xyz_steps_smoke.cjs`
- Against `python tests/mobile_ltz_fixture.py --port 8117`, run
  `node tests/mobile_xyz_direction_browser.cjs` for both teams' native touch,
  rotation, fine ranges and marker alignment, then
  `node tests/mobile_xyz_controls_browser.cjs` for calibrated fake-robot controls.

Cue transport preserves unchanged Play text and attributes during live updates.
Play shows Starting immediately while command receipts are pending; command
validation shares the button's readiness checks and reports refusals. Cue row
receipts compare ordered piece/destination values, independent of JSON field
order; changed or missing rows still fail closed. Numbered
input diagnostics distinguish pointer presses/cancellations, handler activation,
and command submission, including repeated taps. In physical play, Stop remains
an arm hold/pump-off control when connected: it reads Stop arm while idle/stopped and
Stop cue while a cue is active. Mobile UI changes load with the next hub launch
and player-page refresh; restarting the hub discards an in-memory game run.

During the player's calibration turn, disconnect/Stop, physical unlock and
page suspension keep existing suction on while stopping motion and releasing
control. This keeps the calibration Atom attached. Reconnect to operate the
pump; an explicit pump-off still releases suction. Blow is not retained.

Physical unlock invalidates the old motion session. After relocking, press
Connect to synchronize with the measured pose; only a new gesture moves the arm.
The embedded controller follows the same control assignment changes as the
phone, including leaving calibration with an unchanged test unlock. This avoids
a connected phone waiting indefinitely for Cue while the controller retains
calibration's XYZ/Targeting mode. The shared controller HTML is served directly
with no-store headers, so fixes in that file need only a player-page refresh.

Cue playback adds a cyan bullseye at the selected piece's pickup position while
preserving the existing final-destination bullseye and guides. The pickup preview
stays anchored through pre-pickup occlusion and pause. It hides when the virtual
arm holds the piece or the physical controller completes the pickup lift and
its existing failure check. It stays hidden through release; the next placement
or replay captures its own source. Clear view, completion and Stop also clear it.
This is display-only state and never supplies motion coordinates or evidence.
`node --test tests/mobile_cue_bullseye.test.js` checks its lifecycle;
`node tests/mobile_clear_view_browser.cjs` checks both player views and replay.

Saved cues are reusable: Play after completion or Stop starts at row one;
Resume keeps the paused step. Every fresh physical start refreshes camera
mapping, validates ownership/session/readiness, and rebuilds the controller's
queue from the saved rows. The runner acquires new positions for that run.
Play during an earlier runner's cleanup reports that it is still stopping and
preserves its abort flag. The bridge is served with no-store and loads on a
player-page refresh without restarting the hub; Connect alone does not reload
an already-open page.

An acquired physical cue position survives tag occlusion for its current
operation. A conflicting fixed-marker detection holds the arm while the camera
owner confirms or rejects the apparent map change. Recovery of the same map
keeps the acquired pickup; confirmed map/layout/calibration changes require a
new acquisition. Invalidation diagnostics identify the changed identity and,
when supplied by the owner, the fixed marker responsible. No tag-age or robot
feedback safety deadline is extended.

New placements include a separate `{action:"clear_view"}` row immediately after
them by default. Its minus button removes just that action; **+ Clear view** on
the placement restores it. Saved opt-outs stay removed. Placement rows keep their
`{piece,destination}` format. Clear view cannot be first or follow another Clear
view, and counts toward the 32-row limit. Removing a placement also removes its
dependent Clear view row. Saved programs and receipts preserve both row types.
The row has left/right arrow buttons and an editable distance in cm (0.1–50,
0.1 cm steps). The selected arrow shows the phone-view direction. Both fields
lock during playback/pause and persist with the cue. Canonical rows include
`direction:"left"|"right"` and `distance_cm`; legacy action-only rows remain
equivalent to left, 5 cm. Changed direction/distance requires a new confirmed
cue receipt before Play.

After release and return to travel height, physical Clear view reads the measured
arm position, requires the pump off, and converts the selected centimetres to
millimetres in XY toward the selected phone-view direction. The calibrated local camera direction and the phone's
0°/180° rotation at fresh Play determine that direction. It uses the existing
guarded planner and arrival checks; an unsafe offset stops with a row error.
Pause/Resume retains the same target instead of adding another displacement. Clearing
the camera view does not fabricate placement confirmation. Virtual practice uses
a horizontal offset of 10 board units per cm with the same row
sequence and rotation behavior.

`node tests/mobile_clear_view_browser.cjs` runs the complete two-team virtual
placement/clearance flow and portrait/landscape checks against the isolated
fixture at port 8134 (`MOBILE_XYZ_TEST_URL` overrides it). Physical clearance,
rotated calibration, reach rejection, and interrupted arrival are covered by
`cue_recovery.test.js`; `mobile_arm_bridge_smoke.cjs` verifies the typed program.

Physical destination dropdowns combine camera candidates with IDs from the
current level and the other team's assigned Atoms. Both dropdowns show only ID
numbers. Missing camera candidates remain editable, without supplying any
coordinates or evidence to the runner. A camera-map hold explains why Play is
blocked while row editing remains available. Changed layouts immediately remove
obsolete catalog choices; a selected obsolete ID is retained with its number
disabled. Opening a native picker refreshes its options even if the phone
left it focused after its previous opening; SSE does not replace open options.
The cue status message sits directly above the bottom transport buttons. The
panel background is black at 20% opacity (80% transparency); text and controls
retain full opacity.

Cue image-click recovery uses fresh corrected-image readiness independently of
the tag-acquisition map. A disputed fixed tag can hold an automated pickup/drop
without blocking a player-selected image point. The bridge requires a ready
camera view, valid image dimensions/alignment metadata, and at most 1.5 seconds
of frame age including the local game-receipt age. Calibration, connection,
ownership, reach, path and robot-feedback checks still apply. Active cues use
the existing intervention owner: wait for an atomic pump command, lift to travel
height, move to the clicked point, preserve suction and pause state, then require
normal cue revalidation. This does not certify or reset a held tag map.

Physical marker labels use the existing `photon.board.cue-targets` v1 feed and
fresh `photon.board.camera-markers` v1 detections, independently of robot feedback
and connection. The facade publishes current detections as
`mobile_camera.tracking`, with their frame timestamp and projection `server_time`,
even when level alignment is unavailable. A brief cue-map or alignment hold can
therefore leave visible detections on screen. Frame age including local receipt
age is limited to 1.5 seconds; movable sightings expire after 0.5 seconds. Fixed
memory remains displayable only under a fresh ready cue map. No held-map poses
are cached or promoted into movement evidence. These display records never
populate arm state, clear a map hold or authorize movement.
The initial game state, live stream and controller discovery start before the
artwork renderer finishes loading. When it is ready, it paints the newest state.
Virtual and calibration labels keep their existing sources.

`node --test tests/mobile_tracking_startup.test.js` covers disconnected-arm
display, cue-map/alignment holds, stale/malformed feeds, both orientations and
delayed/failed renderer startup. `node tests/mobile_tracking_startup_browser.cjs`
uses the isolated fixture on port 8134 to verify visible labels before
controller/renderer readiness, continued detections during mapping holds, expiry
and recovery, with no robot commands.

The red XY marker, its guides and XYZ actual indicators play timestamped measured
positions at a roughly 30 Hz display cadence. Linear interpolation follows source
time instead of easing toward each packet, so steady travel does not repeatedly
slow and accelerate. Arm snapshots expose `position_at` in Unix seconds: the
physical bridge preserves the relay's `last_feedback`, including on repeated
publications; the virtual owner timestamps its snapshot. The mobile controller
uses its existing non-overlapping status poll at 100 ms and immediately publishes
accepted feedback. Playback buffers 150 ms for physical polling jitter and
250 ms for the virtual stream. `position_settled` flushes playback to the measured
endpoint, including a mid-route stop: two distinct fresh idle feedback poses
60–350 ms apart must agree within 0.05 mm on each XYZ axis, in the same relay
session and motion epoch. Idle mode alone is insufficient. The virtual owner
marks actual joint arrival. No display movement continues after that stop signal.
Playback never predicts beyond received positions, holds on a buffer underrun
and resumes without a catch-up jump. Missing timestamps use the raw position.
Raw feedback remains unchanged for commands, checks and pickup logic. Session,
mode, coordinate-space/layout changes, hidden pages and stale data reset playback.
The green destination and cyan pickup marker keep their existing behavior.

The dashed red `motion_path` shows the current checked movement, including
detours. The calibrated controller publishes its existing execution plan through
the optional read-only `mobileArmPath` callback; the bridge samples robot-space
segments before camera projection and includes `{id,points}` on its arm snapshot.
Points use the same camera-normalized space as the arm tip. Stop, disconnect,
joint control, failed/interrupted movement and changed calibration invalidate
the route. This telemetry cannot issue movement or change the planner. The
virtual owner publishes its actual bounded joint-travel curve in board units.
The player view removes the passed portion monotonically as the smoothed red
marker traverses it; completed portions do not regrow from telemetry jitter.

`node --test tests/mobile_arm_trajectory.test.js` checks constant playback speed
through sparse/jittered/repeated samples, measured stops/reversals, underruns,
detours, path removal and resets. `node tests/mobile_arm_trajectory_browser.cjs`
runs against the isolated fixture to measure intermediate display positions,
verify constant speed with jittered 100 ms feedback in the real renderer for both
orientations, endpoint alignment and path disappearance on arrival. Bridge/planner tests
cover source timestamp preservation, route projection and unchanged commands.
