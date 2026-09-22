# Green mobile LTZ

The hosted player at **https://mecharena.eu/TowerDefence/** uses the same Photon Game as the existing Gamemaster at **http://localhost:8000/s/gamemaster/#laser-tag-y**. There is one simulation. The former mobile game on port 8012 has been retired.

## Play

1. Start the normal Gamemaster, or double-click **Start Mobile LTZ.command**. The launcher attaches the phone relay to port 8000 and opens LTZ. If the main hub is absent, it starts that same hub; it never creates another game.
2. Select Virtual play in Gamemaster. Sign in to Green on the phone. The player automatically joins virtual controls when the game is ready.
3. Start, Pause, Resume and Reset affect the same game on both screens. The battlefield and orcs do not depend on the arm connection. Virtual practice does not award permanent progress.
4. Joint mode uses a base rotation dial, shoulder and elbow sliders, fine tune, and Suck/Blow buttons. The arm illustration and red markers show actual movement. To try XYZ, enable **Virtual test unlocks** in Laser Tag Y, choose **Cartesian XYZ** in **Mobile control unlock**, and Apply. The phone automatically selects the highest implemented unlocked control: Cue for tier 4, Targeting for tier 3, XYZ for tier 2, or Joint for tier 1. This also applies on refresh or reconnect. You can select Joint manually from the control menu for the current connection. The horizontal X slider and vertical Y slider along the full upper-right edge move the green target bullseye; the thin red bullseye shows actual position. They turn orange when XY aligns. Dashed cross lines follow both bullseyes across the screen. Connect and Stop align with the left edge of the Z control; the shorter Z slider starts beneath them, with a red actual-height marker. Beside Z, hold square button **1**, **2**, or **3** for three seconds to save the selected height on this phone; tap a stored button to recall just Z. Stored buttons change color, and light track markers connect to them with dotted lines. Fine tune uses a tenth of the range. Invalid coordinates show feedback and restore the accepted target. Changing control modes freezes the arm at its current position. The zoom toolbar is removed; two-finger pan/pinch still moves only the camera.
5. Brief interruptions freeze the simulated arm and automatically rejoin when fresh game state returns. Returning from the background or refreshing also rejoins. Unfinished movements and ambiguous pump commands are not replayed.
6. **Stop** explicitly disables automatic joining, including after refreshing or starting another wave. Press **Connect** to resume. Other tabs can still watch the game.

Joint, Cartesian XYZ, Targeting, and Cue autonomy are functional when unlocked. Targeting replaces X/Y sliders with finger dragging, keeping height and presets. Cue autonomy opens the right-side piece → marker editor with +/− rows, Play/Pause, Stop, and a compact active-row view. Game settings configure Green IDs (100/101) and Purple IDs (102/103), preserving their weapon roles. Every level target is reachable in simulation at heights 0–400. Tap the map to insert a blue waypoint before the current green cue destination; tap again to replace it or × to cancel. Paused cues stay paused, and idle cues wait for Play. The single Play/Pause toggle is retained in both drawer views. Unavailable markers still show a row error. Virtual overrides never award permanent progress.

## Services and updates

From the repository directory:

```sh
tools/mobile-ltz/Start\ Mobile\ LTZ.command start
tools/mobile-ltz/Start\ Mobile\ LTZ.command status
tools/mobile-ltz/Start\ Mobile\ LTZ.command restart
tools/mobile-ltz/Start\ Mobile\ LTZ.command stop
```

The shared game is on port **8000**, the restricted relay on **8118**, and the local ngrok agent on **4040**. Stopping or restarting the relay leaves the main Gamemaster running. `game_server.py` is only a compatibility launcher for this arrangement.

Restart the **main Gamemaster** to publish changes to its game code or frozen mobile UI. Every game-server launch creates a new mobile build. DreamHost `index.php` obtains that current build on refresh; both the root URL and old `index.html` bookmark use it. Old build URLs return 409. HTML and UI files use no-store headers. PHP/hosting-rule changes still require deployment; ordinary UI changes do not.

