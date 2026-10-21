# Photon Progress

Progress owns event membership, players, linked pair saves, the signed credit ledger,
automatic turret purchases, control progress and match history. Game owns gameplay
truth and commits it through `photon.progress` v2. Initialization uses SQLite schema
5. Importing the module starts no resources. Every public reply carries a contract
name, integer version and ready/unavailable status.

## Events and linked games

Game Master creates/selects an event through Game's serialized `/api/event` facade.
Progress provides `event_snapshot`, `event_preview` and `event_command` (v2).
Commands carry `operation_id`, `action` and either `name` or `event_id`. Switching
requires an idle game and no reserved roster or active calibration. It clears both
selected players and the selected saved game. Names can repeat across events;
player IDs, wallets, upgrades, scores, history and saves cannot cross events.

`player_command(side,{action:create|select,event_id,...})` creates or selects an
event player. New profiles have zero credits, L1 Joint controls, T1 turrets and L1
force field. There are no built-in/test players, credit grants, manual purchases,
control downgrades or practice results. `is_test:false` is a compatibility field,
not a bypass. Missing or stale event IDs reject phone mutations.

`prepare_game`, `saved_game_preview` and `saved_game_command` manage linked saves.
New starts a fresh shared L1 journey and retains each player's event wallet and
turret tiers. Save records progress between matches, never battlefield physics.
Load atomically selects the saved Green/Purple pair, their control progress and
starting Atoms. Wallets/turret upgrades reference the event player, not copied
balances. Start locks both players; individual picker changes then fail until
New/Load. `bind_game_atoms` fixes one configured ArUco/weapon per team through L3;
L4 makes the other team Atom available. Bindings include camera/GM provenance.

## Match settlement and progression

`begin_attempt` freezes run/event/game IDs, both participants, control level,
loadouts, eligible turret tracks, price revision, reward schedule and core-rule
version. `reserve_roster` freezes IDs/revisions before Start.
`release_start_reservation({id})` returns `photon.progress` v2 and removes only
that unconsumed Start reservation. It never releases a calibration/lesson lock,
and rejects release while an attempt is running. Game calls it after a failed
begin and before retrying its own persisted Start; successful begin consumes the
reservation in the attempt transaction. `control_policy(side)`
returns the authoritative frozen level used by the existing relay. No selection
means no normal movement. Stop/release/watchdog paths remain independent.

`checkpoint_attempt` banks cumulative validated kill rewards. Each player receives
the shared match earnings once. `finalize_attempt` validates frozen class counts,
combat/purge counts and stack evidence, then records the score, earnings, upgrades,
credits and both players' progress in one SQLite transaction. Prices default to
T2 500, T3 1,000 and T4 1,500 for each turret. Score is never reduced by purchases.

After a normal win or overrun, buy consecutive affordable upgrades for eligible
tracks: the starting weapon through L3, both team weapons at L4. At L4 choose the
lower turret tier first, with the starting Atom breaking ties. Stop when that next
upgrade is unaffordable. Negative balances must be repaid before automatic buying.

Game Master End match produces `operator_ended`. Preserve actual score/earnings
and force exactly one next eligible turret tier for each player, deducting full
price even into debt. This replaces ordinary automatic purchases for that ending.
A fully upgraded eligible loadout incurs no charge. Unique ledger keys and the
terminal run receipt prevent concurrent/retried endings from charging twice.
Identical final results return their original receipt; conflicting finals reject.
Game's durable result outbox survives a restart and is replayed before recovery.

A center-stack win advances the shared control/force-field level once, capped L4.
Game enforces the 8–16 turret ring and opposing Atom stack, independent of kills.
Settlement accepts zero-kill stack wins and ignores any obsolete combat target
in an older attempt. Kill accounting and stack-health evidence remain validated.
Event peers must share the core-rule version; older results remain in team history.
A wave-clear win retains earnings but does not unlock the next controls.
Force-field capacity is 100/120/140/160% at L1/L2/L3/L4, without a purchase.
Entering L3 still requires the shared calibration lesson before normal movement.
`complete_lesson` validates the milestone and durable calibration receipt.

`advance_level({event_id,run_id})` is the GM between-match override. It only uses
the selected pair's latest finished match and advances both controls/fields once.
It cannot add an extra level after automatic advancement, invent score or buy a
second turret. `manual_advance` and assisted status remain in event history.

