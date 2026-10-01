# Mobile control modes

The mobile control-path dialog selects Joint, unlocked Cartesian XYZ, Targeting, or Cue autonomy. Its
availability combines the game-owned virtual test override with the current team’s saved
progress when the override is absent. Server validation is final. A new connection defaults to the highest implemented
unlocked mode (Cue at tier 4, Targeting at tier 3, XYZ at tier 2, Joint at tier 1). An unlock change also selects
that default and freezes old motion. A manual lower-mode choice remains selected
during ordinary heartbeats until the next unlock change or fresh connection.
Opening the dialog freezes the current target at the actual pose while preserving
the existing session and any held tag. Mode changes clear queued client input.

Joint mode retains its animated arm illustration, dial, joint sliders, fine tune,
and actual-position indicators. XYZ hides the joint illustration and map arm
segments, retaining virtual tags and pump controls. X uses a horizontal slider. Y is vertical along the right edge, starting at the top safe margin. Both sliders
and their arrows follow the displayed playfield: right moves right and up moves
up, including Purple's default 180° view and either team's manual rotation.
Thumbs, track fills and measured-position indicators use the same orientation;
numeric readouts, saved calibration and submitted goals retain map coordinates.
Rotation changes presentation without requesting movement. Connect and Stop are on the left. Z is a vertical left-edge slider with high
values at the top. It fills the available space below the left-aligned Connect/Stop buttons and
above the pump controls. All reuse the joint
slider styling and thin glowing red actual-position markers. Fine tune uses a
one-tenth range and 0.1 map-unit steps. Normal steps are one map unit. Map bounds
expand when the current arm pose lies outside the battlefield.

A green glowing bullseye marks selected X/Y, and a thinner red glowing bullseye
marks authoritative actual X/Y. Both become orange within two map units, regardless
of zoom. Z remains separate, so XY alignment does not indicate height alignment.
Bullseyes share the world transform and keep a constant visual size during zoom.
Dashed horizontal and vertical green/red guide lines cross each respective
bullseye and extend to the visible screen edges, including letterboxed areas.
The guides follow the same orange convergence and stale-position states.
In Cue, marker numbers stay upright and below the displayed code in either
orientation; their placement offset rotates with the player's view.
Stale positions fade and cannot claim alignment. Two-finger pan and pinch remain camera-only. The zoom toolbar, minimap and Fit
button are removed from the mobile UI. Actual positions are never substituted with requested targets.

Invalid or out-of-map XYZ targets produce visible feedback and restore the latest accepted
target without disconnecting. Stop, stale feeds, backgrounding and touch
cancellation use the existing suspension path, clearing pending XYZ input. Mode
revisions prevent queued commands from a previous mode from moving the arm.

The published client retains its established six-file contract. XYZ lives in the
existing HTML/CSS/JS bundle; restarting the main hub publishes a new frozen build
for both local and hosted mobile views.

Checks: `python -m unittest discover -s tests -p 'test_mobile*.py'`, then start
`python tests/mobile_ltz_fixture.py --port 8127` and run
`node tests/mobile_xyz_browser.cjs` with Playwright available. The browser suite
uses only that isolated virtual fixture, including the real Laser Tag Y unlock
form. It checks landscape/portrait layouts, movement, convergence, locked controls,
unlock tiers, rejection, and mode changes. It writes screenshots to `/tmp`.


## Height presets

Three square buttons beside Z provide local height memories. A continuous
three-second pointer or Space/Enter hold stores the selected Z target without
issuing a movement. A fill animation tracks the hold; stored buttons turn green,
and a matching selected target has an amber border. A short press recalls only
Z via the existing validated XYZ command queue, preserving X and Y. Empty slots
show holding instructions. Touch cancellation, focus loss, mode changes, Stop,
and suspension cancel pending holds. Release after a save does not recall again.

Finite preset values persist in versioned browser storage on this phone. If that
storage is unavailable, feedback explains that the save is session-only. Values
outside a later level's height range cannot be recalled but can be replaced.
Each visible saved height draws a thin light mark across the Z track and a dotted
connector to its numbered button. Markers follow resize and fine-tune ranges;
out-of-view values hide their guide until they return to the visible range.

