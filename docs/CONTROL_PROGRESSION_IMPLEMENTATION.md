# Mobile progression implementation and verification

Delivered in the working tree on **1 October 2026**, following the user's approval
to implement [the plan](CONTROL_PROGRESSION_CALIBRATION_PLAN.md). Existing local
changes and calibration data were preserved. No live hub, robot movement, hosted
deployment, or human gameplay trial was performed during implementation.

## Player flow

Both Green and Purple now use the same mobile client and separate authenticated
team routes. Players choose an existing name or create a profile in the picker.
Purchases, credits, mastery, required control tier, and history follow the profile
when it changes teams. One profile cannot occupy both teams at once.

Normal play requires the saved current tier: Joint, XYZ, Targeting, then Cue.
Three qualifying wins advance a tier; failures do not erase wins or downgrade
controls. Cue remains the final tier. Practice never changes earned progression.
Each scored game has one combined score and result; each participating profile
receives the existing full kill-credit reward. Delivery retries do not duplicate
rewards or history.

After a result, both players share one server-owned **30-second** upgrade timer.
The third XYZ win immediately starts calibration, with **Green first, Purple
second**. Only the active side controls the unified playfield. Its partner stays
on upgrades and sees a waiting message. Purchases remain available during that
wait, while player identities are reserved. The original timer is retained:
completing calibration does not add another 30 seconds.

Each player's lesson requires six fresh measurements at markers **30–35**.
Durably saved captures light green; old captures do not start green in a new
lesson. Four outer markers **31, 35, 33, 34** also require ground and raised-Atom
samples. The saved rig model survives games and restarts and bounds Joint/XYZ
movement as well as later controls. A new player still completes the required
lesson. Camera/device changes invalidate physical readiness.

Targeting teaches tap to preview, then explicit **Go**. Height and pump actions
remain separate. As updated on 2 October, **Complete calibration** validates six
fresh arm captures and four raised samples, calculates pickup Z from the mean
of the six captured Z positions and transport Z as pickup plus 40 mm, then
advances the shared journey after a confirmed stop. Guided arrivals, pickup and
Board-verified placement remain optional practice. A browser claim alone cannot
finish the lesson; the calibration owner validates the measurements and issues
the completion receipt.
Raised-Atom pickup uses the existing perspective correction once, after lens
correction. Phone rotation only changes presentation. Missing correction or
unsafe/stale physical data prevents movement.

## Using the implementation

1. Restart the hub through its normal operator workflow to load the updated
   modules and client bundles. Enable Photon Level, Board, Game, Progress, Mobile
   LTZ API, and both teams' Mobile LTZ presenters. Physical lessons additionally
   require Webcam, Camera Calibration, Auto Pickup Game, Playfield Areas, the
   MG400 Relay, and the appropriate team's LTX controller.
2. Open `/s/green/p/mobile-ltz/` and `/s/purple/p/mobile-ltz/` after the appropriate
   sandbox login. Select two different saved names or create two players.
   Both players confirm **Ready**, then the Game Master starts the scored game.
3. Physical play requires an already commissioned, valid rig calibration and
   current camera/relay feedback. Restore or commission it through the existing
   operator tools if the readiness message says it is unavailable.
4. In Laser Tag Y's **Unlocks** panel, check **Use test unlocks**, choose a
   **Mobile control unlock**, and press **Apply test unlocks**. This applies to
   **both Green and Purple**, selects the corresponding default control mode,
   and permits testing through that tier in virtual and physical practice.
   Joint, XYZ, Targeting, and Cue were all verified for both teams. If the current
   game has ended, use **Reset** to return its simulation to setup first.
   The LTX player tab now defaults to **LTZ player controls**; its separate
   **Laser Tag X controls** link retains the older game's controls. The LTZ Score
   **Open player controls** link reaches the same LTZ mode. Both ordinary player
   windows receive Game's live overrides and include the interactive joint
   schematic; the score window identifies these overrides as practice access.
5. Use **Test Green calibration**, **Test Purple calibration**, or **Test
   calibration · Green then Purple** to open a lesson manually. These tests do
   not award wins or unlock earned controls. Exclusive calibration still blocks
   the waiting arm, even with test unlocks enabled. **Cancel calibration / ready
   transition** releases the field after confirmed stopping and restores the
   prior journey. Disable test unlocks before a scored game.

