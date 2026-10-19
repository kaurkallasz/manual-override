# Mobile LTZ API delivery diagnostics

The module's default page is a Game Master-only, read-only delivery dashboard
at `/s/gamemaster/p/mobile-ltz-api/`. It compares Green and Purple independently.
The player projection and existing endpoint contracts stay unchanged.

## Camera detection presentation

Physical snapshots include the existing owner's `photon.board.camera-markers`
v1 envelope in `mobile_camera.tracking`, with a `server_time` for client-side age
calculation. It preserves the source `frame_at` and current detections. This field
remains available when level registration fails; `mobile_camera.status`, its
alignment diagnostics, `mobile_cue_targets` and all movement validation retain
their independent readiness rules. Missing or failing camera owners provide no
display fallback. No extra sampler, camera read or motion authority is created.

Players may render fresh detections through a temporary cue-map hold. Fixed
memory is used only from a ready cue map; stale frames, malformed contracts and
expired movable sightings still disappear. Displaying a detection never releases
a cue hold or supplies pickup/placement coordinates to the robot.

## Measurements

- Generated states: every `mobile_snapshot` result, including unavailable
  results; build time before diagnostic capture, last/mean/peak and a ten-second
  generation rate. Shared SSE preparation counts once even with multiple clients.
- Outgoing SSE: frames and UTF-8 bytes handed to the HTTP server, snapshot/update/
  keepalive counts, ten-second packet and byte rates, and active/opened/closed/
  failed streams. Each subscriber's emissions are counted independently. The
  module wraps the existing `live.LiveState` response; it does not implement a
  second event stream or change its full/delta envelope.
- HTTP: response count, status errors, body bytes, response preparation time,
  and the submitted action name for bounded JSON commands. Binary assets retain
  only content type and known body size, never image/file content in previews.
- Recent activity: the latest 60 HTTP requests and stream lifecycle events,
  without request credentials, cookies or query strings. The UI displays 20.

These are server-side measurements, not evidence of phone receipt, rendering,
or motion. Gateways can buffer/drop frames; they also count as subscribers.
SSE sizes include framing, before downstream compression; HTTP body sizes
exclude headers. Generated-state sizes use compact UTF-8 JSON, so can differ
from Flask's response serialization. Field sizes describe the redacted sample.

## Shared timeline

Above the payload inspector, six full-width graphs compare Green and Purple
on one rolling 15-second axis: generation rate, outgoing SSE packet rate,
combined SSE/HTTP body bandwidth, mean build time, active streams, and delivery
issues (HTTP errors, failed streams and unavailable generated states).
Each graph has its own labeled vertical scale and both teams use that scale.
Green is solid and Purple dashed. A shared pointer or keyboard cursor compares
the same sample across all graphs (left/right arrows; Escape returns to live).

Rates use counter differences between approximately one-second monitor polls,
not the ten-second averages in the summary cards. Build time is the mean of
builds completed within that interval; an idle interval has no build-time
sample. Missed intervals longer than 2.5 seconds appear as gaps. History ages
out after 15 seconds even while disconnected. It is kept in the browser while
the page is open and clears on reload or module restart. Freezing a payload
does not pause the timeline. Graphs reuse existing monitor reads and counters;
they create no additional player traffic or backend jobs.

## Payload inspector and access

`GET /api/monitor` publishes `mobile.delivery-diagnostics` v1 with counters,
sample metadata and recent activity. Optional `side=green|purple`,
`payloads=1`, and `channel=generated|sse|http` select payload previews. The page,
assets and endpoint require the `gamemaster` role, including when the hub's
shared-API allowance admits a player's request to the module.

Latest payload samples are kept only in memory. Expensive preview capture is
limited to once per second per team/channel, with an immediate sample when SSE
switches between snapshot/update. Credential fields and credential-bearing
URLs are redacted recursively without modifying the outgoing value. Lists and
strings are bounded; each pretty-printed preview is capped at 256 KiB and
explicitly labeled if truncated. The inspector can freeze its payload while
counters continue, switch team/channel, show field sizes and download the
redacted sample as text. Its JSON viewer uses `textContent`.

Monitor reads never call Game, Camera, Progress, or robot modules. They and the
existing connection-log endpoint are excluded from delivery counters. No player
traffic means empty samples and zero rates. Counters reset on `hub_init`; no
new persistent payload log is created. Telemetry capture errors are isolated
from player delivery and counted; server exception logs are rate-limited.

The existing `GET /api/diagnostics` connection-log export remains available
from the dashboard, and the player POST endpoint keeps its current behavior.

## Verification

