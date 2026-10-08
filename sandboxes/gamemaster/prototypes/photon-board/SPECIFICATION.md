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
- Camera Calibration: `preview_frame()` -> `hhh.camera-frame` v1. Board's public
  `preview_frame()` forwards the existing corrected JPEG as `photon.board.preview`
  v1 with `status`, `coordinate_space`, `frame_at`, `width`, `height`, and `jpeg`.
  Missing, malformed, simulated, or older-than-two-second input returns unavailable
  with no pixels. This on-demand display branch does not affect observations.
  Laser Tag Y multiplexes those pixels as `laser-tag-y.camera` v1 `camera` events
  on `/api/events?markers=1&preview=1`, alongside its existing Game and marker
  events (about four updates per second). State-only and external-screen clients
  do not request pixels. The browser checks freshness, hides stale images, and
  recovers when fresh frames arrive; hiding Y releases the combined connection.

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

`occupancy_snapshot()` publishes additive `photon.board.occupancy` v1 and the
same cached descriptor is included as `occupancy` in `runtime_observation()`.
It is camera-only evidence for an already installed turret's Atom buff. Relay
availability and pump state do not affect this descriptor; the existing
arm-gated `photon.board.placement` v1 activation contract is unchanged.

The existing sampler advances occupancy using immediate corrected detections,
visible IDs, unique associations within 0.04 normalized distance, and at least
three distinct frames spanning 0.55 seconds. Each relationship carries
`movable_id`, `marker_id`, `relation_id`, `state` (`present`, `departed`, or
`unavailable`), `observed_since`, `evidence_at`, and nullable `departed_at`.
The envelope carries `status`, `error`, `source_epoch`, `revision`, `sampled_at`,
`frame_at`, and the acquisition/grace policy. Board assigns no team, tower,
health, damage, reward or robot action.

Established occupancy retains that Atom's marker anchor beyond the ordinary
120-second fixed-marker memory. After occlusion the same Atom can reacquire its
established association with another stable observation window; this retained
association cannot activate a new turret or establish a different Atom's visit.
Source/camera identity, correction revision, frame dimensions or a visibly moved
fixed marker invalidate retained anchors. Fresh observed displacement establishes
departure. Missing detections do not: after a maximum 0.35-second grace they
become unavailable. Stale camera input and sampler failures also remove authority.
Reading HTTP/SSE snapshots cannot advance dwell or create a new visit.

Smoke test: `.venv/bin/python -m unittest discover -s tests -p test_atom_tower_buff.py`.

- `board_snapshot()`, `GET /api/board`, and sampled `GET /api/events` publish
  the small `photon.board` version 1 projection used by generic games.
- `runtime_observation()` and `GET /api/runtime` publish
  `photon.board.runtime` version 1. It preserves corrected pixel coordinates,
  normalized coordinates, rotations, missing/tracked state, marker corners,
  immediate detections, visible IDs, frame dimensions, and compact arm state.