On startup the hub publishes its existing Green service identity atomically to private `.mobile-ltz-runtime/client-auth-8000`. The relay reads that port-specific identity only for fixed frontend routes. A separate development hub cannot overwrite the main hub's identity. Game data and controls still require player login. The relay permits no arbitrary URLs, administrator commands or hardware routes. The simulated arm remains in Photon Game, guarded by virtual-play mode.

Private credentials, logs and generated bundles stay in `.mobile-ltz-runtime/`, outside Git. Do not upload that directory. `export.py` exports published artwork and hosting files from the main hub and excludes `bridge-config.php` from the ZIP. The public deployment bundle in `output/mobile-auto-update.zip` contains only `index.php`, `api.php` and `.htaccess`.

## Connection behavior

SSE packets carry the `hub.live` version 1 JSON envelope with an explicit snapshot/update kind, run ID and level revision. Lost event labels cannot turn a delta into a scene replacement. The relay forwards complete frames, disables compression buffering and rotates streams after 55 seconds. One client retry owner handles reconnects and bounded snapshot recovery.

The virtual arm's five-second heartbeat deadline freezes motion and turns its pump off, while retaining resumable player ownership. A new join rotates the command token so delayed movement or suspension requests from an old connection cannot affect the resumed session. Repeating an ambiguous join request is idempotent. A stale, suspended controller can be replaced after its deadline; an active controller cannot be silently taken over. Pause, reset and physical mode revoke control, and the phone automatically rejoins when virtual control becomes available again.

The player stores its private join identity and explicit Stop preference in browser storage. Neither the identity nor the command token appears in broadcast state. Command responses carry a server timestamp so older buffered state cannot immediately undo a successful join.

Missing artwork descriptors retain the last usable images. New revisions load into staging caches and commit together. Stale recovery responses and obsolete image loads cannot restore old artwork.

## Enemy movement

The shared Canvas renderer keeps three seconds of timestamped enemy poses (plus
one bracketing sample, capped at 256 samples per enemy). Normal playback runs
300 ms behind the estimated simulation clock initially. The buffer adapts between
250 and 450 ms using recent update cadence and delivery jitter. It increases by
at most 40 ms per second and decreases by at most 15 ms per second; playback never
rewinds when the target buffer changes. The
clock uses simulation timestamps and a rolling arrival offset; each packet does
not restart movement. Monotone cubic interpolation uses endpoint velocities to
follow sampled turns without overshooting their bounds. Facing takes the shortest
rotation. Unobserved turns during a network gap cannot be known in advance.

Snapshots publish the additive `photon.enemy-motion` version 1 contract. Each
enemy gets a bounded guide containing mode, speed, topology revision and at most
12 upcoming points. Road guides use the engine's rounded, offset, rerouted paths;
orbit guides follow an offset of the authored core silhouette. These are movement
intent, not guaranteed future collisions or combat results. Known stalls, pauses
and obsolete barrier routes publish a hold instruction.

If playback exhausts its buffered samples, valid guides maintain speed through
1.2 seconds of prediction, then brake over 200 ms. Prediction stops at the guide
endpoint if it runs out sooner. Legacy snapshots without guidance retain the
150 ms coast/500 ms stop fallback; malformed new guidance holds. Small corrections
decay with a 180 ms time constant and follow the guide when a nearby route
projection exists. Disconnects freeze presentation; fresh data reconciles it.
Pause, run/map changes and large teleports reset movement history. Only positions
and facing are smoothed: health, damage, deaths, enemy membership and scores remain
the latest server truth. Attached beam/zap effects use the same visual positions.

Three seconds of **history** does not add three seconds of input or display delay.
A caller can explicitly set `enemyInterpolationDelay: 3` on `TowerDefenceView.create`
for actual three-second-delayed movement. An explicit delay disables adaptation;
omitting it enables the adaptive default. That longer delay
makes visible positions substantially older than authoritative combat outcomes.
The renderer is served with no-store headers. HUD changes are frozen with the
mobile build, so restart the main server once after updating the UI, then refresh
the phone. No DreamHost upload is needed for these renderer/UI changes.

