# Photon game FPS optimization plan

Date: 2026-09-05

Objective: keep foreground gameplay consistently above 30 FPS on the intended machine and displays, including the supported 1,000-enemy load. Target 60 FPS to leave headroom. The scheduling, rendering-cache, effect-budget, UI and shared-SSE changes have been implemented. See FPS_VALIDATION_2026-09-05.md for measured results and activation notes. The findings below preserve the original baseline.

## Confirmed causes and observations

### The renderer explicitly limits FPS

The quality profiles in `sandboxes/gamemaster/prototypes/laser-tag-y/tower-defence-view.js:31` set these limits:

| Active enemies | Quality profile | Configured frame cap |
| --- | --- | --- |
| 0–399 | Full | 30 FPS |
| 400–799 | Reduced | 24 FPS |
| 800+ | Dense | 18 FPS |

These caps prevent the animation loop from meeting the requested target even when drawing is inexpensive. Immediate interaction redraws can add draw calls, but do not provide a reliable presentation cadence.

The loop at `tower-defence-view.js:2059` also discards scheduling remainder by assigning `lastGameRenderAt = now` whenever it draws. Threshold rounding and alignment with the display refresh can cause additional skipped frames.

A controlled Node benchmark exercised the actual renderer with mock Canvas operations and synthetic animation timestamps over ten seconds. Enemy counts selected the quality profiles; the enemy arrays were empty to isolate scheduling. Results measure scheduled draws, **not browser or GPU performance**:

| Synthetic display refresh | Full, cap 30 | Reduced, cap 24 | Dense, cap 18 |
| --- | --- | --- | --- |
| 60 Hz | 20.4 FPS | 20.0 FPS | 15.0 FPS |
| 120 Hz | 26.5 FPS | 20.1 FPS | 17.1 FPS |

This reproduces 15–17 FPS without expensive drawing. A read-only observation of the open game showed 20 FPS while paused with six orcs, which is consistent with a scheduling problem. It does not establish the cost of individual render passes. The live game was not resumed or reset.

### Additional costs identified in source

These are optimization candidates requiring a browser trace to rank:

- `renderGame`, line 1890, clears and redraws the 1696 × 960 gameplay canvas, including tower graphics, markers, overlays, health indicators and effects.
- Tesla idle charge, lightning and force fields repeatedly use gradients, layered strokes and `shadowBlur`. Electric enemies add multiple trail samples. Larger sprites also increase the area drawn, but the contribution of the recent size changes has not been measured.
- Tower lookups, projectile presentation data and some field geometry are rebuilt during rendering even when their inputs are unchanged.
- `laser-tag-y/index.html:87` updates many DOM properties and invokes `renderControls` for every incoming state. Most controls change less frequently than combat state.
- Quality selection follows enemy count rather than measured frame cost. A small number of expensive effects can therefore keep full detail despite missed frames.

Useful optimizations already exist: a separate cached map canvas, cached enemy animation/orientation sprites, tinted effect caching, marker keep-out caching and a simulation collision grid. Extend these selectively rather than rebuilding them. The data-flow dialog skips its render work while closed.

### Snapshot overhead

`photon-game/prototype.py:525` synchronizes the level and constructs a full public snapshot. `hub/live.py:74` constructs and serializes snapshots separately for each SSE subscriber. Full payloads contain level, artwork and settings data that usually have not changed. A changing server timestamp also prevents otherwise unchanged payloads from comparing equal.

The SSE interval of 0.25 seconds is a wake-up timeout, not a strict four-updates-per-second limit; change notifications can deliver more frequently. Rendering should remain independent of this update frequency.

An offline Python benchmark used an independent engine with 16 synthetic tower placements and 100, 500 or 1,000 cloned enemies. Twelve samples per size produced the following medians:

| Enemies | Compact engine snapshot | JSON encoding | Combined synthetic payload |
| --- | --- | --- | --- |
| 100 | 1.73 ms | 0.79 ms | 132 KB |
| 500 | 2.11 ms | 1.12 ms | 177 KB |
| 1,000 | 2.86 ms | 1.58 ms | 234 KB |

Level runtime bundle reads separately took 6.27 ms median. Level, presentation and configuration together contributed approximately 38 KB of unchanged data per synthetic snapshot. These are local synthetic measurements, not live network captures; they exclude some public fields and do not measure browser parsing or simulation stepping. They justify investigating repeated snapshot work without establishing it as the primary FPS cause.

## Implementation order

### 1. Establish a baseline and correct scheduling

Record frame intervals, actual draw duration, render-pass time, incoming snapshot frequency and size, DOM update time, and server step/snapshot time. Use an isolated repeatable virtual-play fixture so profiling does not disturb an active session. Capture a browser Performance trace on the intended machine.

