Shared Mobile LTZ presentation assets for Green and Purple. Each player's
`mobile-ltz/prototype.py` freezes this same bundle at hub initialization and
supplies `data-mobile-team` in HTML. Runtime state belongs to the team-specific
module, game arm and LTX frame; these frontend files have no global Python state.

Physical Cue tracks confirmed two-Atom stacks by tag ID across rows, Clear view,
pause/resume and subsequent Play runs in the same game/controller. Board's fresh
camera-only stack descriptor can also identify a stack placed by the other arm.
The upper Atom's pickup uses the selected arm's calibrated pickup plus its saved
`stack_drop_offset` (default 31.5 mm), including normal fine tuning. A confirmed
release onto a board marker restores normal pickup height. Command receipt failure
or interruption while carrying leaves height uncertain; stale or conflicting stack
evidence holds acquisition. A revealed lower Atom cannot silently turn an old
stack into a normal-height pickup. Game/layout changes discard local records;
camera outages preserve them and camera epoch changes require revalidation.

The current operation raises travel height by the needed stack offset, including
resume and image-intervention routes, while retaining normal clearance and Z/reach
checks. One-Atom camera calibration remains unchanged; a two-Atom pickup extends
the calibrated parallel-plane perspective model using the recorded sample height.
Inconsistent perspective samples and stacks taller than two Atoms are refused.
Fresh camera acquisition remains the XY authority, even after a confirmed release.
Load the Board addition at a hub restart, then refresh both player pages. No saved
calibration values are changed. `node --test tests/cue_recovery.test.js` includes
both teams/views, stack/unstack, uncertain receipts, pause, Clear view and height
limits using fake camera/robot feedback; physical accuracy still needs a supervised
pickup with the real rig.

Safari memory lifecycle: the shared game renderer limits image requests/decodes
to four at a time and retains only converted runtime textures for tower upgrades,
field tiers and archer poses. It releases source atlases, cancelled requests,
obsolete presentations and evicted canvas buffers explicitly, including failed
conversions and page-cache teardown. A queued state cannot restart a destroyed
renderer. The camera decoder likewise releases each JPEG after the persistent
canvas receives it. Gameplay, camera freshness and motion checks are unchanged.

The isolated Chromium fixture measured retained decoded-image storage decreasing
from 132,194,792 to 44,079,360 bytes, with identical map pixels. These are resource
dimensions, not measured iOS process/GPU memory; those tests did not reproduce
the remaining native iPhone crash described below. The renderer is read from disk with cache revalidation, so its fix loads
on player-page refresh. Physical camera play now avoids creating the hidden
simulation renderer entirely and releases its map/game/arm canvases. Returning
to virtual play recreates the renderer; changing back cancels pending artwork
and releases every owned buffer. Page teardown prevents late script completion
from recreating the view. The 4K camera world no longer requests a permanent
`will-change` layer. Camera coordinates and targeting geometry keep their
original resolution. These mobile JS/CSS changes are in the frozen client bundle
and require a normal main-hub restart and page refresh.

`tests/mobile_camera_memory_browser.cjs` runs in WebKit by default (or with
`MOBILE_TEST_BROWSER=chromium`) against the isolated fixture. It checks both
teams, 3840×2160 camera coordinates with a 1920×1080 preview, physical/virtual
switches, delayed script completion after teardown, and page-cache restoration.
Physical startup downloads no simulation artwork and retains zero hidden-renderer
buffers, versus 79,108,352 bytes in the virtual fixture. These are probed image
and canvas dimensions, not a measurement of the iPhone process's total memory.

Connected-iPhone investigation subsequently confirmed a native memory kill:
WebContent exceeded its 1536 MB soft limit and was killed at 2,245,986 KB while
the JavaScript heap was only 14 MB. Disabling CSS filters or changing JPEG
decoders did not cure it. The main and inset camera canvases now request
`{alpha:false, willReadFrequently:true}` on their first 2D-context creation.
This avoids the accelerated camera surface path that accumulated native memory
on the connected iPhone. Temporary application on that device kept both camera
feeds and the original overlays responsive without further memory warnings.
The user confirmed that connecting the real arm now stays open; the inspector
also verified a live physical session after 383 seconds. After the normal hub
restart, both live team bundles contain the fix and the iPhone loads it at the
normal player URL without a temporary override.
The aligned XY glow also now targets only the small bullseye groups: the
previous selector unintentionally filtered both full-camera guide paths.
The 4K/3×-pixel-ratio relock regression checks that all three guides remain
unfiltered while the arm is connected and aligned.

Checks: `node tests/safari_memory_renderer.cjs` and
`node tests/mobile_video_smoke.cjs`; against the isolated fixture at port 8152,
`node tests/safari_memory_browser.cjs` covers real artwork, repeated cache
replacement/teardown and both player pages' restoration. It issues no gameplay
or robot commands. `MOBILE_MEMORY_TEST_URL` overrides the fixture origin.

