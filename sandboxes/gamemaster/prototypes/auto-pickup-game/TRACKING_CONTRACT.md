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


## Game-owned mobile lesson and safety (2026-10-01)

The owner exposes `calibration_session_snapshot/begin/command/maintain/finish/
release` as `hhh.cal2.session` v1. Begin binds operation ID, side, player and
practice status; one side owns the shared display. Drafts persist atomically in
`data/calibration-lessons.json`, but restart creates a new epoch and revokes
live motion access. Fresh heartbeat and measured arm/camera input renew access;
expiry pauses before Relay hold. Release requires measured stopped motion and
restores Playfield Areas before clearing the lesson reservation.

Six fresh points (30–35), four separate ground/3 cm raised samples
(31,35,33,34), pickup height and consistent shared transport height must validate
before the rig model commits atomically. Accepted captures alone get green glow;
resuming restores only those glows. A field reservation that commits before a
failed lesson write stays blocked and retries under the same ID. The previous
valid rig remains available while a draft is incomplete. New profiles still
perform fresh captures; the click-preview/explicit-Move exercise is optional.

`calibration_session_complete({side,id})` returns `hhh.cal2.session` v1. It
validates and commits the active lesson's six points, four raised samples and
captured pickup/transport heights, then creates a durable `measured-targets`
completion receipt. It does not claim guided movement or pickup evidence and
does not release the arm/display reservation. Game records progression and
requires Relay stop confirmation before handing off the turn. Retries retain
the same committed revision; a fingerprint of the actual measurements ensures
height edits made after optional validation are installed before completion.

`calibration_lesson_target(side,id)` is `hhh.cal2.target` v1. Two arrivals use
actual Relay poses. Pickup proof binds a recently visible owned Atom to suction
and measured lift; Game then verifies fresh Board placement after that lift.
`calibration_safety_snapshot(side)` is `hhh.cal2.safety` v1: server-owned six-point
convex bounds, radial and Z limits, rig revision and reservation. Changed camera
correction/device identity, invalid geometry and missing raised samples fail
closed. Lens correction runs once in Camera Calibration; raised-Atom parallax
runs once in the owner/controller mapping, with no flat fallback.

The old direct robot endpoints return 410. Robot motion continues exclusively
through the existing authenticated player LTX → Relay path. No driver is
imported or instantiated by this module. All calibration files belong here.

Calibration display loading uses this owner's fixed Auto PP Cal 2 template and
its camera settings. Templates have no runtime IDs; begin supplies stable IDs
for Playfield's session-scoped replacement. The session snapshot publishes
`hhh.playfield.display` v1 only as ready when the matching reservation owns all
six displayed markers. Display setup precedes feedback validation, so missing
feedback may leave a blocked display reservation without a lesson. Its owning
side/ID can release it after Relay confirms stopped motion, or use the deferred
stop semantics below for operator screen navigation. No live motion grant
is implied by a display descriptor. Each activation records `activated_at`;
captures require a camera frame newer than that activation and any prior capture.

A restored or partially committed Playfield reservation without an active lesson
publishes `requires_activation: true` alongside its owning side/ID. Maintenance
keeps it blocked; Game must call begin under the same durable ID with fresh
camera/arm measurements. This rebinds the draft to the current process epoch and
restores captured glows. A display reservation alone never renews motion access.

Game lessons use the Green normal / Purple 180° target layout, relative to the
template's `camera_view` (or the saved fallback's `saved_camera_view`). Only the
area X/Z positions rotate; marker IDs, sizes and per-marker glows remain stable.
The lesson records `display_camera_view`, and its draft inherits that view for
the eventual calibration commit. Captured camera/ground/raised coordinates stay
in the corrected camera frame. A resumed draft with captures from a different
layout orientation must be cancelled and reopened; it cannot silently combine
old measurements with newly moved targets. This does not overwrite the previous
committed calibration while the replacement draft is incomplete.

`calibration_session_release({side,id,defer_stop:true})` separates screen exit
from hardware admission. Before restoring the display, an existing lesson is
paused, marked closing, and recorded in durable `pending_stops[side]=id`. Failed
or absent Relay feedback leaves that entry intact across restarts. Snapshot
publishes `motion_blocked`/`motion_error`; both arms, heartbeat renewal, and new
lesson activation remain blocked. Maintenance clears an entry only after a valid
`hhh.relay.stop` v1 reply with `stopped: true`. The same existing Relay path is
used. A never-activated display preview creates no spurious stop requirement.
Ordinary lesson completion/release keeps the strict stop-before-handoff rule.
Targets for the next side may be projected while stop recovery is pending, but
capture and movement remain unavailable. Previous rig calibration is preserved.

Restart clears both `active_side` and `active_id`. Idempotent release also clears
a legacy orphaned ID. Maintenance only renews/stops a session with an active side;
historical drafts cannot block target loading. Deferred stops continue through
`pending_stops` independently and keep motion inhibited until confirmed.


Mobile commissioning and history (2026-10-01)
--------------------------------------------
During an active, unexpired `points`/`perspective` session,
`calibration_safety_snapshot(side)` returns configured robot-workspace bounds
instead of the unfinished camera hull. Fresh corrected camera and enabled Relay
feedback are still required; radial limits (at least 220 mm inner radius), Z
limits and Relay whole-path checks remain in force. All other stages use the
completed six-point hull. The browser reports commissioning coordinates as
`robot-mm`; tutorial/game coordinates stay camera-normalized. No second driver
or movement endpoint is introduced.

