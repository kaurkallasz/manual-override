# Laser Tag Y

## Atom buff display

Both displays render Game's explicit `atom_buff_state`. Active turrets keep a
green halo for both teams, including their L4 companions. The inexpensive halo
survives dense effect quality and clips against authored ArUco keep-out regions.
An active health bar has two equal stacked rows within the existing width and
a ×2 indicator; together they represent the effective doubled maximum. Damage
drains the bonus row before the base row. Inactive/unavailable states restore
the single bar and remove the halo. The selected defense details show
`Health ×2 · Damage ×2` only while active.

The Virtual Atom controls provide **Lift selected Atom**, forwarding the existing
Game `place` command with null `socket_id`. It removes occupancy, not the installed
turret. The renderer cannot decide presence, heal, or calculate weapon damage.
Full and incremental snapshots, including reconnects, carry explicit clearing
through the existing SSE transport. Both pages use renderer revision 18.

## L4 companion display

Both game pages render Game's authoritative `companions` alongside its primary
`towers`. Each 96 px companion pod uses the same L4 artwork, raised head and
readable tier colors at proportional scale; primary pods remain 112 px. The
published optical anchor is applied once. Unique unit IDs separate angle,
charge, fire and projectile visuals. A `C` badge identifies a companion; its
health mirrors the parent. Existing fields remain underneath the pod artwork,
and marker squares render above effects and aiming handles to remain readable.

Clicking either member in Virtual play selects the parent's existing controls.
Aim previews use shared inputs at both origins. The Run panel shows primary and
companion counts separately. Virtual test unlocks explain the L4 companion and
middle-line exception; changing L4 to L3 removes the corresponding companions
through Game, and reconnect/reset snapshots clear stale units. No browser-side
unlock or damage calculation is added.

Presents Photon Game to the Gamemaster and to an external display. It owns no
gameplay, level, board or camera state. Its only persisted operator state is the
display-only table-marker location cache described below.

- Live gameplay input: only `photon.game` v2 snapshots/SSE. Authenticated operator intent
  is forwarded unchanged to Photon Game's command input.
- Asset references arrive only inside Game's `presentation` field, using
  `photon.level.assets` v1. Y prefixes the supplied base with the current sandbox
  mount and downloads those static URLs; it does not discover another module.
  Missing images use code-native Canvas fallbacks and do not stop the game.
  Both displays refresh image caches when the descriptor changes, even if the
  geometry revision is unchanged. Late old requests cannot replace newer art.
  Missing content and image-load failures are reported in the presentation.
  Current pages use the snapshot and SSE, with no separate manifest endpoint or
  fetch in Y.
- Output: the physical-mode and virtual-mode Gamemaster presentation and a
  control-free external screen. Both pages read the same
  authoritative snapshot.
- Grunt, Runner, and Breaker sprites render at twice their original width and
  height in both displays. Brute size is relative to the Grunt and comes from
  Game's frozen `settings.brute_size_multiplier` (default 2). Fallback shapes,
  burn effects, and skeleton-zap overlays scale with each enemy. Rotated sprite
  caches fit the full diagonal and distinguish different sizes between runs.
  Older snapshots without Brute tuning retain the former body-size ratio.
  Gameplay positions and collision sizes remain authoritative Game values.
