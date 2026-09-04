# Laser Tag Y

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
  `/api/art` remains only a compatibility view of Game's descriptor; current
  pages use the snapshot and SSE, with no separate manifest fetch.
- Output: the physical-mode and virtual-mode Gamemaster presentation and a
  control-free external screen. Both pages read the same
  authoritative snapshot.
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
- ArUco 38 and 40–55 are static Level-owned images. Their exact optical
  centers and sizes arrive through Photon Game, so physical, virtual, and
  external views use one alignment.
- The Gamemaster HUD displays Photon Game's authoritative completed-ring field
  immunity countdown, rounded up for display, and returns to `Ring complete`
  when the reported remaining duration reaches zero.
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