Run `node tests/mobile_z_presets_browser.cjs` against the port-8127 isolated
fixture to check three-second timing, recall, persistence, cancellation, no
movement on save, and five mobile layouts.

## Targeting

Tier 3 enables Targeting using the same server-validated XYZ intent and session.
It removes X/Y sliders, retaining height, its actual-position indicator, three
height presets, both bullseyes and their screen-spanning guides. Fine tune sits
directly below preset 3, aligned to the numbered preset column. The Go button
sits beside Suck/Blow, matching their column width and combined height. It is
dim and disabled until a new target preview is ready, then glows green. Pressing
Go submits the preview once and clears its glow; fresh control availability and
the existing server validation still gate movement.

Start a single-finger drag within 32 screen pixels of the green target. Movement
preserves the finger offset and selected height; it previews without moving
until Go is pressed. Fine tune reduces XY drag to
one tenth while retaining the fine height range. A second finger ends the drag
and drops unsent input, then pans/zooms only; already accepted movement completes
through the normal arm simulation. Lifting fingers does not begin another drag.
A fresh touch is required. Tapping elsewhere does not move the arm.

Run `node tests/mobile_targeting_browser.cjs` against the isolated fixture to
check preview/Go submission, fine tune, height/presets, camera navigation,
cancellation, unlock defaults, and portrait/landscape alignment. Set
`MOBILE_TEST_TEAM=purple` to exercise the other player's rotated view.

## Cue autonomy

Tier 4 opens a sliding right drawer with up to 32 ordered piece/destination rows.
Plus adds a row; each row has a minus button. All controls use the square mobile
style. The compact drawer shrinks to its contents, displays `100 → 44` summaries,
and retains Play/Pause and Stop. Both views highlight the server's current row.
During playback and pause, the green bullseye and its guides point to that row's
destination marker, advancing when the row changes. Red follows the actual arm
through pickup, transfer, and placement; orange indicates arrival at the displayed
destination. Intermediate motion goals continue to drive the height slider.
Socket/core IDs and Green piece IDs appear beside their virtual map positions.
These are simulated level positions, not a claim of live camera detection.

Game owns every cue step. Play resolves and validates approach, pickup, lift,
transfer, release and lift-clear poses through the existing arm IK and joint
simulation. A step completes only at the actual joint target. Placement uses
the same Game placement/core rules as manual controls. Travel height is the
selected Z, with a minimum of 80; pickup/release height is 60 map units.
All level markers are reachable at every supported height (0–400). The virtual
arm uses equal longer links and full joint rotation; joint motion remains smooth
and bounded at 12°/s. Hardware geometry and limits are unchanged. Invalid inputs
and unavailable markers still stop a row with an error.

Pause retains the held piece and stage goal. Stop freezes execution while
retaining rows and any held piece; another Play starts at row 1. On a row error,
Play retries that row unless the list was edited. Manual controls remain disabled
while running or paused. Mode changes, global Stop, feed loss and backgrounding
stop the cue through the existing session lifecycle; reconnect never auto-plays.
Editing a paused draft and pressing Play starts the revised list from row 1.

The cue list is retained in the game session; unsent edits are local to the page.
Reloading restores the server's saved list, not unfinished local edits.
`node tests/mobile_cue_browser.cjs` verifies actual two-row placement, pause/resume,
compact highlighting, settings edits, marker overlays, and five phone layouts.

## Blue inserted waypoint

A single tap/click on the battlefield in Cue mode inserts one blue waypoint.
The server visits it at cue travel height, then resumes the interrupted cue step
without advancing the row or repeating pickup/release. Green remains on the
current row's destination; red follows actual motion. Blue has its own glowing
bullseye and screen-spanning guide lines, and disappears after actual arrival.

A later tap replaces blue. The blue row appears immediately before the active
cue row, including in compact view; its × cancels the detour. Paused insertion
and replacement stay paused. Before Play, a tap prepares the cue and queues a
waypoint without starting movement. Stop, mode changes, session loss and
reconnect clear the waypoint. Editing/replacing the saved cue also clears it.