- The Gamemaster's **Data flow** button opens a read-only node diagram of
  the full source chain: physical camera → Webcam → Camera Calibration → Board;
  saved lens coefficients → Camera Calibration; MG400 feedback → Dobot Relay →
  Board; saved Cal 2 measurements → Auto Pickup ↔ Board diagnostics; Player LTX
  intent → Auto Pickup/Relay; authored files → Level → Game/image delivery;
  Game-owned settings and operator commands → Game; Board → Game → Y.
  The operator physical view displays corrected video from Board’s existing
  `/api/preview` endpoint. Video bytes never enter Game. Virtual play and Board
  simulation show the generated view; the external screen always renders the
  map for display on the physical playfield. Camera failures show an explicit
  message and Retry camera button; they never fall back to a virtual image.
  Game disconnects or stale input hide the camera until fresh evidence returns.
  The two calibration datasets, projection arguments/results, controller intent
  versus observed feedback, and virtual input alternatives are distinguished.
  The scrollable graph has branch jump controls and opens on Game/Y.
  Origins and routes are declared architecture, not independent monitoring.
  Webcam, correction, relay and optional tracking-adapter health comes only from
  Game's bounded `inputs.board.upstream` report, where supplied. Missing or
  older-than-three-second reports are unknown/last-known even while Game SSE
  remains live. Virtual play marks physical Board input unused. Hardware device
  identities and calibration values are not sent to this window. The diagram
  reports preview image load/error status, not measured camera frame rate.
  Selecting a node shows the relevant fields, actual received source addresses,
  status, snapshot age, SSE message count, or renderer image-load counts.
  The diagram observes Y's existing Game snapshot/SSE and image loader only; it
  performs no extra requests or commands and introduces no sibling dependency.
  Flow animation reflects recent SSE events and pending/recent image activity,
  not packet speed or measured bandwidth. Disconnected/stale feeds stop the live
  state animation and mark values last-known. Cached image completions count as
  loads. Motion can be paused and respects reduced-motion preferences. The
  window's refresh timer runs only while open and is released on teardown.
  External-screen connections are described but not remotely monitored; that
  control-free page does not contain the diagnostic window.
- The settings button and existing `/settings` URL are shortcuts to Photon
  Game's module-owned settings page. The redirect preserves the current sandbox
  prefix and fails explicitly if Game is disabled, absent, or incompatible.
  Y has no settings form; defaults, presets, validation, active-run freezing,
  persistence, and configuration UI all belong to Photon Game. Start, pause,
  reset, and immediate turret controls remain in Y.
- The embedded level projection is display geometry, not a level-authoring
  input. Its renderer-neutral scene supplies stable art IDs and precomputed
  transforms; Y never interprets a Tiled GID, tileset, or alignment mode.
- ArUco identities are Level-owned images. Their IDs, exact optical centers and
  sizes arrive through Photon Game, so physical, virtual, and external views
  use one alignment. Y discovers marker and sprite URLs from Game's forwarded
  asset descriptor rather than keeping a copied asset-ID list.
- Atom IDs/types, socket total, ring limits, and the core marker ID are derived
  from each Game snapshot. Missing values remain visibly unknown; Y does not
  substitute the current level's defaults.
- The Gamemaster HUD displays Photon Game's authoritative completed-ring field
  immunity countdown, rounded up for display, and returns to `Ring complete`
  when the reported remaining duration reaches zero.
- A local FPS monitor sits beside Virtual play, including on narrow screens.
  It updates once per second from completed animation-frame playfield draws.
  Selection, aiming and state updates coalesce into that frame; diagnostic
  direct draws do not inflate the FPS counter. It displays zero when no playfield is rendered
  and resets its sample when browser visibility changes. Both physical and
  virtual modes use the same monitor; it adds no requests or simulation state.
- Selecting a living defense in virtual mode displays one draggable handle at
  the end of its dotted targeting guide. Handle angle previews direction and
  handle radius previews wide/narrow range; Tesla remains omnidirectional and
  uses radius only. Y submits one existing `aim` command when the drag ends,
  while Photon Game validates and owns the resulting angle and spread.
  Preview geometry comes only from the selected tower's Game-published
  `targeting.control` endpoints. Y contains no weapon rule table and never
  predicts damage, intensity, splash rules or link multipliers. Missing control
  geometry disables derived dragging instead of inventing defaults.
- Direction and wide/narrow sliders remain synchronized keyboard-accessible
  inputs to that same command. They are presentation controls, not another
  gameplay state store, and rejected commands return the guide to Game output.
- Y never reads Photon Level or Board gameplay state directly, opens a camera
  device, parses TMJ, edits a
  level, calculates combat, mutates game state locally, persists runs, or controls
  hardware.
