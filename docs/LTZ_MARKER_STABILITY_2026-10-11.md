# Atom buff and ArUco display stability — 2026-10-11

## Diagnosis

The first live trace contained 60 ready Board snapshots, stable visible IDs and
no camera errors. Frame age ranged from 108 to 461 ms, with approximately
210–287 ms between sampled frames. Occupancy expired after 350 ms, so normal
camera latency plus sampling delay could remove an otherwise established buff.

A separate player trace alternated between 20 ready and 15 partial cue maps.
Mobile discarded remembered fixed labels whenever the map became partial.
Game Master's label styling also followed each individual detection frame.
Those presentation decisions made short misses visible on both surfaces.
Camera identity remained stable in these traces. Size rejection was working;
its thresholds were preserved.

## Changes

- Board publishes a 900 ms occupancy grace. Both its snapshot reader and Game's
  validated consumer use that policy, avoiding contradictory expiration times.
  Legacy contracts retain 350 ms; invalid or excessive grace values fail closed.
- Three distinct frames still confirm cover/reveal. A confirmed reveal or
  displacement removes the buff immediately; a genuinely unavailable source
  does too. Short misses keep the existing visit, health and damage, without
  granting repeated healing. The existing continuous pulse and power-down
  animation follow this steadier gameplay state.
- Green, Purple and Game Master share a one-second display-only sighting cache.
  Expiry uses the original frame timestamp, so repeated snapshots cannot keep
  a missing marker alive. Camera changes, unavailable feeds and explicit
  geometry/size rejection clear this memory.
- Mobile retains non-quarantined fixed labels from fresh partial maps. Current
  corrected camera detections remain an independent display source. Display
  continuity does not authorize robot movement or supply gameplay evidence.

## Verification

80 focused Python checks passed:

```sh
PYTHONPATH=tests .venv/bin/python -m unittest test_atom_tower_buff test_laser_tag_y_camera test_laser_tag_y_markers test_camera_marker_alignment test_cue_targets test_ranged_delivery test_mobile_client_build
```

14 JavaScript checks and the buff renderer checks passed:

```sh
node --test tests/marker_presence.test.js tests/mobile_tracking_startup.test.js
node tests/atom_buff_renderer.cjs
```

The real client browser test exercised Green, Purple and Game Master against an
isolated fixture, alternating ready/partial maps and repeatedly dropping raw
detections. All three retained four labels across all 20 checked frames, with
zero JavaScript errors and zero control commands. Separate browser startup
checks passed for both teams. Test-only export imports are now scoped to avoid
leaking temporary module paths into subsequent tests.

```sh
PYTHONPATH=tests .venv/bin/python tests/mobile_ltz_fixture.py --port 56053
# In another shell with Playwright available:
node tests/marker_flicker_browser.cjs
```

Synthetic screenshots verify label continuity, not physical camera alignment.
Evidence is in `../../output/marker-flicker-2026-10-11/`.

## Live rollout

Reloaded the hub using its existing Python runtime after the match ended and
both arms were verified idle with pumps off. The camera resumed automatically.
All 35 post-reload snapshots were ready, with no errors, frame ages of 74–406 ms,
and the new 900 ms policy. Both served team bundles include the new helper.
Loaded the updated localhost Game Master and Green views and refreshed the
external game screen. The current shop remained available after restart.

The active match had ended before rollout, so a physical Atom hold/lift/return
cycle with a live turret was not observed afterward. Its timing, health/damage,
single-heal and reveal behavior passed deterministic regression tests. Remote
player devices should refresh once to ensure they load the new client bundle.
