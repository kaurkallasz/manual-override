# LTZ score integration and horde implementation

Implemented in the workspace. The new economy API and score contract are already visible in the running hub, which was in setup/lobby at the final read-only check. The final tuned candidate revision is in source and needs a normal hub restart: the live process still has the earlier, unversioned candidate helpers loaded. Existing `Breaker archer candidate` selections remain on all four tiers, and the active migrated catalog remains 12,000 credits. No new candidate or price catalog was selected on the live venue by this task.

## Delivered

- One shared illustrated shop and saved receipt for Green/Purple Score and Mobile LTZ; all 15 sequential upgrade cards use server quotes, actual purchase receipts and the shared 30-second deadline.
- Landscape phone/tablet layouts, automatic saved-result opening, explicit saving state, practice with zero banked reward, and calibration controls retained above a compact result.
- Live weighted-score feedback on both Y views and mobile: merged count-up bursts, brute accent, stale/duplicate rejection, reconnect baseline, reduced motion and saved-only bonus feedback. Wallet and raw kills remain distinct.
- Game Master settings expose all 15 prices and the optional 7,800-credit draft. Price changes stage during games, reservations, calibration or open shops; each shop binds its catalog. Existing prices and historical purchases are preserved.
- Frozen class values (defaults 1/1/2/10), exact scheduled value including brute replacements, health-scaled capped stack bonus, survival wins and the unchanged three-wins-per-control-tier progression. Both players receive their full shared reward once.
- Schema 3 migration, wallet/raw-kill/weighted/bonus reconciliation, backups, restart recovery, durable shop binding and quoted idempotent purchases.
- Exact next-match previews from selected presets; operator Ready/loadout summary; one shared local/hosted/export client assembly with published artwork and connection-log helper.
- Read-only offline balance reporting from explicit Progress exports, with separate cohorts, shared-run deduplication, practice exclusion, wallet snapshots, purchase receipts and unknown historical measurements left unknown.

## Actual combat reference traces

These use the actual engine and current map, seed 42055, finite schedules and normal enemy HP. They are synthetic placement/aiming assumptions, not human playtests. Deploy sixteen primaries from 180–405 seconds; reset destroyed pods every 120 seconds from 600. Aim surviving weapons at nearby enemies every two seconds from 650, or perform an allowed early double stack at 480.

| Tier | Scheduled orcs | Peak living | Outcome | Active seconds | Full-clear credits/player |
| --- | ---: | ---: | --- | ---: | ---: |
| Joint | 1,193 | 106 | Waves cleared | 1,377.1 | 1,694 |
| XYZ | 1,239 | 350 | Waves cleared | 679.3 | 1,770 |
| Targeting | 1,330 | 650 | Waves cleared | 610.7 | 1,893 |
| Cue | 4,092 | 1,000 | Waves cleared | 676.15 | 5,905 |

Cue reached 1,000 with all sixteen primaries and twelve companions alive. It remained at 900+ for 186.8 consecutive seconds and at the cap for 133.45 seconds. Its deferred bank reached 2,000. All 4,092 scheduled orcs were eventually released and killed; none remained or were dropped. Final center health was 82.6%.

The early Cue stack won at 482.5 seconds with 100% center health. It killed/purged 1,685 released orcs for 2,473 kill credits and earned a 1,181 bonus, totaling **3,654** per player versus survival's **5,905**. Unreleased waves were intentionally forgone by this victory. The bonus uses `min(floor(V × .2 × H²), floor((V−C) × .5))`, with H captured before detonation and C including purge kills. No minimum-wave or time gate was added.

Three full-clear wins in each earlier tier provide 16,071 credits before Cue under this candidate. That is a reference ceiling from these schedules, not a promise for early-stack play or human outcomes. The catalog candidate totals 7,800; old catalog total 12,000 remains unchanged until explicitly edited.

Lower-tier counts were raised modestly from the earlier archer baseline because the full-deployment reference initially peaked at only 82–90 enemies. Faster overlapping XYZ/Targeting waves needed lower enemy damage to remain winnable. These values are provisional human-balance candidates.

## Verification and remaining release gate

- 256 Python checks passed across economy, recovery, backups, journeys, presets, team/API isolation, framework, ranged combat, rows, core stacks, companions, brutes and delivery performance contracts.
- JS syntax checks and cumulative-feedback regression checks passed. Green/Purple calibration completion browser checks passed.
- Real browser checks passed at 667×320, 844×390, 1024×768 and 1180×820, plus both Score pages and both Y pages. All fifteen cards, receipts and actual purchases worked; no JavaScript errors, missing shop images or horizontal document overflow. A detected small-phone image/button overlap was fixed.
- Four simultaneous browser views loaded every asset and rendered all 1,000 enemies and 28 defense bodies. They averaged approximately 19 FPS in the final 15-second replay, below the requested >30 FPS. Render command submission was around 2 ms/view; host/compositor contention is a possible factor, not a demonstrated sole cause.
- Final 1,000-enemy synthetic engine benchmark: mixed ranged p95 62.27 ms (50 ms budget), all-archer p95 47.18 ms, with transient backlog peaks of 188.73/65.04 ms. The full gameplay trace also exceeded the dense-tick budget. Contact-neighborhood reuse and arrow blocker bounding-box rejection preserve the combat behavior but do not qualify the whole performance target.

**Horde performance qualification and supervised human balancing remain open.** The separate named candidate and preserved active selections prevent presenting this as a qualified venue default. No robot movement, calibration operation or active-match reset was performed by the validation tools. Browser/combat fixtures used temporary stores and no connected hardware. Live checks were read-only. Hosted bundle assembly was validated; a new hosting upload was not performed.

## Use and reproduce

After a normal hub restart, the operator can select **LTZ score and horde candidate** (candidate revision 1) independently for each tier through Photon Game's saved preset controls. Older revisions stay selectable. Upgrade prices are a separate editor; **Load 7,800-credit candidate** only populates its draft, and **Save upgrade prices** commits/stages it. Do not treat the horde as performance-qualified yet.

```sh
PYTHONPATH=tests .venv/bin/python tools/ltz_horde_balance.py --output /tmp/ltz-all-tiers.json
PYTHONPATH=tests .venv/bin/python tools/ltz_horde_balance.py --tiers 4 --stack --output /tmp/ltz-early-stack.json
.venv/bin/python tools/ltz_balance_report.py exported-progress.json --output /tmp/ltz-balance.json
PYTHONPATH=tests .venv/bin/python tests/ltz_score_fixture.py --port 8132
```

The browser checks are `tests/ltz_score_browser.cjs`, `tests/ltz_horde_browser.cjs` and `tests/mobile_journey_render_browser.cjs` using the installed Playwright/Chrome runtime. The horde browser replay consumes the captured `docs/ltz-score-horde-2026-10-10/cue-1000-frame.json`. Evidence JSON and selected screenshots are in that same folder.

For human tuning, collect at least ten wins per victory method within a matching map/preset/settings/tier/loadout/reward/catalog cohort. Compare credits per active minute, center health at accepted stack, wallet at next tier, purchase order and actual horde peaks. Change one candidate parameter at a time, rerun the reference traces, then repeat the supervised cohort. Never backfill unknown class kills or health into older logs.
