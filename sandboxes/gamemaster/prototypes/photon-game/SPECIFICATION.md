# Photon Game

## Clean reset and player presence

Game registers `photon.player-management` v1 with the Hub at `hub_init`.
`player_connections()` combines Hub browser identities with the selected profile
names from `photon.progress` v2 and `hhh.relay.player-sessions` v1 ownership.
`clean_reset_players({operation_id})` coordinates admission/revocation through
Hub, durable stop obligations through Journey, relay lease revocation, and the
existing event Reset/Progress contracts. It clears current selection/readiness
while preserving saved progress and calibration. With no event selected it
returns to an empty lobby; it never creates an event.

The Hub recovery record blocks player login and Game motion until reset and
required stops complete and fresh QR codes can be rendered. Duplicate completed
operations are no-ops; failed operations retry with the same ID. Player request
draining happens before taking Game's command lock to avoid nested HTTP
deadlocks. No individual kick operation is registered. Creating/selecting events
does not implicitly change browser identities or invitations.

An explicit empty `reset_stop_sides` list means no stop is needed; it never
expands to both teams. Only legacy records with an unknown scope (`null` or
missing) use the conservative fallback. Journey clears the stop error whenever
the known pending list is empty. Idle, disconnected arms therefore do not block
Clean reset, including a QR-generation retry after the game was already reset.


## Operator turret and Atom controls

Authenticated Game Master commands `operator_atom` (`socket_id`, explicit nullable
`atom_tag_id`) and `operator_turret` (`socket_id`, `activation`: `green`, `purple`,
`deactivated`) are accepted in setup, running event matches, including
paused play. Calibration and finished games reject intervention. Other scored-run
placement/loadout restrictions remain in force. Y
forwards through its existing operator command route; no robot commands are added.

Each non-null operator Atom selection installs, replenishes or rebuilds the turret:
a new turret uses the Atom's team and fixed role; an existing turret retains its
weapon and original owner, including after destruction. An accepted number selection is a manual
activation: it never enters effective occupancy and
leaves health/damage multipliers at 1 (other upgrades and link bonuses still apply).
Identical pending number selections are idempotent. Explicit clearing, moving to
another target, or observed departure re-arms activation; unchanged camera evidence
cannot double-activate. Camera-confirmed occupancy can still grant the normal buff. Selecting the same Atom after X rebuilds it without a boost. Null retains
legacy manual-occupancy clearing behavior without destroying the turret. Locked
initial weapons are rejected before changing occupancy. In physical mode, fresh validated
Board occupancy wins both conflicts: the physical Atom's ID and its target socket.
No held manual choice remains to restore after physical removal or camera loss.
Established Board dwell/grace policy remains
unchanged. A command refreshes cached Board evidence before checking priority.

Legacy team-activation commands (not exposed as G/P buttons in Y) create a new turret using the effective Atom's fixed weapon role, with the
chosen team as initial owner. No Atom means no new installation. An existing
weapon and original owner are retained, including when restoring a destroyed unit;
last activation team is recorded separately. Physical placement/replenishment also
updates the last activating team. Repeating the same active team is idempotent.
The X control sends the `deactivated` command value for compatibility, but now
destroys the turret through normal damage/destruction handling: zero HP,
`destroyed` true, destruction timestamp/event, companions destroyed and linked
defenses updated. It does not merely retain a disabled turret. Repeated X commands
do not replay destruction. A destroyed turret cannot fire, take damage, power links
or row barriers, grant an Atom buff, or run a companion weapon. Reactivation uses ordinary replenishment and
installation timing; projectiles already launched retain their normal lifecycle.
The current physical visit is consumed on manual activation/deactivation: unchanged
frames cannot heal or undo X, while confirmed departure and return can reactivate.

Every snapshot and incremental update includes `turret_controls`, contract
`photon.game.turret-controls` v1. Its `sockets` list supplies `socket_id`, `aruco_id`,
`activation` (`initial`, `green`, `purple`, `deactivated`), `last_activation_team`,
nullable `atom_id` and `atom_source` (`physical`, `manual`), and `occupancy_status`.
Destroyed turrets show deactivated. Public primary and companion records include
`deactivated` and set `operational` false while inactive. Reset clears controls;
Start retains configured setup choices as it retains existing setup turrets.

Smoke tests: `PYTHONPATH=tests .venv/bin/python -m unittest test_event_game`.

### Operator core layers (ArUco 38)

The authorized `operator_core` command takes an explicit nullable `atom_tag_id`.
An Atom selection uses the existing core activation rules with source `operator`:
running game, completed 8–16-turret ring, one first layer, then an opposing-team
second Atom. Same-team selections fail; identical layer retries return without advancing or
replacing layer one. There is no kill requirement. The ordinary radial purge and victory path runs after layer
two, including its existing score handling. Event games accept this
referee command; calibration and terminal games reject it.

Null is X: it clears a pending first layer without damaging the core or ending the
game. It cannot undo detonation. The reset consumes resting camera evidence; a
new physical visit is required to re-arm automatically. A fresh physical first
layer overrides a manual first layer, and physical covers retain the normal
opposing-team and post-first-layer dwell rules. Manual selection moves that Atom
out of its manual turret occupancy/buff; a physically occupied turret Atom cannot
be manually assigned to the core.

`core_sequence` adds `first_source`, `second_atom_tag_id` and `second_source`.
The additive `turret_controls.core` capability gives the core's `aruco_id`,
`blocked_reason`, `can_clear` and `cleared` state for the overlay. All state resets
with the game and is published through the existing snapshot/SSE path.
Smoke tests: `PYTHONPATH=tests .venv/bin/python -m unittest test_operator_core test_photon_core_stack`.

## Wave timeline