- A Game contract mismatch is contained here and displayed as `unavailable`.
- Visual interpolation is capped at half a second and freezes at the last
  displayed instant when SSE disconnects. Both displays mark reconnecting state;
  browser animation never makes stale Game output appear to keep advancing.

Repository-boundary smoke test: `.venv/bin/python -m unittest discover -s tests -p test_photon_module_isolation.py`.

## Rendering performance

- The animation loop targets 60 FPS at every enemy count. It retains fractional
  frame deadlines on high-refresh displays, tolerates refresh rounding, skips
  hidden-tab work and avoids catch-up bursts after stalls.
- Enemy count sets a cosmetic detail floor. Sustained expensive draws or missed
  frames reduce detail after 400 ms of pressure; five seconds of headroom are
  required for each recovery step. Dense mode removes blur and shortens trails,
  preserving all enemies, native ArUco markers and authoritative gameplay.
  Burning enemies retain a visible flame on every frame; detail changes only
  the flicker cadence. Long lightning/field halos use layered strokes rather
  than repeatedly blurring large line bounds.
- Enemy bodies, electric glows and small scaled effects use bounded raster
  caches (36 MiB combined pixel budget). Asset and Brute-size changes invalidate
  affected caches. Level/marker geometry changes invalidate clipped field paths.
  Tower presentation records and enemy lookups are prepared once per snapshot.
- Optional `onPerformance` reports FPS, latest draw/frame duration, average time
  in field/tower/enemy/combat passes, quality and cached pixel bytes once per
  second. It is local diagnostics, and callback failures cannot stop rendering.
- Controls rebuild only when their inputs change; unchanged DOM values are not
  rewritten. Nonessential HUD refreshes are capped at 10 Hz, while aiming and
  operator-command feedback remain immediate.
- Y requests `game_events(incremental=True)`. Standard messages replace the
  stream baseline; named `update` events carry all dynamic fields and retain
  only the declared static fields from that baseline. Every connection begins
  with a complete snapshot. Command responses do not overwrite the SSE baseline.

## Row-barrier presentation

Both views render Game's authoritative row geometry and power state alongside
existing links. Gold horizontal barriers distinguish rows from ordinary cyan
links; `ROW n/3` labels show completed contributors, and arrows mark the right
outer openings and left inner openings. A turret loss briefly displays the
broken row in red before returning to the subdued inactive guide. Marker
artwork remains unobscured; visual marker clearances do not create movement
openings in the simulation.

`row_barrier_geometry` is retained from complete SSE snapshots across subsequent
incremental updates. Dynamic `row_barriers` state is supplied on updates. The
renderer owns no activation, damage, collision, or routing decisions and uses
cached line geometry without large Canvas shadow blurs. Renderer asset revision
is 12 in both the gamemaster and external-screen pages.

## LTZ progress presentation

The operator view offers physical scored play or practice, reports Game's frozen
participants/result/save status, and links to Green/Purple performance below the
LTZ Score upgrades table. It never writes credits or completion counts.

The shared renderer selects Level-owned upgrade base/head layers from each
server tower's `upgrade_level`, retains independent aiming/effects, and selects
force-field energy ribbons from the server field level and visible width. Both
the operator view and external game screen follow the same code path. Existing
force-field marker exclusions, health/broken state and team markers remain.
For L2–L4 weapons, the renderer removes transparent pedestal padding and fits
the base into an 84 × 72 px area within the existing 88 px sprite box. Gun heads
are raised 14 px and drawn at 90% scale so the colored tiers remain exposed.
Muzzle, Tesla and mortar launch visuals follow the raised head; socket size,
placement, targeting and simulation geometry are unchanged. Base-level art
keeps its existing composition.

