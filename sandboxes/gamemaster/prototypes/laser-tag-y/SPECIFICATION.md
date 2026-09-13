# Laser Tag Y

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
gameplay, level, board, camera, or persistent state.

- Live input: only `photon.game` v2 snapshots/SSE. Authenticated operator intent
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
  Corrected video terminates at Board's on-demand preview, never Game or Y.
  The two calibration datasets, projection arguments/results, controller intent
  versus observed feedback, and virtual input alternatives are distinguished.
  The scrollable graph has branch jump controls and opens on Game/Y.
  Origins and routes are declared architecture, not independent monitoring.
  Webcam, correction, relay and optional tracking-adapter health comes only from
  Game's bounded `inputs.board.upstream` report, where supplied. Missing or
  older-than-three-second reports are unknown/last-known even while Game SSE
  remains live. Virtual play marks physical Board input unused. Hardware device
  identities, calibration values and video frames are not sent to this window.
  Selecting a node shows the relevant fields, actual received source addresses,
  status, snapshot age, SSE message count, or renderer image-load counts.
  The diagram observes Y's existing snapshot, SSE and image loader only; it
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
- Y never reads Photon Level or Photon Board, opens a camera, parses TMJ, edits a
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

The **Virtual Atom controls → Virtual test unlocks** section appears when Virtual
play is enabled. Gamemaster can enable test overrides, lock turret types for
placement, choose turret/Force Field levels 1–4, apply a complete selection,
unlock all L4, or return everything to base level. The UI preserves unsaved
selections during unrelated SSE updates and shows the server's applied loadout
after refresh. Changes affect existing defenses and subsequent placements on
both shared map views. The form forwards one Game command and owns no upgrades.