Snapshots and SSE include additive `wave_timeline` (`photon.wave-timeline`,
integer version 1): `time_s` is paused simulation time, `end_s` is the final
release horizon (extended by overtime), `queued_orcs` is deferred pressure,
and `waves` contains `wave`, `start_s`, `end_s`, `duration_s` and
`state` (`upcoming`, `spawning`, `released`). Setup previews the selected
map/tier preset. Running windows retain actual launch and completion times;
the frozen event settings remain unchanged until the next match.
Durations describe release windows, including admission to the deferred queue,
not the time to kill every orc. Reading the projection never advances play.
Smoke test: `PYTHONPATH=tests .venv/bin/python -m unittest test_wave_timeline`.

## Event matches and progression

Game Master `/api/event` creates/selects an event through Progress v2 under the
same command/journey locks as Start, after confirming connected arms stopped.
Start requires that event, both linked players, physical Board input, and one
starting Atom per side. Maps with authored homes default to the first configured
team Atom (100/102). Game Master can choose the alternate Atom before binding;
the selection updates the home and starter preview and also applies when the
phone countdown starts the match. Explicit automatic detection still uses Board's
stable target evidence. Legacy maps without homes retain camera-based selection.
Starting Atoms are immutable in a save through L3; L4 enables both team Atoms.

## One-use home defenses

Authored `atom_homes` produce separate `home_platforms` and `starter_turrets`
snapshot arrays. Setup previews show the selected saved game's level and each
weapon's earned upgrades, without participating in combat or accepting aim.
Start deploys one live starter per team in L1–L3. L4 reveals the second home and
deploys a second starter of that team's other weapon type, with its own upgrades.
Green uses machine gun/flamethrower and Purple uses mortar/Tesla under the default
piece codes; configured IDs and a saved alternate first Atom are respected.

Starters are active immediately and use ordinary weapon targeting, damage,
projectiles, enemy contact/ranged attacks, kill rewards and owner-validated aim.
They have their own stable aim instance and 72 px pod footprint. They never enter
construction socket occupancy, activation order, links, row barriers or the core
ring, receive no Atom occupancy buff, and never spawn an L4 companion.

Destroyed starters remain destroyed for that match, including after browser
reload, mode changes or upgrade refresh. Placement, operator activation and
replenishment/replacement cannot rebuild them. Moving the Atom onto a regular
socket still builds there normally. Only a new match creates fresh starters.
The saved run metadata records this starter policy. Physical Atom movement stays
on the existing robot path; homes add no physical marker or robot command.

Smoke test: `PYTHONPATH=tests .venv/bin/python -m unittest test_starter_defenses`.

`end_match`, `unlock_next_level` and `next_match` carry `event_id` and `run_id`.
End match confirms arm stops before ending running/paused play. Progress atomically
settles actual earnings plus one forced turret tier per player, including debt.
Repeated requests return the saved receipt. An old run ID cannot end a newer match.
Unlock advances both control/force-field levels at most once for the finished match.
Continue clears only the battlefield and runs required calibration before readiness.
Results remain visible until Continue; there is no shop timer.

The completed ring alone unlocks the center for an eligible 100-series Atom at
every level, including with zero kills. An opposing Atom stack advances controls
and force field together; wave-clear victory
alone does not. The one-time event preset rollout copies selected venue settings
into retained new revisions, using enemy-health factors 1/2/8/10 by level (maximum
10). Previous presets remain available; subsequent GM selections are preserved.
`event-progression-v1` is provisional tuning, supported by deterministic traces in
`output/event-progression-2026-10-17/balance-event.json`, not human measurements.
Those traces used the superseded kill gate; they do not predict ring-only completion.
Start freezes `core_rule_version: 2` for comparable event statistics. Wave timing,
kill scoring, health-based stack bonuses and automatic purchases are unchanged.
Rejected physical placement evidence is not consumed, so fresh valid frames can
retry the same placement without lifting the Atom. Normal stale-evidence, phase,
ring, eligible-Atom and opposing-team guards still apply.
Smoke test: `PYTHONPATH=tests .venv/bin/python -m unittest test_ring_core_unlock`.

Practice, test matches, player grants, arbitrary test tiers and virtual gameplay
are removed from public commands and UI. Standalone engine simulation helpers are
retained for developer regression/benchmark fixtures only. Calibration setup stays
independent. It grants only the guarded calibration movement scope, never credits,
turret tiers or normal player controls. L1/L2 tolerate a different camera correction
while retaining physical limits; L3/L4 keep the image-calibration guards.

## Atom tower buff

An accepted Atom on a turret's fixed marker grants **2× maximum health and
2× weapon damage** while Board confirms its presence. Normal health/damage
already includes weapon-level, link and weapon-specific modifiers. The Atom
multiplier is applied once; it does not change rate, reach, effect duration,
force-field damage, core damage, link count or score per kill.

Removal or unavailable occupancy removes both bonuses. Health changes preserve
percentage: 150/200 becomes 75/100. A confirmed new placement/return refills the
final doubled maximum once through the existing replenishment path, including
its field repair and cooldown behavior. Staying on the marker never heals or
replaces a destroyed turret. A separate accepted-visit record prevents camera
gaps, pump changes, relation-ID changes and source recovery from granting heals.
Reacquisition without observed departure restores capacity at the remaining
percentage. Occupancy continues to reconcile while the simulation is paused.
Board-confirmed reappearance of a previously covered marker counts as departure.
A cached placement overlap cannot replenish or consume that return visit while
occupancy reports departure/unavailability, including a vertically lifted Atom
still visible at the marker's XY. A fresh accepted return heals once as usual.

