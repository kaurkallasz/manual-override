# Laser Tag Y

Presents Photon Game to the Gamemaster and to an external display. It owns no
gameplay, level, board, camera, or persistent state.

- Live input: only `photon.game` v2 snapshots/SSE. Authenticated operator intent
  is forwarded unchanged to Photon Game's command input.
- Optional static input: immutable files from `photon.art` v2. Missing images use
  code-native Canvas fallbacks and do not stop the game.
- Output: the physical-mode and virtual-mode Gamemaster presentation, plus a
  settings form and a control-free external screen. Every page reads the same
  authoritative snapshot.
- The settings form renders the nested `photon.game.settings` version 1 value
  and forwards only `configure` or `reset_settings` intent. Defaults, presets,
  validation, active-run freezing, and persistence remain owned by Photon Game.
- The embedded level projection is display geometry, not a level-authoring
  input. Its renderer-neutral scene supplies stable art IDs and precomputed
  transforms; Y never interprets a Tiled GID, tileset, or alignment mode.
- ArUco 38 and 40–55 are immutable Photon Art images. Their exact optical
  centers and sizes arrive through Photon Game, so physical, virtual, and
  external views use one alignment.
- Y never reads Photon Level or Photon Board, opens a camera, parses TMJ, edits a
  level, calculates combat, mutates game state locally, persists runs, or controls
  hardware.
- A Game contract mismatch is contained here and displayed as `unavailable`.
