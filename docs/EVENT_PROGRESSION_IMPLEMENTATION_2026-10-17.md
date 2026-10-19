# Event progression rollout — 17 October 2026

Implemented and activated on the local hub (port 8000). The authorized old player
base, saved games, scores, ledgers and legacy database backups are removed. The
new schema-5 store starts empty; Game Master must create/select an event before
players register. Physical calibration data and arm safety limits are retained.

## Player and operator flow

1. Create/select an event in Game Master. Register both players on their phones,
   or load a saved linked pair inside that event. New games start both at L1 Joint.
2. Place one Atom per side on a numbered playfield target. Its ArUco selects that
   player's starting weapon. Game Master can choose the configured code if Atom
   detection fails. Start locks the pair and Atom bindings.
3. Through L3, each player uses that Atom. Complete the ring, then stack opposing
   team Atoms to advance, independent of kill count. At L4 both team
   Atoms become available. Force fields follow game levels for free.
4. Normal completed matches automatically purchase affordable turret upgrades.
   Default T2/T3/T4 costs are 500/1,000/1,500. At L4 lower-tier eligible equipment
   is first, original Atom breaking ties. Score remains independent of spending.
5. Game Master End match preserves real score and earnings, forces one next turret
   tier per player, and charges full cost even into debt. It replaces the normal
   automatic purchase for that ending. Unlock next control level is the separate,
   once-per-finished-match control/force-field override. Manual Atom/core shortcuts
   remain, with server validation and recorded provenance.
6. Results show score, earnings, upgrades, balance/debt and level unlocks. Continue
   prepares the next match, with the existing required L3 calibration first.
   Save/Load restores progress and the linked players, never unfinished physics.

Practice gameplay, test profiles, credit grants, manual purchase buttons, timed
shops, arbitrary tier overrides and practice score datasets are removed. Independent
calibration setup and isolated engine development fixtures remain. L1/L2 can use
saved arm calibration with a different camera correction while physical guards remain
active. L3/L4 retain camera-based calibration checks. Reconnection tests cover fresh
feedback, enable acknowledgement, generation cancellation and both player adapters.

## Durability and scope

One SQLite transaction settles both players. A run has one terminal receipt and
unique purchase ledger keys. Four concurrent End requests produced one T2 purchase
per player (0 to −500 credits), and retries after restart returned that receipt.
A simulated failure during the second player's settlement rolled back both players,
all scores and all purchases. A failed arm stop prevented ending/charging.

A delayed durable result after event selection updates only its original event and
pair. Replayed manual advancement cannot skip another level. Cross-event players and
saves are rejected. Backup import verifies signed balances, reward evidence, eligible
tracks, purchase receipts and event/pair membership; old global/practice backups
are rejected. Test fixtures use temporary data and fake camera/relay owners.

## Balancing evidence

**Superseded on 18 October:** the approved ring-only rule removes the combat
objective at every level. The table below records the earlier rule, not current
completion times. Wave delays, enemy health, prices and stack bonuses are unchanged.
The current simulator stacks as soon as the ring completes; with the selected
300-second first-wave delay, a fast pair can finish before combat. Turret power
therefore cannot slow that particular route without a separate pacing adjustment.
New runs freeze core-rule version 2 so event peers use matching rules.

The baseline venue wave pacing dominated progress: with identical placement/aim,
T1 and T4 completion differed by only 3.5 seconds at L4. A combat objective plus
prices alone was insufficient. The one-time event preset rollout preserves the
old revisions and creates selectable Event progression revisions with enemy-health
factors 1/2/8/10 by game level, bounded by the existing setting limit. Subsequent
Game Master preset choices are preserved.

Synthetic eight-turret traces use one Machine Gun and one Mortar Atom, no occupancy
buff, nearest-enemy aiming every 2 seconds and destroyed-turret repair every 30 seconds.
Fast placement completes the ring at 55 seconds; the slower sequence at 160 seconds.
Both can finish before the existing first wave, so their eventual completion is
combat-limited rather than placement-limited. The combat target is 10/20/30/40% of
scheduled enemies, counting direct combat kills only.

| Level | T1 finish | T4 finish | T1 core health | T4 core health |
|---|---:|---:|---:|---:|
| L1 | 523.8 s | 523.4 s | 100% | 100% |
| L2 | 674.3 s | 673.2 s | 100% | 100% |
| L3 | 757.3 s | 744.4 s | 97.1% | 100% |
| L4 | 856.1 s | 828.3 s | 62.2% | 99.0% |

This demonstrates growing pressure from basic equipment at later levels, not a
prediction of human performance. All four starting weapon combinations, physical
movement speed and real aiming need venue playtesting. No skill-adaptive health or
hidden catch-up adjustment is applied during a match. The preset and reward rules
are frozen at Start. Assisted results stay visible in event history and are excluded
from automatic balance comparisons.

Reproduce: `.venv/bin/python tools/event_balance.py --output /tmp/event-balance.json`.
Evidence: `output/event-progression-2026-10-17/balance.json` (baseline),
`balance-event.json` (event presets), and the browser screenshots in that directory.

## Verification

- 99 selected Python regression tests passed: event persistence/settlement/API,
  preset migration, calibration safety, reconnection, Atom buffs, core stack,
  client assembly and module boundaries.
- 100 selected JavaScript tests passed: motion policy, turret selection continuity,
  cue start feedback and cue recovery. Deprecated practice behavior is superseded
  by the event tests; this was not a full historical-suite run.
- `tests/event_progression_browser.cjs` passed in Chrome: event creation, both
  landscape phones starting L1, pair lock, combat objective, forced upgrades/debt,
  manual L2 advance, Save/New/Load, score page and zero browser exceptions.
- Live hub readback: Game/Progress/both phone facades ready, idle lobby, no active
  match, zero old records, SQLite integrity OK, new catalog and event presets active.
- Arms remained disconnected. No physical movement or camera precision claim is
  made by the automated tests. Refresh Game Master and both phones before use.
