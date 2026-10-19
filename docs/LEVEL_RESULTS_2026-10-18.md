# Level results and future event scoreboard data

Implemented on 18 October 2026 in both phone clients and both LTZ Score pages.
The projected Laser Tag Y playfield stays visible at level end without a statistics
overlay; results are presented on the player screens. A completed level celebrates the level just
played; overruns and Game Master endings retain their actual outcome. Continue
belongs to the existing journey: after both players press Continue / Ready, the
next attempt starts automatically with the shared five-second countdown. Required
calibration completes first. Blocked starts expose a retry on the player screens.

Game Master Reset returns both phones to fresh name selection within the current
event. It clears pending Continue acknowledgements and calibration, preserves
completed results and saved player progress, and abandons an unfinished battlefield
without adding it to the event comparisons. Loading a saved pair remains available.

The saved result counts up total Orcs killed, the viewing player's kills, their
partner's kills, and shared team kills. Direct fire, Tesla chains, mortar impacts,
companions and flame burns credit the owner of the lethal damage. A launched shell
keeps its original owner even if its turret disappears. Force fields and core purge
are shared. Every kill is counted once. Historical results without attribution show
unknown individual counts rather than fabricated zeroes. Earnings remain co-op:
each player's wallet receives the full team earnings under the existing rules.

Performance means weighted kill score, excluding stack bonus, spending and debt.
The previous-game comparison uses the immediately preceding completed result for
the same unordered player pair in the same event. The average excludes the current
game and includes all previous completed games for that pair, across levels. The
graph labels levels and assisted games; it is a score history, not a normalized
skill rating. Different levels and difficulty can change score opportunities.

Other-team comparisons require identical level, map revision, frozen settings,
reward rules, enemy schedule and combat/companion policies. Different upgrades are
allowed because earned equipment is part of progression. Each eligible other team
contributes its average, with equal weight per team. The displayed position compares
this score against those team averages; ties share a position. Assisted games keep
their scores and personal history but do not enter this event comparison. Missing
history and zero baselines are explicit and never produce an invented percentage.

Comparisons are frozen with the result in the same SQLite transaction as earnings
and upgrade purchases. Terminal retries return that same receipt. No history entry,
charge or unlock is duplicated. Team identity is independent of phone colour or save
ID. Switching partners selects that pair's result rather than the old partner's.

The graph draws in, purchased turret artwork reveals with its actual tier and cost,
and L4 also reveals the newly available second Atom/turret. Offscreen graph/unlock
animations wait for visibility. Repeated SSE/render updates retain their timeline.
Replay is optional, and reduced-motion mode shows final values immediately.

L3 end-screen repair: T1 artwork for the second Atom is now included in the
level owner's versioned asset manifest. The files existed, but the mobile asset
route correctly rejected them while they were absent from that publication.
The journey reveal observes one HTML plot container instead of individual SVG
shapes. Saved dots and lines remain visible even if no observer callback arrives;
animation, replay and replacement DOM share the chart's timeline. This is a
presentation fix; stored matches and comparisons are unchanged.

## Data interface prepared, no online scoreboard page

Photon Progress still owns all persistence. `photon.progress` v2 adds
`event_results_snapshot({event_id, cursor?, limit?})`, returning a `results` object
with contract `photon.event-results`, integer version `1`. The read-only HTTP route
is `GET /s/gamemaster/p/photon-progress/api/event-results?event_id=...`; it requires
the Game Master role. No public website or publishing integration was created.

The descriptor includes event ID/name, metric, total, rows and next_cursor. Each
row contains run/event/team IDs, finished timestamp, level, actual outcome, assisted
flag, player IDs/names/colours at the time, score, total kills, per-colour/shared/
unknown attribution, active time, turret purchases, newly available Atoms, control
unlocks and comparisons at finish. A future consumer can page all results for
current or previous teams/events. It must respect assisted flags when ranking.
Limits are 1–100 rows; the local celebration graph shows the latest 60 for its pair.

The interface excludes running, aborted and interrupted games and contains no
battlefield, arm calibration or wallet balance. It does not resume unfinished
matches. Stored reward evidence and comparison snapshots are additive schema-5
fields included in existing backups; no player data reset or schema wipe is needed.

## Verification

- Python: attribution for all four weapons, delayed shell after turret removal,
  burn and core purge, shared fields, result idempotency, saved averages and peer
  weighting, L4 Atom unlocks, pair/event isolation, export/import and private API.
- Existing event progression, physical-motion safety, relay reconnect, core stack,
  turret damage and module-contract regressions.
- `tests/level_results_browser.cjs`: real temporary Game/Progress server with fake
  hardware; both phone perspectives, landscape and portrait layouts, increasing
  counters, comparisons, scroll-triggered unlocks, projector without a results
  overlay, reduced motion, and both Continue buttons starting the next level with
  no Game Master input, plus GM Reset returning both phones to editable name
  selection with cleared drafts/scroll position and retained event results.
  No browser exceptions. Demo screenshots are in
  `output/level-results-2026-10-18/`.
- `tests/level_result_art_browser.cjs`: L3 second-Atom T1 images and the reported
  seven-game score shape, including zero scores, first-game history, assisted
  markers, replay, DOM replacement, reduced motion and observers that skip SVG
  or never deliver a callback. Landscape, portrait and desktop screenshots are
  saved alongside the other previews. `test_photon_asset_publication` verifies
  all four T1 images through the actual mobile asset route and versioned manifest.

Run the focused Python tests with `PYTHONPATH=tests .venv/bin/python -m unittest
test_level_results -q`. Browser test uses the existing Playwright runtime and
Chrome. Its fixture data is temporary and never enters the live event database.
