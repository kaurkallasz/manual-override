# Laser Tag Y

Presents Photon Game to the Gamemaster and to an external display. It owns no
gameplay, level, board, camera, or persistent state.

- Live input: only `photon.game` v2 snapshots/SSE. Authenticated operator intent
  is forwarded unchanged to Photon Game's command input.
- Optional static input: immutable files from `photon.art` v2. Missing images use
  code-native Canvas fallbacks and do not stop the game.
- Output: the physical-mode and virtual-mode Gamemaster presentation, plus a
  control-free external screen. All three draw the same authoritative snapshot.
- The embedded level projection is display geometry, not a level-authoring input.
- Y never reads Photon Level or Photon Board, opens a camera, parses TMJ, edits a
  level, calculates combat, mutates game state locally, persists runs, or controls
  hardware.
- A Game contract mismatch is contained here and displayed as `unavailable`.
