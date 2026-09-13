# Photon Board

Photon Board owns physical-observation truth and nothing else. It never issues a
robot command and does not know game rules, level geometry, damage, or game
rendering. Its own tab shows read-only physical diagnostics and edits only its
own diagnostic thresholds (or explicit simulated input), never robot controls.

## Inputs

The production adapter reads three enabled siblings through versioned public
functions only:

- Webcam `tag_snapshot()` publishes `hhh.webcam.tags` version 1: raw tracked
  tags, immediate detections, visible IDs, and camera dimensions.
- Camera Calibration `corrected_tag_snapshot(tags, detections)` publishes
  `hhh.camera-correction` version 1.
- Relay `arms_snapshot()` publishes `hhh.relay.arms` version 1. This is a
  read-only state function and cannot move either robot.

Additive hardware timestamp fields: Webcam `frame_at` is the Unix-seconds time
of the last processed detection frame (including empty frames), not the time of
the HTTP request. Relay arms carry `feedback_at` (Unix seconds) and
`control_mode` (`cartesian`, `joint`, or null). Diagnostic inference requires
these source timestamps; a still-responsive server is not fresh sensor evidence.

Optional diagnostic adapters, through the same enabled/versioned boundary:

- Auto Pickup (`auto-pickup-game`), the existing owner of Auto PP Cal 2 data:
  `tracking_projection(tags, arms)` -> `hhh.cal2.projection` v1. Projects
  corrected, unrotated camera coordinates into each arm's own millimetre frame
  and projects TCP/base/Cartesian destination back into that camera frame.
- The same owner: `tracking_intent_snapshot()` -> `hhh.controller.intent` v1.
  Last authenticated LTX cue report, not evidence of physical completion.
- Camera Calibration: `preview_snapshot()` -> `hhh.camera-preview` v1,
  status/error and `stream_path: /api/corrected-stream`. Board's `/api/preview`
  resolves this through discovery and redirects to that existing read-only feed.

Calibration is NOT copied into Board. Six-point TPS, raised-tag parallax and
height estimates remain owned by Auto Pickup. Missing/invalid calibration
removes calibrated meters/arm projection without hiding valid camera detections.
No fallback silently treats raised tags as flat or joint angles as millimetres.

Missing, disabled, failing, malformed, incompatible, or uncorrected production
input produces `status: unavailable` with no authoritative tags. Relay failure
also removes all arm evidence, so physical activation fails closed even when
the camera could otherwise be read. Each input has an independent status in
`inputs` so a changed sibling contract is diagnosed at this boundary.

Authenticated `POST /api/simulation` accepts a boolean `enabled`, `tags`, and
optional compact `arms` (`pose`, `target`, `control_mode`, connection/enabled and
pump state). Validation is atomic. Simulation is explicitly labeled, never
reads live controller intent or displays live video, and cannot issue commands.
Its virtual frames/feedback are clocked by Board. Calibration may be used for
its explicitly simulated coordinates; unavailable calibration is still explicit.

## Outputs

- `board_snapshot()`, `GET /api/board`, and sampled `GET /api/events` publish
  the small `photon.board` version 1 projection used by generic games.
- `runtime_observation()` and `GET /api/runtime` publish
  `photon.board.runtime` version 1. It preserves corrected pixel coordinates,
  normalized coordinates, rotations, missing/tracked state, marker corners,
  immediate detections, visible IDs, frame dimensions, and compact arm state.
- Both v1 projections include additive `placement`, named
  `photon.board.placement` v1. It contains only bounded, stable relationships
  between a movable ID (>=100), a fixed marker (<100), and an available arm
  side. It never assigns a player, socket, tower, score, or valid destination.
  `source_epoch`, `relation_id`, sample/evidence timestamps, rank and normalized
  separation let a consumer reject stale or replayed evidence without seeing
  raw coordinates. It is part of the existing cached sample, not another
  service or stream.
- Both v1 projections include additive `tracking`, named
  `photon.board.tracking` v1. `tracking_snapshot()` and `GET /api/diagnostics`
  expose the exact same cached diagnostic value. Existing `/api/events` pushes
  it inside the Board snapshot; no second event-stream implementation.
  The diagnostic value includes the already-cached game-facing relationship as
  `game_placement`, so the operator table can distinguish calibrated transport
  inference from the normalized evidence Photon Game actually consumes. This
  is a copied view of the same Board-owned value, not another calculation.

Every output is a JSON-compatible value. Consumers receive no implementation
objects or sibling file paths. A breaking semantic change requires a new integer
contract version rather than silently changing version 1.

## Diagnostic settings

Expand **Proximity settings** in the Board tab to edit:

| Setting | Original default | Accepted range |
|---|---:|---:|
| Near XY | 90 mm | 1–1,000 mm |
| Near Z | 60 mm | 1–500 mm |
| Unique nearest-runner-up margin | 20 mm | 0–500 mm |
| Sensor evidence stale after | 1.5 s | 0.2–5 s |

**Apply settings** saves one complete validated replacement atomically to
Board-owned `data/tracking-settings.json`. **Use defaults** fills the original
values into the draft; Apply is still required. Saved overrides survive hub
restarts; neither editing nor saving changes the defaults. Live SSE updates
do not overwrite drafts or dismiss rejected-save errors. First use creates no
file. An invalid saved file is reported while original defaults are used; it
is not overwritten automatically. A failed save leaves prior values active.