Game validates Board's separately versioned `photon.board.occupancy` v1 through
its public `occupancy_snapshot(scope=...)` function, independently of unavailable arm
placement evidence. Installation/replenishment/replacement still require the
ordinary placement gate. Board owns coordinates and dwell; Game owns ownership,
socket selection, accepted visits and all health/damage calculations.
Game registers its run/layout scope through Board's public
`game_observation(scope=..., fixed_ids=...)`, validates `photon.board.runtime` v1
and the exact scope/ID acknowledgement, and reads occupancy for that same scope.
The scope comes from `shared.fixed_board.cue_layout`, as on the displays. Missing
scoped APIs or mismatched scope fail closed. Board's confirmed fixed coordinates
remain eligible while hidden for that game, with fresh moving-Atom evidence and
all existing placement/occupancy gates. The engine's ownership, activation order,
buff and replenishment rules are unchanged.
Game validates the advertised finite `policy.grace_s` within 0.35–0.9 seconds
and uses it for evidence expiry. Legacy publishers without the field retain
the 0.35-second limit. Malformed or larger limits fail closed. Brief detection
gaps within the limit preserve health, damage and the existing accepted visit.

Every public primary/companion record includes `atom_buff_state` (`active`,
`inactive`, `unavailable`), nullable `occupying_atom_id`,
`atom_health_multiplier`, `atom_damage_multiplier`, and `normal_max_hp` beside
effective `hp`/`max_hp`. Companions share the parent pool and each weapon receives
the outgoing multiplier once. Direct, Tesla-chain, Mortar-splash and Flamethrower
burn damage use the same state. Mortar rounds capture damage at launch; applied
burns retain their committed damage under the existing burn-combination rule.

Virtual `place` with null `socket_id` lifts an Atom without removing its installed
turrets. Mobile suction uses this same removal operation; release uses normal
placement. Moving an Atom to another socket transfers the bonus, while previous
turrets continue fighting. Repeated virtual placement on the same occupied socket
is idempotent. Core placement removes that Atom's virtual turret occupancy.
Start preserves virtual occupancy for setup placements and reacquires physical
evidence; reset clears visits and mode changes suspend the previous source's buff.

Validation: `tests/test_atom_tower_buff.py`, `tests/atom_buff_renderer.cjs`, and
`tests/atom_buff_browser.cjs`. See `docs/ATOM_TOWER_BUFF_IMPLEMENTATION.md` for
measured browser results and the remaining physical check.

## Physical core completion

After the force-field ring completes, the first valid physical Atom placement
on marker 38 arms that Atom's identity. The first placement retains the existing
Board fixed-marker and owning-arm requirements. From then on the second step
follows the first Atom, not marker 38: a stable Board camera cover of that Atom
by a configured opposing-team Atom starts the core detonation and enemy purge,
then victory. The second team's robot may be disconnected; neither arm's
connection, enable state or pump state is needed for this camera-only finish.
The first Atom can remain visible indefinitely while waiting, and its observed
position follows it if moved. Losing marker 38's 120-second cache is irrelevant
after the first activation.

Game validates Board's additive `photon.board.stacking` v1 descriptor within the
existing placement sample. Only a cover observed after the first activation,
of that exact Atom, by the opposing team can complete the sequence. Same-team,
unconfigured or unrelated Atoms, two visible adjacent Atoms, old/replayed cover
evidence, and invalid/stale samples cannot win. A second fixed-marker relation
to 38 alone no longer completes the physical sequence. Reset clears the armed
Atom and activation time. Existing virtual core commands and ordinary physical
tower-placement requirements are unchanged. Successful physical covers record
`core_stack_confirmed` with both Atom IDs and the Board relation ID.

Regression command: `.venv/bin/python -m unittest discover -s tests -p 'test_photon_core_stack.py'`.

## L4 companion weapons

Weapon upgrade bonuses are saved combat settings: `weapon_upgrade_l2_percent`,
`weapon_upgrade_l3_percent`, and `weapon_upgrade_l4_percent` default to 30, 40,
and 50. They scale both damage and health relative to L1 (1.3×, 1.4×, 1.5×),
not cumulatively. `l4_turrets_per_socket` defaults to 2; setting it to 1 disables
companions. Game Settings exposes these controls under Weapon upgrade levels.
They use the existing draft and immutable per-map/control-tier preset revisions,
freeze at Start, and are projected into both player shops from the selected
next-match preset. Older settings files inherit these defaults without losing
their other tuning. Force-field upgrade capacity is unchanged.

At an eligible Level anchor, an effective L4 weapon creates one same-type
companion when doubling is enabled. It inherits the parent's owner, damage/link multipliers and aim/spread
inputs, while targeting from its own origin with independent charge, cooldown,
shots and projectiles. New pairs activate together. Promotion during practice
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

Game consumes `photon.progress` v2 through the enabled-module context, freezes
its roster at Start, and emits cumulative checkpoints and terminal results.
`progress_link.py` performs disk and ledger I/O off the simulation tick. Terminal
results go to `data/pending-result.json` before delivery and replay before
interruption recovery. The public `progress` object reports participants,
eligibility, banked kills, save failures and the final attempt.

`start` accepts a boolean `reward_enabled` (legacy callers default to practice).
When Progress's validated roster contains a built-in test profile, Game forces
practice before checking scored-only restrictions and freezes the test IDs in
run metadata. Progress independently enforces eligibility using its owned IDs.
The delivery adapter reports the eligibility returned by Progress. A mixed
real/test roster is practice for both participants and cannot affect scored
statistics or control mastery. Its validated kill credits fund persistent upgrades.
Scored Start requires ready progress, selected profiles, physical Board input,
no virtual setup placements and a non-Training preset. Place, aim, loadout,
virtual switching and core assistance are rejected during a scored attempt.
Reset finalizes an abort before clearing the engine. Run commands are serialized.

