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

## Physical cue evidence

`mobile_cue_targets` carries the Board's `photon.board.cue-targets` v1 evidence in
the existing player state/SSE stream. `GET /api/cue-targets?side=green|purple`
provides the same read-only, team-authenticated evidence for an explicit command
refresh. The facade adds `scope`, `scope_since` and `server_time`, and filters
observations older than the active level layout or calibration display. Unavailable
or malformed Board inputs remain unavailable. Neither path reads camera hardware
or issues robot commands. Virtual cues keep their existing simulation behavior.