Remove the 30/24/18 FPS caps from effect quality. Target 60 FPS and use requestAnimationFrame timestamps correctly. If throttling high-refresh displays, preserve the deadline/remainder and avoid catch-up rendering bursts. Coalesce interaction redraw requests into the next animation frame.

Keep the FPS display tied to completed playfield draws, counting at most one presented frame per animation callback. Reset sampling after visibility changes. If unchanged paused scenes stop rendering, show an explicit idle state.

Verify scheduling at synthetic 60 Hz and 120 Hz, with jitter and long gaps, and verify FPS reporting and lifecycle cleanup. This is the highest-confidence first change; removing caps alone does not prove the hardware can render every frame within budget.

### 2. Avoid rebuilding unchanged scene and interface data

Cache tower lookup maps, connections and clipped field geometry against the snapshot/layout inputs that actually change them. Reuse stable presentation data between state updates while continuing to interpolate motion each frame.

Move expensive stable marker/tower-base/text drawing into layers or cached images where profiling shows a gain. Invalidate explicitly on placement, orientation, health, selection, layout and art changes. Preserve native-resolution ArUco markers and their keep-out geometry. Keep the existing cached map layer.

Update DOM values only when changed. Refresh nonessential metrics at approximately 4–10 Hz and rebuild controls only when their inputs change. Aiming and placement feedback must remain immediate.

### 3. Fit visual effects to the measured frame budget

Profile Tesla charge, lightning, force fields, enemy trails, burn effects and text separately. Pre-render reusable glow sprites and scaled effect frames, bound caches, and prewarm common existing enemy sprite variants after asset loading if first-use stalls are visible.

Adapt cosmetic detail using recent render time with hysteresis: reduce glow passes, trail samples and bolt detail when over budget; restore detail gradually after sustained recovery. Consider a lower-resolution effects-only canvas if the trace shows fill or compositing cost. Preserve every enemy, readable combat cues and full-resolution markers.

Do not change enemy sizes, Brute ratios or stats, wave composition, damage, the enemy limit or authoritative simulation behavior to improve the FPS number.

### 4. Reduce repeated state preparation and transmission

Within the existing module contracts and SSE transport, prepare a snapshot once per relevant state revision and reuse serialization across subscribers. Separate revisioned level/art/settings data from frequently changing combat data, with a complete initial/reconnect snapshot and explicit updates when revisions change.

Avoid repeatedly deep-copying unchanged level bundles and rebuilding revision-dependent topology. Keep input-health checks and heartbeat behavior independent from large payload reconstruction. Disabled, malformed or stale inputs must still fail closed promptly; cached data must not conceal an unavailable module. Preserve module ownership and documented contract validation.

Measure the server step and collision solver before changing them. A spatial grid already exists. Any further spatial reuse must preserve collision, targeting and damage correctness. Increasing SSE frequency is not a rendering fix.

### 5. Escalate only if the measured bottleneck remains

After the earlier changes, repeat the same trace and stress scene. Consider a worker/OffscreenCanvas or a GPU sprite renderer only if the remaining measured cost warrants the extra architecture and dependencies. Make no broad rendering rewrite the prerequisite for fixing the known scheduling defect.

## Acceptance criteria

- On the intended machine and displays, after asset warm-up, run foreground virtual play for ten minutes with up to 1,000 enemies, 16 towers and representative simultaneous weapon, status, force-field and core effects.
- Test both the Gamemaster view alone and the Gamemaster plus external game display. Include 60 Hz and 120 Hz scheduling verification, resizing, selection, aiming, pause/resume, visibility changes and reconnects.
- Aim for 45–60 FPS under load, with **every foreground one-second gameplay sample above 30 FPS**. Also inspect frame pacing: target a 95th-percentile interval below 25 ms and a 99th-percentile interval below 33.3 ms, rather than accepting a high average with visible stalls.
- Track long main-thread tasks and heap/cache growth. Keep aiming feedback responsive and verify there is no accumulating queue of state updates.
- Confirm unchanged enemy appearance and gameplay, including Brute size, health, damage, first wave and 40-to-1 ratio. Run relevant renderer, simulation, module-isolation and SSE/reconnect checks for the changes made.

The target is an acceptance test on specified hardware, not a guarantee inferred from these synthetic benchmarks. GPU draw cost and live simulation cost remain to be profiled.

## Primary references

- [MDN: Optimizing canvas](https://developer.mozilla.org/en-US/docs/Web/API/Canvas_API/Tutorial/Optimizing_canvas) supports selective pre-rendering, caching scaled images, layered canvases and reducing expensive shadows and text drawing.
- [MDN: requestAnimationFrame](https://developer.mozilla.org/en-US/docs/Web/API/Window/requestAnimationFrame) explains display-refresh scheduling and timestamp-based animation.
- [Chrome DevTools: Performance reference](https://developer.chrome.com/docs/devtools/performance/reference) describes tracing and inspecting browser performance before and after a change.