Taps must end within 600 ms, move no more than 8 screen pixels, and remain
single-pointer. Pinch/pan, canceled touches, control buttons and taps outside
the map do not insert. Pan/zoom transforms are inverted to map coordinates.
Both drawer sizes retain one Play/Pause toggle, plus Stop; no separate Pause
button is added. Tests: `test_mobile_cue.py` and `mobile_waypoint_browser.cjs`.

The expanded cue editor is 142px wide (half its previous 284px width), with
compact square controls and readable three-digit selectors. Marker numbers use
16.5px screen-space text (50% larger), centered 4px below the rendered ArUco
code using the level’s marker coordinates and footprint. They stay attached when
zooming or panning; movable piece labels follow their current positions.

All four simulated control modes use the virtual 10% speed profile: 12°/s
per joint, based on 10% of the project Dobot joint-speed range (120°/s).
This approximates the low-speed feel; virtual geometry is not calibrated to
physical Dobot timing. Pause, Stop and controller expiry still freeze motion
immediately.

The Joint illustration keeps its original vertical shoulder anchor above the
right slider dock, independent of the expanded virtual joint limits. Those
limits still control the pose and scale, without pushing the drawing upward.

Arrow-shaped buttons immediately outside Suck and Blow step base J1 left/right.
Matching buttons at both ends of the J2/J3 sliders decrease/increase each joint.
All use 1° per tap normally and 0.1° in Fine tune, through the same guarded
target queue as the dial and sliders. The arrows are twice as tall, with their
rectangular tails matching the adjacent button height. The joint sliders retain
their measured red indicators in the shorter track between their buttons.
Steps accumulate from the selected target, preserve fractional feedback angles,
and clamp to the runtime limits. The dial updates with each accepted tap;
Button labels show the active step. Disconnected/disabled arms, other control
modes, backgrounded pages and concurrent map/control drags cannot request a step.
Test: `node tests/mobile_base_step_smoke.cjs`.

## Turret targeting overlay

Confirmed Green placements automatically open a screen-space firing overlay.
Touching a friendly turret reopens it. One square at the firing endpoint previews direction and range together: drag
around the turret to aim and radially to change reach; release saves through Game's `mobile_turret_aim` entry point.
The native weapon control descriptor supplies range endpoints, cone width and
mortar blast radius. The same square adjusts radius only for Tesla. Close retains saved aim.
Turret gestures take precedence over arm movement and cue waypoint taps.

The authenticated `turret_aim` command uses the existing command URL but does
not use a virtual-arm session or move hardware. Game checks run, placement,
Green ownership, activation identity, aim revision, phase and finite inputs.
Stale edits fail explicitly; destroyed/replaced turrets cannot inherit a save.

Physical play replaces map canvases with the shared corrected camera JPEG and
hides inactive virtual-arm controls. A single screen overlay uses the same
camera rectangle and pan/zoom transform. Mobile API registers at least four
non-collinear, fresh level-marker centers to corrected camera coordinates;
missing, ambiguous, stale or inconsistent marker evidence disables editing.
Registration is presentation-only, not arm calibration or placement authority.
The video request uses `assets/mobile-camera.jpg`, already supported by the
hosted authenticated proxy. Lens correction remains owned by Camera Calibration.

Verification: `tests/test_mobile_turret.py` and `tests/mobile_turret_browser.cjs`
cover ownership, revisions, physical-mode edits without an arm session, tracking
failure, actual touch gestures, camera alignment, orientation and reconnect.
Physical browser checks use synthetic camera frames; live optical alignment
still depends on the deployed camera and visible markers.


## Physical team robot controls

Physical play uses the same mobile dial, joint sliders, fine adjustment, XYZ
rails, height presets, draggable target, pump buttons and Cue panel as virtual
practice, over the corrected Photon Board camera. The calibrated reach boundary
and red hatched exclusion area stay aligned while zooming and panning.

