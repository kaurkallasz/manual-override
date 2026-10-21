# MCAM1 Depth

Gamemaster tab at `/s/gamemaster/p/mcam1-depth/` (dashboard `#mcam1-depth`).
The default view estimates relative depth from MCAM1 video in the browser,
without lens calibration, mount measurements, an arm connection, or selected
regions. Measured MG400 travel can subsequently provide approximate distance
scale. It does not open a camera, change camera settings, connect an arm, move it, or operate its
pump. Start MCAM1's preview and use the existing arm controls separately.

The Atom is **31.5 mm high with a 20 × 20 mm base**. Clearance is the minimum
signed distance from its four bottom corners to the observed playfield plane,
assuming an upright Atom centred under the suction contact. The value is named
**Clearance if Atom is held upright**: attachment, tilt and suction compression
are not silently assumed to have been measured.

## Setup

Start preview in MCAM1, then open this tab. Analysis starts automatically. The
first visit downloads a pinned Depth Anything V2 Small model and browser runtime
from Hugging Face/jsDelivr; subsequent visits use the browser cache. Video stays
in a local browser worker. Loading progress, model failures and a retry button
are visible. WebGPU is preferred, with a CPU/WASM fallback. One inference runs
at a time, with no accumulating frame queue. Closing the page releases it;
hidden/live-camera views do not schedule more inference.

Warm bricks mean nearer and blue bricks mean farther. Before usable motion
evidence, these are **AI relative-depth predictions**, not measured distances;
the UI hides millimetre controls and shows a relative label. Brightness is never
used as a substitute for depth. A flat/invalid prediction yields no range.

For automatic motion refinement, select the arm carrying MCAM1 and connect it
through its existing relay controls. Move with a rigid camera mount and steady
tool orientation; roughly 10–40 mm of sideways travel with visible textured
stationary objects works best. The camera's translation direction is recovered
from video; measured TCP travel supplies scale. This path needs no lens or mount
setup. The nominal lens and host frame timing still make its distances
approximate. Repeated observations of the same features are combined into a
motion depth map. The page shows **Collecting viewpoints**, then **Motion refined**
when at least eight features agree across three or more viewpoints. The refined
map takes priority over AI predictions, including for a flat screen that cannot
constrain the AI scale. **Motion measurements** shows the measured samples from
the first usable pair. Without usable motion samples, the default view remains
an explicitly relative AI estimate.

The motion window shows the actual server rejection reason and measured travel
from recent feedback over the last four seconds. If the mount is still the
placeholder, leave **I measured the mounting offsets and orientation** unchecked
so camera direction is recovered from the images. A checked confirmation selects
the configured mount geometry, which must match the physical camera angle.

The following precision setup is **optional for the colored depth view**, but
required to express an observed plane and Atom clearance in robot coordinates:

1. Select Green or Purple and save any changes to the selected arm.
2. Measure the camera lens centre offset and suction contact offset from the
   TCP. Enter the camera orientation at tool R = 0°. Camera axes are image
   right, image down, and optical forward. The camera-to-mount matrix is
   `Rz(yaw) Ry(pitch) Rx(roll)`. A downward camera with image-right along robot
   +X has roll 180°, pitch 0°, yaw 0°. The initial `[0,0,80]` camera offset is
   **only a placeholder**. Confirm the mount after measuring it. Select whether
   the camera turns with tool R; a fixed wrist mount uses fixed base directions.
3. Select a screen region containing stationary, textured references on the
   **physical contact surface**. Exclude reflections and animated screen content.
   Display pixels underneath glass produce an optical plane rather than the
   contact plane. Select an Atom region containing its visible body, excluding
   the suction head. Drag on the preview or enter normalized rectangles in
   Precise region selection. Save setup. The screen region is required for Atom
   clearance; scene depth can run without it or mount confirmation.