The hosted gateway and PHP facade support team-bound player, journey, history,
and stream requests. Export includes the progression/calibration/stats bundle
inside the established `mobile.js` allowlist. The isolated export test verified
this without contacting the live hub; the hosted release still needs its normal
export/deployment workflow to publish these changes.

## Statistics and settings

The mobile **Players · Upgrades · Stats** panel includes purchases, shared score,
score history, completion-time history, filters, and inspectable game details.
Combined history counts each run once. Filters include scored/practice, control
tier, side at the time of the game, map, and date range. Graph points support
touch and keyboard inspection; the table provides the same information.
Trend lines and trailing three-game means remain inside comparable map,
settings, and loadout cohorts. Details retain both players' frozen tiers and
upgrades, map/preset settings, first placements, pauses, and calibration
milestones. Older unknown durations remain unavailable.

In Photon Game's settings tab, choose a map/tier and a preset name, edit settings,
and **Save**. Saved presets have immutable identities/revisions; **Load** selects
a saved revision for that tier. **Rename** creates the corresponding revision;
**Restore defaults** clones the originally commissioned progression defaults.
The ordinary settings draft and selected tier preset are identified separately
in the UI. Changes never rewrite the configuration of a running game.

The difficulty adjustment supports **−10%, −5%, 0, +5%, +10%**, applied once to
rounded enemy counts. Each higher tier's selected progression preset must have
more orcs, shorter wave intervals, and faster releases. Mixed-tier co-op uses the
higher current tier's preset and records both participant tiers. Buying upgrades
does not secretly increase difficulty or change robot speed.

## Balance evidence

The supplied `pickup-game/pickup-log.csv` contains **38 results / 17 display
names**, dated **15–17 June 2026**, ranging **4.22–871.24 seconds**. It has no
control-tier, settings, or loadout columns and no rows in the requested four-day
window around 20 August. The audit preserves every source row and its file hash.
No pooled median or claimed measured control-speed improvement was used.

The selected **Provisional 25-minute progression** presets use a 300-second
preparation interval, a 95-second starting wave gap, and explicit design count
and pace factors of **1.00, 1.08, 1.16, 1.24**. These factors are provisional
settings, not historical measurements. The same placement trace was tested at
all tiers: four owned Atoms near the core at 180/240/420/480 seconds,
replenishment from 600 seconds every 120 seconds. The slower-partner case delays
Purple by another 120 seconds. This trace excludes pauses and missed pickups.

| Tier | Released orcs | Base completion / core remaining | Maximum upgrades completion / core remaining |
| --- | ---: | --- | --- |
| Joint | 1,009 | 1,414.4 s / 45.2% | 1,410.0 s / 60.9% |
| XYZ | 1,088 | 1,334.2 s / 34.4% | 1,329.1 s / 53.5% |
| Targeting | 1,170 | 1,272.0 s / 21.7% | 1,268.4 s / 43.7% |
| Cue | 1,250 | 1,211.9 s / 13.0% | 1,209.7 s / 34.8% |

All eight base/maximum cases won; the Joint slower-partner case also won in
1,414.4 seconds with 42.4% core remaining. Peak active enemies were 116–160 and
deferred backlog was zero. This supports simulator feasibility and a first-run
duration near 1,500 active seconds. It does **not** establish human completion
rates, physical placement accuracy, or that maximum upgrades feel easy.

The complete reproducible record is [CONTROL_BALANCE_REPORT.json](CONTROL_BALANCE_REPORT.json).
Run `.venv/bin/python tools/progression_balance.py` to regenerate it using the
actual Level and Game engine, temporary stores, a fixed seed, and 0.1-second
simulation steps. The tool opens no camera or robot.

For the human pilot, record at least 20 first-time co-op runs with both player
IDs, tier, map/preset/settings revision, frozen loadouts, score, active duration,
first placements, pauses, missed pickups, and outcome. Check the plan's proposed
1,350–1,650-second novice window and base/max completion-rate targets; include
slower partners. Use the matching cohorts for subsequent tier tuning. Import
the original method-labelled August results when available to replace the
unmeasured speed factors. Optical calibration and outer-point pickups still
require a supervised physical trial on both arms.

## Architecture verification

This verifies the feature's consumed paths, not every historical prototype.