Four `control_orc_multiplier_*` settings default to 1/1.15/1.3/1.5. They must
strictly increase, within 0.1–5; a scored Start also checks the actual rounded
totals increase. Co-op uses the maximum mandatory current tier. `/api/orc-preview` is a
read-only POST for exact draft calculations. `/api/events?view=configuration`
publishes `photon.game.preview` v1: `status`, exact
per-tier `previews`, and `virtual_test_control` (integer 1–4 or null). Player
score presentations show this grant as practice access and never save it as
earned progression. Disabled/unavailable input clears that presentation grant.
The existing v2 snapshot and SSE contract remain compatible with additive fields.

Weapon levels default to health and damage multipliers of 1/1.3/1.4/1.5, with link bonuses
composed once. Force-field capacity uses 1/1.2/1.4/1.6 and the minimum endpoint
upgrade; its visual width is 8/9.5/11/12.5 px. Geometry remains authoritative.

## Practice unlocks

Gamemaster `POST /api/command` accepts `action: virtual_test_loadout` with a
complete `levels` object keyed by the four `damage-*` tracks and `forcefield`.
Turrets accept integers 0–4 (0 locks further placement); Force Field accepts
1–4. `levels: null` restores saved-player levels. The command is permitted only
in setup or a practice run, virtual or physical, including while paused. It
requires Gamemaster authorization. Active scored runs reject changes, and scored
starts reject any active defense or mobile test override. The legacy command and
snapshot field names are retained for client compatibility.

The additive `virtual_test_loadout` snapshot field reports the selection. It is
kept in memory across reset and mode changes; restarting the module
clears it. Both teams use the selected levels in virtual and physical practice. Existing tower health
percentages are preserved when health/damage upgrades change; field capacity
and art update without repairing broken fields or erasing absorbed hits.
Locking a type blocks further placement and leaves already placed units intact;
Reset clears those units. Test selections do not mutate player profiles, credits,
or progression and work without a saved player or enabled Progress module.


## Virtual mobile Cartesian controls

`virtual_test_loadout` accepts an optional `control` integer 1–4 or null, validated
atomically with the defense levels. Omission preserves the previous control
selection for older clients. Game state publishes `virtual_test_control`; reset
retains this operator selection, while returning the arm to Joint mode. Disabling
the test override restores saved-profile unlock availability. Lowering the override
to Joint, or disabling it, freezes pending XYZ motion and returns to Joint.

The existing `mobile_command` input supports `control_mode` (`joint`, `xyz`, `targeting`, or `cue`) and
`xyz` with an `xyz: {x,y,z}` target and integer `control_revision`. The server reads
the selected team's saved unlock from the versioned Photon Progress output when no test
override is active. Missing or malformed progress grants only the default Joint
control. Targeting requires tier 3 and reuses the validated `xyz` command. Cue autonomy requires tier 4 and uses the same movement and placement validation.
The existing virtual-play, scored-attempt exclusion, session ownership, monotonic
sequence, lease, pause, Stop and reconnect checks apply to all new commands.

The additive `photon.mobile-arm` version 1 fields are `control_mode`,
`control_revision`, `xyz_limits`, and `xyz_target`. `tip` remains the actual pose.
XYZ uses existing map X/Y units and the virtual arm's existing height scale, not
physical robot millimetres. Inverse kinematics uses both possible elbow branches
and picks the valid solution closest to the current joints. Coordinates must be
finite, within the workspace, geometrically reachable, and within all joint
limits. Rejection leaves accepted targets unchanged. Motion still runs through
the existing 12°/s joint simulation; this initial version does not promise a
straight-line Cartesian trajectory. Mode switching freezes at the actual pose,
preserves held tags, and increments a revision to reject obsolete motion.

New mobile connections select the highest implemented unlocked mode automatically:
Joint for tier 1, XYZ for tier 2, Targeting for tier 3, Cue for tier 4. Changed unlock tiers apply the same default
immediately and freeze pending movement. Ordinary heartbeats and reapplying the
same tier preserve a manually selected lower mode. Preview modes never become
movement defaults.

### Movable piece IDs and virtual cues

Game settings add integer `green_piece_1`, `green_piece_2`, `purple_piece_1`,
and `purple_piece_2` (defaults 100, 101, 102, 103; range 0–999). IDs must be
distinct and cannot collide with socket markers or the core marker 38. Slot
roles remain machine gun, flamethrower, mortar, and Tesla respectively. Old saved
settings migrate with default IDs. Game owns the ID→team/role mapping for both
virtual and incoming Board placements; this does not reconfigure camera detection.
Saved changes apply during setup and at the next Start, never to an active run.
Changing IDs resets the mobile session/cue and remaps existing setup tower roles.
Game snapshots publish `movable_piece_codes` for both teams.

`photon.mobile-arm` v1 adds `markers` (virtual socket/core coordinates) and `cue`
(`rows`, zero-based `index`, `status`, `stage`, `error`). Authenticated, sequenced
`cue_set`, `cue_play`, `cue_pause`, and `cue_stop` require Cue mode/tier 4 and an
exact integer control revision. Rows contain integer `piece` and `destination`
IDs; 1–32 rows are allowed. Only the selected team's configured pieces are eligible.

The module-local MobileCue advances inside MobileArm.step, never on a browser
timer. It preflights each row's IK, retains held pieces on cue pause/stop, calls
the shared pump/placement operations, and rejects competing manual movement.
Session suspension cancels execution under the existing virtual-tag policy.
`tests/test_mobile_cue.py` covers execution, revisions, ownership, pause/stop,
unavailable markers, invalid poses, migration, and custom-code placement.

### Full-map virtual reach and cue detours

The virtual MobileArm uses equal links sized for all map corners and Z=0–400,
and ±180° virtual joint ranges. Initial piece positions are preserved. Existing
IK and 12°/s joint stepping still own actual movement; this does not configure
physical robots or imply collision-free/straight-line Cartesian travel.

