**Breaker archer — implementation and validation, 10 October 2026**

The approved feature is implemented in the workspace. Breakers can stop, draw and shoot at exposed towers before the core; powered rows and operational force fields block arrows. The new red bow/quiver artwork is shared by Y and landscape Mobile LTZ. Game Settings expose attack mode, range, draw, cadence, tower/core damage and arrow speed. Four named **Breaker archer candidate** presets are added on Game initialization, without replacing or selecting existing presets.

**Deployment status:** source implementation and isolated verification are complete. This task did not restart the production hub, change its selected presets or publish the hosted phone bundle. Keep production on its existing preset until the candidate's difficulty has been reviewed and an idle deployment is available. The initial 12-damage candidate is materially harder in the seeded comparison below; 1,000-enemy server performance also misses the target. This is not a balanced 1,000-orc release. The separate economy/shop/live-score plan remains pending implementation approval.

The implementation follows [the approved plan](LTZ_RANGED_BREAKER_IMPLEMENTATION_PLAN_2026-10-10.md). It keeps internal `breaker` IDs, 130 base HP, speed 50, existing wave/class proportions, rare brute replacement, three wins per tier, progression records and legacy hammer artwork.

**Gameplay and delivery**

- Stable exposed-tower targeting, companion aim points, core fallback, 110% retention range and fresh draws after retargeting. A newly exposed tower supersedes the core without resetting cooldown.
- Server-owned flights, damage once at impact, normal tower destruction/row reconciliation, no ranged-breaker contact damage. Existing installation identity prevents hits on a replacement; removed companion bodies also consume the old arrow without damaging the parent.
- Shields rechecked at acquisition, release and each traveled segment. A shield raised ahead intercepts; one raised behind does not. Arrow interception consumes no field contact-wear capacity.
- Death before release cancels; death after release leaves the flight. Pause freezes Game time; reset clears all state. Center double stacks neutralize arrows immediately and capture core health. Full survival waits for damaging flights; the last arrow can defeat. Harmless flights clear on victory.
- Per-class scheduled/released/combat-killed/purge-killed counts and bounded combat aggregates travel through the existing terminal logging pipeline. This supplies measured class data for future tuning; reconstructed historical counts were not written into old games.
- Y serves one revalidated bundle containing its owned archer helper. Game checks renderer capability before ranged starts. Mobile's compact projection now preserves combat poses; the asset allowlist and offline exporter include the same hashed atlas. Refresh existing Y/mobile pages when deploying.

**Verification**

205 Photon regression tests passed. The focused ranged/delivery/preset suite passes 31 tests, including legacy settings/preset migration, frozen runs, time-step cadence, shields during flight, replacement identity, companion health, movement holds/resume, death timing and terminal cases. Additional motion, Atom-buff, mobile export and JavaScript renderer checks passed. Module-isolation and whitespace checks passed. Missing-art tests deliberately emit their expected diagnostic.

Real Chromium pages used an isolated loopback Flask fixture with temporary data and fake hardware. Both Y views and landscape Mobile at 844×390 (Green) and 1180×820 (Purple) received archer poses and flights; all 89 assets loaded, no page errors or horizontal overflow. The 36-archer scene had frame-interval p95 of 16.8/17.3 ms for Y and 26.4/32.1 ms for phone/tablet emulation. [Recorded results](ranged-breaker-2026-10-10/landscape-and-y.json), [phone](ranged-breaker-2026-10-10/phone-landscape.png), [tablet](ranged-breaker-2026-10-10/tablet-landscape.png).

All eight poses were inspected in eight rotations: [pose/direction sheet](ranged-breaker-2026-10-10/poses-directions.png). The [original atlas](../sandboxes/gamemaster/prototypes/photon-level/assets/game-art/sprites/breaker-archer-v1/archer-atlas.png) is the unchanged transparent ImageGen output, 1774×887. The [provenance record](../sandboxes/gamemaster/prototypes/photon-level/assets/game-art/sprites/breaker-archer-v1/provenance.json) contains its exact prompt, reference, hash and pose order. Runtime Canvas slices cells; no Python image manipulation was used. Bow poses/facing and red accents are present; at whole-map phone scale sprites remain small, with the existing zoom available.

**Seeded balance comparison**

These are design traces, not human gaming logs: seed 42055, existing progression settings, no player/reward writes. Partial defense places four nearest-core L1 towers at 180/240/420/480 seconds. Full rows place sixteen L4 primaries, with twelve companions, every 15 seconds from 180 seconds. Both replenish every 120 seconds from 600 seconds. Early-stack runs accept the center stack at or after 650 seconds when the ring is ready. The comparison changes only breaker attack mode.

| Trace | Mode | Outcome / active seconds | Core HP | Kills / released | Peak alive | Towers destroyed |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| Tier 1, partial L1 | Melee | Win / 1408.3 | 8807.75 | 1009 / 1009 | 111 | 0 |
| Tier 1, partial L1 | Archer | Defeat / 1374.4 | 0 | 812 / 1009 | 209 | 2 |
| Tier 4, full L4 | Melee | Win / 1283.4 | 10000 | 1250 / 1250 | 154 | 0 |
| Tier 4, full L4 | Archer | Win / 1208.5 | 3429.24 | 1250 / 1250 | 262 | 17 |
| Tier 4, early stack | Melee | Win / 652.4 | 10000 | 291 / 291 | 66 | 0 |
| Tier 4, early stack | Archer | Win / 652.4 | 10000 | 291 / 291 | 95 | 4 |