Green shows an optional MCAM1 inset at the upper right, immediately left
of the right-side control/Cue panel. Its canvas is half the camera's native
width and height (480×320 becomes 240×160), shrinking further only to fit narrow
screens without covering controls. Availability and freshness arrive in the
existing game SSE projection; a separate, non-overlapping JPEG request loop
loads the read-only video. Disabled, missing, stale, malformed or failed frames
hide the inset without interrupting play. Fresh frames restore it automatically;
hidden pages stop loading it. This never starts capture or connects USB controls.
The Game Master's MCAM1 preview must already be running. The existing hosted
asset proxy and frozen client bundle include this feature. Load changes at the
next hub restart and player-page refresh.

Camera assignment is **Green → MCAM1; Purple → MCAM2**. MCAM2 is not implemented
yet, so Purple keeps the inset hidden and makes no MCAM1 frame requests. Its
`mobile_mcam1` projection is unavailable and its MCAM1 JPEG route returns 503.
When MCAM2 is implemented, expose its own validated still contract through the
mobile API, add Purple's metadata projection and authenticated JPEG route, then
connect Purple's inset to that feed with the same freshness and lifecycle checks.
Never fall back to Green's MCAM1 footage. Update the browser/API coverage to verify
that each player receives only its assigned camera.

Verify with `python -m unittest discover -s tests -p 'test_mobile_mcam1.py'` and
`node tests/mobile_mcam1_browser.cjs` against
`python tests/mobile_ltz_fixture.py --port 8146 --virtual-controls` (isolated, no hardware).

Turret aiming keeps persistent SVG geometry and a persistent touch handle.
Camera timestamps/diagnostics no longer replace the cone's DOM. A valid
registration may keep its display and an existing drag for up to one second,
bounded by the original frame's 1.5-second freshness; repeated frames cannot
renew it. The gesture uses the mapping captured at touch-down, so ordinary
registration jitter cannot move the pointer's coordinate system. Camera,
calibration, level, viewport, turret-revision or significant registration changes
invalidate the draft. A real camera/feed outage or expired registration does too.

New gestures still require current alignment. Releasing an existing drag during
a brief detector miss waits at most one second for fresh alignment before using
the same server-validated aim command. It never submits from cached evidence or
replays an expired draft. This does not change marker size rejection, robot
readiness or game ownership checks. The optional MCAM1 inset is included among
the obstacles when placing the turret's handle.

`node --test tests/mobile_turret_continuity.test.js` checks continuity and
invalidation. `node tests/mobile_turret_stability_browser.cjs` against the
isolated fixture at port 8146 checks both teams' native touch drags, repeated
camera packets, brief registration loss, deferred saving and expiry without
replay. The regular `mobile_turret_browser.cjs` also covers virtual/physical aim,
ownership, rotated player views and four viewport sizes.

The battlefield disables native text/image selection and drag, including
Safari's whole-canvas blue/grey selection highlight. A selection intersecting
the battlefield is cleared on selection changes, page restoration, ordinary
clicks and Escape. Editable controls and status text outside the field remain
selectable. MCAM1 is outside the battlefield's selected document fragment.
`node tests/mobile_selection_browser.cjs` against the isolated fixture at port
8146 covers both teams in virtual and physical-camera modes, stale-selection
recovery, pointer release, and text editing without issuing arm commands.

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

Targeting Go re-reads the camera owner's current Atom observation before applying
raised-tag correction. The background acquisition list refreshes every 750 ms,
so it cannot decide a 500 ms freshness check for an SSE-updated preview. A hidden,
stale, moved, foreign or unverified Atom is rejected without falling back to a
flat camera target. A verified target rejection holds the previous motion,
clears queued gestures, and preserves the session and pump; the player must
select a target again. Camera/feedback/transport failures and failed holds still
follow the disconnect path. The bridge smoke test covers both teams, including
Stop during an in-flight camera read; the limit-recovery smoke covers the phone.

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

Before committing calibration, tap a checked number again to undo that arm
position or raised-tag sample. Saved raised samples can be undone without placing
the crosshair. During the raised-tag step, expand **Saved arm positions · edit**
to undo any of the six arm captures. Removing an arm position clears its dependent
raised sample and calculated heights until it is captured again. The calibration
owner persists these edits and updates the projected highlights without moving
the arm. Projected calibration numbers rotate 180° for Purple; marker geometry
and the phone's already-upright label overlay keep their existing orientation.

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

Fixed board cues consume `photon.board.cue-targets` v2. Once camera-confirmed,
fixed coordinates remain immutable for the game/map; late markers join without
resetting known ones. Malformed individual geometry is diagnostic and does not
remove saved coordinates or shrink a permitted hull. Positive valid positional
contradictions block only the affected endpoint. Coherent movement of separated
markers, camera identity/correction/dimension changes, and a new game reset map
authority. Genuine banner/window relocation still requires reacquisition.