| Owner | Implemented responsibility / boundary |
| --- | --- |
| Photon Progress | Schema-2 profiles and backup, mandatory tier policy, transactional purchases/rewards/roster reservations, deduplicated history; `photon.progress` v2. |
| Photon Game | Simulation, immutable run settings, journey and shared timer, lesson ordering, practice grants, result reconciliation; Game v2, journey/motion v1. Cross-owner calls occur outside the local state lock. |
| Auto Pickup Game | Durable calibration drafts, six-point/parallax validation, atomic rig commit, fresh measured lesson evidence, safety bounds and exclusive leases; documented Cal 2 v1 contracts. |
| Playfield Areas | Owned reservation and display replacement/restoration, saved capture glows, guarded field mutations; `hhh.playfield` v1. |
| Webcam / Camera Calibration | One camera capture; public named raw frame/status/tag/control contracts replace private manager/tracker access. Camera Calibration owns lens correction and atomic lens persistence. Disabled, malformed, and stale inputs become unavailable. |
| Board | Fresh physical placement remains gameplay evidence under its existing v1 contracts; no duplicate TPS/parallax authority added. |
| MG400 Relay / LTX | Existing physical command path, server practice/tutorial checks, calibrated path bounds, stop acknowledgement and lease expiry. Relay watchdog starts/stops with hub lifecycle. |
| Mobile LTZ / Laser Tag Y / gateway | Shared presentation, authorized commands, bounded public snapshots, existing SSE, per-team sessions; no browser scoring, timer authority, or new robot driver. |

Durable result receipts survive delivery retries. Lost calibration-release
acknowledgements replay completion without repeating Green's completed turn.
Restarted drafts do not retain live movement grants. Interrupted scored runs
recover into the shared upgrade flow; missing stop acknowledgement retains
exclusive ownership and blocks Purple. Ready reservations freeze participant
identity and upgrade revision; calibration identity reservations still permit
waiting purchases. JSON stores use atomic replacement and publish only after
successful persistence.

## Verification record

- **402 Python tests**: full `unittest` discovery, including progression,
  authentication/isolation, both-team unlock matrix, calibration durability and
  field ownership, presets, reward/restart recovery, public camera boundaries,
  hosted export, and malformed/expired reservation rejection before motion.
- **36 JavaScript tests**: calibration degeneracy/rotation, mobile state/network,
  controls, dragging, framing, and coordinate transforms.
- **Both-team physical bridge smokes**: fake relay only; origin, session,
  revision, tier gates, calibrated XY/Z, raised-Atom identity/freshness, stop,
  expiry, and pump-off.
- **Chrome mobile fixture**: actual GM-selected Joint/XYZ/Targeting/Cue defaults
  for Green and Purple; score/time graphs, cohort means, keyboard details,
  purchases and filters; six saved-marker glows, capture actions and waiting
  screens at portrait and landscape phone sizes. No page errors. Screenshots
  inspected for readability. Uses temporary stores and synthetic imagery.
- **Balance**: the nine engine scenarios above, with original CSV row audit.
- **Static checks**: changed JavaScript/inline scripts parse; `git diff --check`.

The test suite uses the existing project virtual environment and bundled
dependencies; no dependency installation was needed. No claim of hardware or
human-pilot acceptance is included in these automated results.

### Player-window regression correction — 1 October 2026

The user reported that unlocks failed in player controls and the joint schematic
appeared only in Mobile LTZ. The previous verification covered the mobile
adapter, but the ordinary `ltx/?ltz=1` view still consumed Progress's earned tier
and omitted Game's practice grant. Its old regression script also read a legacy
controller copy instead of the file actually served by LTX.

Ordinary and embedded LTZ controls now consume the same scoped Game facade and
SSE envelopes, with freshness checks and recovery. Practice changes stop old
motion intentions, required tiers are restored when the override is removed,
and exclusive calibration waiting remains enforced. Both LTX defaults select
LTZ mode, and both LTZ Score screens show practice availability without changing
saved mastery. The hub's default shared API now admits Purple to Mobile LTZ too.

The reused joint schematic drives the existing guarded joint command queue and
shows selected targets separately from measured robot angles. It disables
gestures on stale/disconnected feedback, hidden panels, or an unavailable game
scope. No physical command path was added. The new browser regression exercises
the actual Game Master button, both ordinary player windows, both score windows,
all four tiers, schematic keyboard motion through a fake transport, and override
removal. Earlier physical-accuracy and human-balance limitations still apply.

### HTTP player creation and test profiles — 1 October 2026