MobileArm snapshots timestamp their measured pose with `position_at` (Unix
seconds), allowing the player to interpolate on the source timeline independently
of delivery jitter. This display timestamp does not advance simulation or grant
movement authority. `position_settled` is true only when actual joints have reached
their current targets, allowing presentation to remove its remaining playback
delay at a measured stop without predicting arrival.

MobileArm snapshots include optional `motion_path: {id, points}` for presentation,
with finite map-space `{x,y,z}` points. The virtual owner samples its remaining
bounded joint travel at intervals of at most 2 degrees, preserving the actual
curved tip trajectory. The ID stays stable during travel to the same joint target;
joint mode, suspended sessions and missing ownership omit the path. Reading this
field never advances the arm or changes its target. The player draws only the
remaining route as a dashed red line, trimming it against the smoothed red marker.

Cue commands add `cue_waypoint` with finite map `point: {x,y}` and
`cue_cancel_waypoint`, under the same tier/session/revision gates. Cue snapshots
add nullable `waypoint: {x,y,z}`. A waypoint has a separate temporary movement
goal while preserving the interrupted row/stage goal. Arrival clears the detour
and resumes that stage; it never performs a pump action or advances the row.
Replacement keeps only the latest point. Pause retains both goals and any held
piece; Stop and all session/mode transitions discard the detour. Queued idle
waypoints wait for explicit Play.

### Mobile player turret aim

Photon Game v2 exposes `mobile_turret_aim(data)` for the authenticated team
presentation. Required fields are `run_id`, `socket_id`, `atom_tag_id`,
`activation_started_at`, `aim_instance`, `aim_revision`, `angle_degrees`, and `spread` (0–1).
The opaque `aim_instance` changes for every placement/replacement, including setup resets.
The selected live placement must belong to the command’s team and match the supplied run,
activation and revision. Setup and unpaused running games accept the command
in virtual or physical play, independently of robot sessions. The existing
`set_tower_aim` rules remain authoritative and publish the resulting revision.

Mobile commands accept `side: green|purple` (default Green for existing clients).
Game owns a separate virtual `MobileArm` for each team, with independent sessions,
leases, targets, cues and movable pieces. Purple's virtual arm faces the board
from the opposite corner. Start preserves both controllers, while pause/reset
and physical-mode transitions halt both. `mobile_arms` publishes both public
snapshots; `mobile_arm` remains the existing Green compatibility field.
The mobile facade selects only the authenticated team's arm and progress for
`?side=green|purple`, with separate SSE producers. A role cannot read or command
the other team's mobile endpoint or aim its turret.


## Mobile co-op journey and level presets (2026-10-01)

The player controller replaces its compact name-entry window with a mission
briefing after a profile is selected. Its glass background is 20% opaque, with
readable text describing turret activation, the eight-turret core ring, the
two-color ATOM stack, and aiming. Ready closes the briefing and shows “Get ready”
in the countdown typography, repeatedly growing and fading while awaiting Start.
The saved Ready acknowledgement preserves this waiting view across refreshes.
Calibration and explicitly opened player/upgrade windows hide the waiting text;
Start replaces it immediately with the authoritative countdown.

The Game Start command begins a five-second countdown before advancing combat
or the existing first-wave preparation clock. Both player controllers render
the additive `start_countdown` snapshot (`photon.game.start-countdown` v1):
remaining seconds, configured duration, run start identity and gameplay elapsed
time. The sequence is 5, 4, 3, 2, 1, GO!, with each glyph growing and fading.
GO lasts the first second of gameplay. Pause freezes the countdown, Reset clears
it, and joining/reloading reads the current sequence instead of restarting it.
Reduced-motion users see the same sequence without the scaling animation.
Direct engine calls may omit the countdown for headless simulation tooling;
operator starts always request five seconds.

Game owns `journey.py` and `presets.py`; their data files live beside its run
log. `journey_snapshot()` returns `photon.game.journey` v1. Its phases are
lobby, playing, upgrades, calibration and ready. A scored terminal result starts
one server deadline of 30 seconds. The third XYZ win immediately queues Green
then Purple calibration. The partner waits with purchases and history; expiry
never starts a second countdown after calibration. Player Ready acknowledgements
bind selected profile IDs/revisions and are advisory. Game Master's Start can
end shopping immediately, including an untimed practice shop, without either
Ready acknowledgement. Scored Start reserves the current profiles/loadouts
transactionally; purchases completed before reservation remain included. A restarted
scored run reads its canonical interrupted receipt and returns to upgrades.

Game Master `next_level` takes the saved journey `run_id` and prepares setup
without waiting for player readiness or the upgrade deadline. Test-player shops
advance the practice tier through the existing idempotent `advance_test` owner
operation. Regular shops retain earned tiers and reserve current loadouts.
Start directly from setup closes shopping and uses the current tier. Calibration,
fresh Board evidence, motion-stop confirmation and durable result checks still
apply. `next_loadouts.teams` includes profile IDs/revisions so the operator can
distinguish current Ready acknowledgements from ones invalidated by purchases.

The journey's `calibration_side` identifies the queued turn for presentation,
including while camera/arm feedback or a previous stop prevents activation.
It is null outside calibration. `active_side` and `session_id` retain their
motion-authority meaning; selecting a calibration screen never grants movement.
Mobile LTZ API exposes only the selected side's matching saved draft and a
`mobile_calibration_ready` flag for capture presentation. A blocked or restored
draft can be displayed, but cannot capture until the live owner grant is ready.

