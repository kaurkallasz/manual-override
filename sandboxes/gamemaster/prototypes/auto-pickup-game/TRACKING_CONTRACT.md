# Read-only tracking outputs

These public functions add observation adapters to the existing owner of Cal 2
and the authenticated LTX cue-report endpoint. They do not create robot-control
paths or change the legacy X logging response. Consumers use enabled hub
discovery and verify the named integer contract version.

## `tracking_projection(tags, arms)` → `hhh.cal2.projection` v1

Input tags are bounded Board-validated observations with numeric `id`, `nx`,
`ny`, in **unrotated, lens-corrected camera-normalized coordinates**. Input arms
are dictionaries keyed `green`/`purple`, with `connected`, finite Cartesian
`pose` arrays, `target`, and explicit `control_mode`. Joint targets are not
projected. The function is read-only and returns JSON values, not model objects.

Output includes `status: ready`, `coordinate_space:
corrected-camera-normalized`, `units: mm`, and `arms`. Each arm independently
has `status/error`, `base_camera`, `tcp_camera`, `target_camera`, `height_basis`,
and projected `tags`. Each projected tag has `id/status/error`; ready tags add
`ground_camera`, `robot_xy`, `pickup_z`, and `drop_z` (null when not calibrated).
An unavailable arm has no projected tags. Missing parallax makes raised tags
unavailable without rejecting flat markers or the other calibrated arm.

Uses the proven LTX six-point thin-plate spline formula, plus four raised/ground
parallax pairs for the existing >=100 hardware marker family. Cal 2 owns all
calibration values; models are cached by the calibration value and rebuilt on
change. Projection is not reachability, collision checking, or permission to
move. Base-to-TCP camera geometry is illustrative. Pickup/drop Z excludes
player-local live/fine tuning; drop adds the existing 1 mm clearance and the
calibrated stack offset for a raised destination.

## `tracking_intent_snapshot()` → `hhh.controller.intent` v1

Output: `status: ready`, Unix-seconds `observed_at`, `arms[side]` containing the
last relevant authenticated LTX report: `stage`, `operation_id`, optional
`physical_tag/target_marker`, `reported_at`, `source: controller_report`.
Empty arms means no report, not idle or completed. Reports are in memory and
lost on process restart. They do not imply a live controller connection.

The existing `POST /api/laser-tag-x-intent` role/team checks remain authoritative.
Tracking records the report before legacy X logging, so diagnostics can observe
an LTX controller without an active X run. No new POST input or robot commands
are introduced. Unknown stages are ignored; late events for a superseded
operation do not overwrite its successor. Consumers must expire reports and
must not treat cue completion as physical placement confirmation.

All source timestamps use Unix seconds. Breaking semantic changes require a
new integer version. Smoke tests are in `tests/test_photon_board_tracking.py`.