Both `/s/green/p/mobile-ltz/` and `/s/purple/p/mobile-ltz/` serve one shared UI
from `shared/mobile_ltz`. The owning module supplies the team; identity,
saved progress, arm sessions, turret ownership and browser preferences stay separate.
`api/physical-controller` discovers the local team's LTX through
`<team>.robot-controller` v1. Its offscreen execution frame exposes
`<team>.mobile-arm` v1 via same-origin,
source-checked postMessage. State contains real joint feedback, normalized camera
coordinates, millimeter heights and numerical reach polygons. Mobile LTZ only
projects these into its viewport; LTX owns calibration conversion, planning,
Auto PP Cal 2 guards, and the existing Cartesian XYZ Test/team relay path.
Purple uses its own calibration samples, joint guard, reach polygon and relay
side. Missing calibration or hardware feedback remains unavailable.
Physical shoulder/elbow sliders send the latest selected joint goal through
that same guarded follower path as the base dial. They do not use the virtual
1.2-degree feedback-paced slew; the relay owns acceleration and braking.
Virtual sessions keep their existing slew and simulation API.

Connect is explicit and uses the existing player relay connection, which enables
the arm. Enable is also shown if a connected arm has been disabled. Physical
controls never reconnect automatically.
Commands require a session, increasing sequence and current control revision.
Practice overrides/player tiers still apply. Stale game or robot feedback,
pause, hidden pages, parent heartbeat loss and mode changes stop owned motion.
Changing modes keeps a healthy mobile session while cancelling old gestures and
confirming a relay hold. `control_pending` disables movement during this handoff;
failed holds still release the session. Obsolete commands return
`control_changed` with the current arm state, without forcing a reconnect.
Stop cancels pending commands immediately; pump-off remains available even when
motion is unavailable. Cue destinations require fresh camera detections.

XYZ arrows step X/Y by 10 map units and Z by 1 height unit (1 mm physically).
Z arrows also appear in Targeting and Cue; running or paused cues lock manual
height. Fine tune divides arrow increments by ten (X/Y 1, Z 0.1) and updates
their visible numbers and accessibility labels, as Joint does. Taps
accumulate from the selected target and clamp to the full runtime axis limits.
Height requests set `height_only: true` on the existing `xyz` command. LTX uses
fresh measured robot X/Y directly, avoiding camera-warp round-trip drift and
ignoring any supplied XY preview. Cue permits only this manual height form.
Verified Cartesian boundary rejections hold the arm and retain the connection;
invalid calibration, lost feedback and other faults continue to fail closed.
XYZ and manual height use a checked direct path. Targeting and Cue use the
existing calibrated detour planner. A measured overshoot of at most 10 mm may
retreat into the valid field only when every violated constraint decreases or
stays level until re-entry; the relay independently checks that whole segment.
The mobile watchdog holds unsafe motion instead of launching a concurrent
recovery route. Cal 2 planning geometry is cached against the complete samples
and limits, uses the same captured robot-space hull as the relay's calibration
owner, and missing or invalid geometry fails closed.
The bridge publishes the active command ID/action/session. Fresh, matching
physical state may extend a running XYZ command's 15-second reply timeout up
to a three-minute absolute deadline. Other commands, stale/unavailable state,
changed sessions, or mismatched IDs cannot extend it; the existing 1.5-second
feedback/parent watchdogs still apply.
Ended games visibly require Gamemaster Reset before physical reconnection.

Checks: `node tests/mobile_physical_smoke.cjs`,
`node tests/mobile_arm_bridge_smoke.cjs`, and
`python -m unittest discover -s tests -p test_mobile_client_build.py`.
Additional regression checks: `node tests/mobile_xyz_steps_smoke.cjs` and
`node tests/mobile_xyz_controls_browser.cjs` against the isolated
`tests/mobile_ltz_fixture.py` server. The browser check exercises both teams,
real GM mode switches, explicit XYZ reconnect, virtual/physical increments,
and portrait/short landscape layouts with fake robot transport only.
`tests/mobile_boundary_browser.cjs` checks held connections, boundary retreat,
explicit XYZ reconnect, relay rejection and Targeting detours for both teams.


Player presentation: the arm caption sits below the sketch and its angle guides.
The connection buttons own the status area directly below them in every control
mode. The newest status messages appear first; repeated consecutive messages do
not fill the history. The log displays five visual lines: the first three remain
fully opaque, then a continuous mask fades the last two to transparent.

