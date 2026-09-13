# Photon Game

## L4 companion weapons

At an eligible Level anchor, an effective L4 weapon creates one same-type
companion. It inherits the parent's owner, damage/link multipliers and aim/spread
inputs, while targeting from its own origin with independent charge, cooldown,
shots and projectiles. New pairs activate together. Promotion during virtual
testing gives the new companion its normal three-second activation and an empty
weapon charge. Repeated overrides do not heal or reset the primary or fields.

The pair shares the primary's health pool. Enemy contact with either pod damages
that pool; swept contact uses the union of both intervals so one enemy never
deals duplicate contact damage. Companion pods have a 48 px body radius, while
primary pods retain 56 px. Parent destruction disables both weapons; the dead
companion record remains available for destruction visuals until replacement or
reset. Replenishment heals the pair once. Downgrading below L4 removes the child,
while already launched mortar rounds finish normally.

`placements`, link bonuses, force-field endpoints, row-barrier requirements,
activation order and core-ring participation remain primary-only. There is one
physical Atom/marker relationship and one existing aim command per pair.
Companions cannot spawn companions. All kills use the existing authoritative
enemy-removal counter and saved-player credit path; virtual tests remain practice.

The additive Game v2 snapshot fields are `companions` (including an empty array)
and `companion_policy`. Primary `towers` keep their existing shape. Each companion
has a unique `placement_id` ending in `:companion`, `parent_placement_id`,
`is_companion`, `visual_x/y`, `pod_size`, and the standard weapon/health/targeting
projection. Complete and incremental SSE forward these fields. Mortar rounds
retain visual origin offsets and unit scale/level so removal cannot move an
in-flight round back to its parent's origin. Frozen LTZ run metadata records
the companion policy version, keeping history cohorts comparable.

Game validates the optional Level descriptor and its bounds/clearance. Missing
descriptors preserve older-level behavior; present invalid descriptors fail
validation. Saved L4 player ownership and the virtual loadout use the same
reconciliation. No extra player-save schema, purchase, or robot-control path is
introduced. The current map supports 16 primaries and up to 12 companions.

Photon Game owns gameplay truth. It contains the proven Laser Tag Z simulation,
run lifecycle, validated settings, and append-only JSONL history. It does not
own authored levels, physical observation, live-game presentation, or artwork.

## Module tab

The default page (`/`, also available at `/settings`) is Photon Game's own
settings form. It configures the simulation through the existing local
`GET /api/state` and authenticated `POST /api/command` endpoints. Defaults,
presets, numeric limits, field-level validation errors, next-run freezing, and
`data/settings.json` remain under this one owner. The form remains usable when Level, Board,
and Y are unavailable; simulation readiness is reported separately.

Game status and collapsible input/storage diagnostics appear below the form,
updated by the existing SSE stream. Incoming events never replace unsaved form
values. Start/pause/reset and immediate aiming controls remain in the live
presenter; no game Canvas or renderer is introduced here. The tab's back link
goes to the module hub, without a dependency on any particular presenter.

Laser Tag Y's old `/settings` URL is a compatibility shortcut to this module's
`/settings` page. Y checks that Game is enabled and its contract is compatible
before redirecting; it does not retain a second copy of the form.

The Brutes section configures four independent next-run parameters:

| Setting | Default | Limits |
| --- | --- | --- |
| First Brute wave | 4 | Integer 1–12 |
| Size relative to Grunt width and height | 2× | 0.5–10× |
| Base health | 960 HP | 1–100,000 HP |
| Base damage to core and defense pods | 64 per second | 0–10,000 per second |

Health and damage defaults are four times the former Brute values (240 HP and
16 damage per second). Global orc health and each target's global attack-damage
multiplier still apply. Speed remains 34 before global speed tuning; collision
radius and melee reach are unchanged. Size is a presentation setting carried
in the frozen run settings; Y uses it in both displays.

Starting at the configured first Brute wave (default 4), each wave replaces
every 41st scheduled orc with a large, strong Brute: 40 regular orcs, then one
Brute. The pattern spans groups within the wave and restarts for each wave;
remaining slots are regular orcs. A wave of 262 therefore contains 256 regular
orcs and 6 Brutes. Before the first Brute wave all orcs are regular.
Authored Grunt, Runner, and Breaker groups retain their regular roles, size,
and stats; authored Brute groups use Grunts for the regular slots. Only the
rare Brutes receive the configurable large size, health, and damage.
Counts (after the global count multiplier), lanes, and release timings remain
unchanged. Deferred spawns keep their original sequence position so active
enemy limits and blocked spawn lanes do not change the mix. The authored
Level bundle is never modified by this setting.

Complete pre-Brute version-1 settings files retain their saved tuning, preset,
and revision while receiving the four new defaults in memory. The next save
atomically writes the complete settings shape. Unknown keys, missing older
fields, or invalid values still produce an explicit storage error.

## Inputs

- `photon.level.runtime` version 2 supplies the parsed graph, sockets, topology,
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
  contract with the hub's existing Server-Sent Events helper. Snapshot preparation
  and encoding are shared across subscribers with the same output format, once
  per wake revision or 250 ms health recheck.