Below Score/FPS, **Updates** shows received snapshots per second over the last five
seconds; **Age** is time since the latest received snapshot (not network ping);
**Pred** is the percentage of moving frames using prediction in the last sample;
**Buffer** is the current playback delay; **Peak** is the longest frame interval
in the last sample. Age turns amber above 500 ms; Peak turns amber when a frame
interval exceeds 34 ms. Readouts refresh once a second and clear on tab visibility
changes. Detailed timing is available in the readout's hover text and the browser's
read-only `window.mobilePerformance`: source/relay/receive gap maxima, snapshot
build time, correction distance and packet sequence. These measurements diagnose
delivery gaps separately from rendering stalls; they are not absolute network RTT.

For the hosted player, an authenticated state response also offers a ten-minute
`mobile.stream` version 1 read-only URL. The live SSE feed then goes directly to
the existing tunnel, bypassing PHP response buffering. The page, login, commands
and snapshot recovery remain on DreamHost. The opaque token is held only in page
memory and in the gateway's bounded token table; it contains no bridge key or
hub cookie, permits only GET `/live/events`, and requires the hosted page's Origin.
Active streams close at expiry. The client renews before expiry and falls back to
the hosted SSE route after repeated direct failures, retrying direct delivery
after a cooldown. No extra DreamHost deployment or public control endpoint is needed.
The direct feed uses streaming Fetch with the tunnel's browser-warning bypass
header and authenticated CORS preflight. Its bounded SSE parser handles split
UTF-8 and multiline events; HTML warning/error pages never become game state.

`photon.delivery` version 1 marks snapshot preparation and relay arrival. Mobile
enemy packets omit internal lane bookkeeping and round numeric fields to three
decimals while retaining authoritative health and effects. The gateway keeps one
pending owned update per subscriber and merges queued updates while retaining full
scene changes and latest enemy membership. Unknown frame types use a bounded
two-frame fallback. The phone merges received state immediately and applies the
latest presentation once per animation frame. Already queued transport bytes cannot
be recalled, and sustained outages can still exhaust prediction.

Run `python tools/mobile-ltz/measure-delivery.py --seconds 20` for a read-only
comparison of local, gateway, tunnel and hosted SSE delivery using the configured
Green login. It reports packet sizes, gap percentiles and relative excess delay;
it never starts a wave, joins controls, or prints credentials. Keep the current
approximately 6.7 updates/sec until delivery measurements justify a higher rate.

## Verification

- `python -m unittest discover -s tests -p 'test_mobile*.py'`: virtual controls, heartbeat suspension, resumable ownership, idempotent joins, stale command rejection, identity validation, Stop, modes, authorization, relay framing and launch-specific UI builds.
- `node tests/mobile_game_sync.test.js`: lost event labels, scene retention, Start, stale snapshots and recovery.
- `node tests/mobile_live_feed.test.js`: single retry owner, bounded recovery and lifecycle behavior.
- `node tests/mobile_artwork_renderer.cjs`: artwork retention, atomic replacement and superseded loads.
- `node tests/photon_motion_renderer.cjs`: timestamped motion, jitter/batches, turns, bounded prediction, correction continuity, pause/reset, authoritative deaths and actual Canvas integration.
- `tests/mobile_diagnostics_browser.cjs` against the isolated fixture: live readouts, frame-spike detection and four touch-screen layouts, without joining controls.
- `python -m unittest discover -s tests -p 'test_enemy_motion_guides.py'`: route bounds, read-only guidance, core clearance, stale barriers, stalls and mobile timing contracts.
- `tests/mobile_guided_motion_browser.cjs` against the fixture: repeated 900 ms/1.2-second gaps using the actual Canvas loop, then authoritative reset.
- `node tests/mobile_stream_parser.test.js`: streaming Fetch, UTF-8 boundaries, event framing, HTML rejection and cancellation.
- Run `tests/mobile_ltz_fixture.py`, then `tests/mobile_auto_join_browser.cjs` with Playwright: automatic joining, joined-page refresh, Start/orcs, Pause/Resume/Reset, a seven-second outage, no pump replay and Stop persisting across refresh and a new wave.
- `tests/mobile_phone_browser.cjs`: malformed responses, silent streams, FPS and explicit cancellation of join retries.

Physical-phone verification is intentionally left to the user for this revision. Browser tests use an isolated virtual fixture; deployed-page checks compare the hosted player with the shared main hub without starting a test wave on it.