Physical camera framing fits the entire registered board inside the player's
screen, including a vertical margin of 12% of the camera height on each side
for the outer printed rows and border beyond the registered game rectangle. The surrounding camera image stays
visible at the sides to fill the available width without stretching. The corrected video, marker labels, reach hatching and targeting
share the viewport transform, including after orientation changes. Registration
is latched for the run to prevent tracking jitter from moving the player's view;
normal pinch/pan remains available. Until registration is available, the entire
camera image is fitted inside the screen. Virtual framing retains its existing fit behavior.


Camera stability: the mobile player decodes each JPEG offscreen and paints it
onto one persistent canvas. It never swaps display nodes or clears that canvas
between same-size frames. A single in-flight request runs on the existing 80 ms
UI heartbeat independently of game SSE updates, matching the corrected camera's
roughly 12 fps delivery. Completed frames release their object URLs immediately.
Transport/decode gaps retain the last picture with a paused-camera notice;
aiming still requires fresh game/tracking data and a frame younger than two
seconds. Mode changes and backgrounding hide the view and cancel pending work.
Temporary marker loss preserves camera dimensions, framing and manual zoom.

Laser Tag X uses a continuous native MJPEG image from corrected-stream. Mobile
retains the authenticated JPEG asset route for local and hosted-player support;
the persistent canvas avoids the per-frame Safari image/compositor replacement
without adding another camera capture or an unmonitored MJPEG control surface.
The Age diagnostic measures game-state age, independently of camera freshness.


A verified calibrated-boundary rejection is a rejected movement, not a lost
connection. The LTX bridge acknowledges a safe hold through the existing relay,
clears its rejected targets, and returns `motion_limit` with the current arm
snapshot. Mobile clears the active gesture and pending goals while retaining
that same session and the gripper state. The player can immediately choose a safe
retreat. Failed holds, missing calibration, FK failures, stale feedback and other
transport/controller errors retain the existing fail-closed behavior. Important
errors stay at the top of the player log for eight seconds instead of being
replaced by routine telemetry. Stop and newer errors can replace the notice.

Regression checks: `node tests/mobile_arm_bridge_smoke.cjs` and
`node tests/mobile_limit_recovery_smoke.cjs` exercise a rejected move, safe retreat
without reconnecting, failed hold, unknown faults, and readable error lifetime.

The joint sliders sit six pixels below the arm caption and are clamped inside
the viewport. Their position stays fixed during a held slider gesture. Urgent
messages use bold purple text in the left player log, including camera tracking,
alignment and paused-video notices. All runtime notices, including camera loading,
targeting saves, control changes and cue progress, appear only in the left log;
the playfield has no transient status text or loading/error overlay. Camera notices
are logged once per transition and remain readable after recovery for eight
seconds; repeated frame callbacks do not extend that interval or duplicate rows.
`node tests/mobile_camera_notice_smoke.cjs` checks notice recovery and history.

Joint mode also accepts sketch drags: the nozzle handle selects elbow J3, and
the elbow handle selects shoulder J2. A captured gesture keeps its initial pivot
fixed and changes the selected target by its relative angular movement, with
tenfold lower sensitivity in Fine tune. Targets use the same JointControls and
serialized command queue as the sliders, and synchronize their values and range
thumbs. In physical and virtual play, the white sketch and its handles move to
the selected pose on the next animation frame without interpolation or waiting
for robot feedback. The red outline remains tied to measured joint angles and
follows as the arm moves. Releasing a drag retains its selected pose; Stop,
suspension or a rejected movement clears it. This is presentation only and does
not change robot motion speed or the guarded command path. Handles require
an enabled, available session; conflicting touches are rejected, and loss of
feedback, mode changes, limit rejections and interrupted gestures cancel them.
Regression check: `node --test tests/mobile_sketch_drag.test.js`.