`mobile_journey_command(side, value)` accepts ready, calibration replay, lesson
capture/ground/raised/height/commit/arrival/heartbeat, complete, and finish.
Complete asks Cal 2 to validate and install all ten target measurements and both
heights, then consumes its durable completion receipt through the existing
turn/progression path. Green hands off to Purple; the last player proceeds to
the existing shared upgrade/ready step without restarting its countdown.
Practice returns to the preceding screen and awards no player progress.
Both paths require a confirmed stopped arm before handing off the playfield.
The optional guided exercise remains available: Finish consumes
fresh Board stable placement evidence for the measured, picked-up Atom after
both guided moves and measured lift. Browser reports cannot award completion;
Cal 2 owns both measured-target and guided-exercise receipts.
`motion_policy(side)` returns `photon.game.motion` v1: player, practice,
tutorial or waiting. Waiting/expired transitions block motion. Operator
`calibration_test` accepts Green/Purple/Both; `journey_cancel` requires no active
run. `virtual_test_loadout` grants the selected test tier to BOTH arms in
physical or virtual practice; its matches bank kill credits for upgrades without granting scored mastery.

Operator `show_game` closes a saved practice calibration or pauses earned
calibration, preserving its draft/sequence under `deferred_calibration`. Loading
the Y operator page and its Game screen button use this command. Deferred earned
work does not automatically reopen on the next tick/restart; `calibration_resume`
or player replay restores the same operation and remaining sequence. Players
still cannot mark Ready before completing their required lesson.

`journey_cancel` and practice-side switches request the calibration owner's
`defer_stop` release. Display restoration can finish with an offline arm while
the owner retains a durable stop inhibit. Journey exposes `motion_blocked` and
`motion_error`; physical Start and both teams' motion policies honor it even in
the lobby with test overrides. The existing worker maintains the owner in the
lobby too, so fresh stop confirmation can clear the inhibit without another
lesson. No display selection or page load grants hardware access.

The additive `level_presets` snapshot is `photon.game.presets` v1. Operator
`level_preset` saves, loads, renames and restores immutable revisions by map and
tier. Preserved venue settings remain a legacy family. Selected progression
presets require increasing exact counts and release rates and decreasing wave
gaps across all four tiers before scored Start. The highest participant tier
selects one preset; control multipliers/difficulty offsets apply once.
`first_wave_delay_s` pauses with active time, and `difficulty_offset` permits
-10%, -5%, 0%, +5%, +10% enemy-count adjustments. The preview includes per-wave
release windows, overlap and the scheduled release end. Saving a settings draft
alone does not replace a selected level/tier preset. All run settings and preset
metadata are frozen at Start. See `docs/CONTROL_BALANCE_REPORT.json` for the
provisional simulator matrix; historical control-speed factors remain unknown.

## Breaker archer (combat v1, 10 October 2026)

`photon_game_runtime/ranged_enemies.py` owns ranged Breaker state and hostile arrows.
Existing `breaker` waves can use `melee` or `ranged`; settings freeze at Start.
The four **Breaker archer candidate** tier presets are appended once without
selecting them or changing saved legacy revisions. Loading an older revision
projects the missing keys as melee defaults. Scored archer presets retain the
existing increasing tier schedule checks. Start requires an enabled Y renderer
that advertises `photon.renderer` v1 and integer `enemy_combat_version: 1`.

Ranged breakers stop voluntary movement, retain normal collision separation,
aim at the nearest exposed primary/companion tower before the core, draw, then
release fixed-endpoint arrows. A newly exposed tower supersedes a core target.
Tower targets remain stable while valid. Acquisition range is 220 map units,
retention 110%, initial draw 0.5s, release interval 1.5s, tower/core base damage
12 each, speed 420 units/s. All are validated Game Settings; draw must be less
than interval. Existing damage multipliers apply once. Ranged breakers have no
contact damage. Each installation's existing `aim_instance` prevents arrows
from hitting a replacement; companion hits use the parent's single health pool.

Tick order: refresh topology/spawns/purge; advance previously released arrows;
resolve burn/mortar/field damage; acquire/aim; movement/collision constraints;
release due arrows; melee/core contact; tower fire; remove dead enemies; resolve
terminal outcome. A tower kill later in a release tick does not retract that
arrow. Death before release cancels the draw. Shields use authoritative powered
rows and operational field segments, including changes during flight. Arrows
end at pod/core surfaces, with no marker-based blockers or field-contact wear.

Pause freezes simulation time; reset clears combat state. Accepted center
stacks capture `telemetry.core_health_at_stack`, cancel draws and neutralize
arrows. All-wave wins wait for damaging arrows; a final core hit can defeat.
Harmless flights do not delay victory and clear at completion.

Full/compact snapshots publish `enemy_combat` (`photon.enemy-combat`, integer
v1), per-enemy `combat` variant/state/times, `enemy_arrows`, and bounded
`enemy_arrow_impacts`. Held enemies publish a hold motion guide. Game alone
resolves damage. Telemetry records scheduled/released/killed class counts,
combat/purge kills and bounded shot/hit/block/miss/damage/destruction/time
aggregates; existing Progress terminal flushing persists them off the tick.

Validation: `PYTHONPATH=tests .venv/bin/python -m unittest test_ranged_breakers test_ranged_delivery test_control_presets`.
See `docs/LTZ_RANGED_BREAKER_REPORT_2026-10-10.md` for balance limits and rollout.


## LTZ score and horde candidate (2026-10-10)

The engine-owned `MatchRewards` freezes exact per-class scheduled counts (including periodic brute replacement), values and bonus rules at Start. Its cumulative `photon.match-score` v1 output separates raw kills, weighted kill credits and saved bonus; `victory_method` distinguishes `center_stack` and `waves_cleared`. Telemetry retains combat/purge counts, center health at accepted stack, bounded horde timeline, actual peak/cap/deferred counts and longest 900+ interval. No client computes currency.

`photon.next-match` v1 projects the four actually selected immutable tier presets, scheduled counts and full-clear credits. `/api/economy` is Gamemaster-only and forwards the named Progress economy contract. Upgrade prices are saved separately from combat settings. `result_save` distinguishes playing/saving/saved; `next_loadouts` is an operator-only projection removed by Mobile.

