# FPS optimization validation — 2026-09-05

The renderer now targets 60 FPS at every enemy count. Frame scheduling preserves
refresh deadlines, input redraws coalesce, and cosmetic detail responds to frame
cost. Stable geometry and presentation data are cached; small effect sprites,
Tesla halos and electric-enemy glows are pre-rendered into bounded caches. HUD
writes are diffed and controls rebuild only when their inputs change.

The existing SSE helper now optionally shares snapshot preparation/encoding and
sends compact dynamic updates between complete static-data snapshots. Photon
Level offers a validated metadata read so Game can reuse unchanged runtime
geometry. No enemy, Brute, wave, damage, collision or simulation rules changed.

## Ten-minute browser replay

Real Gamemaster and external-screen HTML, renderer and all 75 artwork assets
ran in isolated headless Chrome on the development machine. Synthetic state
updates at 10 Hz maintained 1,000 orcs and 16 towers, including 250 burning and
250 electrified orcs, Tesla chains, flamethrowers and machine-gun effects.
Measurement began after both views loaded and warmed up. The live game and
hardware were not used as test inputs.

| Metric | Gamemaster | External screen |
| --- | ---: | ---: |
| Median measured FPS | 60 | 60 |
| Lowest one-second sample | 44 | 42 |
| Samples at or below 30 FPS | 0 / 594 | 0 / 595 |
| 95th-percentile frame interval | 17.0 ms | 17.9 ms |
| 99th-percentile frame interval | 17.9 ms | 18.6 ms |
| Long main-thread tasks over 50 ms | 0 | 0 |
| Asset failures / JavaScript errors | 0 | 0 |

Typical final draw submission time was approximately 1.5–1.9 ms per display.
The active raster caches stayed at about 346 KB in this dense scene. Browser
draw/frame timing includes real Canvas work, but this is a synthetic replay,
not an end-to-end physical-board gameplay benchmark or a universal hardware
guarantee. Raw summary: `FPS_VALIDATION_2026-09-05.json`.

## Final renderer follow-up replays

The ten-minute run preceded the final continuous-burn and long-line halo
refinements. Separate 30-second replays on the completed renderer covered:

| Scenario, two displays | Median FPS | Lowest FPS | Samples at/below 30 |
| --- | ---: | ---: | ---: |
| 240 orcs, 16 towers, status effects and Tesla chains | 47 / 47 | 42 / 44 | 0 |
| 1,000 burning orcs, mortar explosions and repeated core purge | 60 / 60 | 45 / 44 | 0 |

Both completed without asset failures, JavaScript errors or long main-thread
tasks. Smaller-wave frame intervals reached p95 25.3 ms and p99 33.8 ms, just
outside the plan's secondary pacing targets; its measured FPS stayed above 30.
Peak-effect p95/p99 stayed below 19/33.3 ms. The smaller-wave test revealed the
cost of restoring per-bolt/per-field Canvas blur, so those large-area shadows
were replaced with layered strokes while cached enemy glows remain supported.

## Other checks

- The real scheduling code produced 60.0 FPS at synthetic 60 Hz and 120 Hz for
  0, 400, 800 and 1,000 enemies. Tests cover refresh jitter, long gaps, coalesced
  input, visibility changes, FPS accuracy and adaptive quality recovery.
- Shared-stream tests cover one preparation for multiple subscribers, full
  reconnect snapshots, dynamic updates, null clearing and heartbeat health
  rechecks. Level tests cover revision changes, artwork refresh, isolated
  descriptors, disabled producers and invalid integer-version contracts.
- The full 226-test suite passed before the final cached-glow extension;
  all 132 relevant Photon checks passed after that extension and the added tests.
- Offline medians over 40 reads: full Level runtime bundle 6.56 ms; cached
  runtime-status metadata 0.025 ms; Game's unchanged-level sync 0.13 ms.
- The synthetic 1,000-enemy payload was 284,407 bytes as compact full JSON and
  247,660 bytes as a dynamic update. Shared encoding also removes duplicate
  preparation for displays subscribing to the same format.
- Refreshing the user's existing display showed 58 FPS with the final renderer, versus 24–26 before
  refresh. The same paused wave 4, six enemies and core health remained intact.

## Activation

The refreshed Gamemaster display is using the renderer changes. Other open
game displays should be refreshed to load them. Python changes become active
on the next hub restart. The hub was not restarted during this work because its
current paused run is held in memory and restarting would reset it.

## Reproduce

From the repository root:

```sh
.venv/bin/python -m unittest discover -s tests -p 'test_photon*.py'
.venv/bin/python tests/photon_performance_fixture.py /tmp/photon-scene.json
node tests/photon_performance_renderer.cjs
node tests/photon_browser_performance.cjs /tmp/photon-scene.json 600 2
```

The optional browser replay uses an installed Playwright package (set NODE_PATH
to the package directory if needed) and the local Google Chrome executable.
These are test dependencies, not game dependencies. The replay only fulfills
requests from local repository files and fixture JSON; its mock EventSource
does not connect to the running game. JSON metrics and a screenshot are written
to `/tmp/photon-browser-performance.json` and the matching `.png`, overridable
with `PHOTON_PERF_OUTPUT`.
