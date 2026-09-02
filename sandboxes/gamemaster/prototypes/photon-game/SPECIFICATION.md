# Photon Game

Photon Game owns gameplay truth. It contains the proven Laser Tag Z simulation,
run lifecycle, validated settings, and append-only JSONL history. It does not
own authored levels, physical observation, presentation, or artwork.

## Inputs

- `photon.level.runtime` version 1 supplies the parsed graph, sockets, topology,
  blockers, and waves as values. Photon Game never receives a file path and
  contains no TMJ parser. A changed Level revision is adopted during setup and
  deferred while a run is active.
- `photon.board.runtime` version 1 supplies normalized tags and read-only arm
  state. Missing, stale, malformed, or incompatible Board output becomes an
  explicit unavailable input and contributes no physical evidence.
- `apply_command(value)` and authenticated `POST /api/command` accept the
  bounded actions `start`, `pause`, `resume`, `reset`, `set_virtual`, `place`,
  `activate_core`, `loadout`, `aim`, `configure`, and `reset_settings`.
  Physical Start performs a fresh Board read and fails closed unless that input
  is ready; virtual Start does not require Board. This decision belongs here,
  never in a presentation.

Photon Game calls siblings only through the hub context after checking that the
module is enabled. It imports no sibling package and reads no sibling file.

## Outputs

There is one snapshot contract and one live stream:

- `game_snapshot()` / `GET /api/state` publishes `photon.game` version 2.
- `game_events()` / `GET /api/events` sends compact instances of the same
  contract with the hub's existing Server-Sent Events helper.

The snapshot contains the authoritative phase, timers, enemies, towers,
projectiles, combat effects, topology, core sequence, immutable run settings,
input diagnostics, a nested `photon.game.settings` version 1 configuration
projection, and a small level projection needed by presentations. The settings
projection supplies the saved next-run draft, presets, numeric limits, and
authored per-wave enemy counts; it is available even when Level is unavailable.
That projection contains dimensions, named paths, and display-only socket
identity/position/size/owner values, exact ArUco display positions, central-core
geometry, and the opaque visual scene received from Level. Photon Game forwards
the scene without resolving art or interpreting renderer concerns. Browsers do
not advance time or calculate damage. These visual fields are additive in Level
version 1: an older compatible Level still runs, with Y's plain Canvas fallback.

## Owned state

- `photon_game_runtime/engine.py` is a module-local copy of the proven Laser
  Tag Z simulation. Its file-based `LevelModel` and TMJ helpers were removed;
  only the value-based `ContractLevelModel` remains.
- `photon_game_runtime/settings.py` validates settings and atomically replaces
  `data/settings.json`. Changes made during a run affect the next Start only.
- `data/runs.jsonl` is append-only history for operator commands and numbered
  authoritative simulation events. Storage failures are visible in the
  snapshot and do not invent successful persistence.

The ignored `data/` directory is the only mutable filesystem area. Photon Game
serves no map, sprite, Canvas renderer, or visual asset.

## Lifecycle and independence

`hub_init(ctx)` connects contracts and starts the owned simulation thread only
after a valid Level is available. `hub_stop()` stops that thread and releases
all sibling references. Importing the module starts no thread.

A compatible internal change can be made without knowledge of Level, Board, or
Laser Tag Y. A breaking output change requires a new integer version; an old
presentation then reports only Photon Game as unavailable while unrelated tabs
continue to work.