`LTZ score and horde candidate` is an opt-in four-tier family, added without changing existing revisions or selections. Cue uses 4,092 finite orcs on the current map, cap 1,000 and unchanged lossless 2,000 deferred-pressure capacity. The seeded reference trace deploys 16 primaries and 12 companions; actual lower-tier and dense performance evidence is recorded in the implementation report. The candidate remains separate until performance and supervised human playtests qualify it. No victory gate or minimum wave was introduced.


## Game Master test match → shop → next level (2026-10-11)

`test_end_match {run_id}` is a Game Master command restricted to a running or
paused practice attempt containing a built-in test player. It stops virtual
arm input and simulation, records `aborted` with `gamemaster_test_end` telemetry,
and delivers the actual kills/duration through the durable result outbox.
It creates no victory, currency, mastery or scored-history row. The shop opens
only after the result saves; failures remain visible as Saving and retries are
idempotent. Natural terminal test results use the same practice shop.

`test_next_level {run_id}` closes the saved practice shop through Progress's
named admin contract, prepares the next tier, resets the battlefield and clears
GM control/loadout overrides so the purchased per-player upgrades apply at
Start. A Level 4 win ends the campaign; repeating it requires an explicit replay choice. The normal Start command still checks the current
board/motion state; this operation does not start robot motion or manufacture
calibration evidence. Shared practice shops block ordinary mobile motion after
a finished match. Once reset/restart has returned the engine to `setup`, an
explicit GM test control tier permits setup positioning for both arms; the saved
shop remains available for purchases and Next level. Setup without that grant,
calibration ownership and unconfirmed stops remain blocked. Real-player mastery and the three-win
rule remain unchanged. Stale run IDs cannot end or reset a newer match.

`/api/player-admin` GET/POST is Game Master-only and validates
`photon.progress.admin` v1. POST accepts credit grants only. Tier advancement
is available exclusively through the validated game transition, not this
wallet endpoint. Test shops and advancement receipts survive restart.

Motion policy includes `blocked` and a specific `error` when blocked. Mobile
projects the same `photon.game.motion` v1 decision used by Relay; clients must
not infer motion permission from a test tier or journey phase alone.

## Saved co-op game switching (2026-10-17)

`POST /api/saved-game?side=green|purple` and owner-public
`saved_game_command(side, value)` expose New/Save/Load to authenticated players.
These are between-match operations, serialized by the same command lock as Start.
They reject running matches and calibration transitions. Pending results must
finish saving first. New/Load revoke physical motion through the existing Relay
stop-and-settle contract for each connected arm before replacing player bindings.
A failed stop leaves game selection unchanged and motion blocked until a successful
retry. New/Load clear old practice overrides, result display and readiness,
retain physical/virtual play selection and return to setup. Loading the same game
restores a calibration turn checkpoint saved by Reset, including its session ID;
other games do not inherit it. They never start a match or replay a movement.

Normal fresh Start prepares both players at L1; loading an existing game restores
its control progression. An explicit GM test override continues to be a separate
practice path.


## Start retries and player readiness (2026-10-18)

The Game snapshot exposes `journey.readiness`: `status`, `all_ready` and two
`players` entries with `id`, `name`, `ready`, and `state` (`unselected`, `waiting`,
`calibration`, `ready`). This presentation uses the selected pair, controls and
loadouts captured when each player taps Ready. Bookkeeping revision changes from
preparing a fresh game do not invalidate Ready. New/Load resets acknowledgements;
a changed partner, control tier or upgrade requires confirmation again. Existing
acknowledgements with only profile IDs/revisions remain accepted for that profile.
For the first game, readiness remains advisory and Game Master starts it.
For a completed level, both players' Continue / Ready acknowledgements trigger
the next attempt automatically through the existing `next_match` and `start`
commands, including the five-second countdown. Mobile Ready includes `event_id`
and the finished `run_id`; stale receipts cannot acknowledge a newer result.
Readiness itself grants no motion or calibration permission.

Saved `interrupted` and `aborted` attempts also accept both players' Ready
acknowledgements after a hub restart. Retry starts the current saved level with
the same pair, banked credits and equipment; it does not award completion or
advance the level. The player receipt labels this action `Retry level · Ready`.
A running/unsaved attempt remains blocked, and a result for another pair or
event is rejected separately from a pending save.

End screens display both players' selections and explicitly show disagreement.
Either player can change their choice while waiting; only matching choices
continue automatically. Successful selections clear previous command errors.
Buttons retain the displayed result's run ID, and older command replies or SSE
snapshots cannot restore an end screen after the next run starts. The isolated
`tests/result_agreement_browser.cjs` covers disagreement, refresh, stale errors,
delayed replies and old buttons on both phones and the statistics page.

Game serializes player continuation with operator commands. A pending
`journey.auto_start` records the agreed event, saved pair, result, next level and
loadouts. Required calibration starts only after both Continue acknowledgements;
the intent survives its Green/Purple turns and automatically starts after they
finish. Fresh camera evidence, confirmed arm stops, saved results and the normal
Start checks remain mandatory. A failed Start is visible in both player panels
and can be retried by either phone, with no background retry loop. Changed
players/equipment require both acknowledgements again. Cancelling the journey or
loading a new pair clears the intent. Delayed duplicate Continue requests cannot
reset or start an additional match. No extra charge, upgrade or result is issued.
Tests: `test_player_continue` and the two-phone Continue flow in
`tests/level_results_browser.cjs`.

Game releases its own unused Start reservation before preparing/rebinding a retry,
including a reservation persisted by an older process. It reserves only after
Start metadata is validated and releases that reservation if journey persistence
or attempt creation fails. Progress atomically consumes it on successful begin.
Calibration reservations remain protected. Tests: `test_start_readiness` and
`tests/event_progression_browser.cjs` (isolated fake hardware).


