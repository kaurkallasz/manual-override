# Wave timeline — 2026-10-11

Added the timeline at the external playfield's top center, opposite match
credits, using the same reading orientation. Game Master mirrors it above
the camera/playfield so camera alignment and marker hit areas are preserved.

Game publishes a read-only `photon.wave-timeline` v1 projection. Setup uses
the saved map/tier preset. During a match, actual launch/completion clocks
and live practice retiming determine the bars. The playhead uses simulation
time, pauses with the match and freezes on stale/disconnected running feeds.
Amber outlines mark upcoming windows, orange windows are spawning and muted
green windows are released.
The display labels durations, preparation, next-wave countdown and deferred
orcs. Wave duration means release time; killing the last orcs can take longer.

Validation:

- 69 Python tests: timeline, practice intensity, presets, framework parity,
  ranged delivery and camera routing.
- 4 JavaScript tests: overlap lanes, clock interpolation, pause/disconnect,
  setup/reset, terminal state, stale snapshots and idle-feed labeling.
- Real external and Game Master pages on the isolated fixture at 1920×1080
  and 1366×768: no page errors; timeline bounds, wave counts, movement,
  paused/disconnected clocks and calibration hiding verified.
- Visual screenshots confirm duration labels and no coverage of the current
  map's ArUco markers. Evidence is in the workspace output directory
  `output/wave-timeline-2026-10-11/` (outside this repository).
- Reloaded the live hub only after verifying setup and disconnected arms;
  the camera is ready, timeline contract is ready and both new assets return
  HTTP 200. Refreshed the live projector and Game Master views. No live match
  was started for testing.

Run the browser test with `tests/ltz_admin_fixture.py --port 56055` and
`node tests/wave_timeline_browser.cjs`; its guard rejects the live hub port.

## Retro presentation update

The meter now uses Photon Board's tag-consideration palette and square pixel
track. Elapsed time fills continuously and remains solid behind the stepped
playhead, including between waves. The green fill blends toward orange during
the final 30 seconds before the next release, stays orange while any wave is
spawning, and returns green outside releases/warnings. Game-screen score labels,
totals and bursts are doubled to 22/40/24 px. Compact player HUDs retain their
existing sizes.

Verified with seven JavaScript timeline checks, three Python timeline tests,
and both real game pages at 1920×1080 and 1366×768 on the isolated fixture.
Browser checks cover computed score sizes, green/warning/orange/green fills,
continuous progress width, pause/disconnect, calibration hiding and bounds;
all four page/viewport combinations had no JavaScript errors. Screenshots and
results are in `output/retro-timeline-2026-10-11/` in the parent workspace.

## Single-bar layout — 2026-10-12

Removed the surrounding panel, separate wave boxes, heading and axis labels.
The track and fill are four times thicker (48/32 SVG units), with the bottom
aligned to the former wave-box bottom. Wave windows are small marks on the
bar edges. The current wave, next-wave countdown and clock all sit inside the
bar at the same 22 CSS pixels as the kill-count label, independent of SVG scaling.
The green/orange timing and solid elapsed fill are unchanged. Full wave-window
details and queued-enemy information remain available in the accessible SVG
description and per-window titles.

Seven JavaScript checks and the four page/viewport browser cases passed. The
browser verified all labels remain inside the track, use 22px type and do not
clip; the existing color, progress and pause checks also passed. Refreshed the
live game display and confirmed the new geometry and font sizes without a hub
restart. Screenshots and results are in
`output/single-bar-timeline-2026-10-12/` in the parent workspace.

The bottom game counter now uses the same square green frame, pixel track,
outlined monospace type and uppercase labels. Existing 40/22/24px score sizes
and feedback behavior are preserved; an empty burst no longer reserves space.
The four existing browser cases passed and the refreshed live display was
visually checked. Evidence: `output/retro-kill-counter-2026-10-12/` in the parent
workspace.