`settings_snapshot()` / `GET /api/settings` returns `photon.board.settings` v1:
status/error, active `settings`, immutable `defaults`, and validation `bounds`.
The same descriptor is included in `tracking.configuration`, even when sensors
are unavailable. Authenticated `POST /api/settings` accepts exactly
`{"settings": {"near_xy_mm": 90, "near_z_mm": 60, "unique_margin_mm": 20, "stale_s": 1.5}}`.
Booleans, numeric strings, missing/unknown fields, non-finite and out-of-range
values are rejected without partial application. No calibration or sibling
settings files are modified.

The next sampler tick uses the new values in all proximity meters, tag
consideration, sensor-age tests, and short-lived carry inference. Applying a
replacement clears previous diagnostic transport/dwell evidence. Exact ties
remain ambiguous even with zero margin. Diagnostic placement thresholds
(18 mm / 0.55 s), marker/carry memory limits and controller-report expiry are
not changed. The separate game-facing relationship preserves the original
normalized 0.05 distance, 0.55-second dwell and 120-second fixed-marker memory.
These fixed v1 semantics are not editable by the diagnostic settings form.

This is not a game or safety setting. The sampler reads producers once and
derives two views: diagnostics use the configurable sensor timeout, while
game-facing Board observations keep their existing fixed 1.5-second freshness
gates. A longer diagnostic timeout cannot revive stale game-facing evidence;
a shorter timeout cannot remove otherwise valid game-facing observations.
Sampler/stream liveness still fails closed independently of sensor age.

## Physical tracking and diagnostics

One Python sampler starts in `hub_init`, ticks every 0.2 s, and stops/joins in
`hub_stop`. Only this sampler advances transport/dwell state. HTTP reads, SSE
client count and browser refreshes cannot advance a tag's stage. Every output
is copied; stopped/stalled samplers return unavailable, not the previous truth.

Tracking fields:

- `revision`, `sampled_at`, `frame_at`, `source`, `status`, `inputs`, `errors`,
  frame dimensions and `coordinate_space: corrected-camera-normalized`.
- `arms[side]`: fresh TCP/pump data, calibrated base/TCP coordinates, candidate
  meters, unique `considered_tag`, ambiguity, inferred `carried_tag`, nearby or
  controller-requested target meters, and Cartesian `command_distance`.
- `arms[side].controller`: separate stage/operation/tag/target/`reported_at`,
  labeled `controller_report` and stale after 30 s. Its completion is never
  promoted to an observed pickup, release or stable placement.
- `tags[]`: ID, physical kind, visible/last-seen age, camera center/corners,
  inferred arm, observed target marker, stage, confidence and explanation.
- `limits`: all diagnostic proximity, ambiguity, freshness and dwell thresholds.

The existing hardware convention is IDs >=100 for raised movable tags, IDs
below 100 for flat observed markers. This assigns no team, tower, socket, score
or valid game destination. Fixed-marker display can be toggled in the table.

Diagnostic transport stages: `visible`, `near_arm`, `pickup_suspected`, `likely_carried`,
`release_observed`, `placement_stable`, `unknown`. Disappearance after uniquely
being near an arm plus suction gives a suspected pickup; sustained occlusion
gives a likely carry, never a guaranteed grip. Reappearance during suction,
unknown pump state, stale inputs or ambiguous association cancel the inference.
Pump release is only a release signal. The diagnostic `placement_stable` stage is labeled
**calibrated overlap stable** in the tab and requires sustained,
uniquely nearby corrected-camera overlap (18 mm, 0.55 s, >=3 distinct frames);
this does not activate a turret. Marker memory expires after 5 s; carry/tag
memory after 15 s.

The game-facing `photon.board.placement` relationship is independent of Cal 2
and the diagnostic stage. It uses the corrected normalized tag centers and arm
connection/enabled/pump-off evidence that the pre-Phase-8 Game detector used.
Board owns distance, fixed-marker memory, target-order changes, dwell and source
resets. A stale frame, stale arm feedback, suction, source change or unavailable
sampler removes current authority. Game maps the relationship through Level and
applies ownership/game rules. Deterministic tests compare this path directly
with unchanged Z behavior.

The overlay uses the SAME full corrected-frame rectangle for video, tag pins
and projected TCPs; no cropping or independent rotation. A red segmented arm
line is a base-to-tool illustration, not collision geometry. Amber target lines
and green candidate links are diagnostic presentation of server output.

Meters reuse LTX's 24-segment amber/green styling. All observed movable tags are
compared for each arm. Green means uniquely near within the configured limits
(defaults: 90 mm XY / 60 mm Z, with a 20 mm nearest-runner-up margin); both arms considering the same tag is
ambiguous. Orange is another candidate, NOT a rejected game target. Physical
target distances display the three nearest/requested markers or other raised
tags (including stack destinations), excluding this arm's considered/carried
tag and its reported source tag. Calibrated
Z excludes player-local fine tuning and is explicitly an estimate. Exact
distance to a commanded Cartesian pose is labeled separately. No `DROP`
instruction or robot controls appear. After disconnect, stale meters and arm
associations disappear; raw JSON and independent input health explain why.

Smoke tests: `.venv/bin/python -m unittest discover -s tests -p 'test_photon_board*py'`.
Repository-boundary smoke test: `.venv/bin/python -m unittest discover -s tests -p test_photon_module_isolation.py`.
Hardware/projector verification is separate; fixtures must never connect robots.