The reported `crypto.randomUUID is not a function` came from unguarded receipt
generation in both Score pages and the shared mobile creation/purchase UI. A
shared presentation helper now uses native UUIDs when available, random bytes
on HTTP-compatible Web Crypto, or timestamp/counter/random receipts otherwise.
Both mobile launch bundles and hosted exports include it. Creation and selection
now use one Progress transaction, so a locked roster cannot leave an unwanted
new profile behind. Mobile's control-path menu can open Players/Upgrades/Stats
while a Game Master practice override is selected.

Progress seeds selectable Test player · Green and Test player · Purple profiles
with stable, owner-classified IDs. Any run containing either is practice for the
whole co-op roster, including a real partner, even if scored play was requested.
Practice checkpoints, outcomes, retries and recovery do not alter either
profile's earned totals. Scored history and its difficulty-comparison cohorts
exclude these runs; Practice history retains them. Classification survives
backup/restart, and test profiles use the existing Game Master tier/loadout
overrides rather than earned upgrades. Browsers show the exclusion explicitly
and switch selected test profiles to Practice history, discarding stale history
responses after a profile/filter change.

Validation: the 410-test Python suite passed, followed by two new authenticated
API tests and the affected bundle/export checks. All 39 JavaScript tests passed.
Chrome verified creation and test selection in both teams' Score and mobile
pages with `randomUUID` disabled; the Score check also exercised the no-Web-
Crypto receipt fallback. Both existing browser regressions passed: ordinary
player controls and Game Master tiers 1–4, plus mobile tier controls, history,
calibration markers and waiting behavior. No page errors; screenshots inspected.
Fixtures used temporary stores and fake transport. The live hub was not restarted.

### Review against the approval plan — 1 October 2026

This follow-up reviews the implemented paths against
`CONTROL_PROGRESSION_CALIBRATION_PLAN.md`, including the reported Game Master
Start/control failures and calibration showing the battlefield. It corrects the
earlier verification claim: mocked calibration presentation and reconnecting
before each bridge test did not exercise the failures below.

| Finding | Correction and evidence |
| --- | --- |
| Auto PP Cal 2's fixed/saved target templates omit Playfield runtime IDs. The lesson passed those templates to `replace_areas`, which rejected them. It also omitted the fixed camera settings. | Auto Pickup loads its existing fixed six-target template, assigns session-local stable IDs, and passes its geometry/settings through `hhh.playfield` v1. A regression uses the actual ID-less template. No combat-map coordinates are copied into calibration. |
| Calibration presentation mixed the operator camera with the projected target renderer. | The GM stage uses its existing corrected camera preview at full frame. Only the external Y screen mounts the owner's exact target-screen descriptor, in read-only presentation mode; unavailable targets show a waiting/error surface. Manual/replayed lessons enter physical camera presentation; mobile resets the game crop, hides combat overlays, and retains guarded controls. |
| Capture color/glow was saved on a hidden target body with bloom disabled. | Accepted captures reveal the green surround and use bloom; marker pixels and their quiet border stay in Playfield's sharp overlay pass. The actual WebGL display was visually inspected. A frame predating target activation cannot be captured. |
| Fresh camera/arm prerequisites were checked before displaying targets. Failed setup could leave an uncancellable display-only reservation. | Targets load first; absent feedback grants no motion. Cancellation identifies the reserved turn even before a lesson exists, requires Relay's stopped acknowledgement, and restores through Playfield's owner. |
| Continuous LTX telemetry kept `sample()` from running, which prevented physical bridge mode changes. Missing physical geometry also left the phone displaying its previous mode. | Every bridge snapshot synchronizes the selected mode and revokes the previous motion lease. Phones present Game's assigned schema independently while movement waits for matching mode/feedback. Both bridges are tested with uninterrupted telemetry and no reconnect between selection and acknowledgement. |
| Incoming Y snapshots could overwrite an edited test-tier selection or undo a newer command response. | Keep unsent selections intact, freeze the entire command before rendering, and discard older state. Actual GM buttons now switch Joint/XYZ/Targeting/Cue for both ordinary and mobile player windows. |
| Test overrides left Scored selected; practice bypassed ready-roster reuse and never entered the playing journey, leaving the player lobby visible. | Applying practice overrides selects practice Start. Game handles practice lifecycle and existing roster reservations, blocks Start during calibration/intermission, and returns practice results to the lobby. Scored play still requires both explicit Ready confirmations. Start rejection reasons remain beside the button. |
| A live pending aborted result at sequence 75 conflicted with an earlier synthetic recovery interruption at sequence 63, blocking Progress recovery. | Progress can replace only a synthetic interrupted result with a strictly newer, nondecreasing durable terminal result. The prior result is retained for audit; attempts/rewards are not counted twice. Ordinary terminal conflicts remain rejected. A late XYZ milestone still opens calibration once. Tests reproduce the recorded practice race in temporary storage. |
| A Progress recovery error starved independent calibration maintenance. | The existing owner worker runs journey/lease maintenance even when score recovery fails and exposes errors. No second timer or hardware path was added. |
| Name entry occupied the full upgrades/history screen. | Both teams use a compact glass-styled saved-name/new-name box. Upgrades and statistics open separately; practice can return to controls. Starting the game closes the lobby. HTTP UUID fallbacks and selectable practice-only test profiles remain covered. |