- The optional `game_events(incremental=True)` transport sends a complete normal
  SSE message initially, after reconnect, and whenever static data changes.
  Between those messages, named `update` events omit only `level`, `presentation`,
  `configuration`, `settings`, `loadout`, `force_field_blockers`, and
  `row_barrier_geometry`; consumers
  retain those fields from the last complete stream message. Null/removal and
  availability changes still propagate. Default API/settings streams keep their
  complete-snapshot format.

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

Repository-boundary smoke test: `.venv/bin/python -m unittest discover -s tests -p test_photon_module_isolation.py`.

Game optionally reads Level's `runtime_status()` metadata before requesting a
full runtime bundle. Matching revisions reuse the installed immutable runtime;
active runs still freeze layout changes until reset. Enabled state and the
named/integer-version status contract are checked on each preparation. Older
Level v1 producers without this optional method keep the full-bundle path.

## Row barriers and routing

Game accepts Level runtime v2 with two enabled entrances and four validated
row descriptors. The explicit v1 compatibility branch retains four entrances
and no row barriers. Envelope, metadata, and payload versions must agree.
Active runs keep their frozen level; reset/setup installs a pending revision.

A row powers up only when all three assigned turrets have completed their
normal activation and remain alive. Any missing/destroyed contributor drops
that entire row, independently of the others. Replacement uses normal
activation before restoring power. Ordinary turret links, their damage/wear,
and core-ring membership remain independent. Row barriers have no separate
health, contact damage, wear counter, or ring-completion credit.

The snapshot adds static `row_barrier_geometry`, dynamic `row_barriers`
(`row_id`, `powered`, `active_count`, runtime-clock `changed_at`), and
`row_topology_revision`. One shared reverse Dijkstra serves all route origins;
closed row crossings are strictly excluded before ordinary link costs apply.
Spawns and fallback spawns use enabled entrances and current legal routes.

Topology changes queue road enemies for rerouting, up to 48 per tick, retaining
pending order across rapid changes. Partial current-road paths can exit on
either side, but never through a powered row; rerouting does not teleport the
particle. Swept body-expanded barriers enforce the new topology immediately,
including after crowd separation. Damaging ordinary-link contact retains its
reversal when that direction is row-legal. The two streams take the mirrored
east–west–east routes when all rows are powered.

Performance safeguards include bounded shared road-segment geometry, shared
field costs per reroute batch, staggered road-edge bookkeeping, and conservative
combat bounds before exact collision/damage checks. The simulation retains its
20 Hz target using a deadline that includes work time, without an additional
50 ms post-work sleep or unbounded catch-up bursts. Display FPS is measured
separately from simulation tick frequency.

## LTZ players and rewards

Game consumes `photon.progress` v1 through the enabled-module context, freezes
its roster at Start, and emits cumulative checkpoints and terminal results.
`progress_link.py` performs disk and ledger I/O off the simulation tick. Terminal
results go to `data/pending-result.json` before delivery and replay before
interruption recovery. The public `progress` object reports participants,
eligibility, banked kills, save failures and the final attempt.

`start` accepts a boolean `reward_enabled` (legacy callers default to practice).
Scored Start requires ready progress, selected profiles, physical Board input,
no virtual setup placements and a non-Training preset. Place, aim, loadout,
virtual switching and core assistance are rejected during a scored attempt.
Reset finalizes an abort before clearing the engine. Run commands are serialized.

Four `control_orc_multiplier_*` settings default to 1/1.15/1.3/1.5. They must
strictly increase, within 0.1–5; a scored Start also checks the actual rounded
totals increase. Co-op uses the maximum selected tier. `/api/orc-preview` is a
read-only POST for exact draft calculations. The existing `/api/events` route
supports `view=configuration` for a small settings projection on LTZ Score pages.
The existing v2 snapshot and SSE contract remain compatible with additive fields.

Weapon levels multiply health and damage by 1/1.1/1.2/1.3, with link bonuses
composed once. Force-field capacity uses 1/1.2/1.4/1.6 and the minimum endpoint
upgrade; its visual width is 8/9.5/11/12.5 px. Geometry remains authoritative.

## Virtual test unlocks

Gamemaster `POST /api/command` accepts `action: virtual_test_loadout` with a
complete `levels` object keyed by the four `damage-*` tracks and `forcefield`.
Turrets accept integers 0–4 (0 locks further placement); Force Field accepts
1–4. `levels: null` restores saved-player levels. The command is permitted only
in virtual setup or a virtual practice run, including while paused. It is
rejected for physical/scored play and requires Gamemaster authorization.

The additive `virtual_test_loadout` snapshot field reports the selection. It is
kept in memory across reset and ignored in physical play; restarting the module
clears it. All virtual owners use the selected levels. Existing tower health
percentages are preserved when health/damage upgrades change; field capacity
and art update without repairing broken fields or erasing absorbed hits.
Locking a type blocks further placement and leaves already placed units intact;
Reset clears those units. Test selections do not mutate player profiles, credits,
or progression and work without a saved player or enabled Progress module.