The approved starting damage is substantially stronger in practice because archers can keep firing outside some weapon ranges. In the partial-defense archer case, 5,916 arrows were released, causing 6,809.5 tower damage and 9,135.5 core damage. Full L4 still survives, but the 17 tower destructions are a meaningful change. Earlier wins end exposure to later waves, as expected. Raw kills here are not a forecast of the pending weighted-credit economy. [Full comparison data](ranged-breaker-2026-10-10/balance.json).

For the next tuning experiment, keep the same traces and change one setting at a time: test core arrow damage 6 before lowering tower damage, then compare tower damage 8/12. These are proposed tests, not silently applied changes. Review outcomes by control tier and loadout using the new measured release/kill/shot/damage counters; distinguish combat kills from purge kills and compare center-stack and survival outcomes separately. Collect human runs before choosing a production revision. The proposed 2-credit breaker price, first-Cue equipment timing and 1,000-alive progression require the separate economy work and are not validated here.

**Dense-scene performance**

The synthetic engine fixture sustains 1,000 enemies and 28 defense bodies with large fixture-only health and fixed sampled positions. It compares the same 28% breaker mix in melee/ranged modes plus an all-archer stress case. It does not represent a naturally paced match or prove balance. 160 ticks at 50 ms were measured per case; full compact snapshots were serialized every second tick.

| Scene | Tick median / p95 / p99 | Ticks over 50 ms | Peak arrows | Largest full snapshot |
| --- | --- | ---: | ---: | ---: |
| Mixed melee | 52.6 / 73.4 / 120.3 ms | 100 / 160 | 0 | 596,938 bytes |
| Mixed archer | 50.0 / 74.3 / 120.3 ms | 79 / 160 | 179 | 668,499 bytes |
| All archers | 47.7 / 66.7 / 90.8 ms | 63 / 160 | 593 | 862,438 bytes |

Snapshot-build/encoding p95 was 30.6/32.1/21.9 ms respectively, separate from tick timings. Tick-only cumulative backlog peaked at 903/776/311 ms. The server does **not** reliably sustain 20 Hz in this dense fixture, including the melee baseline. Do not increase live pressure to 1,000 based on this result. [Engine measurements](ranged-breaker-2026-10-10/engine-performance.json).

Two simultaneous real Y pages replayed each ranged fixture at a synthetic 10 Hz for 30 seconds. Mixed-scene FPS was median 60 with minimum 45/43; all-archer FPS was median 60 with minimum 45/46. No sampled second fell to 30 FPS, no long tasks or asset errors occurred; frame p95 stayed under 20 ms. This validates local rendering, not physical phone hardware or real hosted-network snapshot gaps. [Mixed replay](ranged-breaker-2026-10-10/mixed-browser.json), [all-archer replay](ranged-breaker-2026-10-10/worst-browser.json).

Authoritative flights expire at fixed impact time; no damage is dropped to meet a rendering budget. Range/retention and minimum speed bound flight to 2.475 seconds, plus one tick of expiry latency; minimum first draw and 1,000 active enemies also bound replacement-shooter bursts. Hit flashes retain at most 128 server entries / 64 drawn sparks. No per-arrow disk writes were added. New maintained helper/test files remain below the 800-line warning threshold.

**Reproduction and rollout**

- Unit checks: `PYTHONPATH=tests .venv/bin/python -m unittest test_ranged_breakers test_ranged_delivery test_control_presets` and `.venv/bin/python -m unittest discover -s tests -p 'test_photon_*.py'`.
- Balance: `.venv/bin/python tools/ranged_breaker_balance.py /tmp/archer-balance.json`.
- Engine stress: `PYTHONPATH=tests .venv/bin/python tests/ranged_breaker_benchmark.py /tmp/archer`.
- Real pages: start `PYTHONPATH=tests .venv/bin/python tests/ranged_breaker_fixture.py`; run `tests/ranged_breaker_browser.cjs` with Node and Playwright available. The fixture defaults to loopback port 8129 and supports `--port`.
- Dense replay: `node tests/photon_browser_performance.cjs /tmp/archer-mix.json 30 2`, then the `-worst.json` fixture. Tests require local Chrome and Playwright; no new project dependencies were installed.
- At an idle rollout, reload the updated Game/Level/Y/Mobile API owners together, refresh both Y views and phones, then load **Breaker archer candidate** for the desired control tiers in Game Settings. Saving revisions applies at the next Start. Publish a newly exported hosted Mobile bundle before using ranged mode there. Existing selected melee revisions provide rollback.

Production selection, hosted publication, physical-device/network certification and the next balance revision are outstanding rollout work. No calibration, robot driver, player database or live match was modified for this implementation.