**Architecture assessment:** These changes retain the plan's owner boundaries:
Game owns phases and Start, Progress owns transactional results/profiles, Auto
Pickup owns templates/measurements/lessons, Playfield owns target persistence and
rendering, and Relay/LTX remains the sole motion path. Integrations use enabled
public producers and named integer-version contracts. Calibration maintenance
continues on the existing lifecycle-owned worker. Y and mobile only present
owner facts. No new sibling imports, camera acquisition, browser rewards,
independent deadlines, or robot drivers were introduced. This is a review of the
touched feature, not certification of every legacy prototype.

**Test isolation correction:** `test_calibration_display.py` redirected settings
and display-session storage but left `AREAS_PATH` pointing at the venue file.
The existing test therefore wrote its fixtures into the saved field. All three
paths now use temporary storage. The six-target venue layout was restored
exactly from the running Playfield owner's read-only in-memory snapshot; the
before/restore snapshots were retained in `/tmp`. No venue profile database,
calibration model, or robot commands were changed for this repair.

**Validation:** Full Python discovery: **422 passing tests**. JavaScript suite:
**39 passing tests**. Both bridge smokes pass. Chrome exercises actual GM Start,
all four modes for both mobile players, all three manual calibration choices,
real Playfield target rendering, durable green capture, waiting partner, blocked
Start during calibration, and display restoration. The ordinary LTX/Score mode
matrix and HTTP/test-profile regressions also run against temporary stores and
fake robot transport. Screenshots cover the name box, mobile lesson, Y stage,
and external target display. The phone camera in these checks is synthetic;
its images are not physical accuracy evidence.

**Remaining plan gaps:** The complete automatic introduction/unlock reveal and
the detailed pre-Start roster/loadout/preset summary are not separate finished
screens. The physical bridge still requires a local authenticated hub page;
hosted physical-control parity and deployment are not complete. Real display/
camera alignment, supervised outer-point pickups on both arms, and novice
25-minute balance remain unverified. Historical CSV rows still lack control-tier
labels, so no measured tier-speed factors or pooled median were introduced.

The venue process was inspected read-only and was not restarted. Its pending
result will reconcile through the owners after a normal hub restart; refresh
both player pages to load the frozen client bundles. Physical Start continues
to require fresh Board/camera evidence. The observed stale-camera condition is
an operational prerequisite, not something bypassed by this code change.

## XYZ increments and connection handoff — 2026-10-01

Added matching arrow controls to the shared mobile UI: X/Y ±10 map units in
Cartesian XYZ, Z ±1 in XYZ/Targeting/Cue. Fine tune now divides these arrow
increments by ten (follow-up correction below). Height requests keep measured
physical XY unchanged and use the
existing calibrated LTX planner; manual Cue height works only when the cue is
stopped. Short landscape layouts place the status log beside Connect/Stop to
keep both height arrows, the slider and pump controls separate.

Reproduced a control-tier change calling the bridge's full disconnect path.
Mode changes now cancel old intent, increment the revision and confirm a hold
while preserving the existing session. Pending holds disable movement. A failed
hold, stale feedback or game-state failure still stops control. Stale commands
from the previous revision cannot resume motion or disconnect a healthy new
mode. Verified Cartesian boundary rejections use the existing recoverable
motion-limit path, just as guarded joint rejections do.