## Presentation, history and durability

The former store is read-only equipment (`photon.progress.shop` v1, `read_only`).
`latest_result` contains actual score, earnings, purchases, debt and level unlocks.
There are no timed shops. Game keeps the results screen until Continue, then runs
required calibration and readiness. `economy_snapshot/command` retains the existing
price-settings contract for four tracks/twelve prices, editable only while idle.
Each attempt freezes its catalog, so an edit cannot change an old match's charge.

`history_snapshot` supports player or combined, run-deduplicated event history,
tier/side/map/date/cohort filters and pagination. Manual endings, manual advances
and operator activations are labelled assisted and excluded from automatic balance
comparisons. Event scores remain visible. Legacy practice dataset filters no longer
select a second dataset. No global leaderboard mixes events.

Schema-5 backups include events, players, linked saves, matches, signed ledger,
operations and immutable catalogs. Import previews by default, checks references,
reward evidence and ledger balances, skips identical records and atomically rejects
conflicting records. Legacy global/practice saves cannot be imported. The approved
reset removes all old players and results; schema-4 migration only accepts an empty
reset database (including empty legacy built-ins), never silently erases live data.

No unfinished battlefield is saved. Thirty-second reward checkpoints may survive an
interrupted match; recovery records interruption without awarding a turret or control
level. A crash before a checkpoint can lose unbanked kills. Durable terminal results
are retried against their original event and pair, never the current selection.

Validation: `PYTHONPATH=tests .venv/bin/python -m unittest test_event_progression
 test_event_game test_mobile_calibration_safety test_relay_reconnect` and
`tests/event_progression_browser.cjs` (temporary data/fake arms, no physical motion).

## Level result statistics (2026-10-18)

`latest_result.statistics` adds version-1 team score comparisons, authoritative
kill attribution, the last 60 completed team results and actual turret/Atom unlocks.
Same team means an unordered pair of player IDs within an event, independent of
saved-game ID. The selected pair scopes the receipt. Missing historical individual
attribution is null, not zero. Reward attribution is cumulative, reconciles exactly
with team kills and survives the existing terminal outbox/backup path.

`event_results_snapshot(query)` is an additive `photon.progress` v2 owner-public
function. Its `results` descriptor is `photon.event-results` v1: event, metric,
total, rows and next_cursor. Query requires event_id, optional cursor (offset) and
limit (1–100). HTTP `/api/event-results` is Game Master only. It exposes completed
results for current/past event teams without wallets or unfinished battlefield.
No public scoreboard webpage exists yet. Definitions and integration details:
`docs/LEVEL_RESULTS_2026-10-18.md` in the repository root.

## Fresh names after Game Master Reset (2026-10-18)

Game uses the existing `event_command(select)` with the same active event after
confirmed arm stops and attempt settlement. This atomically clears sessions and
the active saved-game selection without deleting any records. An aborted match
banks validated earnings but neither purchases upgrades nor enters completed event
comparisons. Repeated finalization remains idempotent.

Selecting a player by name prepares that profile's L1 controls and force field,
clears its pending calibration and retains its wallet/turret upgrades and history.
This does not overwrite progression stored in an old linked save. `game_command`
with `load` bypasses fresh-name selection and restores that saved pair's controls,
force field and calibration milestone atomically. This prevents an old L3 lesson
from reopening when players choose names for a fresh game.


### Per-level heatmaps and replay saves (19 October 2026)

Terminal attempt evidence accepts optional `kill_heatmap` version 1. Cell counts
plus `unlocated` must reconcile exactly with the saved kill total; dimensions,
landmarks and numeric values are validated at settlement and backup import.
`latest_result.statistics.kill_heatmap` and history rows expose the frozen grid.
The validator is imported when the owner loads: the hub removes private helper
paths and cached modules after loading, so settlement must not defer that import.
Older records explicitly show unavailable location data, and real zero-kill runs
show an empty map. Both phone and LTZ Score result views render the same heatmap.

Saved-game actions `replay_level` and `replay_game` require the latest saved
terminal run for the active event and linked pair, including `interrupted` or
`aborted` runs. A running attempt is not eligible. They create a new saved campaign,
retaining the original campaign, earnings and purchase ledger. Their operation
receipts are idempotent. Replay-level restores controls/force field to the level
played; replay-game resets campaign controls to L1. Game owns player agreement,
physical stop checks and starting the next attempt.