The **Unlocks** panel sits directly below Aruco MNGMNT (Virtual Atom controls
in virtual play). It remains visible and editable in both virtual and physical
practice. Active scored runs cannot change overrides, and a scored game cannot
start until test overrides are disabled. Gamemaster can enable test overrides, lock turret types for
placement, choose turret/Force Field levels 1–4, apply a complete selection,
unlock all L4, or return everything to base level. The UI preserves unsaved
selections during unrelated SSE updates and shows the server's applied loadout
after refresh. Changes affect existing defenses and subsequent placements on
both shared map views. The form forwards one Game command and owns no upgrades.


### Mobile control test unlocks

The same Unlocks form includes **Mobile control unlock**: Joint (1),
Cartesian XYZ (2), Targeting (3), and Cue autonomy (4). Apply sends
`virtual_test_loadout` with `levels` plus `control` (integer 1–4, or null when the
override is off). The selection unlocks through that tier for Green mobile practice, including the
calibrated physical controller embedded in Mobile LTZ. Relay authorization and
physical workspace checks still apply.
Unlock all L4 includes tier 4; All base levels restores tier 1. Targeting enables finger dragging; Cue autonomy enables queued pickup and placement. Unsaved dropdown edits survive unrelated SSE updates.
These overrides do not write saved players, credits, wins, or physical-arm settings.

## Physical ArUco management

Physical operator play labels the Atom/target panel **Aruco MNGMNT**. Current
Board detections light its read-only Atom, socket and core chips green with
“Found”; remembered detections show an explicit last-seen age and dashed border.
Virtual play keeps **Virtual Atom controls** and its existing commands.

The camera image and SVG marker overlay share one fitted full-frame rectangle
and one centered **1.15×** transform during gameplay, clipped by the operator
stage. Calibration removes that crop to show all outer targets. Corner
polygons and ID labels use corrected-camera normalized coordinates, never Level
render coordinates. Current outlines are green; remembered outlines are dashed
and labeled with age. HUD and controls are not zoomed. The external screen and
virtual renderer are unchanged.

The operator's existing Y `/api/events?markers=1` connection carries named
`markers` events alongside the unchanged full/incremental Photon Game events.
Y's server adapter reads Board's public cached `tracking_snapshot()` through the
enabled module contract and validates `photon.board.tracking` v1. It samples
this display projection at most five times per second as Game events arrive;
it neither samples hardware nor adds a browser connection. The external screen
keeps its existing Game-only stream.

The monitor keeps diagnostics received before the first video frame so camera
startup cannot discard the initial marker snapshot. Only display diagnostics
are consumed; Game remains the sole gameplay/placement authority. No browser
detection or gameplay target memory is introduced. Invalid contracts, stale
sample/frame times, or disconnects clear outlines and current-detection
indicators. Mode changes and camera/Game failure hide the display, and teardown
closes the shared stream. Board's reported visibility distinguishes current
detections from retained coordinates. The operator-only table-marker display
cache is described below.

Cache analysis (existing policy, unchanged by this display): Webcam promotes a
tag after 1 second of detection (gaps over 0.5 seconds restart qualification),
retains confirmed tags for 3 seconds after loss, and retains immediate reads for
10 seconds. Board diagnostic history stores fixed markers for 5 seconds and
movable IDs for 15 seconds, only refreshing from visible detections. Its separate
game placement cache stores fixed-marker centers for 120 seconds from qualifying
observations; source changes clear that cache. Camera/arm freshness and placement
dwell still gate gameplay, even when a target center is remembered. The diagnostic
UI does not claim to expose that longer game cache, and a green chip means a
current detection, not a cached placement target or robot readiness.

Smoke test: `.venv/bin/python -m unittest discover -s tests -p test_laser_tag_y_camera.py`.

### Saved table-marker locations

Y stores the last observed corrected-camera centers and corner polygons for
**IDs 40–59** in browser local storage, scoped to this sandbox's Y URL, with a
versioned descriptor and full-frame dimensions. It learns only from fresh,
visible Board diagnostics; neither cached diagnostic rows nor a simulation can
seed or refresh it. At most 20 entries are stored. Writes are throttled to once
per second and flushed on teardown. Invalid records are rejected; storage errors
are visible and leave a visit-only cache.