Read-only venue diagnosis also found Green's relay connected, enabled and fresh
while Game reported `overrun`. The UI now explicitly explains that Reset is
required before reconnecting after game end. No live robot commands were sent.

Architecture remains unchanged: Game owns tier/session admission; shared mobile
code owns presentation; the same team's LTX owns calibration and planning; the
existing Cartesian controller/relay owns robot delivery and safety. No sibling
file access, new motion transport, persistence format or module lifecycle was
introduced. The optional `height_only` command flag and `control_pending` state
extend the existing same-origin mobile-arm contract.

Validation: 61 mobile Python tests and all 39 JavaScript tests pass. Green and
Purple bridge smokes cover same-session handoff, pending/failed holds, stale
revisions, Cue height-only admission, preserved measured XY and boundary/fault
classification. Arrow smoke covers fractional/rapid taps, Fine tune steps,
limits and blocked input. Chrome verifies both teams through actual GM switches,
direct XYZ reconnect, physical and virtual arrows, ended-game messaging, and
390×844 / 844×390 / 667×320 layouts without page errors. Screenshots were visually
checked. Physical transport and sensor data were simulated; no live motion was
used. The frozen mobile bundles require a normal hub restart and player refresh.

## Boundary recovery and Fine tune follow-up — 2026-10-01

QuickTime inspection showed the phone's old XYZ slider-only layout. The user
confirmed a phone refresh made the existing arrows visible. No further layout
change was needed. Fine tune now divides X/Y arrows from 10 to 1 map unit and
Z from 1 to 0.1 height unit, including Targeting/Cue height. Arrow numbers and
accessibility labels match the active step.

The Cartesian relay used to reject the current pose at the first path sample
after a boundary overshoot, so reconnecting alone could not permit a retreat.
Client and relay now permit only a bounded, monotonic return to a valid target
from a measured overshoot up to 10 mm. Larger excursions, unsafe destinations,
deeper excursions and a second boundary crossing remain blocked. Known geometry
errors carry `motion_limit` through LTX and retain the held mobile session;
unknown faults and failed holds still stop it.

XYZ and manual height hold at blocked direct paths. Targeting and Cue use the
existing arc/grid detour planner, with cached validated calibration geometry.
The planner uses the calibration owner's captured robot-space hull, matching
the relay envelope instead of extrapolating beyond the six measured points.
Planning no longer nudges the arm before validating the requested route, and
the mobile watchdog cannot start a competing recovery route. Long running XYZ
requests retain their reply timeout only with fresh same-session progress for
the exact command ID, bounded by three minutes; existing freshness watchdogs
remain unchanged.

Module ownership is preserved: calibration supplies the envelope, LTX plans,
the relay checks and executes, and mobile presents state. No new robot driver,
sibling file access, stored progress, balance settings or gameplay admission
changes were introduced.

Validation for this follow-up: 61 mobile Python tests, four Cartesian recovery
tests, one reservation regression, all 45 JavaScript tests, both team bridge
smokes (including long-command expiry), and physical/limit/Joint/XYZ step smokes
pass. Chrome checks both teams through GM control switches, normal/fine arrows,
XYZ reconnect, boundary rejection/retreat, relay rejection, Targeting detours and
fatal-fault disconnection without page errors. Screenshots were inspected.
All movement was simulated against temporary data. The venue hub was not
restarted; restart it normally and refresh both phones to load the frozen UI.

## Purple orientation audit — 2026-10-01

The in-game calibration loader bypassed Auto PP Cal 2's orientation handling and
copied its fixed target template unchanged for both players. It now places
Purple's six markers at the 180°-rotated X/Z coordinates, relative to the saved
template orientation. Marker identities, size, fresh-frame requirements and
capture glows are preserved. Rotation belongs to the calibration owner and is
sent through Playfield Areas' existing exclusive display contract; rotating an
iframe or the phone alone would not fix physical target placement.

