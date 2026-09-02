# Photon Board

Photon Board owns physical-observation truth and nothing else. It never issues a
robot command and does not know game rules, level geometry, damage, or rendering.

## Inputs

The production adapter reads three enabled siblings through versioned public
functions only:

- Webcam `tag_snapshot()` publishes `hhh.webcam.tags` version 1: raw tracked
  tags, immediate detections, visible IDs, and camera dimensions.
- Camera Calibration `corrected_tag_snapshot(tags, detections)` publishes
  `hhh.camera-correction` version 1.
- Relay `arms_snapshot()` publishes `hhh.relay.arms` version 1. This is a
  read-only state function and cannot move either robot.

Missing, disabled, failing, malformed, incompatible, or uncorrected production
input produces `status: unavailable` with no authoritative tags. Relay failure
also removes all arm evidence, so physical activation fails closed even when
the camera could otherwise be read. Each input has an independent status in
`inputs` so a changed sibling contract is diagnosed at this boundary.

Authenticated `POST /api/simulation` is the only other input. Simulation is
explicitly labeled and never impersonates live camera or arm evidence.

## Outputs

- `board_snapshot()`, `GET /api/board`, and sampled `GET /api/events` publish
  the small `photon.board` version 1 projection used by generic games.
- `runtime_observation()` and `GET /api/runtime` publish
  `photon.board.runtime` version 1. It preserves corrected pixel coordinates,
  normalized coordinates, rotations, missing/tracked state, marker corners,
  immediate detections, visible IDs, frame dimensions, and compact arm state.

Every output is a JSON-compatible value. Consumers receive no implementation
objects or sibling file paths. A breaking semantic change requires a new integer
contract version rather than silently changing version 1.