While fresh camera/diagnostic input is available, obscured cached table locations
remain drawn as dashed green outlines labeled **cached**. Their read-only chips
show **Cached location**, distinct from bright-green **Found** detections.
The cache survives page reload and has no time expiry. A changed frame resolution
automatically clears old coordinates. Reset it after moving the camera/table or
changing calibration; a same-resolution camera move cannot be inferred here.
Core and movable tags continue to use Board's bounded diagnostic history.

**Reset all cached locations** clears every saved and in-memory table location.
The current pre-reset frame cannot immediately reseed the cache; newly observed
frames can. The panel confirms the reset and explains that visible codes will
be learned again. This is an operator display cache only: it neither changes
Board's independent 120-second gameplay marker memory nor provides placement
or robot-control evidence.

### Calibration and practice transitions — 2026-10-01

The main stage shows the existing Photon Board corrected camera preview during
calibration, at full frame without the normal 15% crop. Game-marker registration
can be unavailable after calibration replaces those markers; the existing preview
endpoint still validates the real camera. Camera errors show a retry state, never
generated targets. Game freshness and disconnect handling remain required.

Only the external screen mounts the owner-served Auto PP Cal 2 targets. Its Y
presentation helper validates `hhh.playfield.display` v1 and the exact Playfield
screen path, then requests `?presentation=1` to disable zoom, orbit, target editing
and camera saves. An unavailable descriptor keeps a waiting/error surface over
the game. Normal presentation returns on exit; Y owns no target coordinates.

Selecting another GM calibration test safely cancels the previous practice
session before opening the requested side. Game screen, Green, Purple and Both
controls sit above the camera. Loading the operator page sends `show_game` when
a calibration is retained; the external screen follows the resulting Game state.
Reloading the external screen alone does not cancel an operator-selected lesson.

Projection exit/switch remains available with an offline arm. The calibration
owner first revokes lesson access and durably inhibits motion until Relay confirms
the previous stop. Previewing another side grants no movement. Both starts Green
then Purple; earned progress pauses under `deferred_calibration` and is resumed
with the visible Resume player calibration button. It cannot award or skip a
tier. Errors and hardware readiness are shown beside the screen controls.
The status distinguishes selecting calibration from the owner's targets becoming
ready. Display failures are shown before motion-readiness notices, so an offline
arm notice cannot conceal the actual reason targets have not loaded.

GM test overrides select practice Start and remain applied to both teams. Pending
control edits survive incoming state, and older stream snapshots cannot replace
a newer command result. Start reports its rejection beside the button and stays
blocked during calibration, the shared upgrade interval, or unavailable physical
Board input. Game owns validation and all resulting phase changes.
# Saved calibration selection

Game Master can choose Green or Purple and a saved calibration, preview it over
the current corrected camera, and apply it. The default is the latest complete
calibration; explicit older choices persist until changed or a new calibration
is completed. Each preview shows six numbered ground targets and four dashed
3 cm raised-tag samples. Coordinates are canonical for both arms, with no second
Purple rotation. Preview uses the same contained image rectangle and no gameplay
zoom. It changes no robot, projection, game mode, player statistics or progress.

The operator-only `/api/calibrations?side=green|purple` facade checks the enabled
Cal 2 owner and its exact `hhh.cal2.history` integer-v1 contract. Apply forwards
`calibration_apply` through Photon Game, including the observed rig revision.
Game settles the current lesson/display; Cal 2 owns validation, stops, archives
and persistence. Running games reject Apply. The shared transport height is
restored with the selected arm, and player controllers must reconnect after
lease revocation. Required player calibration remains required.

Preview freshness uses the existing Board tracking messages multiplexed onto
the Game SSE feed. Missing, stale, simulated or malformed camera evidence hides
the historical overlay and pauses the camera preview. No extra polling or
hardware control path is introduced. Closing preview returns to the existing
physical/virtual presentation. New captures become the newest history record;
applying an old record never changes its original capture time.