| Audited surface | Result |
| --- | --- |
| In-game calibration, including GM Green/Purple/Both test buttons | Fixed target layout, draft orientation and resume handling. Green remains first for Both. |
| Ordinary LTZ controls opened from the score page | Fixed Purple's default camera orientation. LTZ now has its own team-specific view preference, separate from old commissioning preferences; explicit player overrides persist. |
| Cue marker numbers | Fixed the label offset so numbers remain below the displayed marker after rotation. Text remains upright. |
| Mobile XYZ sliders/arrows, fills and measured-position markers | Already corrected in the preceding update; use current viewport direction with tenfold fine tuning. |
| Targeting preview, Go, Cue waypoints and pinch/pan | Correct: inverse viewport mapping converts touch back into canonical coordinates. Purple browser flows passed. |
| Turret selection, direction/range handles and camera registration | Correct: uses viewport projection and inverse projection. Purple virtual/physical-mode tests, stale-camera handling and reconnect passed. |
| Camera, bullseyes, calibrated reach boundary and exclusion areas | Correct: all world overlays share the view transform. Boundary and bridge tests verify no double rotation. The hidden bridge remains in the camera frame. |
| Raised-Atom perspective samples and saved poses | Correct: raw corrected-camera samples are transformed consistently at use time, once. Do not rotate stored robot poses or apply perspective correction twice. |
| Joint schematic, Z/height, pump, numbered presets, upgrades and score/history UI | Keep upright. These describe robot joints, height or menus rather than playfield X/Y positions. |
| Standalone commissioning Auto PP Cal 2 | Already follows the gamemaster's explicit orientation setting. The in-game lesson now supplies the fixed team orientation independently. |

Checks used temporary profiles and fake sensors/robot transport: nine calibration
display tests, 24 journey tests, four capture-validation tests, four client bundle
tests, calibration/boundary/viewport JavaScript checks and the Purple bridge
smoke. Browser checks exercised GM-selected calibration, captured glows, screen
restoration, ordinary Green/Purple tier changes and saved view overrides, Purple
Targeting, Cue touch waypoints, label placement in both orientations and turret
aiming. Projected Green/Purple screenshots were inspected; browser runs had no
page errors. No physical robot movement was performed.

Restart the hub and refresh player pages to load the changes. Cancel and reopen
any old Purple lesson that already captured the unrotated layout; those captures
cannot be reused for the new target placement. Previously committed rig data is
retained until the replacement calibration validates and commits.

## Game Master calibration camera repair — 2026-10-01

The earlier display repair incorrectly embedded the interactive Playfield target
renderer over the GM camera. GM now keeps its existing corrected Photon Board
camera preview throughout calibration, at full frame; only the external Y screen
projects the six Auto PP Cal 2 targets. The external frame requests Playfield's
read-only presentation mode, disabling zoom/orbit, selection, keyboard transforms
and camera/area saves. The ordinary Playfield editor retains its controls.

A saved Green display reservation was also being mistaken for an active lesson
after restart. The calibration owner now publishes `requires_activation` when
the display survived without a live lesson grant. Game retries begin with the
same operation ID and fresh camera/arm evidence, rebinding the draft to its new
epoch and retaining accepted glows. Missing evidence remains blocked.

GM can replace an active practice calibration by selecting another test side;
the existing cancellation path must confirm stopped motion and restore the
display before the next reservation begins. Both still starts Green first, and
earned calibration cannot be bypassed by this test selection. Errors are shown
beside the GM test controls.

Ownership remains unchanged: Y owns presentation, Game owns sequencing, Auto
Pickup owns lessons, Playfield owns targets, Board exposes the existing corrected
preview, and Relay owns stop acknowledgement. There is no new camera acquisition,
robot-command path, sibling-file access, or client-authored calibration evidence.

Validation: 40 Python tests passed across operator camera, calibration display
ownership and journey sequencing. The isolated browser flow passed both players'
four GM control overrides, practice Start, Green/Purple/Both calibration buttons,
camera/display separation, rotated targets, accepted capture glow, locked
projection under pointer/wheel/keyboard events, direct practice switching, and
full field/settings restoration. No browser page errors. Camera and target
screenshots were inspected; sensors and robot feedback were fake. JavaScript
parsing and whitespace checks passed. The venue hub was not restarted and no
physical robot commands were sent. Restart the hub and reload the GM/external
pages to activate the backend recovery and practice-switch changes.

## Game-first loading and offline calibration navigation — 2026-10-01

The live GM page was displaying an old Green practice lesson with "fresh camera
and arm feedback required". The screen controls were below the large camera and
turret panels. Their exit/switch path still required a connected arm to confirm
Stop, so the earlier repair did not address this offline failure.

Game screen, Green calibration, Purple calibration and Both are now above the
camera. Opening the Y operator page returns to the game via Game's `show_game`
command; opening the external projector alone continues following the operator.
Earned lessons are paused with their draft and queue retained, and an explicit
Resume player calibration button restores them. Repeated ticks do not reopen a
cancelled/deferred screen, and saved-player tiers/rewards remain unchanged.