4. For a calibrated lens, print `checkerboard.svg` at 100% and check its 10 mm
   squares with a ruler. Capture at least 10 sharp views at varied positions,
   distances and tilts, then solve. The default board has 9 × 6 inner corners.
   The solve rejects high reprojection error and insufficient tilt diversity.
   Changing capture resolution requires recalibration. Keep focus, image flips,
   sensor crop and lens mounting unchanged. Nominal 85° FOV is available for an
   explicitly approximate prototype and ignores distortion.
5. Measure frame delivery delay and uncertainty. The current MCAM1 contract's
   `captured_at` is a host receipt timestamp, not a sensor exposure timestamp.
   This module subtracts the configured delay and interpolates bracketed arm
   feedback. The timing confirmation checkbox documents an operator measurement;
   it does not turn the existing source into hardware exposure timestamps.
6. Move through the normal arm controls with 10–40 mm of mostly
   translational travel, retaining the same surface features in view. Analysis
   can be paused even while setup has unsaved changes. **Depth bricks** shows
   scene predictions or measured samples as raised-looking tiles: warm colors
   are near, blue is far, and empty cells are unknown. Set the near/far range in
   millimetres or use **Fit colors to scene** when a distance scale is available.
   Brick size changes display resolution only.
   **Bricks over camera** adds the matching camera image underneath. Point at a
   brick to read its distance and supporting viewpoint count. The camera
   reference uses the same frame. The refinement summary reports combined
   features, viewpoints and conflicting observations rejected in that frame.

## Processing and validity