The header's 180° button rotates the video, reach hatching, marker labels, XYZ
guides and turret geometry together. Purple initially uses 180° and Green uses
0°; the choice persists separately for each player. Labels remain upright.
Screen gestures invert the same transform before selecting robot/turret goals;
view rotation never edits calibration, changes joint angles or issues motion.
Pinch anchoring, pan direction and hit testing follow the selected orientation.


## Mandatory progression, calibration and statistics (2026-10-01)

Shared frontend assets in `shared/mobile_ltz` provide both teams' profile picker,
new names, owned purchases, current-tier controls, shared upgrade countdown,
ready confirmation and exclusive calibration lesson. Game/Progress own all
state; the UI does not infer an unlock from a timer or local storage. GM test
selection defaults BOTH teams to the selected control method. Ending the test
restores each player's saved mandatory tier. Client files remain frozen and
versioned per hub launch; `journey.js` travels inside the established mobile.js
bundle so hosted filename allowlists remain compatible.

The partner waits with upgrades and stats while the active player captures the
six points. Targeting previews before explicit Move; Z and suction stay separate.
A fresh owned Atom selection carries its ID to the calibrated bridge for raised
perspective correction. Stale/foreign Atom selections reject. Height-only moves
preserve the measured XY position. The physical bridge reloads a new rig revision
before movement; all motion uses the existing LTX/Relay path.

The selected calibration side opens its Auto PP Cal 2 lesson immediately,
even before hardware feedback permits a live session. Its six capture buttons,
XYZ presentation, saved progress and explicit readiness error remain visible;
capture is disabled until the facade reports a live owner grant. Hide/Show steps
collapses only the lesson panel. The other player stays on Upgrades with a named
waiting message, including when neither arm has an active grant. An unselected
player sees upgrade options disabled instead of an empty waiting dialog.

Below purchases, score/time plots group matching frozen map/settings/loadouts,
show trailing three-game means, filters and keyboard/touch run details alongside
an accessible table. Combined history counts each shared game once. Unknown
legacy telemetry stays unavailable; no pooled median estimates human speed.


Calibration UI (shared by Green and Purple): the instruction panel sits at the
upper right, left of Y, with Hide steps to expose the camera. Fresh camera marker
numbers remain visible in green during every calibration stage. Playfield
presentation draws upright white numbers beside all six projected codes; Y hides
cached 40–59 geometry and its cache list while calibration is visible without
erasing those locations. The partner remains on Upgrades.

`mobile_calibration_connect` admits only connection setup for the selected side
or recovery of that side's pending stop; `mobile_calibration_ready` separately
admits captures/movement. The six-point and raised-tag steps hide X/Y adjustment
sliders and the ordinary arm-target overlay. Height controls retain robot
millimetres through the existing LTX bridge. Tutorial movement returns to
calibrated camera coordinates. The six-point quick-capture buttons stay visible
when instructions are collapsed; saved arm points gain checkmarks.

After six captures, the quick controls switch to four outer references
31/35/33/34 and a separate calibration crosshair appears in the camera. Place a
physical 100-series ArUco tag 3 cm above each reference, tap its image centre or
drag the crosshair onto it, then tap the reference number to record it. Dragging
uses Targeting's 32 px grab area, retained grab offset and tenfold smaller Fine
tune scale; coordinates stay inside the camera image. This optical gesture owns
no robot target or movement command. Cancelling it clears the gesture without
suspending the arm connection. Neither positioning nor saving a sample moves
the arm. These four buttons and
their checkmarks remain usable with instructions collapsed. Pan/pinch do not
position or save a sample, and Purple's view rotation is inverted once. The
saved-calibration dropdown reads side-scoped owner history
without overwriting the active lesson. GM and earned progression share this UI
and the same Game/Cal 2 session commands.

Complete calibration stays visible with instructions folded and enables after
all six arm captures, four raised references, pickup Z and transport Z are saved.
Missing measurements are listed beside the disabled button. The action validates,
saves and completes the turn through Game/Cal 2; the partner proceeds next, or
both players return to the shared upgrade/ready step. Save and practice movement
is optional, and already validated tutorial sessions also expose Complete
calibration. Height capture stays accessible in that optional stage. Completion
does not synthesize pickup evidence or issue a robot movement command.