- `camera_markers_snapshot()` publishes `photon.board.camera-markers` version 1
  for Laser Tag Y and Mobile LTZ. It reads the cached runtime sample, never
  hardware. Ready values require a live sampler, a corrected camera frame no
  older than 1.5 seconds, and positive image dimensions. `tags` contains only
  immediate corrected `detections` present in that frame's `visible_ids`, with
  `id`, normalized `camera: [u,v]`, optional normalized `corners`, and `last_seen`
  set to the detection frame's time. Tracked-tag qualification and remembered
  positions are excluded. `frame_at`, `width`, `height`, `source`,
  `coordinate_space: corrected-camera-normalized`, and `max_age_s: 1.5` describe
  the evidence. A valid empty frame is ready with no tags; stale, uncorrected,
  simulated or unavailable input returns unavailable with an error and no tags.
  The camera-marker projection additionally requires relative size agreement:
  measure the mean of four corrected-pixel edge lengths, then retain the unique
  largest group whose largest/smallest ratio is at most 1.15 (a pairwise 15%
  span, not +/-15% around an average). At least two measurements must agree;
  equal-sized competing groups fail closed. Missing, degenerate or non-convex
  quadrilaterals are rejected. No marker ID is exempt or permanently blocked.
  This uses apparent image size, so a legitimately larger or smaller marker is
  also excluded from this shared display/alignment feed. Other raw observation,
  calibration-measurement and game-placement contracts retain their policies.
  `size_filter` reports `max_ratio`, `status`, accepted `minimum_px`/`maximum_px`,
  and `rejected` entries with ID, measured `size_px` (or null), and reason
  (`invalid_corners`, `size_outlier`, `no_size_consensus`). Y removes rejected
  historical positions and checks saved outlines against the current accepted
  size span before displaying them. Cached positions cannot establish the size
  reference. Diagnostic proximity settings do not alter freshness or size
  policy. Consumers
  validate contract/version, frame and per-tag freshness; Mobile additionally
  matches IDs to the active level and checks the registration geometry. Y
  carries this value as `camera_markers` in its existing multiplexed marker
  event, alongside separate diagnostic history. This projection grants no robot
  motion or game-placement authority.
- Both v1 projections include additive `placement`, named
  `photon.board.placement` v1. It contains only bounded, stable relationships
  between a movable ID (>=100), a fixed marker (<100), and an available arm
  side. The fixed-marker activation radius is 0.04 in corrected-camera-normalized
  coordinates (20% smaller than the previous 0.05). It never assigns a player,
  socket, tower, score, or valid destination.
  `source_epoch`, `relation_id`, sample/evidence timestamps, rank and normalized
  separation let a consumer reject stale or replayed evidence without seeing
  raw coordinates. It is part of the existing cached sample, not another
  service or stream.
  Its additive `stacking` field has the separate `photon.board.stacking` v1
  contract. This reports camera-only relationships between a visible upper
  movable tag and a lower movable tag that has disappeared at that location.
  It has no arm, pump, team or game requirement. Immediate detections and
  `visible_ids` are used, so tracked-tag grace periods cannot keep a covered
  lower tag artificially visible. A unique overlap within normalized distance
  0.05 must persist for 0.55 seconds and at least three distinct camera frames.
  Both-visible tags, ambiguous targets and a departing upper tag do not confirm
  a cover. The lower tag must have been seen within five seconds when a new
  cover begins; its position follows every fresh detection for as long as it
  remains visible. An uninterrupted cover retains its target after that window.
  Stale/unavailable camera input, sampler failure and source changes clear this
  evidence. Disconnected arms do not remove otherwise valid cover evidence.
  Relations carry `lower_id`, `upper_id`, `relation_id`, `distance`,
  `lower_seen_at`, `observed_since`, `stable_at` and `stable`, with sample time
  and source epoch on the descriptor. This leaves existing fixed-marker/arm
  placement v1 semantics unchanged.
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
not changed. The separate game-facing fixed-marker relationship uses normalized
0.04 distance, 0.55-second dwell and 120-second fixed-marker memory. Atom-on-Atom
cover retains its separate 0.05 overlap distance.
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

The separate camera-only stacking descriptor does not use fixed-marker memory
or arm availability. Game decides whether the covered movable is its armed
core atom and whether the covering movable belongs to the opposing team.

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

## Cue coordinate memory

`cue_targets_snapshot()` and `GET /api/cue-targets` expose
`photon.board.cue-targets` v1. The existing sampler owns this in-memory evidence;
HTTP readers never sample hardware. It does not change the camera-markers v1
contract or gameplay placement truth. Coordinates are corrected-camera-normalized.

