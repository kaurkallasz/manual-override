# Photon Progress

Photon Progress owns the SQLite player store, profile selection, credit ledger,
upgrade purchases, control mastery and historical results. Game decides results;
Progress commits them. Nothing is initialized on import. `hub_init` opens and
checks the database; `hub_stop` releases the store. No sibling files are read.

## Contract: photon.progress v1

All public replies carry `contract`, integer `version`, and `status`.

- `progress_snapshot({side?})`: revision, simple profile list, full selected
  profile, internal roster and active attempts. HTTP strips the other side's
  balances/loadouts. This is a venue profile picker, not personal accounts.
- `begin_attempt({run_id, reward_enabled, metadata, expected_roster?})`: freezes
  selected profiles, tiers, names and loadouts in one transaction. A scored run
  requires at least one player; a profile cannot join two concurrent attempts.
- `checkpoint_attempt({run_id, sequence, kills})`: applies only the cumulative
  kill delta. Each registered co-op profile receives one credit per kill.
- `finalize_attempt({...checkpoint, outcome, active_seconds, finished_at,
  released_orcs})`: atomically records the result, credits, mastery and unlocks.
  Repeated identical results are harmless; conflicting results are rejected.
- `recover_attempts()`: marks unfinished attempts interrupted using banked kills.
  Game must replay its terminal-result outbox before calling this function.
- `control_policy(side)`: active scored run, frozen tier and run ID. An absent
  participant gets tier zero during scored play. The existing relay checks this
  contract before movement. Stop, release and watchdog behavior are independent.
- `history_snapshot({player_id, dataset?, tier?, level?, from?, to?, cohort?,
  cursor?, limit?})`: paginated results, cohorts and aggregates. Limit is at most
  100. Dates are Unix seconds. Practice and scored results are separate.

These server functions are not player HTTP mutation endpoints. Player routes
are `/api/state`, `/api/events`, `/api/history`, and POST `/api/player` (create,
select, control, purchase). Requests require their own Green/Purple side or
Gamemaster. Purchases/control changes bind to the selected profile, require its
revision and an operation ID, and are prohibited during an active attempt.

## Rules and durability

A confirmed kill in a scored attempt is one credit and one lifetime-score point.
Purchases reduce available credits only. Defeats, resets and interrupted runs
retain banked kills but grant no completion. Practice grants neither currency
nor mastery. Three nonconsecutive wins at a tier unlock the next tier for free;
three wins at each of the four tiers complete mastery. Lower-tier replays do not
advance higher-tier counters.

Machine Gun, Flamethrower, Mortar and Tesla Coil cost 250/500/750 credits for
levels 2/3/4; each level adds 10% base damage and health. Force Field costs
1000/2000/3000 for +20%/+40%/+60% capacity. Purchases are sequential. The canonical
Tesla track is `damage-tesla-coil`; explicit backup imports normalize the legacy
`damage-photon` key, including frozen loadouts. Browser mock credits are never
silently imported.

`data/progress.sqlite3` uses SQLite transactions, foreign keys, unique IDs,
serialized writes and a versioned schema. Game writes checkpoints every 30
seconds away from its simulation tick. A terminal result is atomically written
to Game's `data/pending-result.json`, delivered, then acknowledged by removal.
A hard process crash can lose kills since the last checkpoint if no terminal
result was written. In-flight physics is not resumed after a restart.

Gamemaster GET `/api/backup` exports a versioned JSON backup; POST previews by
default and imports only with `preview:false`. Finish active games first. IDs
with identical contents are skipped; conflicting IDs reject the entire import.
Structural validation, foreign keys, participant membership and ledger balances
are checked, including during preview. A pre-import snapshot is atomically
saved before import. The selected side is not included in a portable backup.

## History comparisons

A cohort includes level/revision, effective settings, scoring version, selected
control tiers, team composition and both upgrade loadouts. Labels and player
names are retained in history; no ranking claims individual kill contribution.
A recent improvement compares the first three and last three matching results
only after six nonoverlapping results exist. Time improvement uses successful
runs and treats lower time as better. Interrupted times are unknown. The client
shows actual points, a three-result mean, unlock markers, and an accessible
results table directly below upgrades in each team's LTZ Score tab.

Smoke tests: `tests/test_photon_progress.py`, `tests/test_ltz_integration.py`,
`tests/ltz_control_ui.cjs`, and the isolated `tests/ltz_browser*` fixture.
