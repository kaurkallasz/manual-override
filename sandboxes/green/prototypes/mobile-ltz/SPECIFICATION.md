# Mobile control modes

The mobile control-path dialog selects Joint, unlocked Cartesian XYZ, Targeting, or Cue autonomy. Its
availability combines the game-owned virtual test override with saved Green
progress when the override is absent. Server validation is final. A new connection defaults to the highest implemented
unlocked mode (Cue at tier 4, Targeting at tier 3, XYZ at tier 2, Joint at tier 1). An unlock change also selects
that default and freezes old motion. A manual lower-mode choice remains selected
during ordinary heartbeats until the next unlock change or fresh connection.
Opening the dialog freezes the current target at the actual pose while preserving
the existing session and any held tag. Mode changes clear queued client input.

Joint mode retains its animated arm illustration, dial, joint sliders, fine tune,
and actual-position indicators. XYZ hides the joint illustration and map arm
segments, retaining virtual tags and pump controls. X uses a horizontal slider. Y is vertical along the right edge, starting at the top safe margin and increasing
downward to match map coordinates. Connect and Stop are on the left. Z is a vertical left-edge slider with high
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
immediately to the right of Suck/Blow at the lower left.

Start a single-finger drag within 32 screen pixels of the green target. Movement
preserves the finger offset and selected height; fine tune reduces XY drag to
one tenth while retaining the fine height range. A second finger ends the drag
and drops unsent input, then pans/zooms only; already accepted movement completes
through the normal arm simulation. Lifting fingers does not begin another drag.
A fresh touch is required. Tapping elsewhere does not move the arm.

Run `node tests/mobile_targeting_browser.cjs` against the isolated fixture to
check touch movement, fine tune, height/presets, camera navigation, cancellation,
unlock defaults, and portrait/landscape layouts.

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