Start uses helper references retained at module initialization, with no request-time
prototype imports. The obsolete combat-target helper was removed by the ring-only
rule. The hub removes prototype helper packages from `sys.modules`
and the prototype directory from `sys.path` after loading; retained function
references remain valid. `test_start_readiness` exercises Start after that cleanup.
Unexpected command errors are logged with their traceback and returned as JSON 500
responses with a readable message; expected validation failures remain JSON 400.

## Game Master Reset (2026-10-18)

Reset prepares a new game in the active event and returns both phones to name
selection. It requests arm stops through the existing relay stop contract,
settles any unfinished attempt as `aborted`, cancels calibration/readiness and
pending automatic continuation, then asks Progress to reselect the same event.
That owner transaction clears both selected players and the active linked save;
it retains player records, wallets, turret upgrades, saved pairs and completed
event results. Reset never forces a turret purchase or level unlock. An already
completed result keeps its actual outcome and existing settlement.

The command requires `event_id`, `run_id` (nullable), `game_id` (nullable), a unique
`operation_id` and `reset_generation` (the previous `journey.reset_operation`, or
null). Serialized duplicate requests do not reset a newly selected pair or match;
older generations and stale event/game/run identities are rejected before stopping
arms. Unavailable stop confirmation does not block Reset: Journey persists a motion
inhibit and retries the existing stop contract before movement or Start can resume.
The required sides are captured at Reset: connected arms, the active calibration
arm, outstanding calibration stops, and both participants if a match is running.
An unrelated disconnected waiting arm does not gain a new stop obligation.
Each confirmed side is removed durably from `reset_stop_sides`, so disconnecting
it later cannot undo that confirmation. Required disconnected arms remain blocked
until the relay confirms their stop. Legacy unscoped errors remain conservative
until confirmed or explicitly recovered from verified operator evidence.
Calibration release uses its owner's durable deferred-stop gate. A save failure
retains the recoverable game and blocks motion until retry.
The final reset receipt is persisted in Journey. Old Continue requests cannot mark
players ready after Reset.

The new lobby clears phone drafts, result browsing and panel scroll position.
Choosing a name prepares L1 controls/force field; explicitly loading a linked game
restores that game's progression. Before Reset, Game checkpoints the exact
calibration queue, turn and session ID by saved-game/event/player identity in
its durable Journey file; measured points remain with the calibration owner.
Loading that game resumes the interrupted side with its partial measurements,
including after restart, without repeating a completed Green turn or reusing
old Continue acknowledgements. Start still requires both player names and the
normal Game Master/physical readiness checks. Older saves without a turn checkpoint
use their saved player completion records to skip finished turns. A verified
completion receipt can recover the original sibling draft when the player pair,
calibration milestone and session evidence match. Existing incorrect Green turns
are reconciled before hardware readiness, so an offline Purple arm still shows
Purple's turn without granting motion. Setup/replay lessons remain explicit.
Tests: `test_event_reset`,
`tests/reset_calibration_browser.cjs`, and the GM Reset flow in
`tests/level_results_browser.cjs` (temporary data and fake arms).
Run the reset browser with `LTZ_CALIBRATION_LEGACY=1` to cover missing checkpoints.


## Campaign results and ring notices (19 October 2026)

A won Level 4 stays on **You Win! Game Over** with the saved level statistics.
The victory heading, immediate kill/score/time stats and kill heatmap appear from
the terminal simulation state even while result saving is unavailable. Replay
choices appear after durable settlement. Configuration SSE includes an optional
`terminal_result` with the same provisional data for LTZ Score; phones receive
the terminal `kill_heatmap` in their regular game snapshot. Live gameplay does
not transmit the heatmap grid.
Continue is available after earlier levels; every results screen offers Replay
last level, Replay whole game, and New game. Both players must choose the same
option, through the existing authenticated journey API (`ready`, `choice`,
`run_id`, `event_id`). Mismatched choices wait. New game returns to name selection;
Replay whole game starts L1 with the same pair and starting Atoms. Replay last
level uses the level just played, even when its win unlocked the next level.
Replays retain wallets, weapon purchases, and historical scores. A replay gets a
new linked save and a fresh attempt; duplicate requests cannot duplicate either.
Existing arm stops, fresh camera checks, calibration gates and countdown still
apply. A blocked start can be retried from either phone.

The simulation records a 32 × 18 kill-count grid per run, at the same point that
lethal damage is counted, including shared force-field and core-purge kills.
The final outbox carries `kill_heatmap` with board dimensions, frozen road/marker
landmarks, center position, and an explicit count for unavailable positions.
The grid resets for every attempt and is never inferred from browser frame rates.

`core_sequence.ring_notice` is the latest numbered activation/incomplete message.
A broken, occluded or unavailable ring boundary locks the center and clears any
pending first Atom. Repairing the ring reactivates it. Incomplete notices remain
visible until repair; activation notices last eight seconds. Phones, Game Master
and projector receive the same simulation state, and reconnects preserve the
incomplete warning without repeatedly announcing unchanged snapshots.

Verification: `test_result_save_isolation`, `test_results_replay_heatmap`, `test_player_continue`,
`test_level_results`, `test_ring_core_unlock`, and
`tests/results_replay_browser.cjs` / `tests/level_results_browser.cjs` use temporary
player stores and fake hardware. Browser evidence is in
`output/results-replay-2026-10-19/`.
The isolation regression purges sandbox helper imports exactly as the production
hub does, completes repeated L4 replays, and recovers a failed save from the
durable outbox without duplicate rewards. Browser coverage keeps saving
unavailable across a phone reload before retrying it.