Run `.venv/bin/python -m unittest discover -s tests -p 'test_mobile_api_monitor.py'`.
For a robot-free browser check, start
`.venv/bin/python tests/mobile_api_monitor_fixture.py` on loopback port 8124,
then run `node tests/mobile_api_monitor_browser.cjs` with Playwright available.
The browser test checks both teams, generated versus emitted envelopes,
freeze/resume, export, stream closure and desktop/phone layouts without POSTs.
Deterministic counter samples also verify graph rates, build means, aligned
spikes/cursors, 15-second expiry, missing intervals and module restarts.

## Optional MCAM1 presentation

Player state/SSE includes `mobile_mcam1` (`mobile.mcam1`, integer version 1).
The facade discovers enabled MCAM1 through hub context and validates its
published `hhh.camera.still` v1 output, JPEG bytes, dimensions and 1.5-second
freshness limit. Only metadata enters game state. `GET /api/assets/mcam1.jpg`
revalidates the frame and returns uncached JPEG bytes under the existing player
team guard and hosted asset proxy. Unavailable inputs are explicit and do not
change game readiness; the frame route returns 503. This path never starts
capture, reads USB controls, or supplies robot/game perception evidence.

## Physical cue evidence

`mobile_cue_targets` carries the Board's `photon.board.cue-targets` v2 evidence in
the existing player state/SSE stream. `GET /api/cue-targets?side=green|purple`
provides the same read-only, team-authenticated evidence for an explicit command
refresh. The facade adds `scope`, `scope_since` and `server_time`, and validates
the owner-acknowledged run/layout or calibration-display scope. Fixed coordinates
learned before a particular reader joins remain available in that same scope.
`fixed_tags` is display memory, separate from current `tags` and motion status. Unavailable
or malformed Board inputs remain unavailable. Neither path reads camera hardware
or issues robot commands. Virtual cues keep their existing simulation behavior.

## Breaker archer projection

The compact player enemy projection retains the additive `combat` variant,
state and timing descriptor. Game's `enemy_combat`, `enemy_arrows` and
`enemy_arrow_impacts` are forwarded without local simulation. The existing
renderer endpoint serves Y's owned bundle, including its archer helper; Level's
published asset allowlist includes the content-hashed red archer atlas.
Offline export integrity and projection checks: `tests/test_ranged_delivery.py`.


## LTZ result/shop delivery (2026-10-10)

The existing player projection forwards authoritative `match_score`, `next_match`, `result_save` and the selected player's Progress `shop`/`latest_result`. Operator `next_loadouts` remains excluded. The published asset manifest adds four explicitly allowlisted shared UI PNGs under `ui/ltz/`; the existing asset route serves only that allowlist. Level-owned upgrade artwork remains accessed through the existing published Level contract. No separate progress, purchasing or hardware API was introduced.

## Delay Analysis (optional recording)

A separate `delay-analysis` manifest page exposes authenticated `delay.analysis`
v1 capture controls, ranked nested timings, incidents, coverage and JSONL/CSV
exports. `hub_init` installs the shared timing recorder; `hub_stop` releases it.
Recording defaults off and toggles at runtime without restarting any game module.
The default duration is until manually stopped. Whole-capture statistics are
checkpointed separately from bounded incident detail, so exhausting the 650 MiB
detail budget warns without stopping summary recording. The latest checkpoint
reopens after restart with recording off. Incident windows retain board validation
evidence and driver failure details; incomplete coverage is displayed prominently.
The regular player state includes a short capture descriptor. The existing
team-scoped diagnostics POST accepts bounded timing batches, including one final
stop acknowledgement, without giving players capture administration access.

See [Delay Analysis](../../../../docs/DELAY_ANALYSIS.md) for lifecycle, timing
semantics, bounds, endpoint examples and verification. Timings are observational;
all robot leases, feedback deadlines and command authorization remain authoritative.

## Motion transition permission (2026-10-12)

Player snapshots include `mobile_motion_policy`, the team's validated
`photon.game.motion` v1 contract from Game. The phone and embedded physical
controller use its ready status, scope and explicit `blocked: false` for
transition admission, retaining their separate freshness, pause, feedback and
calibration checks. Missing or invalid policies fail closed. Calibration
recovery may still connect to confirm a previous stop without granting motion.
Blocked controls show the owner's specific reason, also returned by Relay.

## Linked-game player actions (2026-10-17)

`POST /api/saved-game?side=green|purple` uses authenticated side and same-origin
checks, then calls Photon Game's serialized New/Save/Load operation. The hosted
gateway permits this route. `mobile_progress.saved_games` publishes the active
ID, pair lock and linked-player previews including current credits and upgrades.
The phone exposes these actions between matches. Locked pairs disable individual
selection. A changed saved-game ID clears pending inputs and requires physical
reconnection. Allowed L1/L2 camera mismatches show an approximate-positioning
warning; connected arms blocked from moving are labeled explicitly.