Each outer six-point capture also records its ground camera sample. The four
`raised` commands use `{marker, camera:{u,v}}`: an explicit tap on the raised
physical tag centre in corrected-camera coordinates, at 30 mm above the ground.
IDs are 31, 35, 33 and 34, matching Auto PP Cal 2. The owner validates finite
normalized coordinates, newer frame, current arm identity and unchanged camera
correction. It does not redetect the ground marker hidden by the raised tag.
Recapturing an outer point invalidates that point's raised sample. A valid commit
still requires all six points, all four perspective samples and height settings.

`calibration_history(side)` returns `hhh.cal2.history` integer version 1,
`status: ready`, and side-specific `rows`. Rows contain id, side, revision,
saved_at, optional label/practice, draft measurements and transport_height.
Committed lessons are archived immutably in this owner's durable lesson store;
the existing saved rig is archived before replacement. Current saved rig and
legacy committed lessons are also exposed. The Mobile LTZ API's authenticated
GET `/api/calibrations?side=...` validates this contract. The dropdown only
inspects history: it never activates old measurements or skips the lesson.

Game Master saved selection (2026-10-01)
---------------------------------------
History v1 additionally reports `active_id`, `latest_id`, `selection` and the
current `rig_revision`. Each row includes `active`, `applicable`, `error` and
optional `camera_revision`. Latest means the newest complete, valid record by
original capture time, not the last record applied. Both arms retain their own
source identity and camera-correction revision. Legacy rigs without that
revision remain supported. Explicit choices persist in owned Cal 2 JSON; a new
completed lesson installs its measurements and resets that arm to `latest`.

`calibration_saved_preview({side,id='latest',expected_revision?})` resolves and
validates a saved row without changing any state. It returns `hhh.cal2.saved`
integer version 1, ready, with side, row, selection and rig_revision, or raises
ValueError. `calibration_saved_apply` accepts the same request and returns the
same contract with `applied: true` and the new rig_revision. Photon Game owns
the operator transition: it rejects running games, validates the selection,
returns from the calibration display through Journey, then calls Apply. An
earned lesson stays deferred and still requires fresh player completion.

Apply validates all six finite poses, camera samples, four raised samples,
pickup/shared transport heights, nonsingular transforms and known camera/robot
identity bindings. Fresh Relay `hhh.relay.arms` v1 connection states are required.
Connected arms must confirm `hhh.relay.stop` v1 stopped; disconnected arms never
get enabled. A durable pending-stop gate inhibits both arms while the owned rig
is atomically replaced. Failed stops keep that gate. Both prior source rigs are
archived because transport Z is shared. No public driver or second movement
path is added. The rig revision makes existing mobile controllers halt and
reload their measurements before further movement.


Calibration marker occlusion (2026-10-01)
---------------------------------------
The existing Game maintenance tick learns corrected-camera centres for all six
target IDs as soon as Playfield reserves the calibration display, including while
the arm is disconnected. The owner reads Webcam and Camera Calibration through
their public v1 contracts. Webcam `visible_ids` identifies the latest detector
frame; a nonzero `missing` age alone does not mean that a tag is absent. Empty
visible-ID lists never reclassify held detections as fresh evidence. Legacy
snapshots without `visible_ids` retain strict zero-age detection checks.

These optical positions live in LessonStore memory, separately from durable point
captures and measured arm poses. All six positions must be identified before a
capture/ground command is accepted. Then an obscured target can use its cached
position, with a fresh camera frame, fresh enabled-arm feedback and an active
lesson grant still required. Camera preparation never grants movement access.

The cache is scoped to side, display session, process epoch, target geometry,
projection settings, corrected-camera revision and image size. A camera outage,
invalid observation, changed scope or release clears it; it never loads from
previous lessons or saved calibration files. Only frames newer than display
preparation can seed it. Activating/reconnecting the arm within the same display
preserves it. Retrying offline activation does not reload the projected targets.
Capture stores `camera_observed_at`
and `camera_cached` alongside the point, independently of the current capture
frame timestamp. Outer ground samples retain the same optical provenance for
raised-tag perspective fitting. The session snapshot's optional
`marker_positions` maps string marker IDs to `{camera:{u,v},frame_at}`. The
top-level `marker_preparation` contains `{id,side,marker_positions,ready}` before
a motion session exists; `ready` requires all six positions and a current camera
frame. Mobile LTZ API exposes it as `mobile_calibration_preparation` only to the
selected side. Both phones light identified numbers immediately, show “Ready to
capture” at six, and retain the cached camera labels through occlusion. Capture
buttons require optical readiness and the separate live motion grant. The other
player remains on Upgrades; no partner draft or cache is exposed.

The mobile six-point and raised-tag stages hide X/Y adjustment sliders. After
the sixth arm point is saved, Mobile reveals a dedicated optical crosshair.
Tapping the corrected image only positions that crosshair; tapping a reference
button (31, 35, 33 or 34) sends the existing `raised` command using its selected
camera coordinates. The physical sample is a 100-series ArUco tag held 30 mm
above the corresponding ground reference. No image tap sends a robot command.
The numbered quick-capture controls stay visible when instructions are folded:
six arm points first, then four raised references, with saved checkmarks.