An acquired Atom survives expected occlusion only for its current operation.
New pickup/placement evidence remains live. Camera/sampler staleness, another
occupant, real board movement, calibration, reach/path and robot feedback checks
still hold through the existing control route and preserve suction as before.
The controller selects one current publication: fresh SSE can recover a stale
acquisition poll, while a newer unavailable publication revokes authority even
if its frame timestamp did not advance. V1 retains its old region checks only
for rollout compatibility. Delay Analysis optionally records the precise failing
gate, source and both current/polled ages; disabling it removes extra evidence.

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
The physical adapter takes this orientation directly from the current viewport
when dispatching Play. Legacy commands without it use the player-side default
(Green 0°, Purple 180°); an explicit 0° remains valid for either player. The
standalone controller uses its visible Flip setting. Rotation is disabled while
a cue is starting, running, waiting or paused, so its arrows cannot reverse
relative to a pending Clear view move. Cue-start diagnostics record the angle.
Pause/Resume retains the same target instead of adding another displacement. Clearing
the camera view does not fabricate placement confirmation. Virtual practice uses
a horizontal offset of 10 board units per cm with the same row
sequence and rotation behavior.

`node tests/mobile_clear_view_browser.cjs` runs the complete two-team virtual
placement/clearance flow and portrait/landscape checks against the isolated
fixture started with `python tests/mobile_ltz_fixture.py --port 8134 --virtual-controls`
(`MOBILE_XYZ_TEST_URL` overrides the test URL). Physical clearance,
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

Physical fixed labels use v2 `fixed_tags`, the same run-scoped owner memory as
Gamemaster. They survive camera occlusion, detector geometry rejection and a
camera/feed outage without granting motion authority. A new map/game clears them;
late confirmed IDs appear without flickering existing labels. Current Atom labels
use their own fresh observations with at most one second of display grace; they
are never frozen. Core/Atom physical size is not compared with socket size, and
live alignment size rejection cannot erase a confirmed fixed label. Legacy v1
input retains its previous conservative display behavior. No label cache supplies
arm state, pickup, placement, or permission to move.
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
Physical feedback freshness compares the relay timestamp with
`feedback_observed_at` from that same controller status response. It adds the
full request duration as a conservative transport bound and advances age with
`performance.now()` since receipt. It never compares a hub timestamp with the
phone's wall clock or an independently delayed Game snapshot. Missing/invalid
status timing, future feedback, or a 1.5-second-old measurement blocks control.
The independent Game-delivery watchdog and the relay's own freshness,
enabled-state and motion-epoch checks still apply.
Repeated copies retain their accumulated age, including the sample's age on
first receipt. A phone clock change cannot renew stale feedback or disconnect a
healthy arm. `node --test tests/mobile_arm_clock.test.js` covers both teams with
clock offsets, delayed Game projections, slow status responses, frozen messages,
expired clock evidence and physical unlocks. Deploy the controller Python change
before reloading player pages: old running backends lack the paired timestamp
and the new bridge will fail closed. Connection logs include the signed
Game/feedback delta, status sample age and status request duration; disconnected
measurements do not keep accumulating in the feedback-age delay gauge.
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

Progress presentations cache detached snapshots for each side and Game Master
until a committed database write invalidates them. Commands and motion policy
remain uncached. Database replacement or removal invalidates cached reads too.
Game's progress publication can be read without waiting for its result outbox
writer. Delay Analysis records progress snapshot builds and SQLite/lock timings.
`tests/test_progress_snapshot_cache.py` covers commit/rollback, concurrent reads,
external updates, detached values and the outbox publication.

`node --test tests/mobile_arm_trajectory.test.js` checks constant playback speed
through sparse/jittered/repeated samples, measured stops/reversals, underruns,
detours, path removal and resets. `node tests/mobile_arm_trajectory_browser.cjs`
runs against the isolated fixture to measure intermediate display positions,
verify constant speed with jittered 100 ms feedback in the real renderer for both
orientations, endpoint alignment and path disappearance on arrival. Bridge/planner tests
cover source timestamp preservation, route projection and unchanged commands.


The shared equipment/receipt and score feedback use `shared/ltz_ui` in both
Score/Y and phone clients. `bundle.assemble()` remains the single local/hosted/export
assembly. The store shows eligible unlocked equipment only. Credits, signed debt,
prices, purchases and level unlocks come from Progress; there are no purchase buttons.

Both players register inside the selected event. New games start L1 Joint for both;
Load restores the linked pair and between-match progress. Start locks that pair.
Results display actual score, earnings, automatic or GM-forced turret purchases,
remaining balance and control/force-field unlocks. Continue/Ready acknowledges the
result; Game Master prepares and starts the next match. Required L3 calibration
continues to block normal motion. Independent calibration setup remains available.

Practice/game simulation, test tier overrides, grants and practice datasets are
removed from production flows. Developer engine fixtures remain isolated from
physical hardware and real player data. Validation: `tests/event_progression_browser.cjs`
checks Game Master plus both landscape phones with temporary profiles and fake arms.

Each level's saved result uses the shared `LTZShop.receipt`/`mount` celebration:
count-up totals and personal/shared kills, score comparisons, animated pair history,
and actual automatic turret/second-Atom unlocks. Animation timelines survive SSE
renders, offscreen reveals wait for visibility and reduced motion is respected.
`tests/level_results_browser.cjs` also checks portrait and the existing projector.
