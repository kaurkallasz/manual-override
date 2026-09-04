# Photon Game

Photon Game owns gameplay truth. It contains the proven Laser Tag Z simulation,
run lifecycle, validated settings, and append-only JSONL history. It does not
own authored levels, physical observation, live-game presentation, or artwork.

## Module tab

The default page (`/`, also available at `/settings`) is Photon Game's own
settings form. It configures the simulation through the existing local
`GET /api/state` and authenticated `POST /api/command` endpoints. Defaults,
presets, numeric limits, field-level validation errors, next-run freezing, and
`data/settings.json` remain under this one owner. No data migration or new
settings endpoint is required. The form remains usable when Level, Board,
and Y are unavailable; simulation readiness is reported separately.

Game status and collapsible input/storage diagnostics appear below the form,
updated by the existing SSE stream. Incoming events never replace unsaved form
values. Start/pause/reset and immediate aiming controls remain in the live
presenter; no game Canvas or renderer is introduced here. The tab's back link
goes to the module hub, without a dependency on any particular presenter.

Laser Tag Y's old `/settings` URL is a compatibility shortcut to this module's
`/settings` page. Y checks that Game is enabled and its contract is compatible
before redirecting; it does not retain a second copy of the form.

## Inputs

- `photon.level.runtime` version 1 supplies the parsed graph, sockets, topology,
  blockers, and waves as values. Photon Game never receives a file path and
  contains no TMJ parser. A changed Level revision is adopted during setup and
  deferred while a run is active.
  Its optional `presentation` descriptor uses `photon.level.assets` v1. Game
  checks its version and URL shape, then forwards it without reading files or
  interpreting artwork. Missing or incompatible art is explicitly unavailable
  in `presentation` and `inputs.presentation`, but does not stop valid gameplay.
- `photon.board.runtime` version 1 supplies its nested
  `photon.board.placement` version 1 relationship descriptor. Photon Game does
  not inspect raw tag coordinates or arm poses for placement. It validates
  freshness, identity, bounds and uniqueness, then maps Board's stable
  movable-tag/fixed-marker/arm relationships through Level's marker-to-socket
  mapping. Team ownership, valid destinations, replacement, ring/core sequence
  and rejection rules remain Game-owned. A new run or completed ring requires
  one Board-declared evidence window after the gameplay gate opens, without
  recalculating physical stability. Missing, stale, malformed, or incompatible
  Board output becomes explicitly unavailable and contributes no evidence.
  The existing read also supplies optional `inputs.board.upstream` diagnostics:
  Game's `reported_at`, Board's `observed_at`, `frame_at`, `source`, bounded
  per-input status/error/contract/version, the compatible tracking output's
  status/sample time/input health, and placement status/sample/error. It
  contains no raw tags, arm poses,
  calibration coefficients or video. Unavailable but compatible Board reports
  retain their failure details; missing/failing/incompatible Board output clears
  the report. Malformed optional diagnostics do not change physical validation.
  Game makes no additional sibling read for these fields. They describe its
  last physical read and can age while virtual play continues; consumers must
  not treat fresh Game SSE as fresh hardware evidence.
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

The snapshot includes Level's `presentation` descriptor (URLs, not image bytes)
alongside the authoritative phase, timers, enemies, towers,
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
An art-only revision refreshes the descriptor without replacing the engine or
resetting the run. A new geometry revision and its content stay deferred
together while a run is active. Level files revalidate on HTTP reads; the
manifest's content hashes also change URLs when artwork is edited.

## Owned state

- `photon_game_runtime/engine.py` is a module-local copy of the proven Laser
  Tag Z simulation. Its file-based `LevelModel` and TMJ helpers were removed;
  only the value-based `ContractLevelModel` remains.
- `photon_game_runtime/settings.py` validates settings and atomically replaces
  `data/settings.json`. Persistence completes before the in-memory draft and
  revision change. Invalid saved structure is reported while validated defaults
  remain available for repair; a failed write preserves the previous draft and
  revision. Changes made during a run affect the next Start only.
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

Each tower output includes its authoritative targeting result plus a generic
`targeting.control` descriptor: range endpoints and, where relevant, direction,
target-point, half-angle and blast-radius endpoints. A presenter may interpolate
these supplied display controls while dragging. It does not need weapon-specific
ranges, cone widths, splash sizes, damage, intensity or link formulas.