Fixed IDs 30–59 are learned from at least three distinct frames spanning 0.5 s
with no more than 0.004 normalized drift between samples. Their coordinates
survive occlusion until the camera identity, correction revision, frame dimensions,
or a confirmed fixed position changes. Fixed detections require valid convex
corners. The initial stable acquisition freezes each marker's position, size and
rotation-independent edge/diagonal proportions. Later size or shape spans greater
than 1.15 relative to that marker's own reference are quarantined before movement
confirmation; different legitimate sizes, such as the larger core, are supported.
Camera presentation and cue evidence share the same geometry measurement helper.
A detection more than 0.01 from its frozen position is also quarantined. Neither
kind of suspect observation overwrites the retained coordinates or last-seen time.
Three distinct, geometry-valid consistent sightings spanning 0.5 s, with gaps no
greater than 0.5 s and drift no greater than 0.004, confirm a position change and
reset the map, even if the other markers stayed still.

A quarantined marker is withheld from `tags`, so it cannot start a new approach.
An already acquired cue endpoint can continue only when fresh independent board
evidence verifies the retained map: at least four other mapped markers, each with
three distinct recent sightings spanning 0.5 s and within 0.004 of its frozen
reference. Their convex hull must have normalized area at least 0.02, span at
least 0.15 on both axes and contain every quarantined reference position. Anchor
evidence expires after 0.75 s; repeated frames/reads do not renew it. Too few,
clustered, collinear, distant, shifted or stale anchors make the map unavailable.
A valid return to the original marker position clears its quarantine; disappearance
alone never does. Camera outages revoke verification and reset confirmation samples.
Last-seen times are never renewed by
cache reads. A camera outage retains memory but revokes its motion authority;
frames and sampler output must be at most 1.5 s old. Restart clears the cache.

IDs 100–199 remain moving observations. Missing tags never gain fixed/cached
status. `acquirable` requires at least three distinct sightings of one position
within the last 1.5 s, spanning at least 0.5 s, with the latest at most 0.75 s old.
Each sighting must remain within 0.004 normalized distance of every retained
sighting. Missed frames preserve this bounded evidence; repeated frames/reads
cannot add samples. A longer gap, conflicting position or invalid camera state
resets acquisition confidence. `evidence_samples` reports the retained count;
`visible`/`stable` still describe the stricter current-frame evidence. Records expire
after 15 s. Fixed records separately retain observed `covered_by` Atom IDs, using
camera tag corner bounds, until the covering tag is seen elsewhere or the fixed
marker is visible again. Losing the covering tag or its battery does not mean an
empty destination. This is observed occupancy, not a complete obstacle model.

Each tag carries `last_seen`, `visible`, `stable`, `fixed`, `cached` and
`covered_by`; the envelope carries a camera `epoch`, `frame_at` and `sampled_at`.
`epoch_reason` and `epoch_marker_id` identify the most recent map reset;
`pending_fixed_ids` identifies fixed detections awaiting confirmation.
`quarantined_tags` gives their IDs, rejection reasons and retained `covered_by`
occupancy, without publishing coordinates. The controller still stops for another
Atom occupying its quarantined destination. `verification` reports status,
independent anchor IDs, oldest observation time and coverage area when available.
The mobile facade calls `cue_targets_snapshot(scope=<layout hash>,
fixed_ids=<unique active fixed IDs>)`. This registers a separate camera-evidence
map for that layout, learned by the existing sampler from subsequent frames;
it never copies coordinates or confidence from another layout. Filtering happens
before fixed-marker learning and conflict detection, so a stray calibration ID
such as 30 cannot hold or reset a game containing only 38 and 40–55. The response
acknowledges `layout_scope` and sorted `fixed_ids`; the facade requires both.
Scopes are nonempty strings up to 128 characters; fixed IDs are a nonempty list
of unique integers 30–59. Four recently used scopes are retained. Calls without
arguments preserve the unscoped diagnostic view.

The facade derives game fixed IDs from level sockets and the projected core,
and calibration IDs from the owned calibration display. It adds the active
layout scope and excludes observations from before that scope. Unverified
active-marker contradictions, confirmed marker moves, camera identity/correction
changes, unavailable frames and stale sampler output still revoke authority. A hidden acquired destination has no
visibility timeout while its scoped map stays valid. Existing camera placement
evidence stays separate.