Cal 2's optional deferred release revokes an activated lesson before restoring
the field and persists any unconfirmed stop separately. This allows returning
to the game or previewing Purple while the arm is offline. Neither preview,
heartbeat, test unlocks nor a restart can bypass the stop requirement. Game's
physical Start/motion policies and Relay's existing admission guard honor it for
both sides. Operator Connect remains available solely to restore feedback;
new lesson activation still needs fresh camera/arm evidence. Normal earned
handoff keeps its strict measured-stop requirement. Ownership and the single
robot-control path are preserved.

Validation: 93 Python tests passed across journey, target ownership, Relay
admission, GM camera and framework integration. The browser flow reproduced an
active Green lesson followed by lost arm feedback and page reload, then switched
Purple → Green → Game while motion stayed blocked. Restoring fake feedback
cleared the gate and allowed Purple activation. Both players' four control
overrides, Start, calibrated glows, rotation, locked projection and restoration
also passed, with no page errors. The visible toolbar screenshot was inspected.
All tests used temporary data and simulated hardware; the venue process was not
restarted as part of validation.

## Cancelled-session ID blocking calibration buttons — 2026-10-01

The live failure retained an old Green `active_id` after restart cleared
`active_side`. Cancelling that restored lesson returned early without clearing
the ID. Maintenance then treated the historical paused draft as a live turn and
raised `hhh.relay.stop v1 unavailable` before Game could load the selected target
layout. The earlier offline regression had released the lesson before restart,
so it missed this ordering.

Restart now clears both active fields, idempotent release repairs an orphaned
ID, and maintenance only handles a turn when it has an active side. The separate
durable stop inhibit is preserved. Tests reproduce restart-before-cancel with
an offline arm and the exact legacy ID shape. The GM status reports target
readiness independently of selecting a side and surfaces display failures before
hardware-readiness notices. The open external tab was also observed running the
older inline renderer, requiring a reload to pick up current presentation code.

Validation: 45 targeted Python tests passed and the full isolated browser flow
passed with restart-before-cancel and the legacy active ID. After confirming both
live relay arms were disconnected, the local hub was restarted with the same
Python runtime and both existing Y pages refreshed. Actual Green/Purple button
clicks displayed all six targets, with Purple rotated 180°. The Game screen
button restored the game. Live screenshots were saved, and the venue was left
on the game screen. No robot movement or calibration capture was commanded;
the pending Green stop inhibit remains until connected feedback confirms it.

## Mobile lesson selection while activation is pending — 2026-10-01

The phone chose its lesson from `active_side`, which stays empty while the
calibration owner waits for feedback or an earlier stop. Both phones therefore
showed "Waiting for calibration to finish calibration" even though the selected
targets were projected correctly. Game now publishes the queued
`calibration_side` independently of its live motion grant. The facade exposes
only that side's matching draft and a separate live-readiness flag.

The selected phone immediately presents Auto PP Cal 2's six capture steps and
XYZ controls, saved glows, perspective/height stage and click-to-move lesson.
An unready session displays the actual owner error and disables capture. A
compact Hide/Show steps control frees the camera view without leaving the
lesson or granting movement. The other phone stays on Upgrades with a named
waiting message, including when neither arm is activated. Without a selected
profile it shows disabled upgrade choices and explains why purchases are
unavailable. No movement policy, stop gate or robot-control route changed.

Validation: 57 Python tests passed (journey, mobile teams, display ownership,
client builds), both mobile/progression browser suites passed, and the final
layout passed the full real-route regression again. Coverage includes opening a
phone after offline Green/Purple selection, both switching directions, partner
upgrades, six disabled captures before activation, panel collapse/expand and
successful capture/glow after fake feedback recovers. Both APIs reject expired,
restored or blocked grants for capture presentation; owner commands retain their
existing validation. Screenshots were inspected at 390×844.

The live hub was restarted after verifying both arms were disconnected. Actual
Green and Purple pages opened their selected lessons; Green showed Upgrades
when Purple was selected, and Purple opened Upgrades when Green was selected.
Temporary verification tabs and viewport overrides were removed. Green
calibration was left selected. Live capture was not attempted because arm
feedback remains unavailable; the existing pending-stop requirement is intact.
