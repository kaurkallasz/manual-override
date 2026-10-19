# LTZ rendering and player performance — 2026-10-11

The changes reduce rendering, video and UI overhead without changing simulation
rules, arm feedback cadence, control ownership or safety freshness limits.

## Findings and fixes

- Live Mobile LTZ delivery was about 1.3 MB/s across its parent and controller
  streams. `mobile_progress.shop.server_time` changed on every update but progress
  was classified as static, forcing complete snapshots. Progress now remains in
  incremental updates. In the captured scene, a packet drops from 133,809 to
  95,311 bytes before the SSE envelope (29%); reconnects and map changes still
  send complete state. Profile/tier changes continue to arrive immediately.
- The main camera supplied 3840×2160 JPEGs. The camera owner now prepares one
  shared, aspect-preserving preview of at most 1920×1080 for Mobile LTZ. Full
  camera/tracking resolution and normalized calibration stay unchanged. The
  player's stable canvas also bounds unexpected larger frames. MCAM1 remains
  at half its original resolution and optional when unavailable.
- MCAM1 layout now follows viewport/panel/log changes instead of measuring the
  page twice per JPEG. Hidden joint illustrations skip presentation work, and
  the hidden controller no longer mounts a duplicate illustration.
- Enemy/effect rasters now draw at integral pixel positions. Cached unrotated
  effects avoid repeated scaling and transforms. Dense rendering omits redundant
  electric afterimages while retaining shake, brightness and damage cues.
- Stable row barriers reuse a bounded canvas raster. Break flashes animate live;
  topology, marker geometry and power/count changes invalidate the cache.

## Measurements

Chrome headless on this host, isolated replay, 4× CPU slowdown. These are measured
one-second FPS samples, not a guarantee for every device or every individual frame.

| Replay | Before: minimum / median / maximum | After: minimum / median / maximum |
| --- | --- | --- |
| Main display: 1,000 enemies, 16 towers, active combat effects | 27 / 30 / 31 | 32 / 36 / 38 |
| Player: captured scene, main camera and MCAM1, 1180×820 at DPR 2 | 31 / 39 / 45 | 39 / 53 / 57 |

Main baseline ran 15 seconds; final verification ran 30 seconds with 29 FPS
samples, no sample below 30, all 89 art assets loaded, and no JavaScript errors.
The player replay ran 12 seconds per measurement. Its arm was an unavailable
fake controller, and its synthetic SSE continued sending full snapshots; it does
not measure live connected-arm or Wi-Fi performance. Camera decoding and both
player/control pages were active. No real robot commands were issued.

Reproduce the main stress replay:

```sh
.venv/bin/python tests/photon_performance_fixture.py /tmp/photon-stress.json 1000
PHOTON_PERF_CPU=4 node tests/photon_browser_performance.cjs /tmp/photon-stress.json 30 1
```

The browser harness requires Playwright on `NODE_PATH` and installed Chrome.
It serves repository assets with mocked authoritative input and does not contact
the live hub. A fourth positional argument can select a saved renderer baseline.

## Validation and activation

108 mobile Python tests, 22 camera contract/alignment tests, and seven performance
tests pass. JavaScript checks cover cadence/interpolation, joint controls,
trajectory safety, turret continuity, arm bridge, buffs and ranged rendering.
The MCAM1 browser check passes for both teams, all control modes and six viewport
sizes, including missing/stale/error recovery. The turret browser check exercises
native aiming through tracking gaps and verifies that reduced preview dimensions
do not change calibrated coordinates.

Restart the hub and refresh the game/player pages to activate the backend and
frozen player bundles. The running hub was not restarted during this work.