- The browser uses [Depth Anything V2 Small](https://huggingface.co/onnx-community/depth-anything-v2-small)
  revision `4472b7362082ad9968fee890ca0f1e5aca36b93d` through Transformers.js
  3.8.1 (both Apache-2.0). Model input uses a 294-pixel target, retaining aspect
  ratio and multiples of 14. Relative inverse-depth predictions are normalized
  between the frame's 2nd/98th percentiles. This range can change between frames;
  it is not a persistent ruler. Video frames are never uploaded for inference.
- AI predictions may cover the visible head and held Atom. Their colors are
  visual estimates, not attachment evidence or measured clearance. Reflections,
  transparent surfaces, unfamiliar close-up objects and screen graphics can
  mislead a monocular model.
- Only public `hhh.camera.still` v1 and `hhh.relay.arms` v1 contracts are read,
  obtained through enabled hub context lookups. Both names and integer versions
  are validated. MCAM1 remains the sole owner of its device and video worker.
- Samples use **actual TCP pose**, never commanded targets or constant-speed
  extrapolation. Bracketed interpolation follows acceleration and deceleration
  near arrival. Feedback older than 250 ms or gaps over 120 ms are rejected.
- The observer samples up to 30 Hz, processes selected frames up to 12.5 Hz and
  publishes through shared SSE at about 10 Hz. Histories are bounded to 240 pose
  samples, 8 pending frames, and 24 image keyframes. The server observer is paused
  on hub startup; opening this page starts analysis through its existing API.
- Freshness is measured after each owner read and after acquiring the snapshot
  lock. Samples arriving during those operations must not be compared against
  an earlier loop timestamp. Feedback still expires after 250 ms; invalid poses,
  future timestamps and disconnected arms fail closed with a specific reason
  and the selected arm's name.
- Forward/backward Lucas–Kanade tracking follows textured scene features seeded
  across a 12-pixel grid, excluding the selected Atom region. Each feature keeps
  its identity and a fixed reference ray throughout a short sweep. Tracking from
  the preceding frame supplies an initial position for a second match against
  the reference image, limiting drift without losing large-displacement tracks.
  Distortion-corrected triangulation uses measured travel. Positive depth,
  parallax and reprojection checks reject poor tracks. At least eight valid
  samples are needed for a scene map. A separate fit uses only samples inside the screen
  region and needs at least 12 inliers spread across a nearly horizontal plane.
  Scene depth remains available when that plane cannot be fitted.
- Without a confirmed mount, a robust constant-rotation epipolar fit estimates
  translation direction. A measured TCP baseline of 5–40 mm supplies its length;
  tool orientation change must be below 0.15°. A minimum of 12 moving features,
  broad image coverage, 65% directional agreement, positive depth, parallax and
  reprojection checks gate this estimate. Camera-relative coordinates never
  produce a world-space playfield plane or Atom clearance.
- Each feature retains up to eight triangulated observations plus its reference
  view. A new observation must use a different frame and a measured position at
  least 2 mm from every stored viewpoint. Repeated frames, a stopped arm and
  inferred translation-direction jitter cannot increase the viewpoint count.
  A robust consensus rejects inconsistent inverse depths, then combines agreeing
  values with pixel/timing uncertainty weights. Two conflicting initial samples
  suppress that feature until later views agree; a bad first sample can be
  replaced by later consensus. The fused point must also reproject within 1.5 px
  of its current tracked location. A conflicting current observation is hidden
  even when older views agreed.
- Evidence belongs to a bounded local sweep, not a permanent world map. The
  reference is retained while it meets the travel, orientation and four-second
  limits; changing reference starts fresh feature identities. Lost features,
  tracking gaps over 500 ms, configuration changes, pauses and source resets
  discard dependent evidence. Combining views reduces random noise and improves
  consistency, but does not remove shared reference, nominal lens or timing
  errors. Reported depth spread is observed scatter, not guaranteed accuracy.
- The motion output is a **sample-based depth map**. Those bricks contain only
  measured features;
  textureless cells, uncertain object boundaries and unobserved areas stay
  unknown. A head or attached Atom moving with the camera has no useful parallax
  and cannot supply measured distance samples. Neighboring measured cells are
  not filled by interpolation. Metric colors indicate distance from the camera
  lens, not height above the playfield.
- The browser can fit AI inverse-depth predictions to motion samples from the
  **exact same image**, using robust positive affine regression. At least 20
  agreeing samples, a meaningful depth spread and low residual are required.
  Predictions outside the supported range remain unknown. These outputs say
  **Estimated distance · AI fitted to arm-motion samples**, never measured AI
  depth. Failed fits retain the explicitly relative map unless a refined motion
  map is available. No fit is reused on
  another frame, and no browser estimates feed hardware or clearance logic.
- Reference-to-current travel spans 5–40 mm depending on the configured minimum;
  a new reference is chosen near 20 mm, then retained for repeated observations,
  with at most 4 seconds and 0.75° orientation change (0.15° in automatic mode).
  Pure rotation and insufficient translation do not generate depth. High speed
  relative to configured timing uncertainty suppresses a result. The delay and
  rolling shutter still limit physical accuracy, so outputs remain experimental.
- Atom features staying fixed relative to the camera while the screen shifts,
  with relay pump state `suck`, yield `moves_with_head`. Relative feature motion
  yields `relative_motion`. Missing features, stopped scenes and stale evidence
  yield `unknown`, never a confident “empty head”. Head features accidentally
  selected as Atom features can create false co-motion evidence. No pressure
  sensor or identity classifier is implied.
- Depth bricks and their camera reference use their **own inference/measurement
  image**, not a newer image. AI frames display their age and expire 10 seconds
  after completion or 15 seconds after receipt, whichever comes first. This
  allows slower inference without presenting its snapshot as live video. Motion
  measurements expire after 500 ms. **Motion measurements** keeps the last valid
  map in this browser page for up to five minutes so a brief result does not
  disappear when the arm stops. It is labelled **Last measured map**, with its
  capture age and frozen camera reference; it is never projected onto newer
  video or used for current clearance or AI scale. New valid measurements replace
  it. Pause, settings changes, feedback loss/epoch change, camera loss/mode or
  sequence reset, stream disconnect and page reload clear this display cache.
  Without a map, the motion window shows the live camera with the specific
  blocker, and hides the map reference. Live view is separately
  selectable. A valid world-space plane can support
  updated clearance from fresh feedback for 3 seconds after its last visual
  observation. Attachment evidence expires after 500 ms; video after 400 ms.
  Loss of either required input, settings changes, arm epoch changes and video
  mode changes clear dependent estimates. The browser also clears stale values.

## Owned interfaces

`depth_snapshot()` → `hhh.mcam1.depth`, integer version 1. Status is `ready`
when fresh video and selected arm feedback support a fresh scene map or plane.
Clearance remains null without a valid plane. Quality is
always `experimental`; `ready` does not mean certified metrology or motion
permission. Includes `clearance_if_held_mm`, `attachment`, plane residual,
baseline, frame interval, timing contribution, and scene points. Each point has
normalized image coordinates, optical-axis `depth_mm` and Euclidean
`distance_mm` from the camera lens. Measurements identify the latter with
`distance_kind: "lens_to_point"`. The browser also accepts older snapshots with
only `depth_mm` and labels that scale **Camera forward depth**.
`automatic_motion_supported: true` advertises the setup-free motion path;
`measurement.method` distinguishes `automatic_motion` and `configured_motion`.
`temporal_fusion_supported: true` advertises repeated-view fusion.
`measurement.fusion` reports `state` (`collecting` or `refined`), tracked and
combined feature counts, maximum/median viewpoints, current-frame rejected
observations, median observed depth spread, window age and reason. Each point
adds `track_id`, accepted `views` (including the reference image), and
`spread_mm` (null for the first pair). Track IDs are local to one service run
and reference generation; consumers must not treat them as persistent objects.
Browser AI predictions are presentation only and are not exported as metric
measurements by this public contract.

- `GET api/state`, `GET api/events`: snapshot / shared SSE.
- `POST api/analysis`: `{"running": true|false}`; changes analysis only.
- `POST api/config`: complete configuration; validated and atomically saved to
  this module's `calibration.json`; resets prior observations.
- `POST api/lens`: `capture`, `solve`, `clear_samples`, `clear_intrinsics`;
  optional `columns`, `rows`, `square_mm`. Samples are memory-only; solved
  calibration persists with configuration.

Routes inherit Gamemaster authentication. No camera start, move, enable,
connect, lease, or pump endpoints exist. `hub_init` starts the owned observer;
`hub_stop` joins it. Importing the module starts no resources.

## Verification

```sh
.venv/bin/python -m unittest discover -s tests -p 'test_mcam1*.py'
node tests/mcam1_depth_bricks.test.js
NODE_PATH=/path/to/node_modules node tests/mcam1_depth_browser.cjs
# Optional real-model/network smoke; no hub or robot requests:
NODE_PATH=/path/to/node_modules node tests/mcam1_depth_model_smoke.cjs
# Exercise the CPU fallback with the real model:
MCAM1_DEPTH_CPU=1 NODE_PATH=/path/to/node_modules node tests/mcam1_depth_model_smoke.cjs
```

Tests cover metric triangulation, rendered textured planes and raised objects
through actual optical flow, co-moving texture rejection, scene depth without
a screen region, the Atom base-corner offset, rotation rejection, decelerating
feedback, missing inputs, input contracts, calibration persistence, lifecycle,
brick colors and grouping, unknown cells, range and size controls, browser
region selection, setup-free relative depth without arm feedback, automatic
translation scale with an unknown camera orientation, inconsistent-scale
rejection, stale UI handling and desktop/mobile layouts. Fusion tests measure
error reduction against known noisy geometry, bad-first-sample recovery,
conflicting observations, duplicate/stationary viewpoint rejection, bounded
history and resets. Rendered sequences exercise actual tracking and fusion in
both camera modes. The browser checks refined-map priority over AI, fixed metric
colors, viewpoint readouts and disconnect clearing.
It also checks map retention after motion stops, original-image pairing,
measured-travel diagnostics and cache invalidation. An angled-camera regression
includes a textured co-moving head and checks automatic distances against the
known scene geometry.
Browser UI regression tests mock all requests and cannot send robot commands.
The optional model smoke downloads public assets and does not access the hub. Synthetic
accuracy is not physical accuracy. Validate with measured 0, 5, 10, 20 and
50 mm underside gaps, including during arrival, before relying on estimates.
