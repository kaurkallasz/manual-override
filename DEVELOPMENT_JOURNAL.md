# HHH Gamemaster development journal

Last updated: 2026-10-09, consolidating the development work after `53bb9c8` through the October 8 Atom turret buff and the October 9 publication checks. Earlier entries preserve their original evidence and attribution, including test counts and deployment observations that apply only to their dated checkpoint. The original historical reconstruction was made on 2026-08-29 through `9d22a3a`.

This journal explains how the repository reached its current design: what changed, what was learned, why the next decision followed, and whether the repository records the work as human-only or AI-assisted. The reconstruction is based on commit history and messages, the current README and specifications, implementation diffs, calibration files, and local Laser Tag X run and score logs.

The specifications remain the authority for **what the software must do now**. This journal records **why it came to do that**. If historical reasoning and a current specification disagree, follow the specification and add a new journal entry explaining the change.

## Attribution and evidence rules

Git identifies Kaspar Kallas as the author of every commit in the available history and as the merger of both recorded pull requests. Twelve development commits also contain an explicit `Co-Authored-By` trailer for an Anthropic Claude model. This journal therefore uses these labels:

- **Human decision; AI-assisted implementation** — Kaspar authored or accepted the commit and the commit explicitly credits an AI co-author. The record supports AI participation, but not a claim that the AI had final decision authority.
- **Human-recorded decision; AI involvement not evidenced** — Kaspar authored the commit and there is no AI attribution in the commit. This does not prove that no AI was used; it means the repository does not say so.
- **Inference** — the reason or lesson is reconstructed from the order and content of changes rather than stated in a commit message. Inferences are called out instead of being presented as remembered fact.

Where a human request and an AI implementation record are both available, the entry separates the human product constraint from implementation choices made by the AI. An AI-selected implementation is not the same as AI having final authority: no commit in the available history supports an **AI-only final decision**. Final repository acceptance was human in every recorded case.

Uncommitted files have no author or co-author metadata. Unless a prompt or another durable record is available, their owner is recorded as **not evidenced** rather than guessed from the active branch name, file style, or the fact that Codex is writing this reconstruction.

Other human participants appear in gameplay score logs, but the repository does not identify them as design decision owners. Their influence must not be invented retroactively.

## Where we are now

HHH Gamemaster is a single Python/Flask hub serving three password-gated sandboxes: `gamemaster`, `green`, and `purple`. Machines remain modular prototypes, but authentication, discovery, routing, setup import/export, and cross-sandbox access live in the shared hub.

During normal play, the gamemaster relay exclusively owns two Dobot MG400 arms. Each team receives a separately leased, server-enforced side; a watchdog stops an abandoned arm. Because both robots retain the same factory IP, each arm's sockets are pinned to a dedicated USB Ethernet interface.

The physical-game stack combines corrected ArUco camera observations, camera-to-robot calibration, relay pose and pump state, Atom impact sensors, shared playfield rendering, and per-team automation. Laser Tag X remains the mature two-arm cooperative placement game: it has browser-side high-frequency fusion, coarse server state, append-only diagnostics and scores, recovery from visible board state, and operator escape hatches.

The active tower-defence implementation is now the modular Photon stack: Level owns authored content, Board publishes physical observations, Game owns the simulation, Progress owns saved player progression, and Laser Tag Y presents the game. Laser Tag Z remains the rollback/reference implementation. Commit `cd00d97` records progression, row barriers, L4 companions, and artwork; `2ea92b5` checkpoints the shared mobile controls, streaming and turret aiming; `53bb9c8` checkpoints two-player progression and calibration.

Green and Purple Mobile LTZ now share one frontend and the same authoritative Game through a restricted gateway. Both teams have Joint, Cartesian XYZ, Targeting and Cue progression, virtual practice, and calibrated physical controls through the existing relay. Calibration derives pickup/transport heights from the six ground captures, records four raised samples, supports offline completion, and lets the gamemaster explicitly associate a saved arm calibration with the current camera correction. Reconnect adopts measured robot position and requires a new gesture; stale sessions cannot replay old targets. Relay-owned floor/ceiling limits and the calibrated 220–439 mm reach envelope constrain physical motion.

The October continuation makes physical cues reusable, retains acquired endpoints through temporary camera-map holds, supports pause and player intervention, detects a failed pickup, and adds a configurable Clear view action after placement. Fresh marker labels arrive independently of robot connection or renderer startup. Camera detections, cue acquisition and physical occupancy have separate versioned Board contracts: a visible label never grants motion permission. Mobile delivery and connection diagnostics make generation, transmission, camera holds and player input inspectable. Actual-arm graphics use timestamped measured positions, settled-position feedback and an erasing checked trajectory.

Game now accepts camera-observed opposing-Atom cover to finish an armed core and owns the persistent Atom turret bonus: a confirmed occupied turret has a green halo, twice the health capacity and twice the weapon damage. Removing the Atom preserves health percentage; a confirmed return heals once. Camera dropouts do not manufacture a return or healing. L4 companions, upgrades, row barriers and both Y displays retain their existing ownership boundaries.

This is a source checkpoint, with fresh automated verification recorded in the October 9 entry below. The latest Atom-buff entry records isolated browser/performance validation and a pending planned hub restart and physical placement/hold/pickup/return check. Earlier successful restarts do not prove that the final source is active now. This journal update does not establish a new live-hardware or hosted-phone release.

Across both games, the most important physical-play rule is that the **stable corrected-camera result is board truth**. A robot operation says what was intended and supplies transaction receipts; it helps attribute or diagnose the result, but it cannot replace or overrule a uniquely observed physical placement. Laser Tag Z adds a second distinction: physical observation activates gameplay state, while only the defence engine owns combat, topology, health, and objective state.

## Chronological decision record

### 2026-06-10 — Start from a modular game-host baseline

**Evidence:** `2e64247` introduced a vendored Manual Override hub plus three machines: the MG400 relay, webcam/ArUco tracking, and playfield areas.

**Lesson available at the time:** the existing hub already supplied machine discovery and a UI shell, so the fastest route to a working physical-game host was to reuse it and keep hardware capabilities in separate machines.

**Decision and why:** vendor the hub and make the relay the sole robot owner, with camera and playfield as peer services. This established the modular boundary still visible today.

**Owner:** Human decision by Kaspar; AI-assisted implementation explicitly credited to Claude Opus 4.8.

### 2026-06-11 — Add takeover, two-arm concurrency, and a first deployment topology

**Evidence:** `970eb18` added direct joint and Cartesian manipulators for operator takeover; `c99a4b6` launched gamemaster and two player sandboxes as three processes; `2f027f8` made one relay own both arms concurrently. `1fa2861` added the calibrated tag-game flow and Atom/WT32 firmware.

**Lessons:** one connection owner per arm is a real hardware constraint, and unattended remote control needs a safe handoff. Two teams also need independent arm state rather than a single global controller. The calibrated tag flow showed that gameplay had to span firmware, vision, playfield, and robot services.

**Decisions and why:**

- keep normal play behind the relay, but let the operator disable it and take over directly;
- give each relay side its own state and allow the two sides to run concurrently;
- initially run the three roles as separate processes so the complete system could be exercised quickly.

The three-process launcher was a useful stepping stone, not the final architecture; it was superseded the next day.

**Owner:** Human decisions by Kaspar. The takeover, launcher, and relay work explicitly credit Claude Opus 4.8; the calibrated tag-game commit has no recorded AI attribution.

### 2026-06-12 — Replace three hosts with one authenticated hub

**Evidence:** `486573a` and `93260e3`, merged by `5c86e5b`, folded the gamemaster and player repositories into `sandboxes/<name>/prototypes/`. They added per-sandbox passwords, roles, cross-sandbox service tokens, setup ZIP import/export, a landing page, and sandbox-aware discovery. Stale upstream-upgrade machinery was removed.

**Lesson:** the three-process/repository split duplicated configuration and deployment work, while team isolation still needed to be enforced centrally. A physical event setup benefits more from one process, one port, and portable sandbox bundles than from independently administered clones.

**Decision and why:** use one hub as the deployment and security boundary, but preserve three logical sandboxes. Team code may call shared services only through explicit doors, and the relay must still enforce `side == authenticated team` rather than trusting the browser.

**Owner:** Human decision and merge by Kaspar; AI-assisted implementation explicitly credited to Claude Fable 5.

### 2026-06-12 — Solve identical robot addressing at the socket layer

**Evidence:** `a2e4b00`, merged by `e02c347`, records that both MG400s had to keep factory IP `192.168.1.6`. `4ebaef5` then derived controller identity from the authenticated sandbox, locked players to relay-only control of their own color, removed the now-redundant Game Link machine, and kept the player controller copies identical.

**Lesson:** ordinary routing cannot distinguish two devices with the same destination IP. Separately, asking players to re-enter team and host data creates avoidable mismatch and security risk when both values are already known by the server.

**Decision and why:** pin every robot socket to the USB Ethernet interface that owns a fixed local IP (`.50` purple, `.51` green), auto-detect the interface name, and fail with a setup-specific error if it is absent. Derive side and relay host from trusted hub context.

**Owner:** Human decisions by Kaspar; AI-assisted implementation explicitly credited to Claude Fable 5.

### 2026-06-13 to 2026-06-18 — Grow from manual play to automated pick-and-place

**Evidence:** `5042744` added the two-player tag game; `5664549` added team-specific webcam rotation; `0b3e8c0` and `df67311` introduced pickup controllers and a side-by-side video/control view; `f929a5a` and `ccc5c17` added and expanded automatic pickup; `abc47cd` added relay Z-floor and state handling; `c14ae88` revised calibration field mapping; `867cb32` added Auto PP X; `6466987` required player-name confirmation.

**Lessons:**

- manual motion controls are necessary for commissioning but are not a game workflow;
- camera presentation may differ per player, while robot identity and calibration must remain stable;
- automation needs explicit calibration, Z constraints, state feedback, and a visible relationship between camera and controls;
- participant identity must be confirmed before an autonomous run if scores and logs are to remain meaningful.

**Decision and why:** build automation incrementally on top of the same relay and sensing contracts instead of creating a second robot-control path. Keep safety and ownership server-side while iterating player workflow in the sandbox UIs.

**Owner:** Human-recorded decisions by Kaspar. The June 15 pickup and layout commits explicitly credit Claude Opus 4.8; the other commits in this period contain no AI attribution.

### 2026-07-23 — Integrate the Kaur3 physical build

**Evidence:** `647324d` updated Atom firmware and management, relay diagnostics and Z limits, auto-pickup calibration and logs, and added Tag Invaders.

**Lesson:** physical-game development was producing useful state outside the original narrow game flow: device health, impact data, command history, calibration values, and score/run records all needed operator visibility.

**Decision and why:** bring that working rig state back into one branch and make hardware diagnostics part of the operator system rather than an external debugging exercise.

**Owner:** Human-recorded decision by Kaspar; no AI attribution is present. The commit message says only “Upload current codebase,” so the detailed rationale above is an inference from the files changed.

### 2026-08-05 — Establish a corrected camera and second-generation calibration path

**Evidence:** `7291f9d` added chessboard camera calibration, corrected streams and coordinates, native focus lock, Auto PP Cal 2 data and UI, Atom testing, persistent relay command monitoring, and the first Laser Tag prototype.

**Lesson:** raw camera coordinates and autofocus behavior are not stable enough for repeatable robot-to-board placement. Calibration must cover the lens field, all consumers must share the same corrected frame, and the rig needs a way to inspect commands when physical behavior differs from intent.

**Decision and why:** share the webcam capture instead of opening competing camera handles; make one correction map feed preview, video, and tag coordinates; add a denser camera/arm calibration path; retain command evidence; build Laser Tag on those services.

**Owner:** Human-recorded decision by Kaspar; no AI attribution is present. The stated lesson is partly inferred from the calibration design and the later corrections it enabled.

### 2026-08-09 — Make behavior reconstructable and runs diagnosable

**Evidence:** `3b62e4f` created the first 1,419-line Laser Tag reconstruction specification, expanded Laser Tag and green-side automation integration, and extended camera and relay diagnostics.

**Lesson:** once game acceptance depends on timing and evidence from several asynchronous systems, the code alone is a poor account of the intended behavior. Comparing player automation with gamemaster decisions requires shared operation IDs and durable events.

**Decision and why:** document compatibility behavior as a reconstruction specification and record cross-system diagnostic events so an observed activation can be compared with the operation that intended it.

**Owner:** Human-recorded decision by Kaspar; no AI attribution is present.

### 2026-08-14 — Fork Laser Tag X as the integrated game

**Evidence:** `1b249f2` introduced `laser-tag-x`, a 1,462-line reconstruction specification, per-team LTX endpoints, motion settings, scoring, diagnostic run logs, and coordinated updates to Auto Pickup, calibration, relay, and player controllers.

**Lesson:** the original Laser Tag tab had become a systems-integration surface, not just a game screen. A high-frequency sensor-fusion loop, durable diagnostics, team automation, scoring, recovery, and operator controls needed an explicit contract.

**Decision and why:** create Laser Tag X as a separately specified integration. Keep high-frequency per-tag fusion in the browser for rapid iteration, persist only coarse phase/finale state on the server, and append detailed diagnostic events to JSONL. Map the game's blue presentation to the relay's purple side at one adapter boundary.

**Owner:** Human-recorded decision by Kaspar; no AI attribution is present. The reason for the browser/server split is reconstructed from the specification's stated boundaries.

### 2026-08-17 — Add operator completion paths and meaningful scoring feedback

**Evidence:** `7f730c5` added manual activation for outer targets; `99cef90` extended it to the two center covers and made that state recoverable; `366d54a` added scoreboard rank/gap feedback and safer late player-name capture. Physical Laser Tag X run and score logs begin before this date and continue through it.

**Lesson:** a live physical game must remain finishable when a sensor, calibration, or automated sequence fails. A manual action must use the same state transition and visual effects as an automatic action, or recovery creates a second, inconsistent game. Scores also need immutable start-time context but a narrow fallback for registration that finishes late.

**Decision and why:** give the gamemaster explicit outer and center placement controls, persist a manual first-center sentinel instead of inventing a tag ID, and route manual completion through normal win/scoring behavior. Make the score table explain place and time gap while preserving append-only history.

**Owner:** Human-recorded decisions by Kaspar; no AI attribution is present.

### 2026-08-18 — Persist board progress and tighten motion/calibration semantics

**Evidence:** `d2f4fa4` persisted `activated_targets`, recovered visible progress after reload, added player distance meters, and introduced horizontal/Z drop windows. `801a993` reduced target-drop Z arrival tolerance from 40 mm to 1 mm and applied the 31.5 mm height offset only when stacking on a physical tag.

**Lessons:**

- coarse phase alone cannot reconstruct an in-progress board after a browser reload;
- a single broad distance check can report arrival while the robot is still descending;
- a flat board target and a physical tag used as a stacking target require different Z geometry;
- operators and players need the same calibration error made visible, not just a silent accept/reject result.

**Decision and why:** make activated marker IDs part of coarse shared state; recover the rest from the live playfield; separate horizontal and vertical acceptance; require near-exact final Z before release; add tag height only for tag-on-tag placement; expose the measured error in the LTX player HUD.

**Owner:** Human-recorded decisions by Kaspar; no AI attribution is present.

### 2026-08-19 — Move from command truth to camera-observed board truth

**Evidence:**

- `ab81919` changed outer verification from release-pose target selection to sustained, unique, parallax-corrected visual overlap. Release pose became diagnostic, missing pose ceased to invalidate coherent camera evidence, and placement IDs separated a physical placement from an optional automation operation.
- `659441d` updated the measured camera and robot calibration data.
- `6ccd3b2` made a video click a safe temporary motion override: finish atomic pump work, lift, move, then retry the interrupted cue without changing queue index or operation identity.
- `81f19fd` made stable camera evidence authoritative even when operation receipts are late or ambiguous. It added typed destinations, post-observation operation attribution, an “unattributed board truth” state, and divergence only when one uniquely correlated released operation actually contradicts the observed result.

**Lessons:**

- robot pose and queued destination describe intended motion, not proof of where the tag ended up;
- camera occlusion is useful provisional evidence but is not enough by itself;
- a physical result needs multi-frame voting, jitter limits, uniqueness margins, and parallax correction;
- asynchronous receipts can arrive after the automation queue advances, so “newest active operation” is not a safe proxy for the operation that caused the visible result;
- an operator correction during a cue should not destroy transaction identity or silently skip a queue item.

**Decision and why:** let the corrected camera decide the physical board only after stable geometric confirmation. Correlate completed, receipt-valid operations afterward; report matched, late-matched, unattributed, or true divergence explicitly. Preserve an observed result when attribution is ambiguous, and never compare it with an operation that has merely started. Keep runtime overrides transactional and return to the interrupted operation.

**Owner:** Human-recorded decisions by Kaspar; no AI attribution is present.

### 2026-08-19 — Separate current requirements from development reasoning

**Evidence:** the current human request asked for a development journal covering decisions, reasons, lessons, timing, and human/AI ownership, plus a note from the specification to the journal. This entry and the specification link are pending worktree changes rather than part of the earlier commit history.

**Lesson:** the reconstruction specification is detailed about current behavior but intentionally does not explain the sequence of discoveries and reversals that produced it. Commit author fields also do not, by themselves, distinguish human decision authority from AI implementation help.

**Decision and why:** keep the Laser Tag X specification focused on current normative behavior, create this repository-level journal for rationale and attribution, and link the two documents with an explicit precedence rule.

**Owner:** Human-requested decision. OpenAI Codex performed the evidence review and drafted the journal and cross-reference; final review and acceptance remain with the human.

### 2026-08-19 — Put Game 2 Cartesian control in the camera context

**Evidence:** the human requested a crane-themed overlay at the bottom of the LTX player video for Game 2 and supplied a versioned manifest, empty triangular frame, and three transparent neon handle images. The requested mapping was left handle to Z, right handle to forward/back, and bottom handle to left/right.

**Lesson:** the player makes Cartesian adjustments by watching the camera, so the most relevant controls can live in that visual context. The existing native X/Y/Z sliders and their input handler already feed the established queue, relay ownership, limits, and safety behavior; bypassing them would create an unnecessary second robot-control path.

**Decision and why:** show a responsive triangular overlay only in `game_2`, alpha-extract the frame so black pixels are genuinely transparent, and make the supplied handles draggable along their pictured rails. Map left to Z down/up, right to X back/forward, and bottom to Y right/left. Treat the handles as synchronized presentations of the native sliders, disable them when Cartesian control is disconnected without recoloring the supplied artwork, and include keyboard slider behavior. Place the game instructions below the video instead of stacking them over the camera. This gives Game 2 the requested direct manipulation without changing the robot-control contract.

**Verification:** both Green and Purple asset routes returned the PNG assets; the inline JavaScript and both LTX Python entry points passed syntax checks; projection endpoint tests covered all three rails; and browser inspection confirmed Game 2-only visibility, loaded assets, responsive landscape and portrait layouts, a true-alpha frame, instructions below the video, separated apex labels, reference-colored levers, accessibility roles, and no console errors. No live robot was connected or moved during UI verification.

**Owner:** The feature, visual assets, game-mode restriction, and axis mapping are human decisions from the request. OpenAI Codex chose the reuse-and-synchronization implementation, added the code and documentation, and performed non-hardware verification. Final acceptance remains with the human.

### 2026-08-19 — Share both arm positions in each LTX camera view

**Evidence:** the human requested an `Arm` checkbox in both player LTX windows. When enabled, each player must see where their own arm and the other player's arm are moving, represented as straight lines of the same red squares used for the unsafe base-center area. The request identified the gamemaster Laser Tag X arm movement information as the tracking source.

**Lesson:** collision awareness is a shared visual problem even though robot ownership remains team-specific. The gamemaster already reads both relay arm poses, and Auto PP Cal 2 already contains a separate robot-to-camera model for each arm. Reusing those contracts is more reliable than inferring an arm from camera occlusion or creating a second motion channel.

**Decision and why:** expose a role-checked, read-only player snapshot containing only the two arms' compact live relay fields and never the relay command log. Poll it only while the player's `Arm` checkbox is enabled. Project each pose through its owning arm's calibration into the viewing player's current camera orientation, then render a clipped base-to-TCP line of red squares with explicit `YOUR ARM` and `OTHER ARM` endpoint labels. Hide disconnected, invalid, or stale positions. This supplies cross-arm awareness without changing leases, motion commands, or safety authority.

**Verification:** Python and inline JavaScript syntax checks pass; authenticated Green and Purple requests return the same canonical Green/Purple compact snapshot while the gamemaster route retains its Green/Blue naming adapter; mathematical tests cover line clipping, square-line generation, and both calibration projections; and browser inspection confirms the checkbox layout in both player views, toggle behavior, and endpoint polling only while checked. With both local relay arms disconnected, the fail-closed behavior was verified; no live robot was moved for this UI test.

**Owner:** The checkbox, two-arm visibility, red-square form, and gamemaster tracking source are human decisions from the request. OpenAI Codex chose the read-only snapshot boundary, per-arm projection, stale-data handling, labels, and implementation. Final acceptance remains with the human.

### 2026-08-20 — Preserve score history beyond the live table

**Evidence:** `c7c5c65` added a Laser Tag X `/stats` page and `/api/scores/history`. The page plots chronological winning times, filters by player, labels partners, distinguishes game types, shows a three-game rolling average and improvement tiles, and retains a table view. The history endpoint reads the full append-only score log even when the live scoreboard view has been reset.

**Lesson available at the time:** a current leaderboard answers “who is ahead now,” but it cannot show whether a participant is improving or how game type and partner affected a result. A UI reset also must not become an accidental deletion of historical evidence.

**Options and decision:** either continue deriving every view from the resettable score table, or separate durable history from current presentation. The project chose the second option: retain one append-only source and give longitudinal analysis its own read-only endpoint and page.

**Verification:** the commit records the new route, full-log endpoint, graph, filters, rolling average, and table. No automated verification is recorded in the commit.

**Owner:** Human decision and acceptance by Kaspar; AI-assisted implementation explicitly credited to Claude Fable 5.

### 2026-08-20 — Treat calibration and command history as versioned rig state

**Evidence:** `7801c28` updated both robot calibration files, camera calibration, Laser Tag X settings, and the persistent relay command monitor.

**Lesson available at the time:** the physical rig is partly defined by measured data, not only by source code. A calibration update changes behavior, while retained command history provides evidence for comparing intended and observed motion.

**Options and decision:** keep measurements and command evidence outside version control as operator-only state, or commit the working rig snapshot alongside the behavior that depends on it. The project chose to version the measured configuration and runtime evidence. This makes a historical build more reproducible, at the cost of large, installation-specific diffs.

**Verification:** the commit contains the revised calibration values and runtime log. The record does not identify a separate automated or live-robot acceptance run for this change.

**Owner:** Human decision and acceptance by Kaspar; AI-assisted implementation explicitly credited to Claude Fable 5.

### 2026-08-24 — Fork Laser Tag Z instead of turning Laser Tag X into tower defence

**Evidence:** `2bc33b3` added Laser Tag Z as a separate Gamemaster prototype, a server-authoritative defence engine, settings and tests, a modular Tiled project, two editable TMJ levels and wave files, normalized Z-pixel artwork, ArUco-aware tower sockets, enemy sprite sets, validators, and Tiled render evidence. The original Laser Tag X routes, settings, logs, scores, and assets were left in place.

**Lesson available at the time:** the camera, calibration, player robots, and safety services were reusable, but tower defence had a different simulation, map, display, and tuning lifecycle. Replacing Laser Tag X in place would couple a working physical game to a large experimental ruleset. A flattened background would make the first map quicker to display but would prevent meaningful editor iteration.

**Options and decision:** modify Laser Tag X directly, build an unrelated standalone game, or fork only its integration boundary. The project chose the third option. Laser Tag Z reuses the mature physical stack, owns its mutable gameplay state, and treats `assets/tiled/levels/z-pixel-first-map.tmj` plus its TSJ dependencies as the editable production map. Physical play remains the default, while a Gamemaster-only virtual mode makes hardware-independent iteration possible.

**Verification:** the initial tests checked the exact 40–55 fixed-marker range, virtual and physical placement rules, bounded spawning and core attack, and immutable settings snapshots. The commit also included modular validation reports and native Tiled render/round-trip evidence for the authored map.

**Owner:** Human-recorded decision by Kaspar; no AI attribution is present in the commit. The comparison of the three architectural options is an inference from the retained Laser Tag X boundary and the files introduced.

### 2026-08-24 — Replace lane slots and core orbits with continuous particle flow

**Evidence:** ten small commits record the movement model changing in response to visible and testable defects:

- `15b8660` corrected Tiled object alignment so the renderer and engine used authored object centers;
- `38af50a` animated distinct walk frames and exposed core health;
- `72e6749` added personal space and distributed attackers around the core;
- `6556785` resized and oriented enemies and fit three tracks across a road;
- `217c2c7` blended headings through corners and tested complete-wave drainage;
- `0ab3e3d` removed per-enemy health-bar clutter and loosened crowd presentation;
- `f68d4e5` replaced discrete crowd/orbit handling with particle integration and a much denser center basin;
- `a31dc6a` removed the visible jump between the final road segment and the basin;
- `6b07852` filled all faces of the core; and
- `c0d16ee` changed the terminal boundary from a square approximation to the map's octagonal core.

**Lesson available at the time:** exact path slots made small groups legible, but produced queueing, corner snaps, empty floor around the objective, and hard capacity limits under a full wave. Pure collision separation alone did not create a convincing swarm. The rendered core shape also had to match the collision boundary or the crowd appeared to float or overlap.

**Options and decision:** keep adding lanes and fixed orbit slots, remove collision and allow sprites to overlap freely, or use authored routes as directional guidance feeding a bounded particle basin. The project converged on the third option. Enemies retain route intent and collision radii, integrate continuously through turns, then pack and move around an octagonal terminal region without teleporting.

**Verification:** each intermediate model added regression coverage for the defect it addressed: object-center agreement, unique animation frames, spacing, directional facing, corner continuity, wave drainage, blocked-step bounds, basin capacity, continuous entry, face coverage, and octagonal clearance. These commits are unusually useful decision evidence because later tests replace assumptions from earlier tests rather than hiding the abandoned model.

**Owner:** Human-recorded iteration by Kaspar; none of the ten commits records AI co-authorship. The cause-and-effect chain is an inference from commit order, diffs, and changing tests.

### 2026-08-25 — Separate the physical operator view from the public game feed

**Evidence:** `a3f182e` extracted a shared `tower-defence-view.js`, added a clean `/screen` display, and added a read-only `camera-arm-overlay.js`. The Gamemaster page shows corrected camera, live marker outlines, and both calibrated arm overlays in physical mode; virtual mode and the external screen show the complete registered game feed. Both game displays consume the same snapshots and Server-Sent Events.

**Lesson available at the time:** compositing the map, orcs, towers, camera, controls, and robot overlays into one stage made the physical board harder to operate and the audience feed unsuitable for a separate screen. Duplicating renderer code for the two screens would let their interpretation of the same state drift.

**Options and decision:** keep one composite view, run an independent second simulation for the audience, or split presentation while sharing state and renderer. The project chose the shared-renderer split. Mode changes are presentation-only and do not reset the run. Arm visualization fails closed when pose or calibration is invalid or stale and contains no robot-command path.

**Verification:** tests cover mutually exclusive physical/virtual feeds, the control-free external screen, shared rendering, calibration reuse, the 1.5-second stale cutoff, and the absence of movement or pump APIs in the overlay module.

**Owner:** Human-recorded decision by Kaspar; no AI attribution is present in the commit.

### 2026-08-25 — Make defence placement editable, physical, and combat-relevant

**Evidence:** `9d22a3a` added setup-only socket editing, atomic TMJ saves, virtual marker selection, stable camera-and-arm-gated physical placement, per-turret aim controls, defence health and destruction, three weapon behaviors, and force-field durability and rerouting. It also added combat-effect art and expanded the specification and tests.

**Lesson available at the time:** an attractive map was not yet a physical game. Socket geometry needed to be adjustable at the installation, camera overlap had to be coupled to the correct enabled and released arm, and placements needed distinct combat roles. Setup force fields also confused preview with live collision.

**Options and decision:** hard-code socket positions in JavaScript, edit only in Tiled between runs, or expose a constrained editor that still writes the TMJ as the authority. The project chose the constrained editor: stable ArUco IDs and validation are preserved, saving is atomic, and editing is disabled after setup. Atom 100 became Machine Gun, 101 Flamethrower, and 102 Mortar. At this stage Atom 103 was deliberately a reserve/reset unit rather than a fourth weapon. Force fields were withheld until Start, then created from activation order, counted each orc once, broke after a configured capacity, and turned attackers toward another route.

**Verification:** tests cover layout identity and validation, setup/live field separation, fixed Atom roles, unique impact counting, rerouting and breakage, the 15-percent defence-health default, reserve repair, weapon aim/burn/falloff, Gamemaster-only layout routes, real dictionary-correct ArUco rendering, and physical release safety.

**Owner:** Human-recorded decision by Kaspar; no AI attribution is present in the commit. The reserve role and the original field rules are recorded here because the current working tree supersedes them.

### 2026-08-26 to 2026-08-29 — Change Atom placement from occupancy to durable activation

**Evidence:** the current uncommitted specification, engine, renderer, routes, settings, assets, map, and tests change the placement model introduced by `9d22a3a`. A defence now remains after its activating Atom moves away; one Atom can seed multiple sockets; every Atom can use every empty socket; returning any Atom to a living defence replenishes it and its connected fields; and a destroyed pod disappears to reveal the original ArUco marker so any Atom can replace it. Atom 103 is now a Tesla Coil, replacing the earlier reserve/reset role.

**Lesson available now:** a movable physical Atom is a scarce activation tool, so equating “tag no longer overlaps” with “tower no longer exists” prevents a full sixteen-socket defence. A dedicated reset tag also leaves the fourth team's unit without a combat identity and makes repair a special case unrelated to placement.

**Options and decision:** preserve live one-tag/one-tower occupancy, create sixteen physical activators, or treat a stable release as a durable gameplay event. The working tree chooses durable activation. Repair and replacement use the same placement interaction instead of a reserve-only branch. Team ownership still controls colour and which arm may carry the Atom; it no longer restricts which socket can hold that weapon.

**Verification:** the current suite covers one Atom seeding independently aimed defences, any Atom using any socket, persistence after movement, replenishment, destroyed-tower replacement, and matching physical and virtual activation rules. The complete current Laser Tag Z suite passes: 84 tests in 58.321 seconds on 2026-08-29.

**Owner:** Decision and implementation ownership are not evidenced in Git because these are uncommitted working-tree changes and no earlier prompt transcript is stored in the repository. OpenAI Codex reconstructed and wrote this entry but did not make these prior code changes during the present journal task. Human acceptance is pending.

### 2026-08-26 to 2026-08-29 — Give force fields one safe, reconcilable lifecycle

**Evidence:** the current working tree introduces immutable ArUco identification footprints, authored and dynamic line-of-sight blockers, retained placement requests, an idempotent reconciliation pass, pending/established/occluded/broken/suspended/retired phases, per-impact evidence, and `connection_contract_version: 2`. One canonical `connections` array now derives the older `gates`, `force_field_visuals`, `force_field_topology`, and `placement_links` projections.

**Lesson available now:** using the editable 208-pixel socket art as collision geometry made a visual resize silently change topology. Dropping a blocked link request made activation order and temporary occupancy permanently change the graph. Letting several public arrays recompute lifecycle independently allowed a field to exist, render, and collide differently. Most importantly, a line crossing the central ArUco 38 code could obscure the objective and make physical recovery impossible.

**Options and decision:** reject blocked links permanently, rebuild all links from scratch whenever occupancy changes, or preserve field identity and reconcile it against current safety geometry. The working tree chooses reconciliation. A fixed 77-pixel socket-code footprint and a permanently protected 156-pixel square around marker 38 are independent of visual size. Empty sockets block links; living endpoints do not. Temporarily obstructed established fields become non-visible and non-collidable without losing identity, while any stale field crossing marker 38 is retired. Runtime invariants fail loudly when authoritative existence, visibility, collision, or compatibility projections disagree.

**Verification:** tests cover visual-size independence, protected-core rejection, retirement of legacy unsafe fields, empty-socket occlusion and resumption, authored blockers, pending retries, unique per-orc durability impacts, exact contact points, endpoint destruction and repair, physical/virtual reconciliation, canonical IDs, and snapshot consistency. These tests are included in the 84-test passing run recorded above.

**Owner:** Decision and implementation ownership are not evidenced for the uncommitted changes. OpenAI Codex's role in this task is limited to reconstruction and documentation; final human review remains required.

### 2026-08-26 to 2026-08-29 — Replace the four-link objective with a deterministic spatial ring

**Evidence:** the initial `2bc33b3` rule said four endpoints closed the ring. The current engine and specification instead require 8–16 living turrets forming a non-self-intersecting polygon around marker 38. The solver evaluates spatial subsets independently of activation order, ranks them by turret count, longest edge, total perimeter, and stable marker IDs, and creates every missing boundary in one rollback-protected transaction. Setup exposes non-collidable partial previews; a completed boundary is fixed, replenished, and temporarily immune. A two-team tag stack on marker 38 triggers a radial fire purge and ends the run.

**Lesson available now:** an activation-history loop can be topologically valid yet fail to contain the physical objective, cross protected markers, or change when the same turrets are placed in a different order. Creating ring edges one at a time can also leave half a finale when a later edge fails validation.

**Options and decision:** keep the original four-link sequence, rely on authored neighbor cycles, or solve the objective from current spatial state. The working tree chooses one spatial solver and keeps authored neighbors as validation hints only. The same living layout must select the same ring for every activation permutation. The largest angular gap defines a stable preview opening and closing edge. If any required edge is unsafe, none of the missing boundary is committed.

**Verification:** tests exhaust activation permutations, compare the solver with an independent brute-force oracle, exercise 8–16-turret selection, require core enclosure and non-intersection, verify atomic rollback and retry, preserve a completed ring after extra placements, test immunity expiry, and exercise the opposing-team core purge. These tests are included in the current 84-test passing run.

**Owner:** Decision and implementation ownership are not evidenced for the uncommitted changes. The description of rejected alternatives is an inference from the replaced specification, the new solver, and its regression tests.

### 2026-08-26 to 2026-08-29 — Scale connected defences and make combat readable at crowd density

**Evidence:** the current working tree adds linked-component scaling, Tesla Coil combat, delayed projectile impacts, richer weapon snapshots, generated runtime weapon layers, tower-damage stages, and dense-rendering controls. Each living turret now receives `0.8 + 0.1 × connected turret count` for weapon damage and maximum health. The server remains the 20 Hz authority; the browser renders compact snapshots with extrapolation, cached sprites, density throttling, and an adaptive 18 fps target at the 1,000-enemy cap.

**Lesson available now:** force fields need a positive cooperative benefit as well as a blocking role. A single generic firing flash cannot explain which enemy was targeted, when a shell lands, whether flame damage follows the visible jet, how a Tesla chain weakens, or why a tower died. At high density, transmitting or rebuilding every cosmetic detail at simulation frequency makes presentation compete with authority.

**Options and decision:** keep all towers statistically independent and render generic effects; make the browser simulate combat; or expose authoritative identities, timings, paths, charge, health, and impact events while leaving interpolation and particles cosmetic. The working tree chooses the third option. Machine Guns show two barrel streams but apply damage once; Flamethrowers rebuild one synchronized swept spline for aim, art, and damage; Mortars damage only on shell impact; Tesla trades reach for first-link power and chains with falloff. Health percentage is preserved when a component multiplier changes, and damage thresholds drive cracks, smoke, fire, and a debris sequence that clears the physical marker after destruction.

**Verification:** tests cover exact group multipliers and health-percentage preservation, split groups, all four weapon contracts, dual-barrel single damage, delayed mortar impact, Tesla gap/depth/falloff/reach/charge, immediate flame-path reversal, swept melee contact, exact low-damage health, damage thresholds, marker reveal, cached rendering, and bounded dense snapshots. The generated assets and manifest are present but remain uncommitted. The 84-test suite passes; no live-robot movement was performed for this journal update.

**Owner:** Decision, visual-generation, and implementation ownership are not evidenced for the uncommitted changes. OpenAI Codex only verified the suite and documented the observable decision record in this task.

### 2026-08-29 — Continue one evidence-based development journal

**Evidence:** the human requested that the existing tower-defence development blog be found and continued in its established format, with decisions, the path to each decision, and human/AI responsibility recorded.

**Lesson:** the existing journal ended before Laser Tag Z began and its headline still described Laser Tag X as the current culmination. Without an update, the reasons for the tower-defence fork, movement-model reversals, display split, placement changes, topology contract, ring solver, and combat model would exist only as commit order and tests.

**Decision and why:** continue `DEVELOPMENT_JOURNAL.md` rather than create a competing blog. Preserve the existing evidence and precedence rules, add explicit options and reversals, and mark uncommitted ownership as unknown when the repository cannot prove it. This keeps the specification authoritative for current behavior and the journal authoritative only for reconstructed rationale and provenance.

**Verification:** commit history, trailers, specifications, diffs, tests, map evidence, and working-tree status were inspected. The current Laser Tag Z suite passed all 84 tests. The journal was checked for chronological placement and updated attribution counts.

**Owner:** The scope and attribution requirement are human decisions from the request. OpenAI Codex selected the evidence-reconstruction method, drafted these entries, and ran the non-hardware verification. Final acceptance remains with the human.

### 2026-09-02 — Add the smallest modular Photon vertical slice beside Laser Tag Z

**Trigger:** Laser Tag Z proved the game, but its map loading, physical evidence, simulation, persistence, assets, and presentation still lived behind one machine boundary. The requested framework must let an LLM change one separately versioned module without needing the implementation of every sibling.

**Options and decision:** splitting every concern into a service, registry, schema package, and message bus was rejected as more infrastructure than the current single-process Flask hub needs. The chosen slice keeps the hub, auth, discovery, plain HTML, Canvas, and SSE. It adds three runtime owners—Photon Level, Photon Board, and Photon Game—plus the presentation-only Laser Tag Y and static Photon Art. Siblings communicate only through small public snapshot/command functions carrying a named contract and integer version. Laser Tag Z remains unchanged and authoritative for its existing feature set; Y is a minimal framework vertical slice, not yet a parity replacement.

**Hub decision:** an optional manifest `group` places all Photon tabs under one Photon Engine dashboard label without inventing a Photon shell service. Disabled state is loaded before lifecycle hooks, disabled routes return 503, optional `hub_stop()` runs on disable, and a live hub restarts after a toggle so module state cannot remain half-enabled.

**Verification:** a focused six-test suite checks contract versions, invalid-input rollback, server-side simulation without a presenter, local containment of a changed sibling contract, the Y presentation boundary, dashboard grouping, disabled-route 503 responses, skipped initialization, and clean stop hooks. The preserved Laser Tag Z regression suite also passes all 92 tests, and every changed/new inline browser script passes a JavaScript parse check. No hardware commands or live robot movement were performed.

**Owner:** The modular scope and minimal-framework goal are human decisions from the request. OpenAI Codex implemented this initial vertical slice and its non-hardware tests; final acceptance and any decision to port Laser Tag Z feature parity remain with the human.

### 2026-09-02 — Phase 4: extract the production level without replacing Laser Tag Z

**Trigger:** the initial Photon Level proved a module boundary with a toy JSON
level, but Laser Tag Z still parsed and wrote the production TMJ and loaded its
waves directly. It therefore did not yet prove that a separately versioned
Level repository could change without knowledge of game or presentation code.

**Options and decision:** deleting Z's known-good parser immediately would turn
the extraction into a risky rewrite, while keeping both modules writable would
create two authorities. Phase 4 instead copies the exact validated production
Tiled project into Photon Level and makes that module the only live layout-write
owner. `photon.level` version 2 publishes the small generic projection;
`photon.level.runtime` version 1 publishes the complete JSON-compatible graph,
blockers, ring topology, marker geometry, and waves. A narrow Z adapter consumes
those values and reuses its game-side routing algorithms. The unchanged former
map and parser remain read-only rollback fixtures for standalone Z until a later
cleanup phase proves the new boundary in operation.

**Interface decision:** layout changes are no longer arbitrary JSON replacement.
The one accepted input is all sixteen stable sockets plus an expected revision.
Photon Level performs the existing geometric and graph validation, validates a
complete candidate TMJ, and atomically replaces its own map. Z proxies map and
wave reads to Photon Level, forwards layout writes, surfaces the active source
and contract error in state, and adopts a new revision only during setup. A
revision published during a run waits until reset.

**Tiled-skill influence:** the extracted project retains native TMJ/TSJ
editability, normalized modular components, hidden references, exact 1696×960
bounds, and semantic objects. No asset normalization was rerun because the
source pixels were copied unchanged. The component alpha audit found 73 readable,
non-empty images; the native render was visually inspected for seams, missing
tiles, accidental overlays, and clipping.

**Verification:** the Photon contract/extraction suite passes 12 tests, including
self-contained Level asset paths, same-input legacy/new parser parity for routes,
sockets, rings and blockers, a file-path-free Z runtime, hub-style blueprint names, and Z
map/wave proxying. All 92 preserved Laser Tag Z tests pass. The modular validator
reports 18 ground modules, 61 sunken road modules from six distinct road assets,
100% ground coverage, 16 sockets, 23 nodes, 40 edges, no warnings, and no visible
reference layer. Tiled 1.12.2 successfully round-trips the 14-layer, eight-tileset
map and created a temporary 1,980,641-byte native render for visual inspection.
Changed inline JavaScript parses.
No hardware command or live robot movement was performed.

**Owner:** Extracting the production level while preserving Laser Tag Z is the
human decision. OpenAI Codex implemented the contract, adapter, editor, module-
local assets, specifications, and non-hardware verification. Human review and a
live installation trial remain required before deleting the rollback fixtures.

### 2026-09-02 — Phase 5: extract production board observation and fail closed

**Trigger:** Photon Board's initial vertical slice normalized simulated tags,
but Laser Tag Z still assembled gameplay evidence by calling Webcam, Camera
Calibration, and Relay directly. A separately versioned Board repository could
therefore be changed or disabled without its advertised boundary actually
controlling the production game.

**Options and decision:** moving camera capture or robot ownership into Board
would merge unrelated jobs and create another robot-control path. Keeping Z's
direct reads as an automatic fallback for every Board error would hide broken
contracts and defeat isolation. Phase 5 instead adds three small versioned,
read-only hardware outputs and makes Photon Board their validating adapter.
`photon.board.runtime` version 1 carries the complete corrected observation;
the existing `photon.board` version 1 remains the small generic projection.
Laser Tag Z prefers the runtime contract and accepts only fresh output labeled
as corrected live-camera evidence.

**Failure and rollback decision:** missing or disabled Board permits Z's former
direct reader solely as a standalone rollback path. Once an enabled Board is
present, mismatch, malformed values, simulation, stale data, or invalid camera
correction produces no tags and no arms; Z never bypasses the failure by reading
the legacy siblings. Board reports each hardware input independently, and Relay
failure removes arm evidence so the existing connected/enabled/pump-off safety
gate still fails closed.

**Verification:** the 17-test focused framework suite covers the three versioned
input contracts, preservation of production tag corners and arm poses, the
generic projection, local containment of a changed calibration contract, Z's
Board-first adapter, its arm-state route, and refusal to bypass an incompatible
Board and the explicit standalone rollback path. All 92 preserved Laser Tag Z
tests pass, the complete 109-test repository
suite passes, and the changed inline JavaScript parses. No hardware command or
live robot movement was performed.

**Owner:** The phased modular extraction and preservation of Laser Tag Z are
human decisions. OpenAI Codex implemented the Phase 5 contracts, adapter,
diagnostics, specifications, and non-hardware tests. Human review and a live
camera/robot-state trial remain required before deleting the rollback reader.

### 2026-09-02 — Phase 6: extract the proven simulation into Photon Game

**Trigger:** the initial Photon Game tab proved a small input/output boundary,
but its toy path follower did not implement Laser Tag Z's waves, particles,
placement lifecycle, force fields, ring objective, core sequence, or four
weapons. Laser Tag Y could therefore demonstrate modular wiring without being a
credible production game.

**Options and decision:** gradually reimplement Z mechanics in the toy engine
would create two subtly different games, while importing Z's package or reading
its files would make the repository boundary false. Phase 6 instead copies the
proven server-authoritative simulation and settings store into Photon Game's own
package. The file-based LevelModel, TMJ helpers, path constants, rendering, and
asset serving are omitted. Construction and reload accept only validated
`photon.level.runtime` version 1 values; physical ingestion accepts only
validated `photon.board.runtime` version 1 values.

**Contract and ownership decision:** `photon.game` advances to version 2 because
the production snapshot replaces the toy schema. One `game_snapshot()` output
contains authoritative simulation state, input/storage diagnostics, and the
small level projection a presenter needs. One `game_events()` SSE stream carries
compact instances of the same contract. Settings are atomically stored under
Photon Game, and numbered simulation events plus operator commands append to its
module-local JSONL history. Changes saved during a run apply to the next Start;
the active settings snapshot remains immutable. Laser Tag Y was adjusted only
to consume version 2 and render its value shapes. Laser Tag Z remains untouched
as the proven rollback game.

**Failure and lifecycle decision:** no valid Level means no engine thread and an
explicit unavailable snapshot. A changed Level revision is adopted in setup and
deferred during a run. Bad Board output supplies no tags or arms but does not
prevent virtual play. The hub lifecycle owns the copied simulation thread, and
history writes are serialized so simultaneous simulation and operator events
cannot interleave JSONL records.

**Verification:** the focused framework suite now passes 23 tests. New coverage
compares deterministic production snapshots from Z and the extracted engine for
the same contract input, rejects file/TMJ/camera/renderer/asset dependencies,
checks module-local settings and JSONL history, proves active settings remain
frozen, verifies exactly one snapshot route and one SSE route, contains changed
Level and Board versions locally, and defers Level revision adoption until
reset. All 92 preserved Laser Tag Z tests pass as part of the complete 115-test
suite, and both changed inline scripts parse. No hardware command or live robot
movement was performed.

**Owner:** The Phase 6 scope and the instruction to copy the proven simulation
are human decisions. OpenAI Codex implemented the value-only runtime, storage,
contract adapter, Y compatibility update, specifications, and non-hardware
verification. Human review and a live full-game trial remain required before Z
can cease being the production rollback reference.

### 2026-09-02 — Phase 7: create the Photon Game presentation in Laser Tag Y

**Trigger:** Photon Game version 2 could run the proven simulation in isolation,
but Laser Tag Y still used a toy single-Canvas view. It omitted Z's combat
presentation, physical/virtual operator experience, and dedicated external
screen, so it could not yet exercise the intended production boundary.

**Options and decision:** importing Z's browser code or continuing to fetch its
map and assets would couple two repositories. Rebuilding every effect would
discard proven presentation work. Phase 7 therefore copies Z's renderer into
Y, removes its TMJ loading, level editor, camera overlays and interpretations,
and replaces those inputs with the display projection embedded in
`photon.game` version 2. The renderer retains towers, directional aiming,
enemy animation, weapon effects, force fields, destruction, and the core
sequence. Its map layer is drawn from snapshot paths and sockets rather than
authoring files.

**Contract and ownership decision:** Photon Game is Y's only changing input.
Y's physical, virtual, and external-screen views all render that same snapshot,
and authenticated UI intent is forwarded to Game without local gameplay
mutation. Physical-start readiness moved into Photon Game so the presentation
cannot become the rules authority. The display projection adds socket owner and
size fields without exposing a Level file or sibling API. Photon Art advances
to `photon.art` version 2 and owns the copied immutable Z runtime images. Y may
read that optional static repository; all units still have Canvas fallbacks.

**Isolation and rollback decision:** Y looks up only Photon Game and optional
Photon Art through the hub. It contains no Level or Board lookup, camera URL,
TMJ parser, level mutation, settings/history owner, or combat calculation. A
bad Game contract produces a local unavailable presentation; missing Art only
reduces visual fidelity. Laser Tag Z and all of its files remain unchanged as
the rollback reference.

**Verification:** the focused framework suite passes 30 tests. New coverage
checks separate Gamemaster and external routes, exact command forwarding,
physical-start authority in Game, complete display geometry, forbidden Y
dependencies, preserved Z combat drawing, Canvas fallbacks, and Art ownership.
The complete 122-test repository suite passes, including all 92 preserved Laser
Tag Z tests. The copied renderer and both inline browser programs pass Node
syntax checks. A live local browser trial rendered the Game projection, loaded
the production tower/effect assets, changed to virtual mode, placed Atom 100 on
socket 40 through Game, and showed the same state on the control-free external
screen with no browser warnings or errors. No hardware command or robot motion
was performed; the physical path still needs an installation trial.

**Owner:** The Phase 7 scope and requirement to preserve Laser Tag Z are human
decisions. OpenAI Codex implemented Y, the display projection additions,
Photon Art pack, physical-start validation, specifications, and automated/live
non-hardware verification. Human review and a complete physical game remain
required before making Y the production default or removing any Z rollback
copy.

### 2026-09-02 — Phase 7 visual-parity correction

**Trigger:** a live Laser Tag Y screenshot showed the authoritative game and
combat effects over a schematic fallback: modular terrain and road sprites were
absent, socket markers were plain numbered boxes, and marker-to-tower placement
could no longer be checked against Laser Tag Z. The Photon Level source itself
was still complete, so this was a presentation-boundary omission rather than a
damaged authored map.

**Options and decision:** letting Y fetch or parse the TMJ would restore pixels
but violate the one-job boundary and couple Y to Level's source format. Letting
Game resolve image paths would mix simulation with artwork. Level now projects
visible Tiled objects once into `photon.visual-scene` version 1 values containing
stable asset IDs and precomputed draw transforms. Game forwards that opaque
scene and exact socket/core marker geometry in its existing version 2 snapshot.
Photon Art owns the independently served normalized image copies and real ArUco
PNG files; Y joins IDs to the Art manifest and only draws. The local Level image
copies remain solely so its Tiled project is independently editable.

**Compatibility and failure decision:** the visual-scene, exact marker, and
core fields are additive to `photon.level.runtime` version 1. Photon Game accepts
an older compatible Level without them and supplies Y's plain Canvas fallback,
so repository updates do not require a lockstep deployment. Missing or invalid
Art likewise reduces fidelity without changing game truth. Asset URLs do not
cross module filesystems, and neither Level nor Art imports the other.

**Verification:** Photon Art's 12 scene assets all resolve from the Level IDs;
all 17 generated marker images (38 and 40–55) decode to their intended OpenCV
ArUco IDs. Alpha/visible-bounds inspection confirmed edge-filled ground/road
tiles and intentionally transparent objective/structure sprites. The modular
map audit still reports 18 ground modules, 61 road modules using six road
assets, 16 sockets, 23 nodes, 40 edges, full ground coverage, and no visible
reference layer. Native Tiled 1.12.2 opened, round-tripped, and rasterized the
14-layer/eight-tileset source successfully. In a local browser, Y displayed the
full industrial terrain, road, core and real markers; placing Atom 100 on marker
40 produced the same touching 112-pixel tower / 77-pixel marker alignment as Z,
with no browser warnings. The 33-test focused framework suite and complete
125-test repository suite pass, including all 92 preserved Z tests. No hardware
command or robot motion was performed.

**Owner:** the request to restore Z's graphics and ArUco presentation while
following the new module rules is a human decision. OpenAI Codex implemented
the contracts, Art catalog, Y composition, compatibility fallback,
specifications, and non-hardware verification. A full physical-camera and
external-projector trial remains human work before Y replaces Z.

### 2026-09-02 — Restore game settings through the modular boundary

**Trigger:** Laser Tag Y had Start, Pause, Reset, placement, and aiming controls,
but Phase 7 did not carry over Z's Tower Defense settings button or form. Photon
Game already owned the validated settings store and command handlers, leaving
the rules present but inaccessible to the Gamemaster.

**Decision:** settings remain part of Photon Game rather than becoming another
module. Its existing `photon.game` version 2 snapshot now embeds
`photon.game.settings` version 1 with the saved next-run draft, preset values,
numeric limits, revision, and authored per-wave enemy counts. No settings API or
second changing output was added. Laser Tag Y owns only the settings HTML: it
renders that value and forwards `configure` and `reset_settings` through its
existing authenticated command proxy. Defaults, validation, atomic persistence
in Photon Game's ignored `data/settings.json`, and immutable active-run settings
remain server-owned.

**Isolation decision:** configuration and reset do not require a live Level or
simulation engine. This lets Photon Game's own input be repaired while a sibling
repository is disabled or incompatible. Invalid fields return structured errors
for Y to display, while the parent Game contract and all unrelated tabs remain
available according to their existing failure rules.

**Verification:** the 35-test focused framework suite and complete 127-test
repository suite pass, including all 92 preserved Laser Tag Z tests. Tests cover
the nested settings contract, limits/presets, authored-wave summary, persistence
in a temporary module-local file, field errors, active-run freezing, operation
without Level, the Y route, and the game-page link. A local browser trial loaded
all 26 settings, three presets, limits, and calculated 12-wave/4,584-orc summary;
an invalid wave count displayed Photon Game's field error and the return link
reopened Y with no console warning or error. The invalid trial did not create or
change the real settings file. No hardware command or robot motion was performed.

**Owner:** the placement of the Gamemaster form in Y and settings authority in
Photon Game follows the human-selected modular structure. OpenAI Codex
implemented the projection, form, command/error bridge, specifications, journal,
and non-hardware verification.

### 2026-09-02 — Restore the ring-immunity HUD counter in Y

**Trigger and decision:** Laser Tag Y showed only `Ring complete` after closing
the objective ring, omitting Z's remaining-immunity counter. Photon Game already
publishes the authoritative `core_sequence.field_immunity_remaining_s`, so no
simulation or contract change was needed. Y now displays `Ring immune Ns`, using
the reported value rounded up for legibility, and returns to `Ring complete` at
zero. It does not derive an immunity deadline or modify force-field rules.

**Verification:** the inline Y script parses, the focused 36-test framework
suite passes, and the complete 128-test suite passes including all 92 preserved
Laser Tag Z tests. Regression coverage requires the reported remaining-time
field and forbids Y from consuming the internal absolute immunity deadline. No
hardware command or robot motion was performed.

**Owner:** restoring the operator-visible counter is a human decision. OpenAI
Codex implemented the presentation-only change, specification, regression test,
and non-hardware verification.

### 2026-09-02 — Restore direct turret aiming in Y

**Trigger:** Laser Tag Y exposed the copied direction and spread range inputs,
but lacked Z's direct relationship between the targeting guide and those
values. The Gamemaster had to adjust an abstract percentage away from the game
board, and the selected dotted guide had no draggable affordance.

**Decision:** Y now draws one circular handle at the end of the selected living
turret's dotted guide. Pointer angle changes direction; pointer radius changes
distance. For machine guns and flamethrowers, nearer means wider and farther
means narrower. Mortars use radius as target distance, while Tesla coils remain
omnidirectional and use radius as reach. The existing Direction and Wide/Narrow
sliders remain synchronized, accessible alternatives. Dragging is a local
presentation preview and sends one existing `aim` command on release; Y neither
applies combat rules nor commits aim state. Photon Game continues to validate,
store, simulate, and publish the authoritative angle and spread, and a rejected
command clears the preview back to Game output.

**Verification:** both Y JavaScript sources parse, the focused 38-test Photon
framework suite passes, and the complete 130-test suite passes including all 92
preserved Laser Tag Z tests. Node regression coverage checks direction
normalization, optical-position alignment, and the machine-gun, mortar, and
Tesla radius mappings. A local browser trial placed and selected a machine gun,
confirmed the handle aligned
with its dotted center guide, and confirmed that changing from narrow to wide
moved the handle inward while widening the rendered cone. No hardware command
or robot motion was performed.

**Owner:** restoring the Gamemaster aiming interaction is a human decision.
OpenAI Codex implemented the Y-only interaction, renderer geometry, contract
documentation, regression coverage, and non-hardware verification.

### 2026-09-04 — Complete Photon Level's authored-map preview

**Trigger:** Photon Level's tab drew plain path strokes and socket circles,
despite the existing projection already containing a renderer-neutral visual
scene. The authoring screen did not show the terrain, roads, core artwork, or
side-mounted marker locations that the operator needed for placement editing.

**Decision:** add a small Level-owned Canvas preview of the existing scene,
using the module's local Tiled assets. A module-local `photon.level.editor` v1
endpoint captures the layout, scene, image URLs, and marker resize vectors at
one revision. The browser draws precomputed sprite transforms and affine marker
offsets, without parsing TMJ, importing Y, or depending on Game/Board/Art being
enabled. Local authoring copies of ArUco 38 and 40–55 are the only new images.
No runtime OpenCV dependency is added. Public Level/Game contracts, simulation,
Z, the map, and wave definitions remain unchanged.

Owner-colored placement bounds, centers, labels, real marker codes, and optional
route guides sit above the static scene. Dragging either a placement or its
marker preserves the pointer offset; resizing preserves the fixed code footprint.
The existing authenticated all-socket validation and optimistic revision check
remain the only write path. Rejections retain the draft. Reload uses an inline
discard confirmation, avoiding a blocking browser-native dialog in embedded tabs.
Missing source artwork fails explicitly instead of silently showing a schematic.

**Verification:** 136 tests passed (the existing 130 plus six editor tests).
The six additions cover local image serving with no sibling modules, unchanged
runtime output, real ArUco decoding, missing-asset/source failures, authentication
and stale revisions, and Node display geometry checked against Python's parsed
TMJ at three socket sizes for every socket. Browser checks used a temporary map
copy: graphics loaded, marker dragging changed the corresponding coordinates,
a resized placement saved and reloaded at the next revision, and an out-of-bounds
marker was rejected without clearing the draft. The unchanged map passed the
modular validator (18 ground objects, 61 road objects, 16 sockets, full terrain
coverage, no visible reference painting), Tiled 1.12.2 round-trip, and native
raster inspection. No physical camera/projector or robot trial was performed.

**Owner:** the human requested an art-backed authoring preview. OpenAI Codex
implemented the Level-only preview, documentation, and non-hardware verification.

### 2026-09-04 — Put the settings form with Photon Game

**Trigger:** the operator requested that the Photon Game tab contain its own
configuration controls rather than requiring Laser Tag Y to edit game settings.
Game already owned the presets, defaults, validation, persistence, and immutable
active-run settings; only the form remained in Y.

**Decision:** move the existing form into Photon Game's default page, with a
stable `/settings` alias. It uses Game's existing state and command endpoints
directly. Game's command response now includes field-level validation errors,
matching the information previously supplied by Y's forwarding route. There is
no new settings API, module, or data migration. Status and collapsible input and
storage diagnostics below the form consume the existing SSE stream without
overwriting unsaved form values. Immediate Start/Pause/Reset and turret controls
remain in Y; Game still serves no live renderer or artwork.

Y's existing settings button and bookmarked `/settings` route now redirect to
Game's form, checking that Game is enabled and contract-compatible and preserving
the sandbox URL prefix. The duplicate Y settings HTML is removed. Game's own
page links back to the hub and remains usable without Y, Level, Board, or Art.
Existing saved configuration and Z are unchanged.

**Verification:** all 139 tests passed, including three added regressions for
shortcut isolation/prefix handling, the standalone Game settings page and HTTP
validation/persistence, and a Node form test proving SSE does not replace draft
edits. Existing tests continue to verify frozen active-run settings. A local
browser trial followed Y's shortcut into Game, saved seven waves, rejected an
invalid 99-wave value with its inline field error, and reloaded the saved value.
The trial used temporary settings/history files and no camera or robot module.
The temporary server and browser tab were closed; the running installation was
not restarted.

**Owner:** the human requested moving the form to its module owner. OpenAI Codex
implemented the move, compatibility shortcut, documentation, and verification.

### 2026-09-04 — Give Photon Board physical tracking diagnostics

**Trigger:** the human requested arm tracking, target proximity, observed tag
transport stages, a diagnostic overlay and per-tag table, with the same
segmented proximity-meter appearance as the LTX player.

**Decision:** extend the existing Board, not add another runtime module. One
Python sampler owns physical observation and bounded transport/dwell state;
browser refreshes and additional readers cannot advance it or multiply hardware
sampling. Existing Board/runtime v1 outputs add `photon.board.tracking` v1 and
the existing SSE stream carries it. The tab renders corrected-frame tag pins,
projected base-to-TCP arm illustrations, candidate/target lines, two arm panels
with 24-segment amber/green meters, per-tag evidence and optional fixed markers.
Both normal marker destinations and other raised tags can be measured; source
tags are excluded from their own destination list.

**Boundaries:** Auto Pickup remains the owner of Auto PP Cal 2. It now exports
read-only projection and last authenticated LTX controller-report contracts;
Board never reads its calibration files or imports its implementation. Webcam
exports the processed-frame timestamp; Relay exports source feedback time.
Cartesian movement-target error is separated from calibrated marker proximity,
and joint angles cannot be shown as millimetres. Calibrated Z is an estimate,
explicitly excluding player-local fine tuning. Camera preview uses the existing
corrected stream through a discovered, versioned preview descriptor.

**Truth and failure handling:** the physical stage is separate from the
controller-reported stage. Near-arm occlusion with suction can infer a pickup or
likely carry, never guarantee a grip. Pump release still needs camera placement
confirmation. Ambiguity, stale frames/feedback, missing parallax, malformed or
incompatible outputs and sampling gaps do not preserve authoritative inferred
state. Stable placement is diagnostic, not turret activation. Z is unchanged;
Game's existing physical placement acceptance remains pending Phase 8 parity
work, and no robot-command, scoring or combat path was added or changed.

**Verification:** 27 dedicated tracking tests cover projection/parallax,
candidate ambiguity, two-arm conflicts, pickup/carry/release/stable placement,
frame-unique dwell, stacked-target distances, source freshness, contract errors,
simulation/authentication, lifecycle and cached readers. A plain-JS DOM smoke
test verifies the bars, frame alignment, SSE/draft behavior and stale clearing.
The combined Photon suite has 74 passing tests; the full suite passed all 166
tests in 64.468 seconds. Browser inspection used a
temporary localhost server with synthetic tags, arm feedback and calibration;
it verified the visual meters, fixed-marker filter and loss-of-stream clearing.
The temporary server and tab were closed. No robots were connected or moved,
no installation calibration was changed, and the user's hub was not restarted.

**Owner:** the human requested the feature and module boundary. OpenAI Codex
implemented and verified this working-tree change; it is not yet committed.

### 2026-09-04 — Merge Photon Art into the Level content package

**Human request:** proceed with the proposed merge: Level owns maps, waves,
and static artwork; Game forwards the asset references; Y consumes only Game's
output. Preserve Laser Tag Z and the independent module boundaries.

**Decision:** the standalone Art prototype is removed from hub discovery.
Its runtime images and manifest now belong to Photon Level. The original
163 Art files were compared byte-for-byte: 90 were already identical Level
files, 73 were added, and no conflicting files were overwritten. The remaining
old folder was moved to `/private/tmp/photon-art-merged.tj8iPs/photon-art` as a
temporary recovery copy. Tracked originals also remain recoverable from Git.
No new dependency, service, module registry, or hub change was needed.

Level's existing Artwork gallery moved to its local `/art` page, linked from
the editor and Level's module entry. The new additive `photon.level.assets` v1
descriptor lives in `runtime_bundle().presentation` and `/api/assets`.
Scene asset IDs resolve from the local tilesets rather than a duplicate filename
table. Runtime and editor images share the same package files. Content hashes
version image URLs; stat-cached hashing avoids rereading unchanged images.
HTTP responses revalidate because Level does not promise historical image bytes.

Game checks and forwards the descriptor, never reading or serving asset files.
Missing/incompatible artwork reports an unavailable presentation input while
valid simulation and settings continue. Art-only updates do not reset a run;
pending geometry and its associated presentation stay deferred together.
Both Y displays now take asset references from their Game snapshot/SSE, refresh
image caches on content revision changes, and reject late superseded image
loads. Y has no Art or Level module lookup. Its old `/api/art` is only a
compatibility projection of Game's output. No image bytes are placed in SSE.

**Verification:** all 174 tests pass, including eight new content-boundary tests,
78 manifest URL/hash checks, ArUco decoding, shared editor/runtime file mapping,
asset replacement/removal/recovery, incompatible optional inputs, state/command/
SSE pass-through, active-run preservation, sandbox prefixes, and the real Y
renderer exercised with a deterministic Canvas/Image harness. Modular validation
reports 18 ground modules, 61 roads, 16 sockets, complete coverage, and no visible
reference painting. Tiled 1.12.2 round-trip and native render pass. Browser checks
of the Level editor, merged gallery, Y gamemaster, and Y external screen passed
on an isolated localhost fixture with temporary game settings/history and no
hardware modules. Canonical map and Laser Tag Z checksums are unchanged.

The running hardware-connected hub was not restarted. A safe hub restart and
page refresh are required to load the new Python module layout; physical trials
and Phase 8 cleanup remain separate work. No commit or push was made.

**Ownership:** user-directed architecture; OpenAI Codex implementation and
non-hardware verification in the current uncommitted working tree.

### 2026-09-04 — Make Board proximity diagnostics configurable

**Human request:** allow editing Near XY, Near Z, unique margin, and stale age
in Photon Board while retaining the original defaults: 90 mm, 60 mm, 20 mm,
and 1.5 seconds.

**Implementation:** Board's new **Proximity settings** form offers four numeric
fields, persistent **Apply settings**, and **Use defaults** (draft until applied).
Defaults and bounds come from the module's `photon.board.settings` v1 output,
also carried in the existing tracking/SSE output. Saved overrides live only in
`photon-board/data/tracking-settings.json`, loaded at hub initialization and
replaced atomically after complete server validation and gamemaster auth.
No settings file is created on first use. Invalid saved files are reported and
left untouched while defaults are used; failed writes preserve prior settings.
SSE does not overwrite unsaved values or dismiss save errors.

The next sample uses the new thresholds; old consideration, carry and placement
dwell inference is cleared to avoid mixing evidence collected under different
limits. Equal-distance ties stay ambiguous, including at zero unique margin.
The configurable sensor timeout is diagnostic only. Board reads inputs once,
then derives the diagnostic and game-facing observations with separate age
gates. The existing 1.5-second game-facing gate, sampler/stream liveness,
placement tolerances, calibration ownership, robot safety, and Game's rules
remain unchanged. No new module, dependency, or control path was introduced.

**Verification:** 187 tests passed, including 13 new settings tests and expanded
plain-JS UI tests. Coverage includes defaults, numeric boundaries, proximity
and meter behavior, ambiguity, shorter/longer freshness, auth, atomic save
failure, corrupted-file diagnostics, restart persistence, explicit defaults,
missing-input operation, evidence reset, and isolation from game-facing gates.
An isolated browser fixture confirmed editing all four fields, active limits
updating, reload persistence, and restoring the original defaults. It used
fake sensor/arm inputs and temporary settings, not the hardware-connected hub.

**Ownership:** user-directed change; OpenAI Codex implementation and verification.
The change is uncommitted. The running hub was not restarted; load the new
Python code at a safe stopping point and refresh the Board page.

### 2026-09-04 — Show Y's data flow without adding dependencies

**Human request:** add a visual window to Laser Tag Y showing its information
sources, connected nodes, flowing animation, and labels.

**Decision:** keep observability inside the presentation instead of adding a
monitoring service or independent reads of Level and Board. The **Data flow**
button opens a native dialog with Level/Board → Game → Y and image files → Y.
Upstream edges are dotted and labelled as Game-reported dependencies. Image
source addresses come from Game's presentation descriptor, not module discovery.
Clicking a node reveals fields, input addresses, health and received counts.

The window consumes callbacks from Y's existing snapshot/SSE and renderer image
loader. Moving dots indicate recent SSE or actual image-loader activity;
cached image completions are not claimed to measure network traffic. Missing,
incompatible, disconnected or stale feeds show explicit diagnostic states and
stop the live-state animation. Controls allow pausing motion, reduced-motion
preferences are respected, and a local age-refresh timer exists only while the
window is open. The external screen uses the same contract but is not remotely
monitored. Game, Board, hardware controls, and Laser Tag Z are unchanged.

**Verification:** 190 tests passed. New route, boundary and plain-JS smoke tests
cover source labels, initial snapshots, SSE arrival/loss/staleness, reconnects,
incompatible contracts, image failures, pause/resume, narrow-layout connector
geometry, and cleanup. Renderer tests also verify image counters and rejection
of late superseded asset loads. An isolated, hardware-free browser preview
confirmed the diagram layout, source details, real image counts and motion
controls using temporary game data. No live hub restart or hardware action was
performed. New static routes require a safe hub restart before page refresh.

**Ownership:** user-directed change; OpenAI Codex implementation and non-hardware
verification. The implementation remains in the uncommitted working tree.

### 2026-09-04 — Trace Y inputs back to their original sources

**Human request:** extend Y's data-flow tree through calibration, Dobot relay
and camera feed to the ultimate sources, rather than stopping at Board/Level.

**Decision:** show the existing architecture, not add another dependency chain.
The expanded tree distinguishes captured pixels, raw ArUco detections, corrected
tags, saved lens calibration, saved Auto PP Cal 2 arm calibration, MG400 feedback,
relay command/pump state, Player LTX stage intent, authored content, and Game's
settings/operator inputs. Board's projection call into Auto Pickup and its
returned diagnostic values are both visible. Corrected video ends at the Board
preview and is never presented as a Game/Y input. Static files stay with their
owner. Branch jumps keep the larger scrollable tree readable.

Game now forwards a bounded `inputs.board.upstream` health summary from the
Board value it already reads. Compatible unavailable input retains useful error
reports while contributing no physical evidence. Missing/incompatible input
clears the report. No new read, endpoint, module, calibration copy or hardware
control path was added. Y describes known routes and displays only forwarded
reports; hardware identities and video connections are explicitly unmonitored.
Report age is independent of Game SSE age, and virtual play marks Board unused.

**Verification:** 194 tests passed, including four new Game diagnostic-boundary
tests and expanded real-JS diagram tests. Coverage includes one-read behavior,
unavailable/incompatible/malformed inputs, no raw-data leakage, contract version
checks, all source branches, video exclusion, historical health during live SSE,
and diagram cleanup. A hardware-free browser preview checked the scrollable
layout and source details; no live camera/robot was opened or hub restarted.

**Ownership:** user-directed change; OpenAI Codex implementation and verification
in the uncommitted working tree. Reload the new Python code at a safe stopping
point and refresh Y; there was no commit, push, or hardware action.

### 2026-09-04 — Phase 8 authority cleanup after deterministic parity

**Human request:** execute Phase 8 in the accepted order: baseline, Board
contract, parity comparison, Game migration, Y cleanup and final acceptance,
without a new module, broker or calibration-ownership change. Laser Tag Z must
remain unchanged.

**Baseline:** the complete 194-test suite passed before cleanup. The exact
Laser Tag Z tree fingerprint was
`1412875013ae9a0218f08925d4483c2c1c846490ac05257a87bae2c5f7488c6b`.
The audit confirmed Photon Game already had no copied LTX state/scoring system
and neither Game nor Y parsed TMJ. Remaining duplication was Game's raw
normalized-coordinate placement detector and Y's weapon-control formulas.

**Decision:** add one nested `photon.board.placement` v1 value to Board's
existing sample. Board now owns game-facing movable/fixed marker association,
fixed-marker memory, arm-ready/pump-off gating, target-order resets and dwell.
It uses corrected normalized camera data directly and does not depend on Auto
PP Cal 2. Calibration and robot-control ownership did not move. The descriptor
contains generic physical relationships only; Photon Game still owns tag/team
identity, Level marker-to-socket mapping, placement legality and core sequence.
No endpoint, stream, module or process was added.

A deterministic fixture compares unchanged Z's original raw-input detector to
Board → Game for suction blocking, the original dwell, first placement and a
second placement after moving the same tag. After parity passed, Game's marker
cache, distance calculation and physical candidate timers were removed. Game
now validates and consumes only the named placement descriptor. Board failures
clear current evidence and are surfaced instead of being swallowed. Run/core
gates require one Board-declared evidence window after opening, without Game
recalculating physical stability.

Y's copied weapon range/cone/splash/damage preview table and link-multiplier
fallback were removed. Game publishes generic control endpoints with each
authoritative tower targeting result; Y only interpolates those supplied values
for the existing handle and sliders. Both Y displays cap interpolation and
freeze it when the SSE feed disconnects. Game settings now validate saved-file
shape, expose load errors, persist before publishing a new draft/revision, and
preserve the previous in-memory state on save failure.

**Verification:** 204 automated tests pass, including new Board-contract,
unchanged-Z parity, malformed-boundary, settings-corruption/write-failure,
Game-supplied drag-geometry and disconnected-feed tests. This is hardware-free
acceptance only. An isolated browser fixture rendered Level-owned map art and
ArUco markers, all four turret sprites, the selectable aim handle, Game's own
settings page, and Y's external screen. The final Z fingerprint remained
`1412875013ae9a0218f08925d4483c2c1c846490ac05257a87bae2c5f7488c6b`
with no Z diff. No camera or robot was opened and no live hub was restarted. A
full physical four-weapon/ring/core/external-screen run remains an operator
acceptance step.

**Ownership:** user-directed change; OpenAI Codex implementation and
non-hardware verification. The work remains uncommitted.

### 2026-09-04 — Close the Phase 8 audit gaps without new infrastructure

**Human request:** execute correction-plan steps 1–6: protect the Phase 8 tree,
remove Y's remaining copied identifiers, add changed-contract and repository-
boundary checks, distinguish Board's diagnostic and game placement evidence,
and audit compatibility routes.

**Decision:** checkpoint commit `279b715` was pushed to the existing fork before
further edits. Y now derives loadout IDs/types, socket count, ring bounds, core
marker identity and available image keys from Photon Game's existing values. It
does not substitute a flame range when targeting geometry is absent. No contract
version or endpoint was added. Board's existing tracking projection now carries
an additive copy of its already-cached `photon.board.placement` value so the tab
can label calibrated diagnostic overlap separately from the normalized evidence
Game consumes; neither calculation nor calibration ownership moved.

One fixture-only isolation suite exercises Level from its own files, Board from
explicit simulation, Game from an in-memory `photon.level.runtime` producer,
and Y from a changed Game-shaped value. It loads no sibling implementation as a
producer. Y's application code and available request logs contained no caller of
the compatibility-only `/api/art`, so that route and its tests were removed. The
actively used `/settings` shortcut remains and still checks Game's contract.

**Verification:** all 113 Photon-focused tests and the complete 208-test
repository suite pass, including the four new isolation/variation checks, and
the updated Y renderer parses with Node. Laser Tag Z has no post-checkpoint
diff. No camera, robot, projector or live hub was opened. Physical acceptance
and publication of the correction remain separate later steps.

**Ownership:** user-directed cleanup; OpenAI Codex implementation and
non-hardware verification.

## 2026-09-04 — Brute size, strength, and Gamemaster tuning

The user requested Brutes four times the Grunt's visual width and height,
introduced in wave 4, with four times their former health and damage. Photon
Game now defaults to 960 HP and 64 damage per second against both core and
defense pods. Its settings tab exposes first wave, relative size, health, and
damage; existing global multipliers continue to apply and changes take effect
on the next Start. The current authored Brute waves remain 4, 8, and 12.
Changing the first wave substitutes roles while retaining authored group
counts, timing, and lanes. Game never edits Level's wave source.

Y reads relative size from the active run settings, scales the body and its
effects in both displays, and allocates sprite caches for the full rotated
diagonal. Collision geometry, speed, and melee reach retain their existing
values. Complete older settings files acquire the new defaults without losing
saved tuning; malformed files remain explicit failures. Laser Tag Z remains
the rollback implementation.

Verification covers default/custom Brute stats, wave introduction, unchanged
group totals, validation, persistence, next-run freezing, older-file loading,
and the real renderer's fallback, rotated sprite cache, burn, and skeleton
dimensions. User-directed implementation by OpenAI Codex; working-tree change,
not yet committed. No hardware operation is part of this change.

## 2026-09-05 — Rare Brutes among regular orcs

The user changed the requested mix to one large, strong Brute for every forty
regular-sized orcs. From the configured first Brute wave (default 4), every
41st scheduled enemy is now a Brute. The pattern restarts each wave and spans
its groups after count scaling; remaining slots stay regular. Wave 4 keeps
its total of 262 enemies, now comprising 256 regular Grunts and 6 Brutes.
Authored Brute groups supply Grunts in regular slots; other authored roles,
release timing, and lane weights are retained. Brute size, health, damage,
and first-wave settings remain available.

Deferred spawns retain their sequence position through blocked lanes and the
active-enemy cap. Regular Grunt, Runner, and Breaker sprite sizes are unchanged.
The settings hint and Game specification describe the revised mix.

Verification: all 124 Photon tests pass, including actual spawn-sequence
checks for every wave, count multipliers, group boundaries, remainders,
deferred spawns, and renderer checks for all regular orc sizes. User-directed
implementation by OpenAI Codex; working-tree change, not yet committed.

## 2026-09-05 — Halve Brute visual size

The user requested Brutes at 50% of their current size. The default size
relative to Grunts changes from 4 to 2 in Photon Game, with matching settings
help and specifications. Y already derives sprites, fallback shapes, and
attached effects from this run setting. Health, damage, spawn ratio, and regular
orc sizes retain their existing values. The local saved settings contain no
Brute size override and will acquire the new default on load. Existing Brute
tests cover the updated default and renderer proportions. User-directed
implementation by OpenAI Codex; uncommitted working-tree change.

## 2026-09-05 — Live playfield FPS monitor

The user requested current FPS beside Virtual play. Y now keeps a compact
readout with that control and updates it once per second from completed
playfield draws. Samples reset on browser visibility changes; optional monitor
callbacks cannot stop rendering. The monitor adds no network or Game state.
All 125 Photon tests pass, including measured draw rates, interaction redraws,
visibility recovery, and cleanup; renderer and page scripts parse successfully.
User-directed implementation by OpenAI Codex; uncommitted working-tree change.

## Lessons retained in the current design

1. **Prototype topology is disposable; security boundaries are not.** The three-process launcher was replaced within a day, but role isolation and relay-side enforcement survived in the single hub.
2. **Derive identity from trusted context.** Team and local service location come from the authenticated sandbox, reducing both setup burden and spoofable inputs.
3. **One component owns each actuator.** The relay arbitrates all normal robot access; leases, stale-token rejection, watchdog holds, workspace clamps, and hardware E-stops define the safety envelope.
4. **Presentation transforms must not alter calibration math.** A player's rotated video is a UI concern. Calibration and live detections stay in one raw corrected-camera coordinate frame.
5. **Intent is not outcome.** Motion commands, release poses, and queue destinations are evidence about intent. Sustained physical observation is the final board authority.
6. **Do not turn missing attribution into false divergence.** Late or ambiguous telemetry yields “board truth unattributed”; divergence is reserved for a unique, evidence-backed contradiction.
7. **Recovery paths must share normal transitions.** Manual placement, reload recovery, and late operation replay reuse normal activation, center, scoring, and run-ending behavior.
8. **Preserve evidence before polishing it.** Command monitoring, JSONL run logs, append-only score logs, operation IDs, and typed destinations make later corrections possible.
9. **A live operator needs escape hatches.** Direct takeover, pause/resume, stop, runtime click override, manual placement, and score-table reset each solve a different operational failure without erasing durable history.
10. **Write “what” and “why” separately.** Reconstruction specifications define current compatibility behavior. This journal records chronology, reversals, evidence, and rationale.
11. **Editor geometry is a runtime contract.** Tiled object alignment, marker IDs, path graphs, blockers, and code footprints must be interpreted identically by the editor, validator, engine, and renderer.
12. **A movable activator should record an event, not occupy the whole game state.** Stable physical release can create durable gameplay state while ownership and arm safety remain physical constraints.
13. **Visual size is not safety geometry.** Editable socket art can change presentation and interaction without changing the protected ArUco identification footprint used for topology.
14. **One lifecycle should derive every public projection.** A canonical connection record prevents a force field from existing, rendering, and colliding differently in separate consumers.
15. **Spatial objectives must be spatially deterministic.** The same living layout should produce the same safe ring regardless of activation history; multi-edge completion must be atomic.
16. **Keep simulation authority and visual richness separate.** The server owns targets, damage, timing, and outcomes. The browser may interpolate motion and render particles, but it must not invent combat results.
17. **A module boundary needs a small contract, not a new platform.** In one trusted process, versioned public functions plus explicit unavailable states preserve isolation without a broker, registry, or universal I/O abstraction.
18. **Extract one authority before deleting the fallback.** A versioned value contract and exact parity fixture let production consumers move first; the old parser can remain read-only until live operation proves removal safe.
19. **A fallback must not mask an installed module failure.** Standalone rollback is useful when an adapter is absent, but a present incompatible safety input must fail closed and remain visible in diagnostics.
20. **Copy proven rules, not proven coupling.** Simulation behavior can move intact while file parsing, hardware lookup, rendering, and asset ownership are replaced by versioned values at the new boundary.
21. **A presentation may receive geometry without owning the level.** A small display projection lets Canvas draw and hit-test authoritative state while TMJ parsing, editing, revision control, and authored files remain in the Level module.
22. **Project source once; compose it at the edge.** Level converts editor-specific alignment into stable visual transforms, Game transports those values without interpretation, Art resolves stable IDs, and Y remains a presentation rather than a second level parser.
23. **Put the form with the operator and the rules with the authority.** Y may present every tuning control, but Game publishes the schema, validates intent, freezes run settings, and owns persistence.

## Human and AI contribution record

The following commits explicitly record AI co-authorship:

| Commit | Recorded work | Human authority | Recorded AI contribution |
|---|---|---|---|
| `2e64247` | initial gamemaster host | Kaspar Kallas | Claude Opus 4.8 |
| `970eb18` | operator takeover controls | Kaspar Kallas | Claude Opus 4.8 |
| `c99a4b6` | three-process launcher | Kaspar Kallas | Claude Opus 4.8 |
| `2f027f8` | two-arm relay and controllers | Kaspar Kallas | Claude Opus 4.8 |
| `486573a`, `93260e3` | single authenticated hub | Kaspar Kallas | Claude Fable 5 |
| `a2e4b00` | dual-interface robot routing | Kaspar Kallas | Claude Fable 5 |
| `4ebaef5` | server-derived controller identity and UX | Kaspar Kallas | Claude Fable 5 |
| `0b3e8c0` | pickup prototypes and relay/controller updates | Kaspar Kallas | Claude Opus 4.8 |
| `df67311` | side-by-side pickup UI | Kaspar Kallas | Claude Opus 4.8 |
| `c7c5c65` | Laser Tag X score-history analysis | Kaspar Kallas | Claude Fable 5 |
| `7801c28` | calibration data and runtime evidence | Kaspar Kallas | Claude Fable 5 |

The remaining commits through `9d22a3a` are authored by Kaspar without an AI trailer. Their correct label is **human-recorded; AI involvement not evidenced**, not “definitely human-only.” Commit `561b4e4` is a special case: it lacks an AI trailer, but the journal committed in that change explicitly records OpenAI Codex's implementation and verification role for the crane controls and arm overlays. That narrower file-level provenance should be retained without rewriting the Git trailer record.

At the August 29 reconstruction, the Laser Tag Z changes after `9d22a3a` were uncommitted. Subsequent checkpoints include `d8ffbdf`, the September modular extraction commits, `279b715`, and `cd00d97`; the earlier working-tree status is historical, not the current release boundary. Commit `cd00d97` records Kaspar Kallas as author and committer without an AI trailer. Earlier journal entries retain their narrower recorded AI provenance. The mobile continuation after `cd00d97` remains uncommitted, so its implementation ownership is not inferred from file style or the current assistant. OpenAI Codex reviewed evidence, ran the checks listed below, and wrote this September 22 continuation at the user's request.

## Evidence of physical iteration

At the 2026-08-19 reconstruction, the local working setup contained 89 Laser Tag X JSONL runs from August 9–19, totaling 21,968 events, and 26 appended win records. That is historical evidence recorded by the earlier journal pass; those ignored local files are not present in the current checkout and were not recounted on 2026-08-29. The recorded event mix showed repeated real-system iteration rather than a purely paper design: release-pending and unresolved center transactions, activation blocks, late attribution, operation failures, reload recovery, and finally camera-authoritative decisions with matched operation attribution.

The August 29 reconstruction recorded a focused 84-test Laser Tag Z suite; later entries record the growth of Photon and integration coverage. On September 22, the focused mobile and enemy-guidance Python runs passed 54 tests, and the selected Node run passed 26 checks. These are selected suites, not a current full-repository count. The older physical-game stack still relies substantially on specifications, runtime diagnostics, score/run logs, and physical trials. Deterministic tests should still be added around state patches, recovery, event correlation, scoring, coordinate transforms, and multi-frame voting wherever hardware can be simulated.

## Known trade-offs and unfinished edges

- The browser owns high-frequency fusion state. Reload recovery can reconstruct activated targets and finale state, but not every per-tag sequence index, frozen pose, or historical binding.
- Server game state and the current diagnostic run are process memory. JSONL files are durable evidence, but a server restart does not automatically resume the previous run.
- Manual completion keeps an event running but intentionally weakens the claim that every transition was physically sensed; the diagnostic record must retain that distinction.
- Calibration is installation-specific data. Updating it is a real system change and should be paired with the physical setup and a dated journal entry.
- The current camera-authoritative rule depends on camera quality. It fails closed when corrected tracking or a valid spatial model is unavailable, and the gamemaster remains the recovery authority.
- The earlier Laser Tag Z, Photon, mobile and two-player calibration work has Git checkpoints through `53bb9c8`. The October 9 entry records the next publication scope and verification; a Git checkpoint alone does not establish installation acceptance.
- Laser Tag Z server simulation state is process memory. The external screen can reconnect to the current process, but a process restart does not resume an in-progress defence run.
- Ordinary force-field links preserve activation history while the objective ring is spatial and order-independent. This is intentional, but diagnostics and the connection contract must continue to make the distinction visible.
- The deterministic ring solver explores spatial subsets from sixteen down to eight. Current pruning and tests keep the authored sixteen-socket level tractable; a materially larger socket set would require a new performance decision.
- Phase 4 deliberately retains Laser Tag Z's legacy map/parser as a read-only rollback fixture. It is duplicate code, not a second mutable authority, and should be removed only after a live installation trial confirms Photon Level startup, editing, restart, and in-run revision deferral.
- Phase 5 deliberately retains Z's direct Webcam/Calibration/Relay reader only for standalone operation when Photon Board is absent or disabled. Remove it only after a live trial confirms corrected marker freshness, arm-state propagation, pump-off gating, and Board failure diagnostics.
- Phase 6 deliberately retains the proven simulation in both Laser Tag Z and Photon Game. Photon Game is the new modular owner used by Y; remove Z's rollback copy only after production presentation parity and a complete live game prove the new Level → Board → Game chain.
- Phase 8 completed the deterministic authority cleanup after direct Z parity. Z remains unchanged as the requested rollback/reference implementation. A full physical Game → Y trial is still needed to prove camera-derived Board placement, all four weapons, ring/core completion, failure handling, and external display continuity before declaring an installation release.
- The former Level/Art normalized-image duplication is resolved: Level owns one shared authored content package for Tiled editing and runtime delivery, and Game forwards its versioned asset descriptor to Y.
- Mobile virtual geometry deliberately reaches the full map and is not calibrated physical MG400 geometry. Virtual practice does not award permanent progression; cues do not resume automatically after session loss.
- Hosted delivery and physical-camera alignment require installation checks beyond isolated fixtures. Bounded enemy guidance cannot reconstruct unseen collisions or arbitrarily long network outages; measured arm playback does not predict beyond received positions. Changed Python modules and frozen mobile bundles require a main-hub restart, which must account for the in-memory game run. The shared no-store controller and bridge can load on a player-page refresh when their backend contracts are already active.
- Atom occupancy, camera-map quarantine/recovery, core cover and physical arm display timing have deterministic coverage, but final installation acceptance still requires supervised camera/projector and robot checks. Browser stress results in the October 8 entry describe that machine and replay, not physical camera latency or a sustained hardware game.

## How to record the next decision

Append a dated entry containing:

1. the observation, failure, user need, or measurement that triggered work;
2. the options considered and the chosen trade-off;
3. the decision and affected contracts;
4. verification performed, including run IDs when relevant;
5. the human decision owner;
6. AI participation exactly as recorded, without guessing; and
7. the commit or pull request that implemented the change.

If the decision changes required behavior, update the relevant specification in the same change. If it only explains existing behavior, update this journal without rewriting the specification as history.

## 2026-09-05 — Remove Photon presentation FPS limits and repeated render work

- **Human decision; AI-assisted implementation:** the user requested applying
  the FPS optimization plan after observing 17 FPS and below. Codex implemented
  the changes in the working tree; no commit or PR was created.
- The 30/24/18 FPS quality caps and discarded scheduling remainder were a
  confirmed limiter. Y now targets 60 FPS for every quality tier, coalesces
  interaction draws, resets visibility samples and measures completed animation
  frames without inflating FPS through diagnostic redraws.
- Stable geometry and snapshot-derived lookups are cached. Small effect
  rasters, electric glows and Tesla halos use bounded caches. Measured frame
  pressure changes cosmetic detail with hysteresis. A smaller-wave replay
  exposed expensive long-line blur returning during quality recovery, so
  lightning and field halos now use layered strokes. Burn cues stay visible
  while lower quality slows their flicker. Enemy/Brute sizes and gameplay rules
  remain as previously configured.
- Y diffs DOM writes, limits nonessential HUD updates to 10 Hz and rebuilds
  controls only on input changes. The existing SSE helper optionally shares
  preparation and encoding, with full initial/reconnect messages and named
  dynamic updates. Default complete-snapshot consumers remain supported.
  Level's optional validated runtime-status read avoids repeated geometry
  copies and bounds art revalidation to 250 ms.
- Verification: the full 226-test suite passed, followed by 132 Photon checks
  on the completed renderer. Synthetic 60/120 Hz tests, shared-stream and
  reconnect checks, revision/error tests and isolated real-Canvas replays cover
  the new logic. A ten-minute two-display replay with 1,000 orcs and 16 towers
  reported median 60 FPS and minimum 42 FPS, with no samples at or below 30.
  Additional smaller-wave and peak-effect replays are recorded in
  `docs/FPS_VALIDATION_2026-09-05.md`.
- The existing paused wave 4 was retained. Refreshing its display raised the
  observed FPS from 24–26 to 58 with the final renderer. Server changes await the next hub restart,
  because restarting now would discard the in-memory run.

## 2026-09-05 — Four row barriers and two-entry winding routes

Implemented the approved row-barrier plan alongside ordinary turret links.
Photon Level revision 18 publishes runtime v2 with explicit three-socket rows,
alternating end openings, two outer left entrances, and westbound middle-road
connections. Game validates v2 while preserving v1 compatibility, powers rows
from completed living turrets, strictly blocks crossings, and reroutes in
bounded shared batches with swept collision. Y shows row progress, openings,
and breakage, retaining static geometry across incremental SSE updates.

Preserved enemy/wave balance, existing links, the center sockets, and the core
ring mechanic. Added lifecycle/routing/collision/transport regression coverage,
modular and Tiled-native validation, and isolated server/browser stress replays.
The final ten-minute two-view/1,000-enemy display replay measured median 60 FPS,
minima 44/43 FPS, and no reports at or below 30. Server profiling also reduced
unnecessary exact combat checks and road-geometry work and removed a duplicate
post-work scheduling delay. See docs/ROW_BARRIER_VALIDATION_2026-09-05.md for
measurement limits, reproduction, and rollout details. The live run was not
reset or restarted by this implementation.

## 2026-09-05 — LTZ saved progression and upgrade map integration

Implemented the requested LTZ Score plan: Photon Progress SQLite profiles,
transactional kill credits/purchases, three-win control unlocks, recoverable Game
results, per-method orc settings, Tesla Coil naming, player stats/history below
upgrades, and all weapon/field upgrade artwork on both Y map views. The existing
relay validates saved active control tiers; no extra robot connection was added.
See `docs/LTZ_IMPLEMENTATION.md` and Photon Progress's specification for the
contracts, operator workflow and recovery limits. Verification uses temporary
stores and browser fixtures, with no live player or hardware mutations.

## 2026-09-05 — Gamemaster virtual upgrade testing

Added an in-memory virtual test loadout to Photon Game and a Virtual test unlocks
panel to Y. Gamemaster can lock turret placement, choose each weapon/field level,
unlock every L4 upgrade, or restore player levels. Existing defenses refresh
immediately with health percentages preserved; player progress is untouched.
The override is virtual-only and survives game Reset within the current module
session. Validation: 156 Photon + 12 LTZ integration tests, plus an isolated real
Game/Y browser test and a visually inspected panel screenshot.

## 2026-09-05 — Readable upgraded turret pedestals

Normalized the transparent padding of all twelve L2–L4 turret bases and raised
the independently rotating heads, with a slight head scale reduction. The green,
blue and amber armor tiers are now exposed within the existing socket footprint.
Firing effects follow the new visual mount; gameplay geometry and L1 art are
unchanged. Both game pages use the shared renderer and a refreshed script version.
The isolated `tests/turret_bases_browser.cjs` check renders every upgraded weapon
at eight aiming angles, verifies base/socket bounds and front visibility, and
writes `/tmp/turret-bases-preview.png` for visual review. It measured at least 80%
of each pedestal front exposed. All 156 Photon tests passed.

## 2026-09-08 — L4 companion turret implementation completed

Completed the approved companion plan: Level revision 19 publishes twelve
validated opposite-side anchors, excluding the four middle sockets. Game owns
same-type child weapons with independent fire, shared health/aim, and unchanged
primary-only topology/scoring. Both views render 96 px companion pods and route
selection to the parent; LTZ descriptions and frozen history metadata explain
the new rule. Existing turret and marker positions remain unchanged.

Finished the interrupted validation: 167 Photon tests and 12 LTZ integration
tests passed, alongside virtual/companion/LTZ browser checks and modular/Tiled
verification. Both displays measured median 60 FPS with 28 weapons and 1,000
orcs. Extreme server stress remained over a 33.3 ms tick budget (42.8 ms median,
versus 38.0 ms baseline); see `docs/L4_COMPANION_IMPLEMENTATION.md` for measured
limits, reproduction and activation instructions. Live hub/game/player state
was not restarted or modified by these isolated checks.

## 2026-09-13 — Checkpoint progression, barriers, companions, and artwork

**Trigger and evidence:** the September 5–8 entries described completed Photon
progression, routing, performance, virtual upgrades, and companion work. Commit
`cd00d97` (September 13) brings that work and its documentation into a recorded
repository baseline.

**Options and trade-off:** retaining the changes only in the working tree versus
recording a recoverable checkpoint is the relevant distinction. The checkpoint
is evidenced by Git; this rationale is an inference, not a quoted decision.

**Decision and affected contracts:** preserve the modular Photon implementation,
including Level row/companion geometry, Game combat, Progress persistence, Y
presentation, and the LTZ score interfaces. The detailed decisions remain in the
earlier dated entries and their implementation reports.

**Verification:** inspected the commit metadata and changed-file list. The
September 8 record reports 167 Photon and 12 LTZ integration tests and documents
the extreme-stress tick-budget limitation in `docs/L4_COMPANION_IMPLEMENTATION.md`.
Those historical results were not rerun by this checkpoint review.

**Human decision owner:** Kaspar Kallas is the recorded author and committer.

**AI participation:** no AI co-author trailer appears in `cd00d97`; earlier
file-level journal attribution remains valid without inventing commit attribution.

**Implementation commit or PR:** `cd00d971e2d3f8730591df7ebbdcd9bbacd06d47`.

## 2026-09-22 — Share the main Photon game with the hosted Green player

**Trigger and evidence:** `tools/mobile-ltz/README.md` records the retirement of
the separate port-8012 game and describes the hosted player using the main
port-8000 Gamemaster. New `mobile-ltz-api`, Green `mobile-ltz`, and gateway/hosting
files implement that shared-game arrangement. This date records reconstruction;
the exact implementation date is not evidenced by an uncommitted diff.

**Options and trade-off:** a separate mobile simulation would isolate mobile
development but split gameplay truth. The chosen arrangement shares Game through
an authenticated adapter and restricted gateway. The architectural trade-off is
inferred from the implementation; the retired separate instance is documented.

**Decision and affected contracts:** retain Photon Game v2 as the authority for
both screens. The gateway exposes fixed player routes and published Level assets,
not an arbitrary proxy or a new robot connection. Green's port-scoped service
identity supports frontend delivery; game state and commands still require player
authentication. `mobile.client` v1 freezes the six-file client at each hub launch,
rejects old build URLs, and lets the hosted PHP entry point obtain the current
build on refresh. Hub discovery supports a prototype allowlist; the dashboard
supports a requested tab and origin/source-checked mobile expansion.

**Verification:** the September 22 mobile Python run passed 50 tests, including
gateway authorization, route restrictions, build freezing, stale-build rejection,
and helper bundling. Tests use temporary files and mocked upstream responses.
The documented hosted URL was not checked, deployed, or restarted in this update.

**Human decision owner:** not evidenced in the reviewed implementation record.
The current user requested this journal continuation, not a deployment.

**AI participation:** implementation attribution is not evidenced. OpenAI Codex
reviewed the local record, ran the focused verification, and drafted this entry.

**Implementation commit or PR:** uncommitted working tree after `cd00d97`; no
implementation commit or PR is identified in the reviewed evidence.

## 2026-09-22 — Make mobile sessions and streamed state recoverable

**Trigger and evidence:** the mobile README and regression tests address lost SSE
event labels, buffered or truncated responses, stale recovery snapshots, phone
backgrounding, and ambiguous joins. These are evidenced failure cases in tests;
their frequency in live use is not recorded here.

**Options and trade-off:** reconnecting transport alone does not resolve who owns
controls or whether an old command is safe to replay. The implementation chooses
explicit stream identity and resumable ownership, with bounded queues and
recovery. This rationale is reconstructed from code and tests.

**Decision and affected contracts:** optional `hub.live` v1 JSON envelopes carry
snapshot/update kind plus run and level identity. A single retry owner handles
feed recovery. Five-second virtual-arm expiry freezes motion and turns the pump
off; rejoining rotates command tokens, and repeated ambiguous joins are
idempotent. Explicit Stop persists across refresh and prevents automatic joining.
Pending motion and ambiguous pump actions are not replayed. Artwork revisions
load into staging caches and replace the visible set together.

The hosted feed can use a ten-minute, origin-scoped, read-only `mobile.stream`
v1 URL through the existing tunnel, with renewal and hosted fallback. Bounded
stream parsing rejects HTML and incomplete frames. Gateway coalescing retains
scene changes and latest enemy membership; `photon.delivery` v1 reports preparation
and relay timing without presenting snapshot age as network round-trip latency.

**Verification:** the 50-test mobile Python run covers session ownership,
stale-command rejection, framing, token scope/expiry, and coalescing. The selected
Node run passed all 26 reported checks across eight files, including game sync,
feed retry/fallback, JSON handling, stream parsing, and atomic artwork loading.
These runs did not measure real hosted delivery latency.

**Human decision owner:** not evidenced for these uncommitted changes.

**AI participation:** implementation attribution is not evidenced; OpenAI Codex
performed this evidence review, isolated checks, and journal update.

**Implementation commit or PR:** uncommitted after `cd00d97`.

## 2026-09-22 — Separate joint targets, arm illustration, and confirmed movement

**Trigger and evidence:** the September 18 asset output contains MG400 outline
concepts and a `JOINT-RIG-PLAN.md` marked user-approved and implemented. The
current Green `JOINT-RIG.md` explicitly supersedes the earlier direct head/elbow
drag interaction with native joint sliders and a read-only arm illustration.

**Options and trade-off:** the recorded progression compares dragging an
articulated drawing with sliders plus a pose illustration. The current design
keeps touch controls explicit and distinguishes a selected target from slow
confirmed movement. The reason for the final switch is inferred; the switch
itself is documented.

**Decision and affected contracts:** J2/J3 retain independent selected goals,
fine adjustment, a fixed-base SVG sketch, and red actual-position indicators.
J1 has its own rotation dial; Suck/Blow are acknowledged pump toggles. A bounded
approach and serialized sender preserve one command path. Stop, stale telemetry,
cancellation, or backgrounding cancel pending approach. Illustration and
indicator smoothing remain presentation-only. The helper is bundled into the
existing mobile client rather than adding a hosted script route.

**Verification:** all 19 `mobile_joint_rig.test.js` checks passed within the
September 22 Node run, covering geometry, independent targets, limits, slew,
telemetry handling, and indicator continuity. `JOINT-RIG.md` also records earlier
isolated Chrome checks; those browser checks were not repeated for this update.
The generated reference images are visual evidence, not measured robot geometry.

**Human decision owner:** the saved plan records approval by the user without
naming that person. Ownership of the later slider revision is not evidenced.

**AI participation:** `../output/mg400-green-controls-20260918/PROMPTS.md` records
Midjourney concept generation. It does not establish who implemented the current
controls. OpenAI Codex ran the checks above and wrote this continuation.

**Implementation commit or PR:** the current mobile implementation is uncommitted
after `cd00d97`; the reference plan/output is outside the nested repository.

## 2026-09-22 — Add virtual XYZ, Targeting, cues, and temporary waypoints

**Trigger and evidence:** the Photon Game and Green mobile specifications now
describe four unlocked control tiers, local height presets, configurable movable
piece IDs, and queued pickup/placement. They define current behavior; exact dates
and original requests for the individual additions are not available in Git.

**Options and trade-off:** browser-timed automation would make execution depend
on phone visibility and delivery timing. The implementation keeps the cue state
machine inside Game's simulated arm and reuses its movement and placement checks.
Full-map virtual reach favors practice coverage over reproducing physical MG400
geometry. These trade-offs are inferred from the implementation and specifications.

**Decision and affected contracts:** additive `photon.mobile-arm` v1 fields expose
mode, mode revision, actual pose, target, markers, and cue status. Saved Green
progress or a virtual-only Game override unlocks Joint, XYZ, Targeting, and Cue;
missing progress grants only Joint. A fresh connection chooses the highest
implemented unlocked mode. Mode revisions reject obsolete inputs.

XYZ uses validated inverse kinematics and the shared 12°/s joint follower;
Targeting replaces X/Y sliders with finger dragging. Three phone-local Z presets
save on a three-second hold. Game owns cue approach, pickup, transfer, release,
and completion for up to 32 rows. A blue waypoint temporarily detours the current
stage without advancing the row or repeating pump actions. Pause retains the
stage and held piece; reconnection does not automatically play a cue. Configurable
piece IDs retain their team/weapon roles and apply in setup or at the next Start.
Practice overrides never award permanent progression.

**Verification:** the 50-test mobile Python run passed, including XYZ validation,
mode defaults, cue execution, custom IDs, pause/stop, full-map reach, and detours.
Phone-layout and gesture scripts are present for XYZ, presets, Targeting, Cue,
and waypoints, but were not executed in this journal pass. Physical timing and
collision-free Cartesian travel are not established by these virtual tests.

**Human decision owner:** not evidenced for these uncommitted changes.

**AI participation:** implementation attribution is not evidenced. OpenAI Codex
reviewed the specifications and tests, ran isolated verification, and wrote this entry.

**Implementation commit or PR:** uncommitted after `cd00d97`.

## 2026-09-22 — Smooth enemy motion while retaining server combat truth

**Trigger and evidence:** the mobile delivery documentation and new
`test_enemy_motion_guides.py` / `photon_motion_renderer.cjs` cover jitter, batched
updates, turns, and 900 ms–1.2 second gaps. The code distinguishes rendering stalls
from delayed state delivery; no new live performance measurement is claimed here.

**Options and trade-off:** drawing only the latest position causes visible steps;
unbounded straight-line prediction invents motion through turns. The chosen
approach combines a short adaptive playback delay with bounded server-authored
route guidance. It trades some visual delay for continuity without moving combat
authority into the browser.

**Decision and affected contracts:** the shared Y renderer retains three seconds
of pose history but normally starts with a 300 ms playback delay, adapting between
250 and 450 ms. Interpolation follows sampled velocity and facing. Additive
`photon.enemy-motion` v1 supplies up to twelve guide points, mode, speed, and
topology revision. Valid guidance predicts for up to 1.2 seconds, then brakes over
200 ms; stale topology and known stalls hold. Disconnects freeze presentation,
while pause, run/map changes, and large jumps reset history. Health, deaths,
membership, scoring, and outcomes remain current server facts. Mobile diagnostics
expose update cadence, age, prediction share, buffer delay, and peak frame interval.

**Verification:** all four Python enemy-guidance tests passed. The Node motion
renderer check passed interpolation, turns, prediction bounds, corrections,
authority, and Canvas-call integration using a stubbed Canvas context. The real
browser gap replay script exists but was not rerun. These checks do not establish
a new FPS benchmark or guarantee continuity through sustained outages.

**Human decision owner:** not evidenced for these uncommitted changes.

**AI participation:** implementation attribution is not evidenced; OpenAI Codex
ran the focused checks and drafted this evidence-based continuation.

**Implementation commit or PR:** uncommitted after `cd00d97`.

## 2026-09-22 — Aim Green turrets in virtual and corrected-camera views

**Trigger and evidence:** the Green mobile specification and new turret tests
describe a firing overlay for placed Green turrets, including physical play where
there is no virtual-arm session. Camera Calibration adds a small public cached
frame contract for that presentation.

**Options and trade-off:** sharing the arm's control session would unnecessarily
couple turret settings to robot practice. The implementation gives aiming a
separate Game-validated intent and uses camera registration only for display and
hit-testing. This rationale is inferred from the boundaries and regression tests.

**Decision and affected contracts:** `mobile_turret_aim` on Photon Game v2 validates
run, Green ownership, placement identity, aim revision, phase, and finite inputs
before using the existing tower-aim rules. A touch handle adjusts direction and
range, or radius for Tesla. Destroyed or replaced turrets cannot inherit a stale
save. Physical mode displays the shared corrected JPEG; at least four fresh,
non-collinear marker centers establish presentation registration, and invalid or
stale evidence disables editing. `hhh.camera-frame` v1 returns only fresh cached
frames, with no second camera capture or copied lens calibration. Camera
Calibration also gains an explicit stop path for its encoder resources.

**Verification:** all seven `test_mobile_turret.py` tests passed as part of the
50-test mobile run: ownership/identity rejection, revision checks, replacement,
registration failure, physical edits without an arm session, and authenticated
fresh-frame delivery. The browser suite uses synthetic camera imagery and was
not rerun here. Live optical alignment and physical-installation acceptance remain
unverified by this update; no hardware was moved.

**Human decision owner:** not evidenced for these uncommitted changes.

**AI participation:** implementation attribution is not evidenced. OpenAI Codex
reviewed source/specifications, ran the isolated tests, and updated the journal.

**Implementation commit or PR:** uncommitted after `cd00d97`.

### Verification record for this continuation

On 2026-09-22, OpenAI Codex ran the following from the repository root:

```sh
.venv/bin/python -m unittest discover -s tests -p 'test_mobile*.py'
.venv/bin/python -m unittest discover -s tests -p 'test_enemy_motion_guides.py'
node --test tests/mobile_game_sync.test.js tests/mobile_live_feed.test.js tests/mobile_network.test.js tests/mobile_stream_parser.test.js tests/mobile_viewport.test.js tests/mobile_joint_rig.test.js tests/mobile_artwork_renderer.cjs tests/photon_motion_renderer.cjs
```

Results: 50 mobile Python tests, four enemy-guidance Python tests, and 26 Node
checks passed. The initial system-`python3` attempt could not import Flask; using
the existing project `.venv` resolved the environment issue without installing
dependencies. No live game run ID applies: these were isolated deterministic
checks, not a physical trial. No hub restart, deployment, saved-player mutation,
or new implementation commit was performed. This continuation explains existing
code and specifications; it does not introduce new required behavior.

## 2026-10-01 — Complete both-player control progression and mobile calibration

**Trigger and human decision:** the user approved implementation of the control
progression/calibration plan and explicitly required Game Master test unlocks to
work for both players at every selected tier. The user specified mandatory tiers
until advancement, three XYZ wins before calibration, Green first on the unified
field, a shared 30-second upgrade interval with extended calibration waiting,
saved rig bounds, player-owned upgrades, combined scores, graphs and adjustable
per-level settings. The approval plan and implementation/verification report are
saved in `docs/CONTROL_PROGRESSION_CALIBRATION_PLAN.md` and
`docs/CONTROL_PROGRESSION_IMPLEMENTATION.md`.

**Implementation choices and ownership:** Green and Purple share the mobile
presentation and controller assets. Progress v2 owns profiles, mandatory current
tiers, transactionally saved rewards/purchases/history, and roster reservations.
Game owns the shared timer, journey, immutable selected presets, and practice
grants. Auto Pickup owns fresh six-point and raised-Atom calibration evidence,
rig commits, leases and movement bounds; Playfield owns exclusive field display
and green saved-marker glows. Board remains the physical placement authority,
and the existing LTX/Relay route remains the only physical command path.
Calibration uses preview followed by explicit Move, with independent height and
pump commands, measured pickup/lift and stable placement evidence.

Touched legacy boundary violations were repaired: both teams consume owned
shared presentation assets, calibration/display state uses public versioned
contracts, Camera Calibration no longer reads Webcam's private manager/tracker,
and Relay's watchdog is hub-lifecycle owned. Camera and lens files use atomic
replacement. Safety rejects unavailable, stale or malformed prerequisite data;
missing stop acknowledgement retains the active side's field reservation.
Retries and restarts reconcile durable result/lesson receipts without duplicate
rewards or repeating an already completed Green turn.

**Balance evidence and limitation:** the supplied pickup CSV contains 38 June
results for 17 display names and no tier/settings/loadout metadata. The requested
August window is absent. No pooled median or inferred measured method gains were
used. Explicit provisional tier count/pace factors 1.00/1.08/1.16/1.24 were tested
with the actual engine and the same assumed placement trace at base and maximum
upgrades. All eight tier/loadout cases and a slower-Purple case won; the base
Joint run took 1,414.4 active seconds. `docs/CONTROL_BALANCE_REPORT.json` preserves
the CSV rows/hash, settings, seed, actions, and results. Physical accuracy,
human completion rates, and maximum-upgrade ease require the documented pilot.

**Verification:** 402 Python tests, 36 JavaScript tests, both-team fake-relay
bridge checks, and a Chrome fixture passed. The browser verified actual GM
selection of Joint, XYZ, Targeting and Cue for each team, plus mobile score/time
graphs, comparable-cohort means, keyboard details, purchases, filters, marker
glows and waiting screens. Camera public-contract, failed-persistence, roster,
exclusive-field and cross-owner recovery tests passed. The hosted export bundles
the journey UI inside the established client allowlist. Static syntax/whitespace
checks passed. These were isolated fixtures with temporary stores and synthetic
camera evidence; no live hub, robots, deployment or human game was run.

**Human decision owner:** the requesting user; their approval is explicit in the
current task. No identity is inferred from historical gameplay names.

**AI participation:** OpenAI Codex implemented this continuation and performed
the recorded checks. Pre-existing working-tree changes were preserved and are
not attributed retroactively to this task.

**Implementation commit or PR:** uncommitted after `2ea92b5`; no PR created.

### 2026-10-01 — Correct unlock propagation in ordinary player windows

**Trigger:** the user reported that Game Master control unlocks did not reach
players and that the joint schematic appeared only in Mobile LTZ.

**Finding:** ordinary `ltx/?ltz=1` controls still subscribed to Progress's earned
tiers; Game's practice override was absent from that input. The default LTX tab
also selected the older Laser Tag X view. The previous ordinary-controller smoke
script read a legacy controller copy, while the newer checks exercised the
mobile adapter. Consequently the earlier passing tests did not establish this
ordinary-window behavior.

**Correction:** both LTX tabs default to LTZ controls and retain a separate
Laser Tag X link. Ordinary and embedded LTZ controls consume the same scoped
Game facade and SSE messages, stop superseded intentions, restore mandatory
saved tiers when practice ends, and retain calibration exclusivity. Game's
small preview stream now publishes its named v1 contract and practice tier;
both LTZ Score windows display practice access without persisting it as earned
progress. Purple is also included in the hub's default Mobile LTZ API sharing.

Both player windows reuse the pure mobile joint schematic, contained inside
their joint panel. Its gestures update existing sliders and the same guarded
joint queue; white selected targets remain separate from red measured feedback.
Stale/disconnected feedback and unavailable game scopes disable gestures. The
mobile schematic's existing framing is preserved. Old Auto Pickup name prompts
and Laser Tag X reset watching no longer interfere with LTZ player controls.

**Verification:** 402 Python tests and 36 JavaScript tests passed. The corrected
ordinary-controller smoke reads the actual served shared source and covers both
teams in ordinary and embedded modes, all four practice tiers, restoration and
calibration waiting. A new Chrome regression clicks the actual Game Master
unlock button and verifies both ordinary controllers and both score windows,
schematic keyboard commands through a fake transport, complete arm framing,
and override removal. The existing mobile progression browser regression and
both-team physical bridge smokes also passed. Screenshots were inspected.
Fixtures use temporary profiles, synthetic imagery, and fake robot routes;
no hardware was moved or live hub restarted.

**Decision owner / implementation:** the requesting user authorized diagnosis
and correction; OpenAI Codex implemented and verified it. Changes remain
uncommitted after `2ea92b5`.

## 2026-10-01 — HTTP profile creation and selectable test players

**Trigger:** user reported `crypto.randomUUID` undefined when Green creates a
player and requested a selectable profile whose testing does not affect later
statistics. Both Score pages and the mobile creation/purchase handlers depended
on the missing method.

**Change:** shared receipt helper supports native UUID, random bytes and a
timestamp/counter/random fallback. Both launch bundles and hosted exports include
it. Profile creation can select the authenticated side atomically; failed roster
selection rolls back the new profile. Added a mobile menu entry for the profile,
upgrade and statistics panel during Game Master practice.

Progress owns two stable built-in test profiles, one named for each team. Their
classification is based on owned IDs, not client input or display names. Game
and Progress force any mixed or all-test roster to practice. No participant
earns score, currency, attempts, wins or tiers from it; default Scored history
and difficulty cohorts exclude these results. Separate Practice history retains
them. Test progress stays at baseline and testing uses existing Game Master
control/loadout overrides. Backups preserve classification. Browser switching
uses Practice history and prevents old profile/filter responses from appearing
after a selection change.

**Architecture:** Progress retains sole ownership of profiles and eligibility;
Game reads its validated public v2 roster and owns gameplay/delivery. Shared
JavaScript generates receipts and presents state only. Existing side auth,
server input validation, SQLite transactions, SSE and robot paths are retained.

**Validation:** full 410-test Python suite passed; two added side-authenticated
API tests and affected bundle/export checks passed. All 39 JavaScript tests
passed. Chrome exercised all four Green/Purple Score/mobile creation and test
selection flows with UUID disabled, plus the no-Web-Crypto Score fallback.
Existing both-team Game Master tier matrix, ordinary controls, mobile history
and calibration/waiting regressions passed without page errors. Temporary
stores/synthetic imagery/fake robot transport only; screenshots inspected.
No live hub restart or hardware movement. User authorized this correction;
OpenAI Codex implemented it in the existing uncommitted worktree.

## 2026-10-01 — Progression review: target display, live control changes and Start

User requested review against the mobile progression/calibration approval plan,
a compact player-name box, repairs to Game Master mode switching/Start, and the
actual Auto PP Cal 2 targets during calibration. OpenAI Codex implemented these
corrections in the existing dirty worktree, preserving unrelated edits.

The most direct calibration failure was the ID-less fixed Auto PP Cal 2 template
being passed to Playfield's ID-requiring replacement API. The lesson now adapts
that owner-held template, preserves target geometry and camera settings, and
shows it in both Y views before waiting for measured readiness. Captures use
visible green surrounds with crisp ArUcos. Mobile clears combat overlays and
reframes corrected video. Reservations without a completed lesson can be safely
cancelled after stopped-motion acknowledgement; pre-activation frames cannot
be captured.

Continuous physical telemetry no longer suppresses mode synchronization. Y
retains edited test selections and rejects old stream snapshots. Both players
receive all four GM practice tiers. Practice Start uses the proper scoring mode,
reuses an existing frozen roster, enters the playing journey, and closes the
lobby; calibration remains exclusive. The live recovery conflict was reproduced
in an isolated database and repaired through monotonic owner reconciliation,
without manual edits to venue scores. Journey maintenance is independent of
score delivery failure.

A pre-existing calibration test left AREAS_PATH unisolated and overwrote the
saved Playfield file. Tests now redirect every persistence path. The original
six-target file was restored from the running owner's read-only snapshot, with
both copies retained in /tmp. No calibration model or player database was changed
for that repair. No live movement or venue restart was performed.

Verification and honest remaining gaps are recorded in
`docs/CONTROL_PROGRESSION_IMPLEMENTATION.md`: 422 Python tests, 39 JavaScript
tests, both fake-relay bridge smokes, actual-button Chrome checks, and visual
inspection. Physical alignment/pickup trials, hosted physical parity, complete
intro/pre-Start presentation, and human balance acceptance remain open. A normal
hub restart and both-player refresh are required to load the updated code;
stale camera input continues to block physical Start with a visible reason.

### 2026-10-01 — XYZ arrows and physical mode-switch connection repair

The shared mobile UI now has X/Y ±10 arrows and Z ±1 arrows; Targeting and Cue
share the height arrows. Height uses measured robot XY through the existing LTX
planner and is disabled during cue execution/pause. Fixed steps, clamping,
delayed feedback and short landscape layout are covered by regression checks.

Reproduced the mode switch clearing a healthy mobile connection. The bridge now
invalidates old movement, confirms Stop and preserves the session; movement is
disabled during the handoff and a failed Stop still disconnects. Known Cartesian
boundary rejections retain a held session, while unknown faults fail closed.
The live read-only snapshot showed Green connected/enabled with fresh feedback
but the game overrun; ended-game reconnect now gives an explicit Reset message.
No live motion or venue restart was performed. Module ownership, Game admission,
Cal 2 validation and the one existing relay delivery path are preserved.

Validation passed: 61 mobile Python tests, 39 JavaScript tests, both team bridge
smokes, arrow/physical/base/limit smokes, and the complete physical/virtual Chrome
matrix with fake hardware. Screenshots checked at 390×844, 844×390 and 667×320.
Reload the hub normally and refresh both player pages to pick up the frozen
client bundles. No physical accuracy trial was performed.

### 2026-10-01 — Cartesian boundary recovery and tenfold Fine tune arrows

The user confirmed that refreshing the phone resolved the missing arrows seen
in QuickTime. The shared mobile layout was left intact. Fine tune now divides
X/Y arrow steps from 10 to 1 and height from 1 to 0.1, including Targeting/Cue,
with matching visible numbers and accessibility labels.

Cartesian path validation previously rejected the measured starting pose after
a boundary overshoot, preventing recovery even after reconnect. The planner and
relay now allow only a bounded (up to 10 mm), monotonic retreat to a valid target.
The planner uses the same captured robot-space hull as the calibration owner's
relay envelope. Known geometry rejections preserve a held session; missing
calibration, failed holds, feedback faults and unknown failures remain fatal.
XYZ/height use direct-path holds; Targeting/Cue retain calibrated detours. Mobile
watchdog holds cannot start a competing recovery move, and preflight/planning
cannot move the arm before the route has been checked. Matching fresh bridge
progress extends long XYZ replies only up to a three-minute absolute deadline.

Validation: 61 mobile Python tests, four relay Cartesian recovery tests, one
reservation test, 45 JavaScript tests, both team bridge smokes and focused step/
physical/recovery smokes passed. Actual mobile/LTX browser flows exercised both
teams' normal/fine increments, mode changes, XYZ reconnect, boundary retreat,
Targeting detours and fatal fault handling with no page errors. All robots and
movement were simulated; fixture data was temporary. No venue restart or live
robot motion. Module ownership and the single existing relay path are preserved.
Normal hub restart and phone refresh are required for the frozen mobile bundle.

### 2026-10-01 — Targeting Go button and preset-column precision

Replaced the wrapping Move to preview label with Go beside the Suck/Blow stack.
Go matches the stack's width and combined height, remains dim until a new preview
can be submitted, and glows green when ready. Submission clears readiness at
once; active gestures, pending XYZ, mode switches and unavailable controls keep
it disabled. The existing command, calibration and relay path are unchanged.

In Targeting, the same Fine tune control moves below preset 3 in the numbered
column, retaining its event handling and tenfold precision. Compact landscape
spacing keeps it above Go and the pump controls; XYZ/Cue retain their own dock.
Updated the player hints to say Go and describe the current fine arrow steps.

Green and Purple passed touch preview/submission, glow state, fine drag, preset,
pinch/cancellation and five portrait/landscape layout checks in the isolated
virtual fixture. Screenshots were inspected, including the short landscape
layout. Client bundle tests (4), XYZ arrow smoke, syntax and whitespace checks
passed. No live robot motion or venue restart; normal hub restart and refresh
are needed to load the frozen mobile bundle.

### 2026-10-01 — XYZ directions follow the player's viewport

Purple defaults to a 180° playfield rotation, but XYZ sliders and arrows were
still applying unrotated map directions. The shared mobile UI now maps X/Y range
values and arrow deltas through the viewport direction. Slider bounds, fills,
actual-position markers and off-range indicators use the same transform, in
normal and fine modes. Rotating the view refreshes the controls without sending
a move. Height remains upright; readouts and command targets keep canonical map
coordinates. Calibration, safety validation, module ownership and the existing
serialized robot-control path are unchanged.

Validation: native touch drags moved the virtual arm in the displayed direction
for both players at 0°/180°, with normal/fine ranges, aligned measured markers,
preserved sessions and no movement caused by rotation or rendering. The real
mobile/LTX browser suite with fake six-point calibration and fake robot feedback
passed both players' increments, GM mode changes, layouts, XYZ reconnects and
virtual controls. Arrow and viewport smokes, four frozen-client bundle tests,
syntax and whitespace checks passed; browser suites had no page errors. A
portrait screenshot was inspected. No live robot motion or venue restart.
Normal hub restart and phone refresh load the new frozen bundle.

### 2026-10-01 — Purple calibration placement and orientation audit

The lesson loader copied the fixed Auto PP Cal 2 targets without the standalone
loader's orientation adjustment. Purple now receives the 180°-rotated physical
target positions; Green receives the normal layout. The saved template's view
is accounted for exactly once. Marker IDs, green capture glows, camera settings
and the single Playfield display reservation are retained. Drafts record their
display orientation, preserve raw corrected-camera measurements, and refuse to
resume old captures after their target orientation changes. Previously committed
rig calibration is retained until a replacement draft validates.

The audit also corrected ordinary LTZ's Purple camera default and isolated its
manual view preference from commissioning settings. The hidden mobile bridge
stays in canonical coordinates. Cue marker-label placement now follows the
rotated marker edge while keeping text upright. Targeting, Cue waypoints, turret
aiming, reach/exclusion geometry and raised-Atom correction already use matching
forward/inverse transformations. Height, joints and menus stay upright.

Validation: 41 Python checks (display, journey, capture and frozen client), 13
JavaScript geometry/viewport checks, Purple bridge and LTZ/XYZ smokes passed.
Isolated browser flows passed GM calibration for either/both teams, target
rotation, durable glow and restoration; ordinary player tiers/view overrides;
and Purple Targeting, Cue waypoints, label positioning and turret control. No
page errors; projected Green/Purple screenshots were inspected. Sensors and
robot transport were fake, with no venue restart or physical robot movement.
The full audit is recorded in docs/CONTROL_PROGRESSION_IMPLEMENTATION.md.
Restart the hub, refresh player pages and reopen an old captured Purple lesson
before recapturing its six targets.

### 2026-10-01 — Restore the GM camera during calibration

Removed the target-renderer overlay from the GM stage: calibration now uses the
existing corrected Board camera preview at full frame, including outer points.
Only the external Y screen projects Auto PP Cal 2 targets, using a read-only
Playfield presentation mode so wheel, drag and keyboard events cannot alter the
projection. Camera failure shows the existing retry state instead of a synthetic
target image. The regular Playfield editor keeps its controls.

Fixed restart recovery where a persisted Green display reservation appeared to
be an active lesson despite its revoked process epoch. The owner explicitly
requires fresh activation; Game retries the same draft only with current
camera/arm evidence. GM practice calibration selection can safely switch to
another side through the existing stopped-motion release. Earned Green-first
progression is unchanged. Test failures now appear beside the GM controls.

Validation: 40 Python tests and the full isolated progression browser flow
passed. Browser checks covered both players/all control overrides, practice
Start, Green/Purple/Both calibration, full-frame GM camera, Purple target
rotation, captured glows, locked projection, practice switching and restoration.
Screenshots were inspected; no page errors. Syntax/whitespace checks passed.
Tests used temporary data and fake camera/robot feedback. No live hub restart or
physical robot motion. Restart the hub and refresh GM/external display pages to
load the backend and presentation changes.

### 2026-10-01 — Game-first loading and offline screen navigation

The prior Green practice session persisted on page load, and selecting another
side or cancelling still required live arm Stop feedback. With the arm offline,
that trapped the external projection on Green. The controls were also buried
below the large camera/turret panels. Moved Game screen, Green, Purple and Both
above the camera, with visible selection/errors. Loading the Y operator page
now requests Game's game-screen transition; the external projector remains a
follower. Earned lessons pause without losing their draft or granting progress,
and Resume player calibration restores the saved sequence.

Added owner-managed deferred display release: revoke lesson access, persist any
unconfirmed arm stop, then restore projection. The durable pending-stop gate
blocks both arms, heartbeat renewal, new lesson activation and physical Start
until Relay confirms stopped motion. Display-only previews require no arm
connection. Operator Connect remains usable to restore feedback without enabling
or moving an arm. The existing worker handles stop recovery in the lobby, too.
Normal earned handoff still requires measured Stop before advancing.

Validation: 93 Python tests passed plus the isolated browser progression flow,
including offline Green → reload → game, Purple/Green target switching, exit,
retained motion blocking, feedback recovery, both-player control overrides and
Start. No browser errors; toolbar screenshot inspected; whitespace checks pass.
No live robot motion or venue restart. Restart the hub and refresh the GM page
to load these Python changes; the page then selects the game screen itself.

### 2026-10-01 — Repair stale lesson ID and verify calibration buttons live

Reproduced the reported Green button failure on the live GM page. Journey entered
calibration, but maintenance raised `hhh.relay.stop v1 unavailable` before loading
targets. Restart had cleared the lesson's active side while retaining its old
active ID; idempotent cancellation left that historical paused draft eligible
for maintenance. Restart now clears both fields, release cleans an orphaned ID,
and maintenance handles only a turn with an active side. Durable deferred stop
requirements remain independent. The GM status now distinguishes target readiness
from selecting a side and no longer masks display errors with a hardware notice.

Validation: 45 targeted Python tests and the isolated browser progression flow
passed, including the actual restart-before-cancellation ordering and legacy ID.
Both live relay arms reported disconnected. Restarted the hub using its existing
Python runtime, refreshed the existing operator and external pages, and clicked
Green → Purple → Game. All six live targets appeared; Purple was rotated 180°;
Game restored successfully. The old external tab had loaded the earlier inline
renderer and needed that refresh. Screenshots saved under /private/tmp. No arm
movement or calibration captures were sent. Left the live projection on the game
screen; its pending Green stop inhibit is preserved until feedback confirms it.
# 2026-10-01 — Mobile calibration selection and partner upgrades

Fixed the phone routing bug where a selected calibration with no active arm
grant showed both players a blocking "Waiting for calibration to finish
calibration" dialog. Game now exposes the selected queue side separately from
motion authority; Mobile LTZ API returns its matching draft and explicit capture
readiness. The selected player sees the six-point Auto PP Cal 2 lesson with
XYZ presentation, readiness errors and a Hide/Show steps control. The partner
sees Upgrades and a named waiting message. Capture stays disabled until the
existing owner grant is live. No robot-control or stop checks were relaxed.

57 targeted Python tests and both browser suites passed; the final phone layout
also passed the full route regression. Verified offline/restart cold opening,
both sides, capture recovery, glows, collapse/expand, and upgrades with/without
a selected profile. Restarted the live hub after confirming both arms were
disconnected, checked real Green/Purple lesson and waiting screens, and left
Green calibration selected. No live movement or capture was requested.

# 2026-10-01 — Mobile calibration setup, marker labels and saved measurements

Separated connection commissioning from the active calibration movement grant.
The selected player can use the existing Relay connect/acquire/enable sequence;
initial XYZ captures use robot millimetres before a camera fit exists. Movement
still needs the same exclusive, fresh, unpaused owner grant, validated Relay path,
radial/workspace/Z limits and pending-stop recovery. No sibling file writes,
second driver or browser-owned progression were introduced. GM and earned
calibration both use the same Game/Cal 2 session pathway.

Y now suppresses cached 40–59 overlay geometry and controls during calibration,
preserving the cache for gameplay. The phone shows fresh green marker numbers;
Playfield presentation adds upright white numbers outside each code. Moved the
collapsible lesson to the upper right, left of Y. Added side-scoped, read-only
saved calibration history and immutable archives, including a rig before it is
replaced. Owner contract and hosted gateway allowlists were documented/updated.

The user confirmed four outer samples at 3 cm, matching Auto PP Cal 2. Capturing
an outer point records the ground view; selecting 31/35/33/34 then tapping the
raised physical tag in video records the corrected-camera position. Pan/pinch do
not capture; Purple rotation is inverted once. Old raised samples invalidate on
recapture, and commit still validates the six-point and four-point transforms.

Validation: 80 targeted Python tests passed, both arm-bridge smoke tests passed,
and the real-route browser regression passed all four GM control overrides for
both players, Start, projector orientation/glows, transitions, pending stops and
safe cancellation. New fake-hardware browser coverage passes offline Connect,
raw XYZ and 10x Fine tune, all six captures, all four 3 cm video taps, commit and
per-arm history for both players. Visual inspection corrected two problems the
initial assertions missed: CSS still hiding numbers, and sprite height failing
to inherit the projected marker size. The final screenshots show both fixes.

The live hub was restarted after confirming both real arms disconnected. Y opens
the game first, then Green calibration was restored; the live phone shows the
existing saved rig in its dropdown. Multiple desktop live streams saturated the
browser's same-origin connection pool during further live phone verification;
all movement tests used the isolated fixture, never real hardware. Phones need
a refresh to load the newly versioned bundle.

# 2026-10-01 — Covered calibration-marker capture

Fixed the requirement that marker 30 still be detected after the arm was placed
on top of it. Cal 2 now proactively caches the six static target positions using
the existing Game maintenance tick. Capture uses the last valid optical position
from this activation with a fresh measured arm pose. Cache entries are ephemeral
and scoped to side/session/epoch, layout, projection settings, camera correction
and image size; camera outages and scope changes invalidate them. The phone shows
how many positions are located and retains cached target labels during occlusion.
Raw live arm/camera freshness, exclusive turns and movement checks remain intact.

Tests cover complete occlusion for Green and Purple, current pose vs old optical
timestamp, fresh reobservation, perspective ground samples, glow preservation,
never-observed/malformed detections, stale hardware, camera outage, changed lens,
resolution/layout/reservation, restart and reactivation. The real-route browser
fixture now runs the actual measurement/cache code with fake sensors: both phone
flows pass with marker 30 hidden after all six targets are located, followed by
six captures, four raised samples, commit and saved history. No live capture,
robot move or enable command was used during validation.

Validation completed with 75 targeted Python tests plus the complete two-player
calibration and GM progression browser regressions. Before reload, both real arm
followers were stopped with no controller lease; Green was in backdrive. Restarted
the verified hub in its existing Python runtime to load the fix, without replacing
any saved capture data. The temporary fake-hardware server was stopped. Refresh
and reconnect the phone, let every target be seen once (6/6 located), then the arm
may cover a cached marker during capture.

# 2026-10-01 — Identify calibration markers before connecting the arm

Corrected two causes of missing marker 30: optical memory previously began only
after fresh arm feedback activated a lesson, and it required exactly zero marker
age although Webcam reports elapsed polling time for visible detections. Cal 2
now prepares its runtime cache when the display is reserved and uses Webcam's
latest-frame visible IDs with Camera Calibration's corrected coordinates through
validated public contracts. Game's existing maintenance tick accumulates all six
positions while disconnected. Same-display activation/reconnection preserves
them; offline retries no longer reload the targets. Release, restart, camera
outage and optical/layout changes still invalidate the runtime cache.

The owner exposes side-scoped marker preparation independently of the live lesson
grant. Mobile shows each identified number in green before Connect and says
"Ready to capture" at 6/6. The API also carries cached overlay labels before a
motion session exists. Backend captures require all six positions plus the
existing fresh camera, enabled-arm feedback and live lesson permission. No robot
driver, motion endpoint or sibling file access was added.

Validation: 79 targeted Python tests passed, including offline preparation for
both players, nonzero polling age, held detections, all-six gating and cache
preservation. Both real-route mobile browser flows passed: partial green glow,
all-six readiness while disconnected, marker 30 hidden before Connect, successful
six-point captures, four raised samples and saved history. The shared progression
browser regression also passed for all four control methods on both phones.
After confirming idle/stopped followers without controller leases, restarted the
local hub using its existing Python runtime. The live Green page shows all six
real markers identified, green glows and "Ready to capture" before connection.
No live robot move, enable or capture was used for verification. Phones need a
refresh and reconnect to use the update.

# 2026-10-01 — Compact calibration captures and optical crosshair

The shared phone UI now hides X/Y adjustment controls during six-point and raised
tag calibration, retaining height and its fine-tune switch beside the saved
height buttons. The six point-capture buttons remain visible with instructions
folded. After the sixth arm capture, they are replaced by the four raised
reference buttons (31, 35, 33, 34) and an independent calibration crosshair.

As clarified by the user, this crosshair only records optical sample locations:
place a physical 100-series ArUco tag 3 cm above a ground reference, tap the image
to position the crosshair, then tap the reference number to save the existing
`raised` command. A tap alone never saves a sample or moves the arm. Each saved
sample gains a checkmark; the next requires another explicit camera tap. The
four reference buttons remain accessible while instructions are folded, with a
completion hint directing the player back to height capture and final save.
Purple uses the existing viewport inversion once for both crosshair display and
recorded coordinates. Backend capture and motion authorization are unchanged.

Validation: 34 targeted Python contract/client tests and syntax checks passed.
Both real-route phone flows passed with all six captures and all four raised
samples performed while folded, hidden XY controls, retained 0.1 mm height fine
tune, correct visible crosshair alignment in both orientations, no robot move
requests from image taps or raised capture, and saved history. The shared
progression browser test also passed for both players, all four control modes,
upgrades, graphs and the partner waiting screen. All movement testing used the
isolated fixture and fake hardware.

Loaded the UI by restarting the verified local hub with its existing runtime,
after checking both followers stopped and no controller lease. Live Green kept
its six completed arm points and displayed the new four-reference crosshair UI;
folding the instructions retained all four buttons. Its camera was on Camera 0
and showing a person instead of the playfield, so no live sample was recorded or
camera selection changed. Reported that the playfield camera must be selected
before continuing. Temporary browser checks and the fake-arm server were closed.

# 2026-10-01 — Game Master saved calibration preview and restore

Laser Tag Y now offers per-arm saved calibration selection, a live-camera overlay
preview and explicit Apply. The newest complete calibration is the default;
applying an older capture preserves its original timestamp, and an explicit
choice survives restart. Completing a fresh mobile lesson installs the new rig
and resets that arm to the latest default. Six numbered ground squares and four
dashed 3 cm perspective samples share the corrected camera image rectangle;
Purple uses canonical camera coordinates without a second rotation. Preview is
read-only and its camera/overlay pause on stale Board evidence from the existing
SSE stream, including when a video connection leaves a last decoded frame.

The Game Master facade reads Cal 2 history through its enabled public contract.
Apply is serialized through Photon Game/Journey, rejects running games, and
returns from calibration without awarding or bypassing required lesson credit.
Cal 2 alone validates and persists measurements. It checks the source revision,
finite complete geometry/heights, known camera/robot bindings and fresh Relay
connection states. Both connected arms must confirm Stop because transport Z is
shared; durable stop gates inhibit new motion during atomic replacement. Prior
source records remain immutable. The existing mobile rig revision path reloads
measurements, with reconnection required after controller lease revocation.

Validation: 76 targeted Python tests passed, including history restoration,
restart persistence, both arms, invalid/stale inputs, failed stops, shared-height
archival and preservation of earned progression. The real-route Game Master
browser test passed for Green and Purple: latest default, read-only preview,
correct camera coordinates, older/latest Apply, camera loss/recovery, exit from
practice calibration and running-game rejection. The full mobile six-point plus
four-raised-sample browser flow passed for both players and confirmed fresh
commits become the latest applied rig. All movement/capture tests used temporary
files and fake arms. Existing real Green and Purple saved rigs also pass restore
validation. JavaScript syntax and git whitespace checks passed.

Deployment: verified both physical arms disconnected, followers stopped, pumps
off and no controller leases, then gracefully restarted the exact existing hub
runtime (new PID 83955). Reloaded the real Game Master page and verified Green
and Purple each list their existing saved rig, default to Latest and render
six ground plus four raised overlays over the current corrected camera. No real
Apply, capture, enable or move was sent. Returned the UI to Game screen with
Green/Latest selected. An existing Green pending calibration-stop hold remains
visible and requires reconnecting Green before an Apply can proceed; reported
this instead of weakening the durable stop requirement.

# 2026-10-02 — Draggable calibration crosshair and explicit completion

Raised-sample calibration now supports dragging the optical crosshair with
Targeting's 32 px grab radius, retained grab offset and tenfold Fine tune scale.
The same viewport inversion handles Green/Purple and zoom. Coordinates clamp
to the image. A second finger hands off to camera navigation; removing it does
not restart a drag. Optical cancellation clears its own gesture without
suspending the arm connection. Tap/drag still requires a separate numbered
reference press to save and never creates robot movement commands.

The previous Validate and save action committed the rig but left completion
behind mandatory guided arrivals/pickup/placement. Added Complete calibration
in the persistent quick controls, including with instructions folded and for
already validated tutorial sessions. Missing targets/heights are listed and
completion enables only after six arm captures, four raised samples and both
height captures. The guided movement exercise remains available as optional
practice. Height capture remains accessible in that optional stage.

The new Game command asks the Cal 2 owner to validate/commit measurements and
create an explicit measured-target completion receipt. It uses the existing
progression/turn path and strict Relay stop before handoff: Green to Purple, then
the existing upgrade/ready deadline; GM practice returns without score credit.
Old saved rigs cannot supply fresh lesson completion. Receipts are idempotent,
and measurement fingerprints ensure edits after optional save are installed
before completing. No module ownership or robot-control boundary was changed.

Validation: 92 targeted Python tests passed, including measured completion,
incomplete rejection, repeated commits, changed heights, Green-first handoff,
shared deadline, score preservation and failed-stop retry. Both mobile browser
flows passed real routes with fake arms: regular/fine drag, off-centre grabs,
Purple inversion, touch cancellation, pinch handoff, saving all samples, visible
completion while folded and exit from both direct and already validated flows.
Existing Targeting browser regressions passed for both teams across five
layouts. No real arm movement or calibration capture was used in verification.
JavaScript syntax and git whitespace checks passed.

## 2026-10-02 — Publish progression/calibration work and audit with Ponytail

User requested the development-log update, GitHub push and a codebase/Mobile LTZ
audit against Ponytail, supplying `DietrichGebert/ponytail` when no local skill
was available. Read its audit, review and base rules at reference commit
`e3ba2aa6f1e6f0bc4d69eb09c9f0d0a93af56156`, without installing its plugin/hooks.
The report is [PONYTAIL_AUDIT_2026-10-02.md](docs/PONYTAIL_AUDIT_2026-10-02.md).

The structural scan covered 287 source/test files and 109,393 physical lines
before adding this audit's regression. The main opportunity is duplicate
presentation/controller code: about 12,000 lines could be removed through the
listed consolidations and confirmed unserved-page removal, with no demonstrated
dependency removal. These are estimates, not applied changes. Mobile LTZ's
shared frontend and owner boundaries compare well; legacy player Playfield
Areas still starts saver threads on import and writes non-atomic JSON, and
older Auto Pickup/Cal 2 presenters still read sibling files. Those outstanding
violations prevent a whole-repository compliance claim.

Normal correctness review found one remaining issue in the preceding completion
work: a transport-height update after the countdown expired was absent from the
UI render signature, and a save response could leave the busy-disabled button
rendered. Reproduced it with synthetic owner state, added the two measured
heights to the signature, and rerendered after saves finish. The browser check
now passes for both teams and for an update received while the save is busy.
No Ponytail deletion/refactor was applied. Updated the implementation overview
to reflect explicit measured completion and optional guided movement practice.

Verification: full Python discovery passed 475 tests; Node's test runner passed
46 tests. The new isolated completion browser regression passed for Green and
Purple. The full both-player fake-arm calibration browser flow was rerun after
the final fix and passed: six points, four raised samples, drag/Fine tune,
folded completion and return to the game, including previously saved tutorials.
Whitespace checks passed. No robot movement or physical calibration completion
was performed in this audit.

Operational note from the preceding continuation: hub PID 84651 loaded the
initial completion/dragging update. Live Green retained its four raised samples
but still needed pickup and transport height captures. The corrected camera was
stale; Webcam reported `camera returned no frame`. Reselecting the existing
camera was attempted before interruption, without verified recovery. This audit
does not claim that hardware condition is resolved. The final render correction
needs the normal hub restart and phone refresh because client bundles are frozen
at startup; the live hub was not restarted during this audit.

Publication scope: code, shared assets, tests and documentation on the existing
`photon-engine-phase-4` branch, using its configured `fork` GitHub remote. Local
hub credentials/settings, live calibration models, calibration session data,
projection session state and the robot command log are deliberately retained
locally and excluded from the commit.

## 2026-10-02 — Derive mobile calibration heights from the six captures

Pickup Z now uses the arithmetic mean of the six ground-point arm Z positions;
transport Z is pickup plus 40 mm. Removed the separate height-capture buttons
from Mobile LTZ and show the calculated values beside Complete calibration,
including with the instructions folded. Both values recalculate after a ground
point is recaptured. Unfinished saved lessons derive them from their existing
six measurements when resumed; completed historical calibrations are preserved.

Cal 2 owns the calculation and checks finite measurements and workspace bounds
before committing. New transport heights are stored per arm, avoiding the old
shared-height consistency gate when Green and Purple have different robot Z
origins. Controllers, guided targets, history and restore use that arm's saved
height. Older calibrations retain the shared transport fallback. Explicit
standalone commissioning height controls remain available and show the correct
arm value. No additional robot-control path or automatic motion was introduced.

Validation: 122 focused Python tests and 13 geometry/motion JavaScript tests
passed. Tests cover unequal ground heights, recapture, unfinished-draft resume,
per-arm commit/restore/restart, nonfinite/out-of-workspace rejection and legacy
fallback. The isolated UI regression and full fake-arm six-plus-four browser
flow passed for both teams without any separate height measurement or real
robot movement.

Deployment: the live relay still had Green connected with servos enabled
(follower stopped, pump off, no controller lease), so its hub was left running.
Restart the hub and refresh both phones to load the updated backend and frozen
mobile bundles. The isolated fake-arm test server was stopped after validation.

## 2026-10-02 — Verify offline calibration completion and disable the waiting arm

Complete calibration now commits the saved six-point/four-raised-sample evidence
without requiring a connected arm, camera refresh or live capture lease. The
same action works after a hub restart and after optional movement validation.
It checks the saved geometry, perspective model and calculated heights, keeps
the capture camera/rig identity, and never renews motion permission. The mobile
button stays available while disconnected; capture and practice still require
live feedback. Green's current saved draft was inspected read-only: six arm
points, four raised samples, valid geometry, pickup -100.370 mm and transport
-60.370 mm, both inside the workspace.

Game records completion and advances Green to Purple, then to upgrades/ready;
gamemaster Green-only, Purple-only and both-player tests return to the previous
lobby without changing player statistics. A failed or unconfirmed physical
shutdown retains the separate durable motion gate rather than trapping saved
calibration completion. Before each turn and during maintenance, Cal 2 asks
Relay's new documented `hhh.relay.disabled` v1 API to revoke the waiting arm's
controller and disable connected servos after measured settling. Offline arms
are never connected automatically. The completed arm is also disabled when
connected; a failed disable cannot be cleared by a hold alone.

Verification uses real UI/routes/owners with fake hardware and temporary data.
The individual gamemaster, both-player gamemaster and earned XYZ-milestone
browser scenarios all completed both players with both arms disconnected and
the lesson store restarted immediately before Complete. They cover folded
controls, saved history/default selection, waiting-arm disable, waiting-player
upgrades, next-phase transitions and unchanged practice statistics. No real
robot movement or live calibration completion was issued. An unrelated content
test had an intermittent missing-Progress-owner race; its isolated fixture now
provides that real owner instead of depending on background-worker timing.

Final validation: all 482 Python tests passed, the isolated mobile rendering
check passed for both teams, and all three browser completion scenarios passed.
The final earned scenario also passed with the durable disable-failure gate.
The live hub was loaded with the final update as PID 96725 after both arms were
observed disconnected, servos/followers/pumps off and without a controller lease.
The live Green page shows Complete calibration enabled while disconnected;
its measurements were preserved. Both phones need a page refresh. The fake-arm
test server was stopped and the development log/contracts were updated.

## 2026-10-02 — Count down the four raised-target glows

After the sixth arm capture, the calibration display now hides unused markers
30 and 32 and shows only the four raised references, 31/35/33/34. These targets
start green; saving each raised sample removes that target's glow while keeping
its ArUco code and white number visible. Mobile live/cached labels also omit
30/32 in this phase. Instructions explain the glow countdown, and the folded
capture controls retain their saved checkmarks. Both player orientations use
the same behavior without changing target geometry or measurement data.

Cal 2 derives presentation from the durable lesson via Playfield's documented
`hhh.playfield` v1 progress command. The display owner validates visible and
highlighted marker lists, owns persistence/SSE, and skips unchanged writes.
Resume and maintenance restore the remaining glows after restart even before
hardware reconnects. The first six captures retain their original behavior:
accepted points gain green glow.

Validation: 94 focused Python tests passed, including both sides, invalid
progress rejection, interrupted-display recovery, no redundant maintenance
writes and filtering hidden cached labels. The full both-player gamemaster
browser flow passed with fake hardware and temporary data: four glows count
down to zero, saved codes stay visible, both players complete offline after
restart, the waiting arm stays off, and practice statistics remain unchanged.
JavaScript syntax and whitespace checks passed. No real arm movement or live
calibration capture/completion was issued.

After confirming both real arms were disconnected with servos/followers/pumps
off and no controller lease, the local hub was reloaded as PID 97168. Green's
live saved draft retained all four raised samples, displayed only 31/33/34/35,
and exposed Complete calibration while disconnected. Its projected targets
have no remaining glows, as expected for four saved samples. The isolated test
server was stopped. Both phones need a page refresh for the updated UI.


## 2026-10-06 — Share fresh marker evidence between Y and Mobile LTZ

Photon Board now publishes `photon.board.camera-markers` v1 from its cached,
corrected, immediate detections and current visible IDs. Laser Tag Y and both
Mobile LTZ teams consume this same projection and fixed 1.5-second freshness
policy. Mobile no longer drops detections merely because tracked-tag
qualification is pending or the old 250 ms missing cutoff was exceeded. Y's
remembered table positions remain display history and never satisfy alignment.
The four-marker minimum, spread/fit checks, calibration safety and existing
robot-control path remain enforced.

Mobile reports detected and level-matching counts/IDs, explains insufficient
matches, and keeps current alignment readiness in the left status log. A
recovered scene notice becomes resolved history immediately; it cannot remain
an active pinned failure. Unrelated command errors retain their normal pin.

Validation: 131 focused Python tests passed across Mobile, Photon Board, module
isolation, Y camera/stream and the new shared-evidence regressions. Four Node
smoke checks passed (camera notices, physical controls, arm bridge, video), as
did JavaScript syntax and whitespace checks. The isolated real UI with temporary
data and fake hardware showed the same twelve markers in Y and both Mobile API
projections with 300 ms frame delay and no qualified tracked tags. The Green
browser showed three-marker failure and automatic twelve-marker recovery
without refresh, including a landscape phone layout. No live robot commands
were sent. Loading the backend requires a hub restart; the live game was over,
but Green remained connected and enabled, so restart approval was requested.


## 2026-10-06 — Reject inconsistent marker sizes

The shared Y/Mobile camera-marker projection now measures mean edge length
from the corrected pixel quadrilateral and keeps the unique largest group
whose maximum/minimum size ratio is at most 1.15. This is a strict pairwise
15% span. At least two sizes must agree; ambiguous groups and missing/invalid
corners cannot establish acceptance. No ID-specific blacklist or historical
size reference is used. Correctly sized marker 49 can recover immediately.
Y purges explicitly rejected cached locations and older cached outlines that
are incompatible with the current accepted size range. Mobile reports the
number of size rejections and includes it in insufficient-marker explanations.
Raw observation, physical calibration and game-placement contracts are unchanged.

Validation: 137 focused Python tests passed (13 shared-marker regressions, 7 Y,
70 Mobile, 43 Board and 4 isolation), plus the Node camera-notice smoke check,
JavaScript syntax and whitespace checks. The captured live frame's twelve
markers measured 75.25–77.48 pixels and all passed. Marker 49 was absent in
that fresh sample. The isolated browser fixture rejected an oversized 49,
accepted it when restored to normal size, then removed its cached outline
when oversized again while twelve valid markers stayed aligned. No live
robot command or hub restart was issued; the earlier activation approval is
still pending. The fixture now serves Level's assets when exercising Y,
avoiding unrelated renderer retry traffic during future browser checks.


## 2026-10-06 — Synchronize reconnects after manual arm repositioning

Green and Purple now connect/enable through the existing relay without starting
ServoJ/ServoP. The relay requires new finite feedback, <=250 ms old and stable
for 80 ms, before first movement; timeout fails closed. Follower targets and
velocity reset to the measured pose. Physical unlock/disable/fault/pause is
latched at feedback rate, even across a brief unlock/relock, and changes the
motion generation. Lost feedback, unexpected tracking displacement and socket
failure also discard movement. Generation checks extend through validation,
follower startup, target submission and the socket send boundary. Replacing a
connection invalidates its lease; serialized relay connection/move operations
prevent a delayed request from binding to a replacement arm.

Both player adapters preserve feedback timestamps, robot modes and movement
generations, reject reordered heartbeat snapshots, and expose a separate player
connection identity. LTZ movement requests carry that identity and generation.
The mobile bridge clears old joint/XYZ goals and queued input, waits for previous
lease release, requires a fresh status for the new connection, and ignores old
status/movement replies. Unlock or lost feedback requires Connect again. The
controls adopt measured feedback and wait for a deliberate gesture. Out-of-range
LTZ joint/rotation targets report a limit instead of silently clamping an
untouched axis into motion; existing calibrated path checks remain enforced.

Validation: 91 Python tests passed (21 relay, including 13 reconnect regressions,
and 70 Mobile); both-team bridge smoke tests and physical-routing smoke passed;
all six Cal 2 motion and five calibration-command Node tests passed. The new
integration regression runs both real player Connect routes through fake relay
HTTP/feedback and confirms enable/synchronization sends zero servo targets.
Tests also cover stale/missing feedback, brief unlock, relocation in joint/XYZ,
unlock during path validation, old lease/session requests, delayed replies and
telemetry, socket failure, and out-of-range untouched rotation. Syntax and
whitespace checks passed. A read-only live check found Green connected/enabled
with an active servo loop and Purple disconnected. Activation requires a hub
restart; no live movement/stop/disconnect or restart was issued during the fix.


## 2026-10-06 — Reuse saved arm calibration with the current camera

Game Master Apply now explicitly associates a saved arm calibration with the
current camera correction instead of rejecting a different original revision.
The source revision, measured points, raised references and heights remain
intact. The association persists separately in that arm's calibration, survives
reload and is cleared when new measurements are committed. Apply checks the
current camera identity again after connected arms have stopped. A later camera
change requires another explicit Apply or new calibration.

Laser Tag Y shows a precision warning for different or unknown source sessions
before and after applying. As requested, this is informational only: all control
levels retain their existing availability, with no session-based tier cap.
Existing robot identity, geometric limits, progression and stop checks remain.
Matching camera revisions remove the warning. The current camera's settings
are never replaced by the older arm record.

Validation: 100 focused Python tests passed (24 saved-calibration tests plus
76 safety, Journey, display/cache, Y camera/marker and module-isolation tests).
Regressions cover both arms, all four control modes, original-data preservation,
restart persistence, unknown source revisions, malformed persisted association,
camera changes during Apply, and new measurements replacing the association.
JavaScript syntax and whitespace checks passed. Browser verification using the
isolated fake-arm fixture confirmed older Green/Purple Apply succeeds, the
amber warning remains visible, and matching revisions hide it. Fixture command
records confirmed no move or enable commands. The browser regression was also
extended for these cases. No live robot command or hub restart was issued;
activation still depends on the previously requested stop/restart approval.


## 2026-10-06 — Adjustable relay ceiling and player height range

Dobot MG400 Relay now has Enforce ceiling / Ceiling Z (mm) / Save ceiling
directly below the floor row. The ceiling defaults to 80 mm for both arms,
including existing floor-only configuration files. Floor and ceiling values
must be finite, ordered and inside the robot workspace. Changes save atomically,
surface failures, and settle connected arms and revoke their leases before
replacing the limits. Invalid input and stop/save failures retain the old range.

Cartesian targets above the ceiling are rejected rather than replaced with an
unrequested lower target. Joint paths use controller forward kinematics to
enforce the ceiling even without a learned floor model; only descending joint
recovery is allowed from a manually positioned arm above the ceiling. Existing
Cal 2 bounds and other movement checks still apply.

The versioned hhh.relay.z-limits contract is exposed through relay config,
state/heartbeat and a read-only endpoint. Both player adapters validate and
forward it. Shared player Z controls and Mobile LTZ take their effective height
range from those limits, including updates. Cue height respects the ceiling.
Range updates cancel queued input without issuing a movement; known ceiling
rejections remain recoverable by selecting a valid target. The operator UI
reports ceiling unavailable if an older running backend has not been restarted.

Validation: 60 focused Python tests passed, including 13 new ceiling regressions;
both-team mobile bridge, physical-routing and Z-range Node smoke tests passed,
as did all six Cal 2 motion tests. Inline and standalone JavaScript syntax and
whitespace checks passed. The isolated browser fixture verified the row layout,
80 mm default, editing to 65 mm, live player and Mobile LTZ range updates,
restoration to 80 mm, rejection of 300 mm, and saved value after reload. All
fixture arms are fake; no live hardware was commanded or restarted. Live
activation remains pending the previous stop/restart approval.


## 2026-10-06 — Complete the core by covering its armed Atom

The physical core sequence now remembers the first Atom activated on marker 38
and consumes a separate Board-owned camera cover relationship for the opposing
Atom. The second arm can be disconnected, and the finish no longer depends on
marker 38 remaining in its 120-second cache. First activation and ordinary
tower placement retain their existing arm requirements. Virtual commands keep
their existing behavior. Core detonation, enemy purge and victory use the
existing simulation path; successful covers add a diagnostic history event.

Board follows each visible movable and recognizes its disappearance beneath a
unique nearby upper movable. Confirmation needs 0.55 seconds and three distinct
fresh camera frames; tracked-tag grace periods are excluded. A newly covered
lower tag must have been visible within five seconds, while uninterrupted cover
evidence persists. Both-visible tags, ambiguous covers, movement away, stale
camera input and source changes cannot create a win. Game validates the new
additive versioned descriptor, exact lower Atom, opposing ownership and the
post-activation timestamp. Reset discards the armed Atom.

Validation: 121 focused tests passed (21 core-stack regressions, 43 Board,
48 framework, 4 module-isolation and 5 input-report tests). Cases include the
reported 100/103 sequence with Purple disconnected after marker 38 expires,
neither arm connected, reverse team order, following a moved first Atom,
wrong-team/wrong-target covers, stale/replayed/ambiguous evidence, contract
validation through the public Board/Game boundary, existing tower arm checks,
and detonation waiting for the enemy purge. No live robot command or hub
restart was issued during implementation.

## 2026-10-06 — Preserve player connection evidence

Investigated physical run `6f05c2d8c98f4b3fbdc43b9c33b6f681`, from
15:34:51 to 15:39:05 Europe/Tallinn. Green's relay command monitor records
player-originated Hold / pump-off / Release at 15:35:20–21 and 15:36:18–19,
followed by new acquisitions at 15:35:33 and 15:36:22. No robot error was
recorded at those releases. The final release at 15:39:05 coincided with
`run_won` after core detonation. The previous logs did not retain browser
suspend reasons or watchdog causes, so they cannot establish which freshness,
visibility, feedback or transport event caused the two earlier releases.
The stream-error and 1.5–2.5-second freshness paths are candidates, not a
confirmed explanation. Earlier tunnel errors were outside this run.

Added team-authenticated, bounded JSONL connection logging in Mobile LTZ API,
with a GM-only download linked from the relay Command monitor. Green and
Purple record exact bridge halt causes, status/stream failures, suspend/Stop,
connect outcomes and command timeouts, together with run/build/page identifiers,
freshness ages and relevant feedback flags. Parent stop reasons survive the
iframe handoff. Credentials, full states and positions are excluded; sensitive
strings in errors are redacted. Pending browser evidence retries separately
from motion and survives refresh, with a bounded 48-hour recovery window.
The relay logs lease expiration only after both affected arms have stopped,
and logs rejected heartbeats. No safety threshold, motion grant or reconnection
behavior changed.

Validation: 59 focused Python tests (logging, gateway, teams, reconnect, height
limits and module isolation) and four JavaScript smoke runs passed. Coverage
includes disk failure, authentication/origin/team checks, rotation, deduplication,
offline/refresh retry, no secrets, and logger failure during a command timeout.
An isolated browser fixture confirmed Stop remains responsive and its events
reach the persisted download. No real robot commands or live hub restart were
issued. Activation requires a safe hub restart and player-page refresh; hosted
PHP/gateway deployment is separate.


## 2026-10-06 — Inspect Mobile LTZ generation and outgoing traffic

Mobile LTZ API now has a Game Master-only delivery dashboard. It shows separate
Green/Purple generation and SSE emission rates, build latency, byte totals,
snapshot/update/keepalive counts, HTTP errors, stream lifecycle counts and
recent requests. The inspector compares the full generated player projection
with actual sampled SSE envelopes and HTTP responses, including per-field
sizes, freeze/resume and redacted sample downloads. A connection-log export
link retains the existing diagnostics endpoint.

Instrumentation wraps the existing shared LiveState stream and records every
subscriber's emitted frames without changing player payloads or caching. The
monitor only reads bounded in-memory records; opening it creates no game
snapshots or robot calls and its own requests do not inflate counters. Preview
capture is sampled, bounded and credential-redacted. Observer failures cannot
interrupt player delivery, and authentication failures do not make diagnostics
consume rejected request bodies. The page labels server emission separately
from phone receipt and downstream compression.

Validation: 61 focused Python tests passed (16 new monitor tests, 10 mobile,
15 team, 4 client-build, 3 calibration-safety, 4 module-isolation and 9 gateway).
The client-build fixture was missing its already-required connection-log.js
helper; it now copies that file into its temporary bundle. Headless browser
checks against a robot-free fixture verified both teams, snapshot/update
differences, freeze/resume, downloads, disconnect accounting and responsive
layout, with zero POSTs and no page errors. JavaScript syntax and whitespace
checks passed. The live hub was not restarted; activation is still pending
the previously requested restart approval.

## 2026-10-06 — Graph Mobile LTZ delivery on a shared timeline

Added six full-width Green/Purple graphs immediately above the payload inspector:
generation and SSE packet rates, combined SSE/HTTP bandwidth, interval mean
build time, active streams and delivery issues. Every graph uses the same rolling
15-second axis with a shared pointer/keyboard cursor and its own labeled units.
The solid Green and dashed Purple series remain distinguishable when overlapping.
The existing monitor polls supply cumulative-counter differences, so the graphs
show roughly one-second measurements without extra API or player traffic.

Browser history expires continuously, including during disconnection; missing
poll intervals appear as gaps, idle builds have no latency sample, and module
restarts clear prior history. Payload freeze leaves the graphs running. History
is local to the open dashboard and resets on reload.

Validation: all 16 monitor Python tests and the extended robot-free browser
check passed. Deterministic measurements verified interval rates/build means,
aligned spikes and cursors, 15-second expiry, gaps, restart resets and payload
freeze independence. Desktop and 390-pixel phone screenshots were reviewed;
there was no page-wide overflow, no browser error and no POST or robot command.
The live hub remains unchanged; the pending restart is still required to load
the previously added dashboard routes.

### 2026-10-06 — Physical cue cache and player-assisted recovery

Fixed the cue validation race between 750 ms UI refreshes and the bridge's 500 ms
freshness cutoff by awaiting a refreshed map. Added Board-owned fixed-marker
memory and stable moving-Atom observations, projected through the mobile API and
existing SSE stream. Camera/layout changes invalidate authority; known covered
fixed destinations do not become clear when the covering Atom disappears.

Physical cues retain their row while awaiting a tag. The player can use the
existing playfield click override to reveal it, then the step remaps and resumes.
No automatic leftward arc was added. Missing Atom prompts mention battery failure;
pickup completion now requires player confirmation because disappearance cannot
prove grip. Stop and changed sessions cancel late detections/confirmations. Recovery
uses the existing relay path and preserves suction while waiting. Added cache,
recovery, fake-relay cancellation and phone layout tests; no live arm commands.

Validation: 9 cache tests and 11 cue recovery tests passed, plus 92 mobile backend
tests, 43 Board tests, 21 camera tests, 4 module-isolation tests, Cal 2 motion tests,
and fake physical bridge checks for both teams. Browser checks verified normal
cue placement and recovery controls on both teams across phone layouts. The full
browser suite exposed an obsolete settings-message assertion (updated to the
current draft wording); its final rerun stalled during browser launch and was
terminated along with the temporary fixture. The live hub was not restarted and
no physical arm commands were issued.


### 2026-10-06 — Limit Atom occlusion tolerance to one cue row

Corrected the recovery regression where the approaching arm hid its own 100-series
target and stopped. Each LTZ row/attempt now acquires a fresh stable source before
approach, then retains that position for its current pickup. The drop endpoint has
its own acquisition and retention through descent. Missing individual detections
do not interrupt that move or trigger the former manual grip-confirmation gate.
The next row (even the same Atom or another loop pass) acquires again. Clicks
before contact, changed mappings and observed movement invalidate the retained
approach; full camera failure, relay safety and Stop retain their gates. No LTZ
pickup can fall back to a commanded release position.

A revealed fixed source marker is logged only as supporting departure evidence;
it never grants new Atom coordinates or placement confirmation. Board/Game still
require visual placement evidence. Removed the obsolete grip-confirmation buttons
and command. Tests exercise the actual queue loop with hidden source/destination
tags, next-row reacquisition, interruption and departure-versus-placement evidence.

Validation: 15 cue recovery tests, 31 Board tracking tests, 9 target-cache tests,
13 camera-alignment tests, 4 frozen-client build tests and 6 Cal 2 motion tests
passed, as did the physical bridge smoke tests for both teams and the physical
mobile smoke test. JavaScript parsed and the diff passed whitespace checks.
No live arm commands or hub restart were performed.

## 2026-10-06 — Visible cue startup failures

Retained cue failure message, stage and row separately from periodic camera
status, and exposed them through the physical bridge to the shared mobile UI.
Moved controller/UI startup work inside their cleanup handlers, kept the first
failure when pump cleanup fails, and logged requested/blocked/failed starts via
the existing diagnostic stream. The cue panel now distinguishes Game, Arm and Cue
state and explains disabled Play; idle map taps explain how to start intervention.
The existing motion, calibration, pickup retention and Stop gates remain in use.

Validation: 21 cue recovery/start-feedback tests, Green and Purple bridge smoke
tests, physical-control and notice smoke tests, and 4 frozen-client build tests
passed. Browser inspection stalled, so visual layout verification is incomplete.
The isolated fixture was stopped. No live arm commands or production hub restart
were performed; restart the hub and refresh player pages to load the frozen UI.

## 2026-10-06 — Restore the selected webcam and report disconnects accurately

Live investigation found the running hub serving a 1552×1552 computer-facing
camera while labelling index 0 as the Verbatim USB webcam. Its AVFoundation
inventory still had two cameras, while a fresh process saw the reconnected
Verbatim as a third device. Blind probing produced the reported indices 2–5
warnings. USB bus order had incorrectly supplied capture-index names, and camera
status considered a capture handle live even when reads failed or stopped.

Added native AVFoundation inventory in the capture process, matching OpenCV's
unique-ID order. Names and persisted identity now refer to the actual device;
startup/reconnect resolves the saved identity and does not substitute another
camera. Listing no longer probes absent macOS indices. Fresh-frame status clears
live dimensions/FPS/images/tag evidence on failure or staleness; read failures
invalidate the cue epoch. Webcam has explicit Reconnect and unavailable labels,
and Stop stays stopped across stream viewers. Existing cue behavior is unchanged.

Validation: 18 webcam tests passed with both the project and live hub Python
runtimes; 21 camera contract/alignment tests, 31 Board tracking tests, 9 cue-cache
tests and 3 Webcam UI tests passed. Native helper/library rebuilt successfully;
Python syntax and whitespace checks passed. Saved the verified Verbatim identity
without changing optical/resolution preferences and restarted only port 8000 in
setup mode. Live checks recovered 3840×2160 at roughly 24–25 FPS and alignment
with up to 14 matching markers; startup/probing had no bounds errors or tracebacks.
No robot movement commands were sent. Player pages need refresh/reconnection
after the hub restart. UI rendering was checked with DOM fixtures, not a browser.

## 2026-10-06 — Restore Webcam preview and release old module pages

The live camera was delivering valid 4K board frames and tracking 17 tags, while
Chrome's Webcam image stayed pending with naturalWidth 0 and its separate status
stream continued updating. Multiple live tabs shared the same HTTP origin. The
controller now receives the existing JPEG and status over one optional SSE stream
at up to 10 FPS, using the existing LiveState helper with shared encoding. It
closes that subscription when hidden/unloaded and while finite camera requests
run, reconnects on return, and shows a video-specific waiting/error notice. The
state-only event API, capture/tracking rates, saved resolution and camera identity
are unchanged. Observation does not reopen a stopped camera.

Also reproduced a hub module switch that changed the selected label and iframe
URL while the previous Webcam document kept running. Setting about:blank followed
by the next URL in requestAnimationFrame did not reliably dispose of that old
document before the next navigation. Switching, Reload and disabled modules now
replace the iframe browsing context outright, releasing its streams. Player
fullscreen messages remain restricted to the current frame and expected origin.

Validation: 19 hardware-free webcam tests passed in both project and live hub
Python runtimes; 9 JavaScript webcam/navigation regressions passed. Restarted only
the local port-8000 hub after verifying game phase setup. Verified Chrome rendered
the new Webcam JPEG at naturalWidth 3840 / naturalHeight 2160, and visually verified
Webcam → Photon Board → Webcam after loading the dashboard repair. The return
preview showed the board and 17 tracked tags. Browser automation stalled during
reload; native Chrome UI recovered and completed the visual navigation check.
No robot motion commands were sent. Other open dashboards require a full-page
refresh to receive the new iframe lifecycle code.

## 2026-10-06 — Restore Laser Tag Y camera through the existing game stream

Reproduced Y showing “Connecting to Photon Board camera…” while its Game SSE
updates arrived: the separate preview image remained pending with naturalWidth 0.
The earlier Webcam controller repair did not change Y's independent MJPEG branch.
Added Board's public `photon.board.preview` v1 display-frame adapter over Camera
Calibration's existing shared corrected JPEG. It rejects unavailable, malformed,
simulated and stale input. Y optionally multiplexes versioned camera events onto
its existing Game/marker SSE connection, without putting pixels into gameplay.
External-screen and state-only consumers retain their existing payloads.

The operator consumes those frames without opening an MJPEG request, checks their
timestamps, hides expired images and automatically resumes on a fresh frame. A
missing first frame gets an explicit delayed status and Retry option. Hidden Y
views close their one connection and reconnect with a fresh Game baseline. Existing
calibration command suspension and virtual/physical presentation gates remain.
Updated the public contract documentation, data-flow explanation and UI fixtures.

Validation: 47 Board tests, 8 Y camera/marker tests and 6 calibration-command tests
passed, plus an isolated real-route fixture verified corrected JPEG camera events.
Y tests also passed under the live hub Python. During live verification macOS lost
the Verbatim device; after the user's USB replug, its native ID changed from
0x1100001bcfdc17 to 0x1200001bcfdc17. Refreshed the idle hub's macOS inventory and
explicitly selected the verified Verbatim at its new ID, preserving saved capture,
tracking and optical preferences. Y recovered automatically to “Live camera ·
Photon Board” with a decoded 3840×2160 image. Verified Y → Photon Board → Y and saved
browser proof. Current detections are intermittent; overlays correctly distinguish
cached table positions from recent sightings. No robot commands or calibration
application were performed.

## 2026-10-06 — Restore manual exposure access and concentrate the existing slider around 0.03 s

- Reproduced the Calibration page with auto exposure checked, manual slider disabled, and a checkbox change that never reached the server while the MJPEG feed occupied a browser connection. The page had only completed its initial focus read; subsequent polls/control requests were queued.
- Camera Calibration now sends its preview, calibration state and optical controls through one shared LiveState SSE connection. Finite commands close that connection until their complete JSON response arrives, then resume it. Hidden/unloaded pages release it; periodic HTTP polling is removed. Focus/exposure writes are serialized, and pending edits cannot be overwritten by older readback.
- Kept the existing manual-exposure slider. Its middle 80% now covers 0.0100–0.0500 s in native 0.0001 s increments on the Verbatim camera, centred at 0.0300 s. Logarithmic tails retain the complete reported range. Mapping adapts/clamps to other camera ranges and hardware steps.
- Webcam retains its native control interface before capture starts, but reapplies remembered focus/exposure after AVFoundation opens/configures capture so startup mode resets do not undo manual settings. Native readback is preferred without repeatedly probing OpenCV setters. Unsupported exposure writes return an explicit failure.
- Verified 55 relevant checks: calibration exposure JS (6), existing webcam JS (6), camera contracts (9), webcam lifecycle (15), and calibration display (19). Camera contracts/lifecycle also passed under the running Conda runtime. `git diff --check` passed.
- Restarted only the idle port-8000 hub after checking game phase `setup`. Verified the existing browser tab restored manual exposure at 0.0309 s, successfully switched auto on then off, accepted individual fine steps, and displayed a loaded 3840×2160 preview. Left the webcam in manual mode at its previous 0.0309 s and focus 2. No robot movement commands were sent.
- Visual proof: `/Users/kaur/.codex/visualizations/2026/10/06/01a11195-be23-77e0-ba32-ce15dda855fc/manual-exposure-fine-control.jpg`.

## 2026-10-06 — Laser Tag Y Start and unlock requests blocked behind live feeds

- Live page showed a ready physical board and visible tag 100, but remained in setup with Start enabled and test unlocks stuck at “Applying test unlocks…”. No corresponding Y command had reached the server since the view opened. Only calibration commands reserved a browser HTTP connection; normal commands and reads competed with the long-lived stream.
- Added a shared finite-request wrapper in Y's existing controller: reference-counted reservation closes its SSE connection through response parsing and any follow-up state read; visibility, retry and boot paths cannot reopen it while requests remain pending. All requests have a bounded deadline, and commands are never automatically retried after timeout.
- Start now displays “Starting…” while pending, blocks duplicate clicks, and surfaces backend rejection/timeouts while retaining authoritative game-state checks. Page teardown also prevents a late request completion from reopening its stream.
- On loading the updated page, the previously queued Start reached the server (HTTP 200; a duplicate was rejected with HTTP 400), and the authoritative mobile/game state became `running`, `paused:false`, physical mode. Left the user's practice game running; did not issue another Start, reset, pause, or arm-motion command. Saved-calibration refresh also completed with the live feed active.
- Validation: 11 JS command/connection tests, 3 Y camera tests, and 34 journey tests passed (48 total); `git diff --check` passed. New tests cover saturated connections, duplicate Start, backend rejection, timeout recovery without retry, full-body/follow-up reads, concurrent reads, and unloaded/hidden-page lifecycle.
- Visual proof: `/Users/kaur/.codex/visualizations/2026/10/06/01a11195-be23-77e0-ba32-ce15dda855fc/laser-tag-y-start-fixed.jpg`.

## 2026-10-06 — Move to a player-selected point while Cue is idle

- Removed the mobile Cue UI's active-cue-only map-click gate. A ready player can tap a point without submitting their draft or pressing Play. The hint now describes both immediate map movement and cue playback.
- Physical Green/Purple bridges route idle `cue_waypoint` commands through the existing calibrated `video target` planner at transport height, preserving cue rows/status and pump state. Active/paused physical cues retain the existing intervention path. Current camera mapping, arm feedback, connection/session/revision, bounds and relay safety checks still apply; a visible source Atom is not needed for this manual repositioning.
- Fresh matching `cue_waypoint` progress can extend the existing physical adapter deadline like a planned XYZ detour, with the same absolute limit. Stop/session/mode changes still invalidate late completions and cannot replay the target on reconnect.
- Virtual idle/stopped/completed/error cues also reposition immediately through their existing arm solver without changing cue state. A paused cue can be repositioned while remaining paused; cancelling that waypoint holds its measured pose.
- Validation: 22 cue presentation/recovery tests, 12 virtual cue tests, 4 frozen-client build tests, and both Green/Purple fake-relay bridge smoke suites passed. JS syntax and `git diff --check` passed. Tests cover no rows, absent source tags, paused cues, invalid/missing mapping, bounds, pump/queue preservation, delayed Stop and bounded detour deadlines. No physical arm movement was used for verification.
- Activated after the user approved ending the practice game and restarting now. Restarted only the port-8000 hub with its existing Conda Python runtime; the game returned to `setup`. Both Green/Purple live player bundles and arm bridges exactly match the tested source, with fresh build IDs. The Verbatim camera recovered at 3840×2160 with manual exposure 0.0309 s and focus 2 preserved. Players must refresh and reconnect to load the updated controls. No physical arm movement was used for verification.

## 2026-10-06 — Height and preset cue intervention; identify excluded endpoints

- Z sliders, step buttons, Fine tune and stored-height recalls now remain available in idle, running, waiting and paused Cue states. They retain the existing height-only XYZ command, session, mode revision, limits and readiness checks; presets are still saved without issuing motion.
- Active physical height requests share the playfield override owner. They wait for a pump transaction to finish, hold through the existing robot route, read measured XY, and move vertically to the requested height without a transport lift or lateral detour. Arrival resumes the current cue step, or preserves a paused cue. Superseded/old-session completions cannot finish newer overrides. Failed interventions hold and pause without changing suction. Idle height remains immediate without starting or editing the cue.
- Virtual height requests use measured XY through the authoritative arm solver, preserving queued steps, pump state and held pieces. Added coverage for paused intervention, automatic continuation, rejected input and Stop cleanup.
- Live diagnosis of the previous failure showed source 100 inside the permitted robot-space polygon, but destination 45 outside it. The generic error did not identify the endpoint. LTZ queue capture now defers pose conversion to the current row, and acquisition distinguishes mapped-but-unreachable endpoints with a row/role/tag message. A later row cannot reject startup by converting its target early. Calibration and exclusion limits remain enforced.
- Validation: 28 cue/recovery/height UI tests, 14 virtual cue tests, 6 Cal 2 motion tests, 4 frozen-client tests, XYZ arrow smoke and both Green/Purple fake-relay bridge smoke suites passed. Controller inline JS and mobile JS syntax checks passed; no physical arm motion was used.
- Activated after the user's explicit restart approval. Restarted only the port-8000 hub with its existing Conda runtime. Both fresh Green/Purple bundles and bridges exactly match tested source; live controllers contain vertical overrides, endpoint-specific messages and deferred row validation. Game returned to setup; Verbatim preview recovered at 3840×2160, manual exposure 0.0309 s and focus 2. Player refresh/reconnect is required. Startup error checks and `git diff --check` passed.

## 2026-10-06 — Accurate cue cache labels and stable target selection

- Live diagnosis found all 17 cue targets visible/stable, with camera evidence 138–211 ms old. The player independently marked tags cached at 350 ms while refreshing its acquisition/calibration snapshot every 750 ms. Laser Tag Y used the current camera projection. Repeated visible/cached changes also rebuilt every cue row and native select, interrupting selection.
- Added a read-only cue display projection that follows the latest compatible SSE evidence and preserves owner-provided visibility between observations. Fixed occluded tags retain their cached label; stale, unavailable or changed-scope maps remain unavailable. This presentation path never updates acquisition evidence, stability, retained pickup positions or observation timestamps. Both teams' bridge markers and cue choices share this projection.
- Cue rendering now retains row/select nodes. Focused native pickers defer option changes and server draft replacement until blur; handlers edit the current draft even after a server row replacement. Selected missing targets remain identifiable and recover when mapping returns. Disabled state is written only when it changes.
- Validation: 35 JavaScript cue/selection/recovery/height tests, 9 camera-target tests, 4 frozen-client tests and both teams' fake-relay smoke tests passed. Browser verification with the real cue rendering/control functions and simulated 10 Hz camera flicker preserved selection of 100 → 45. No physical arm commands were used. Inline controller/mobile syntax and whitespace checks passed.
- Activated by restarting only the existing port-8000 hub after confirming setup phase and both arms disconnected, disabled and pump off. Green build `0854ba7ee3174337a0d4da42632c1597` and Purple build `a9104ba39ee64bee979977219d9e3405` exactly match the tested bundle/bridge source. Camera recovered at 3840×2160; the live cue projection reported 17 visible, zero cached targets at 195 ms frame age. No startup tracebacks. Refresh/reconnect player pages to load the update.

## 2026-10-06 — Flicker-tolerant acquisition, accurate reach and explicit cue selection

- Investigated the reported 100 → 50 non-start. The player logged a generic wait for 100 despite server sightings; acquisition still imposed 350 ms end-to-end age and consecutive-frame stability. Another attempt had reached its pickup/drop sequence; at 22:45:35 Tallinn time feedback reached 1558 ms and the client disconnected. The separate accidental 47 selection was outside the captured envelope. Initial calibrated evidence placed 100 outside the envelope and 50 inside; 100 subsequently moved. The user later identified a depleted Atom battery behind a turret/detection interruption. No turret activation rules changed.
- Board now adds `acquirable` evidence for moving tags: three distinct, consistent sightings within 1.5 s, spanning 0.5 s, newest at most 750 ms old. Short missing frames retain confidence without changing observation times or granting fixed-cache status. Movement, long gaps and camera invalidity reset confidence. Acquisition uses this bounded evidence; legacy owners retain strict visible/stable handling. Each row still needs a post-start sighting and retains its source only for its current operation. Recent contradictory positions invalidate an approach even after a missed frame.
- Recovery prompts distinguish confirmation of recent sightings, unavailable camera mapping, genuinely missing tags/battery and reach failures. Reach contour now respects the measured robot-space polygon, with remaining invalid cells shaded. Bridge choices report reachability using the raised-tag correction; known unreachable destinations are disabled. First-row failures name the source/destination before Play, while later rows remain validated on arrival.
- Play verifies its setup acknowledgement and sends its exact rows to both physical and virtual owners; mismatches cannot run an older target. Diagnostics record requested/accepted sequences. Paused cue rows stay locked until Stop, and editing a new draft clears obsolete local failure text.
- Validation: 55 JavaScript selection/acquisition/recovery/height/geometry tests, 12 Board evidence tests, 15 virtual cue tests, 4 frozen-client tests and Green/Purple fake-relay smoke suites passed. Syntax and whitespace checks passed. No physical motion commands issued.
- Activated after the game reached `overrun`, with both arms disconnected, disabled and pump off. Restarted only the verified port-8000 hub. Green build `00d4f2ab66d442d39dbe5a93d159553a` and Purple build `808cb0acdec8472b92eeabb85b431739` exactly match tested bundles/bridges. Live Board reported 100 visible/stable/acquirable with seven sightings and 128 ms age; 50 remained visible/stable. Camera recovered at 3840×2160 with manual exposure 0.0309 s and focus 2; no startup tracebacks. Game returned to setup. Player refresh/reconnect is required.

## 2026-10-06 — Expanded configured reach and pickup-retention regression analysis

- The six calibration captures were also being used as a robot-space motion hull, excluding points within the configured MG400 reach. The calibration owner now publishes `hhh.cal2.reach` v1 as `motion_envelope`: 430 mm outer radius (10 mm inside the nominal 440 mm), unchanged 220 mm base exclusion, and a concave sector ending 5 degrees inside the configured +/-160-degree J1 limit. Valid calibration and camera/rig identity remain mandatory; Relay keeps path validation and floor/ceiling checks. This is the nominal XY envelope, not a measurement of reach at every height. Corrected both player proxies' nominal radius from 450 to 440 mm.
- Controller planning, joint guard, target availability and displayed reach share the owner's polygon. Older owners retain the captured hull; malformed reach contracts fail closed. Camera reach geometry caches by captures and limits to keep repeated rendering off the feedback-critical path. Saved calibration files were not modified.
- During investigation the user reported the pickup waiting for 100 again. Live records show 100 -> 54 acquired at 23:07:26, a source-hover command at 23:07:26.677, hold at 23:07:38.002, then a missing-100 prompt. No suction-start command occurred. Repeated camera-unavailable/ready transitions followed, then an independent feedback timeout at 23:09:52. The logs do not identify the first retained-target invalidation reason. Both arms were subsequently disconnected with pumps off.
- Offline execution of the actual endpoint resolver reproduces loss of the acquired source on a 1.5-second frame expiry, temporary mapping-unavailable status, and a single displaced unqualified detection. All return to acquiring a hidden 100. Existing tests only covered tag occlusion with a continuously ready mapping and intentionally required re-acquisition after global camera failure. No cue-retention behavior changed in this turn. Proposed correction: preserve the row-scoped robot position while holding for transient map recovery, resume it only under the same mapping/rig/session identity, distinguish confirmed movement from jitter, keep hard invalidation for changed geometry/session and relevant intervention, and log every invalidation reason. Test outage plus occlusion through approach/descent/release and require fresh acquisition for the next row.
- Validation: 57 JavaScript geometry/planning/cue tests, 68 Python owner/relay/calibration/frozen-client tests and the fake-relay bridge smoke suite passed. JavaScript/Python syntax and git diff whitespace checks passed. No hardware movement commands issued. Activation pending hub restart.
- Activated after rechecking `overrun` and both arms disconnected/disabled/pump-off. Verified port-8000 PID 19567 and its working directory/interpreter, stopped only that hub and started PID 20051. Green build `1e41010072ba49acaa206dfd7bfa22cc`, Purple `cf9db2dafbbd45a5acc3ad435a199bb2`; both serve the tested controller and bridge, 440 mm nominal config and 430 mm published working envelope. Camera is ready at 3840x2160; no startup tracebacks. Game is setup. Green calibration readiness correctly waits for the calibrated connection identity to be restored after restart (saved en14 versus empty unconnected relay identity); no automatic arm connection or enable was issued. Players must refresh and reconnect.

## 2026-10-06 — Preserve acquired cue endpoints through camera mapping outages

- Applied the approved cue correction in the shared physical controller. A transient unavailable/expired mapping now holds the approach through the existing stop API while retaining independent copies of its acquired tag, robot base and offset position. After fresh mapping returns, matching epoch/scope/calibration/orientation resumes the current step without seeing the occluded tag again. Changed identity, relevant player intervention or newer qualified contradictory evidence invalidates explicitly. Single unqualified displaced detections no longer erase acquisition.
- Acquires each source once after destination validation, reusing its resolver through row preflight, hover, descent and pre-vacuum verification; removes the former duplicate source acquisition immediately before movement. Destination acquisition is likewise retained through its approach, descent and pre-release verification. The next row still starts a new acquisition; there is no cross-row or cross-run position grant. Supporting lower-marker sightings and visual placement confirmation semantics remain unchanged.
- Interruption causes are latched across asynchronous recovery so a quick camera recovery cannot erase the reason for a hold. Simultaneous manual intervention takes priority over an automatic camera hold. Added explicit retained-position wait text and acquired/invalidated/motion-held/map-recovered diagnostics with phase reasons. Existing physical-session/Stop/operation ownership and pump checks remain enforced.
- Regression coverage now executes the real queue loop, resolver, motion retry wrapper and pre-pump checks with fake camera/relay I/O. It injects outages during source hover/descent and target hover/descent, keeps both physical tags hidden, verifies unchanged pump state during hold and exactly one release, then tests fresh acquisition on the next row. It also covers expiry/SSE outage, hidden-tag preflight handoff, unqualified jitter, changed mapping identity, Stop/session/operation loss, and manual override priority.
- Validation: 66 JavaScript tests and 36 Python cue/evidence/diagnostic/frozen-client tests passed; fake-relay bridge smoke and controller syntax/whitespace checks passed. No physical motion commands issued. This controller-only change uses the existing no-store route, so activation verification does not require a hub restart.
- Activation verified by authenticated read-only requests: both Green and Purple no-store controller routes exactly match the tested file (SHA-256 prefix `b1f9e21460518843`). No restart was needed; game remained in setup. Both team fake-relay bridge smoke suites passed. The final message-only update also passed all 49 cue-related JS tests, and recovery now clears the stale waiting text when resuming. Players must refresh/reconnect to replace their already-loaded controller.

## 2026-10-06 — Immediate cue pause, positive failed-pickup detection and outer destinations

- Pause was gated by new-motion readiness/height limits and the movement wrapper only interrupted for intervention/camera changes. Pause/Stop now retain authenticated session checks while bypassing new-motion gates; Pause interrupts each automated motion stage through the existing hold API, preserves suction and resumes the retained stage. A generation counter captures quick Pause/Resume between feedback polls. A paused camera wait displays Paused.
- Once the pickup lift completes, a fresh visible sighting of that same source Atom before release latches a failed pickup. Periodic acquisition and SSE receive paths both observe evidence, so a brief sighting between 750 ms acquisition polls is not lost. This stop-only observation does not overwrite retained coordinates or grant acquisition. The runner holds before reporting, preserves the pump, skips release/later rows and retains a player-visible failure. Cached pre-lift sightings, lower fixed tags, other Atoms and sightings after release do not trigger it. No automatic retry or placement claim is added.
- Read-only live geometry placed Green #40 at 426.7 mm, #47 at 426.1 mm, #45 at 438.0 mm and #42 at 442.7 mm. The user approved a small inward placement offset for #42. The owner envelope expands uniformly from 430 to 439 mm, retaining the nominal 440 mm limit, base/rear exclusions and relay path/Z checks. Flat 30–59 destinations within 5 mm of the outer edge may project radially to 0.1 mm inside the actual owner polygon; the selector shows the offset. Source Atoms and manual coordinates are unchanged. Forward robot geometry is authoritative for both selection and motion, avoiding a second rejection from the sampled screen outline.
- Validation: 77 JS tests across geometry, motion, recovery, selection, UI, height and diagnostics, 40 Python safety/evidence/cue/diagnostic/client-build tests, and both team fake-relay smoke suites passed. Added measured 40/42/45/47 fixtures, full-stage Pause/Resume tests, post-lift failure/retained-suction checks and a brief SSE sighting regression. No physical motion commands issued. Syntax and whitespace checks passed.
- Activation pending: the last live check showed a running game with both arms disconnected, disabled and pumps off. Owner constants and frozen mobile bundles require a hub restart; request approval because restarting ends this game. Existing pages must refresh/reconnect afterwards.
- User approved restart. Verified the current port-8000 listener belonged to this workspace, gracefully stopped PID 20484 and started PID 21362; unrelated listeners were untouched. Green build `a2cdd87effd34324be29efd147a6a7b9` and Purple build `5f26e562df614caa84fb08bfb3d2a6e3` match the tested frozen bundle byte-for-byte; both no-store controller/bridge responses also match. The live owner publishes 439 mm working reach, 440 mm nominal and 220 mm base minimum. Game is setup and both arms remain disconnected/disabled/pump off. Camera is open at 3840×2160 with fresh frames and no error; zero hub startup tracebacks. Green readiness awaits restoration of its calibrated arm connection after restart; no automatic connection, enable or movement was issued. Players must refresh and reconnect.

## 2026-10-08 — Cue Play feedback and stable transport controls

- Play retains unchanged text nodes, disabled state and accessible attributes through live updates. Accepted input immediately shows Starting; shared admission checks report busy, switching, unavailable, incomplete-row and endpoint refusals without silently returning. Numbered pointer/activation diagnostics preserve evidence of repeated taps without issuing additional motion commands.
- Stop visibly reads Stop arm for idle/stopped/completed cues and Stop cue while active. Its existing physical hold/pump-off path remains available with a session; virtual Stop does not claim pump-off behavior.
- Browser verification exposed a separate receipt bug: JSON string equality rejected identical cue rows whose object fields were reordered by the server. Row comparison now checks the ordered piece/destination values, and outgoing rows use canonical fields; changed or malformed receipts still cannot start a cue.
- Validation: 66 JavaScript checks, 4 frozen-client Python checks, syntax and whitespace checks passed. The isolated virtual browser reproduced the receipt rejection before the correction, then started from one click and showed the correct Stop labels. Compact screenshot: /tmp/cue-controls-verified-compact.png. Fixture server and tab were closed. The physical-controller lost-tap cause is not proven by the virtual receipt reproduction.
- Activation pending: read-only live checks show a running physical game with Green connected/enabled and pump off. Frozen mobile bundles require a hub restart, which would discard that game. No live movement, game reset or hub restart was performed.

## 2026-10-08 — Reusable physical cue preparation and restart feedback

- The user reported that deleting and recreating a cue makes it start. Fresh Play previously skipped cue_set preparation for unchanged saved rows, although the runner reads separate controller selects. Extracted that preparation and run it on every fresh Play: refresh mapping, recheck session/readiness/ownership, rebuild the hidden queue, and disable looping. Resume keeps its existing step. Bridge receipt comparison now uses ordered piece/destination values rather than JSON field order.
- Confirmed a separate silent no-op: Stop clears cue-running before the previous runner has finished cleanup, so Play could return success without starting anything. It now explicitly reports still stopping. Cue set/play no longer clear the previous runner's abort flag; only an actual new run clears it.
- Added fake-relay checks for three unchanged starts after completion/Stop, restoration of drifted hidden selects, reordered receipt fields, unchanged paused resume, cleanup refusal with abort preservation, and cancellation during asynchronous start validation. The drift/reordered-receipt reproduction failed before the patch and passes after it. A test using the real runner and capture path executes the same 100-to-42 cue twice, reacquires 100 at a changed camera position, and requires distinct operation IDs and two releases.
- Validation: 66 cue/recovery/selection/height JavaScript tests and both team bridge smoke suites passed; bridge syntax and git whitespace checks passed. Authenticated read-only checks verified both no-store bridge routes match the tested file (SHA-256 prefix `9ad9b641a585ce73`). No physical movement, game reset or hub restart was issued.
- The server now serves the earlier UI fix (Green build `6cf3e4e0803a45d2bc68a3e1741f3b75`, Purple `07404aefe6a64901bc67b8ca1cb26cb9`), but the latest phone diagnostics still identify old build `3d9014c1ce744fefbe944f774aa56ce7`; Connect did not reload it. Logs show the same 100-to-42 cue starting at 12:41:53 and 12:42:57 Tallinn, which rules out a run-once rule. The exact earlier lost-tap cause remains unproven. Refreshing the player page and reconnecting is required to load the available fixes; live physical verification remains pending that refresh.

## 2026-10-08 — Preserve acquired pickup through a transient fixed-marker contradiction

- Read-only diagnostics for run `d4df5fad51a94baa815c7eba5dfa711a` show the last 100-to-40 cue acquiring its source at 12:57:55 Tallinn. At 12:58:00 during hover and 12:58:47 during pickup descent, a brief mapping hold was followed by `mapping_changed`, discarding the retained source and waiting for the now-hidden 100. No pickup timeout failure was logged. Earlier manual interventions correctly required reacquisition. The historical diagnostics do not distinguish which map-identity component changed.
- Reproduced an overly eager map-reset path in the camera owner: a single fixed-marker detection more than 0.01 from its stored position immediately rotated the entire map epoch. The owner now marks mapping unavailable immediately while retaining its epoch and coordinates. Three distinct consistent observations over at least 0.5 s confirm movement and reset the map. Return of the suspect marker to its original position restores the same map; missing evidence alone cannot release the hold. Camera identity, correction or dimensions still invalidate immediately. Outages clear tentative confirmation samples. No robot-feedback, camera-frame or initial acquisition freshness deadline was extended.
- Added pending fixed-marker IDs and epoch change reasons to the camera-map envelope. Controller invalidation diagnostics distinguish camera/map epoch, layout, arm calibration and camera view, and identify a confirmed moved fixed marker when available. The existing operation-scoped pickup resolver handles same-map recovery without seeing the hidden Atom again.
- Validation: 75 Python tests (camera targets, board tracking/preview, mobile gateway and frozen clients), 67 JavaScript cue/recovery/selection/height tests, and both team fake-relay smoke suites passed. New Python cases failed before the correction. An integration regression feeds real Python camera-owner envelopes into the actual JS cue runner: fixed-marker outlier during descent, safe hold, same-map recovery with 100 hidden, unchanged pickup coordinates and exactly one release. Syntax and whitespace checks passed. Tests issued no physical movement commands.
- Activation: the game naturally reached `overrun` before deployment. Rechecked the ended phase, both pumps off and Green idle/stationary before replacing only the verified workspace hub PID 28166 with PID 28620 using its existing Miniconda interpreter. Saved the ended-game diagnostic snapshot privately at `/tmp/cue-occlusion-ended-game.json`. Read-only verification confirms the new owner fields, ready camera mapping, both arms disconnected/disabled/pump-off, and both controller routes matching SHA-256 prefix `dac7d960de78fc5e`. Green build `44a54deb49264015b3baacc19e8f63d3`, Purple `f80c27dcc39c4c1082e884c8d1f9097d`; no startup tracebacks or module-load failures. Game is setup. Players must refresh/reconnect; a new physical pickup has not been exercised by this task.

## 2026-10-08 — One-tap Clear view cue row

- Added **+ Clear view** under each placement row for both teams. One tap inserts a separate `← Clear view · 5 cm` row immediately afterwards. The row needs no coordinates; duplicates/orphans are rejected, the 32-row limit applies, and deleting the placement also deletes its dependent clearance. Saved cues, semantic receipts, editor synchronization and the physical bridge retain mixed placement/action rows. Every fresh physical run receives the full typed program rather than losing action rows in the legacy placement selects.
- After release and lift, physical clearance requires a measured pose and pump off. It converts phone-view left into a calibrated XY direction, normalizes the displacement to exactly 50 mm, and uses the existing guarded planner and confirmed-arrival path at travel height. Fresh Play captures the phone's 0°/180° view. Pause and motion interruption retry the same target; unsafe offsets fail with a row error. Camera confirmation remains based on camera evidence. Virtual practice uses 50 native board units through its existing IK path.
- Validation: 73 JavaScript cue/selection/recovery/height checks, 36 Python cue/client/team checks, and both team fake-relay bridge suites passed. Coverage includes typed capture, row persistence/removal, rotation and calibrated distance, release-before-clear ordering, reach rejection, and pause without repeated displacement. Isolated browser runs completed placement plus clearance for Green and Purple and verified portrait/landscape layout; final screenshots are `/tmp/clear-view-{green,purple}-{844x390,390x844}.png`. Controller inline script, JS syntax and whitespace checks passed. No physical motion was exercised.
- The user authorized interruption. The port-8000 workspace hub was already offline; the unrelated port-8011 hub was left untouched. Started PID 29455 with the existing Miniconda interpreter and private `/tmp/clear-view-hub.log`. Verified both controller and bridge routes match local bytes, both frozen mobile bundles include the final JS/CSS, and startup reports no traceback/module-load failures. Green build `60e7afdcf2af4bdbbaae90fdd172261a`; Purple `76cacb97dbfc4ed4987e5565294c18af`. Game is setup; both arms disconnected/disabled/pump off. Refresh and reconnect to load the new controls.

## 2026-10-08 — Default Clear view and editable destinations after completion

- New cue placements now include Clear view automatically. Its minus button removes only that action, and the existing + Clear view restores it. Saved opt-outs are preserved instead of silently adding motion to an existing cue. Adding a placement reserves both rows within the 32-row limit.
- Live inspection of run `24749a467e2b4803ae0b3c5195257489` found the camera owner holding on conflicting fixed-marker detections for 40 and 48, returning an empty tag list. The editor derived its entire destination list from those camera candidates, leaving only the previous selected ID. It now also lists the current level's destination IDs and opposing assigned Atom IDs, marked waiting for camera when unmapped. These are selection IDs only: no stored coordinates, fabricated detections, or relaxed motion checks. Play explains a camera hold while editing remains available. An additional reproduction showed that a native picker left focused after closing could keep the emptied list through recovery; focus/pointer/keyboard opening now refreshes its options without mutating an already-open picker during SSE updates.
- Validation: the three new selection/default regressions failed before the patch and passed after it. All 77 cue selection/feedback/recovery/height JS checks and 4 frozen-client Python checks passed. The dedicated browser suite passed for both teams: default/remove/restore, portrait/landscape, three successive target destinations, and persisted opt-out after reload. Syntax and whitespace checks passed. The older general cue browser suite completed placement-only pause/resume and both placements, but its broader layout assertions still report a pre-existing Fine tune/pump overlap at 568×320; no height/pump layout code was changed in this task. Updated its stale paused-height assertion and parent/child overlap comparison to match previously implemented controls.
- Activation used the user's existing interruption authorization. By restart time the game had reached overrun; verified both pumps off and the connected Green arm idle/stationary. Saved a private pre-restart snapshot at `/tmp/cue-dropdown-pre-restart.json`, replaced only this workspace's verified hub PID 29699 with PID 30213 using its Miniconda interpreter, and left port 8011 untouched. Both served mobile bundles exactly match the final JS (SHA-256 prefix `5c145e0265dd80e3`); Green build `d2e8750f7c0648b99cfaa5bb32fe52b8`, Purple `a65b7696376a472293f399ad5c388185`. Camera mapping is ready with 16 tags, game setup, both arms disconnected/disabled/pump off, and no startup traceback/module-load failure. Refresh/reconnect required. No physical motion commands issued by this task.

## 2026-10-08 — Unblock image-click recovery during a tag-map hold

- Live run `fc413f4b8e6c49aeae9c2a985d59ed4e` acquired 100 and destination 42, then held during target hover when fixed marker 54 became disputed. The subsequent user image taps were `cue_waypoint` commands rejected by the bridge's full tag-map readiness gate. The camera view itself was ready, with ten matching board markers and valid Cal 2 safety revision 3. Height still worked because it uses measured robot XY and does not depend on that tag map.
- Replaced the waypoint's tag-map gate with corrected-image readiness: ready view, finite dimensions and alignment matrix, valid server/frame times, and frame age plus local receipt age no greater than 1.5 seconds. Point conversion still uses existing Cal 2 calibration and all current ownership/session, arm feedback, reach and path checks. An active or paused cue still uses the existing override owner, waits for any atomic pump operation, lifts before lateral motion and preserves suction/pause state. No tag-map status, retained evidence, or autonomous acquisition policy was relaxed.
- The fake-relay reproduction failed before the patch and passes for both teams. Added stale/unavailable/malformed image and stale game-receipt rejection, plus recovery clicks during active/paused cues with suction on. Added a real override-function regression proving lift then image movement during a held map, no pump command, and no fabricated camera recovery. All 78 cue/recovery/selection/feedback/height JS tests and both bridge suites passed; bridge syntax and whitespace checks passed. No physical motion commands were issued.
- Both no-store bridge routes now match the tested file, SHA-256 prefix `3e90c0b82f1795c6`. No hub restart is needed or performed. Initially Green was idle with suction on, so no page refresh or disconnect was forced. A later read-only check showed both pumps off, Green still connected/enabled/idle, current game running, camera view ready and tag map still held. The player must refresh and reconnect to load the updated bridge; it permits recovery image clicks without claiming the underlying fixed-marker dispute is resolved.

## 2026-10-08 — Cyan cue pickup bullseye

- Cue playback now marks the selected movable piece with a separate cyan bullseye at its starting position. The existing final-destination bullseye/guides and actual-arm marker are unchanged. The pickup preview retains its position through occlusion, carrying, pause and camera wait, resets for the next placement or replay, and clears on Clear view, completion, Stop, mode/session/game changes. It scales with the existing viewport so its screen size stays constant. This is presentation-only state; robot commands and camera evidence are unchanged.
- Validation: four new renderer lifecycle tests and 32 related cue UI/selection/height tests passed, plus all four frozen-client tests. The isolated browser suite passed for both teams, verifying cyan source position/color, unchanged destination, pause, portrait/landscape views, three successive cue runs and saved Clear view opt-out. Visually inspected `/tmp/cue-pickup-green-844x390.png` and `/tmp/cue-pickup-purple-844x390.png`; fixture was stopped. Syntax and whitespace checks passed. No physical motion commands were issued.
- Activation used the existing interruption authorization after confirming the current game was overrun, both pumps off and Green stationary/idle. Saved private pre-restart state to `/tmp/cyan-pickup-pre-restart.json`, replaced only the verified workspace hub PID 30642 with PID 31296 using its existing Miniconda interpreter. Both served mobile JS bundles match the tested source (bundle SHA-256 prefix `7888ae9ee364d1cc`), CSS matches exactly and both pages contain the pickup SVG. Green build `7cd3be705df9447b99c9dbf6ca808037`, Purple `37ea44093fb54b86bcc3d14e9011f460`. Camera ready, game setup, both arms disconnected/disabled/pump off; no startup traceback/module-load failure. Players must refresh and reconnect.

## 2026-10-08 — Restore ArUco images on the calibration projection

- The user confirmed the projected gamefield showed only calibration numbers for both teams. The live marker endpoint returned a valid PNG. Reproduced the exact numbers-only display in an isolated browser with five existing event streams: Playfield's sixth HTTP/1 stream received area geometry, but all six marker requests stayed pending until another stream was closed. Number textures are generated locally, so they still rendered.
- Playfield now uses its texture loading manager to close only its own SSE stream while marker images are pending, then reopens the full-state feed after the batch settles. Failed image textures show an explicit status, are disposed and retried after three seconds. Numbers, marker IDs, both team layouts, crisp marker rendering and calibration ownership remain unchanged. No new robot-control or calibration-data path was added.
- The browser regression fails against the old fixture and passes against the repair for Green and Purple while five other streams remain open. OpenCV decoded all six codes 30–35 from each rendered screenshot; the test also injects a 503 image failure, verifies recovery, then switches the owned layout and checks the resumed feed moves the codes. All 19 calibration-display owner tests, JS syntax and whitespace checks passed. Visually verified `/tmp/calibration-green-verified.png` and `/tmp/calibration-purple-verified.png`. The isolated fixture was stopped; no physical movement or live calibration command was issued.
- The live no-store projection route exactly matches the repaired HTML (SHA-256 prefix `dae155f79c7644eb`). No hub restart is required or performed. The existing physical run `f708b53fe8a8442eb7ab21f49b57c175` remained running/playing during verification. Refresh the projected gamefield once, or let a newly opened calibration iframe load the repaired screen.

## 2026-10-08 — Pickup-only cyan marker and configurable Clear view

- Cyan now hides when the virtual arm holds the selected Atom, or when the physical controller completes its pickup lift and existing pickup-failure check. The bridge publishes that operation state explicitly. The renderer latches the preview hidden through release, pause and later sightings, then resets for a new row/run. Occlusion before pickup still retains the source marker; the final destination display is unchanged.
- Clear view now has selected left/right arrow buttons around an editable cm field, defaulting to 5 cm left. The minus button remains. Valid distances are 0.1–50 cm; invalid or empty inputs block Play. Typed rows and semantic receipts carry direction/distance through editing, persistence, simulation, the physical bridge and the existing calibrated controller. Legacy action-only rows normalize to left/5 cm, while changed settings reject an old receipt. Editing stays locked during playback/pause.
- Physical clearance converts cm to mm, applies the chosen direction in the player's 0°/180° view and calibrated camera orientation, and retains the existing pump-off, reach/path and confirmed-arrival checks. Pause/Resume retries the same target. Virtual clearance uses 10 native board units per cm. Neither path creates another pickup/release.
- Validation: 86 JS cue/selection/recovery/height/marker tests, 18 Python cue tests, four frozen-client tests and both team fake-relay bridge suites passed. The isolated browser suite passed for Green and Purple: cyan hidden during held-piece motion, default/remove/restore, invalid-input blocking, portrait/landscape fit, rightward 7.5 cm displacement, custom settings after reload, successive destinations and saved opt-out. Visually checked `/tmp/clear-view-configurable-green.png` and `/tmp/clear-view-configurable-purple.png`. Syntax and whitespace checks passed; fixture stopped. No physical movement commands issued.
- Activation used the prior interruption authorization after twice checking the ended game, both pumps off and Green stationary/idle. Saved private pre-restart state to `/tmp/cue-options-pre-restart.json`; replaced only the verified workspace hub PID 31617 with PID 32410 using its existing interpreter. Both teams serve the tested bundle (`1f203f1ff9939f73`), controller (`fd1c8c8ecdd9b111`) and bridge (`a1eb05bf88881bf0`); CSS matches. Green build `e9680baa2b5f46aca068a1d9cc332eb8`, Purple `d2257abc642b46eeb3bbb7e1c92979d9`. Game setup, camera ready, both arms disconnected/disabled/pump off, no startup traceback/module-load failure. Refresh player pages and reconnect.

## 2026-10-08 — Keep inactive calibration tags from interrupting a game cue

- Run `beca6b00f18d4f50ac761f91850e6ece` acquired destination 40 at 15:36:45 Tallinn and held during target hover at 15:37:00. No target timeout was logged. Live inspection found the camera and robot feedback healthy but the global cue map unavailable on a conflicting marker 30 detection. Marker 30 is not in this level (core 38, sockets 40–55). The old camera cache included calibration markers in the same conflict/epoch policy as game targets, so an irrelevant decode could freeze a previously acquired hidden destination indefinitely.
- Added owner-scoped cue maps keyed by the active layout and its fixed IDs. The mobile facade derives those IDs from the actual level or calibration display and verifies the owner's scope acknowledgement. The existing board sampler learns each scope independently; filtering occurs before conflict detection, not just when presenting the tag list. Four recent scopes are retained; new layouts cannot inherit old coordinates. No second hardware read or robot-control path was added. Active-marker conflicts, stale/unavailable camera evidence, calibration changes, pickup failures and motion limits retain their existing holds.
- Validation: 95 Python owner/gateway/camera/client/team tests and 87 JS cue tests passed. A real Python camera-owner → JS queue-runner regression reproduces the old hold and epoch reset on repeated false 30 detections, then completes 100 → 40 with 40 hidden for 72 seconds under the scoped policy: no hold, unchanged acquired destination, suction retained during transport and exactly one release. Additional tests cover scope registration through the real sampler, malformed requests, acknowledgement mismatch, layout changes, bounded cache and active-marker/camera failure rejection. No physical motion was issued by tests.
- Activation used the existing interruption authorization after the game reached overrun. Twice verified both pumps off and Green idle/stationary, saved private pre-restart state at `/tmp/cue-layout-pre-restart.json`, and replaced only verified workspace hub PID 32570 with PID 32983 using its existing interpreter. Both teams now receive the same ready scoped map, fixed IDs 38 and 40–55, no pending conflicts and no mapping error. Camera ready, game setup, both arms disconnected/disabled/pump off, no startup traceback/module-load failure. Both fake-relay bridge suites and whitespace checks also passed. Refresh/reconnect for the next game; no live physical pickup was exercised.

## 2026-10-08 — Validate the board independently during an active-marker occlusion

- Run `cb387ce9d09d456992227db2974e1957` acquired 49 at 16:02:33 Tallinn and held at 16:02:36. The live map retained a conflicting 49 detection while the camera still matched 13 other board markers. Reproduced the indefinite hold after one displaced detection followed by absence. The preceding layout filter correctly excludes calibration IDs, but did not address a suspect detection of an active destination.
- Shared corrected-camera geometry measurement between camera presentation and cue tracking. Cue fixed markers now require valid convex corners and retain their own initially learned size, edge/diagonal proportions and position. Later geometry changes beyond a 1.15 ratio are isolated before motion confirmation. Per-marker references preserve deliberately different marker sizes and prevent gradual drift from redefining the original board pose.
- A suspect marker is withheld from new acquisition, preserving its original coordinates/timestamp privately. The current cue can retain its already acquired endpoint only when four or more independent, stable, fresh markers verify the unchanged board around every suspect position. Verification requires three distinct observations over 0.5 s within 0.004 of frozen references, at most 0.75 s old, plus a containing convex hull with normalized area >=0.02 and spans >=0.15 on both axes. Missing, clustered, collinear, distant, shifted or stale anchors revoke authority. Three consistent geometry-valid displaced sightings still reset the map. Camera identity, correction, dimensions, feed freshness, existing reach/path checks and pickup-failure detection remain authoritative.
- The envelope exposes verification diagnostics and quarantined IDs/reasons/occupancy without making their coordinates available for new approaches. The controller explains new-acquisition waits and still stops for another Atom occupying a quarantined destination. Existing source/destination acquisition, pause, transport, release and Clear view execution paths remain in use.
- Validation: 117 Python camera/board/gateway/client/team checks, 89 JS cue checks and both team fake-relay suites passed. The real Python owner → JS queue regression carries 100 to the original 49 position through repeated bad-size detections and 63 seconds of occlusion, then releases once and performs Clear view with no camera hold. Negative coverage includes anchor loss/recovery, valid confirmed movement, malformed geometry, same-perimeter distorted shapes, fresh timestamps, slow drift, coverage failures, new acquisition and occupancy. Syntax/whitespace checks passed. Tests sent no physical motion commands.
- Activated with the user's existing interruption authorization after twice verifying both pumps off and Green idle/stationary. Saved private pre-restart state at `/tmp/cue-49-pre-restart.json`; replaced only the verified workspace hub PID 33067 with PID 33655 using its existing interpreter. Both teams expose the new quarantine/verification fields, ready camera maps with 16 tags and no pending conflicts. Both served controllers match SHA-256 prefix `cc6ccf6e566bf5fd`. Game is setup, camera ready, both arms disconnected/disabled/pump off, and no startup traceback/module-load failure. Refresh/reconnect required; no live physical cue was executed by this task.

## 2026-10-08 — Show camera tracking before robot/controller startup completes

- Live analysis found the camera already tracking in setup (14 visible field markers, 8.4 detection FPS, 157 ms frame age) while both arms were disconnected. Physical marker labels previously came only from `MobilePhysicalArm.arm()`, which returns null until fresh robot feedback and a usable pose are available. Reproduced valid detections being hidden solely because robot feedback was unavailable.
- Physical labels now read the existing versioned corrected-camera cue map directly. Map readiness and the 1.5 s frame deadline include local receipt age; movable labels require a visible sighting no older than 0.5 s. Fixed memory remains displayable only under a fresh valid map. Invalid, held and stale maps clear labels. This is presentation only: it does not populate arm state, create pickup evidence or change movement admission. Calibration and virtual marker sources are unchanged.
- Initial state delivery, live updates and physical controller discovery now precede renderer loading, so camera presentation does not wait for the renderer. The renderer paints the latest state after loading; feed recovery remains active during renderer delays/failures.
- Validation: 48 JS tests (including nine new startup regressions), 19 Python client/team tests, both fake-relay bridge suites and camera-notice/physical-control smoke checks passed. Updated two existing smoke harnesses for previously added cue helpers. Real-browser tests for both teams deliberately delayed controller discovery and renderer delivery: labels were visible with null arm state, expired on stale camera data, recovered with the feed, and sent no robot commands. Existing two-team virtual Clear view/cyan-target flows also passed. Inspected `/tmp/tracking-startup-green.png` and `/tmp/tracking-startup-purple.png`; syntax and whitespace checks passed.
- Activated after twice verifying setup, no run, both arms disconnected/disabled and both pumps off. Saved private pre-restart state to `/tmp/tracking-startup-pre-restart.json`; replaced only verified workspace hub PID 33655 with PID 34190. Both teams serve the exact tested bundle (SHA-256 prefix `084ab4a47c23fd1a`), both camera maps are ready with 16 mapped tags, game remains setup, arms remain disconnected/disabled/pump off, and startup has no traceback/module-load failure. Refresh player pages to load the new bundle; no physical motion was issued.

## 2026-10-08 — Smooth red arm tracking and erase the completed trajectory

- The actual-position bullseye and its guides now use the existing cascaded indicator smoothing on a roughly 30 Hz animation clock, instead of jumping directly between robot feedback samples. Raw feedback, commands and arrival decisions remain authoritative. Session, revision, coordinate-space and stale-feed transitions reset presentation state. Green destination and cyan pickup markers retain their existing behavior.
- Added a dashed red remaining trajectory. The existing physical controller publishes its checked plan through an optional read-only drawing callback; the bridge samples robot-space segments before camera projection, retaining detours and calibrated curves. The virtual owner supplies a sampled route from its actual bounded joint stepping. Display progress advances monotonically only near the planned line, erases crossed segments and hides at arrival, stale feedback, stop or invalidation. Drawing failures cannot alter motion commands.
- Validation: 134 JS tests and 48 Python tests passed, including smoothing, route clipping, stale/session resets, virtual trajectory accuracy, controller callback isolation, cue recovery and existing target behavior. Both fake-relay bridge suites and physical presentation smoke passed. Real-browser tests recorded 31/26 distinct red-marker positions from 9/8 feedback positions for Green/Purple, verified progressive erasure and disappearance at arrival, and produced inspected screenshots at `/tmp/arm-trajectory-green.png` and `/tmp/arm-trajectory-purple.png`. Both-team Clear view/cyan-target cue flows also passed. Syntax and whitespace checks passed; tests issued no physical movement.
- Activated after the game reached overrun, checking both pumps off and Green idle/stationary against two fresh feedback samples. Saved private pre-restart state at `/tmp/arm-trajectory-pre-restart.json`; replaced only verified workspace hub PID 34254 with PID 34750 using its existing interpreter. Both teams serve the exact tested bundle (SHA-256 prefix `ce3f507b0873bf96`) and controller; cameras and cue maps are ready, the game is in setup, arms are disconnected/disabled, and startup has no traceback/module-load failure. Stopped the isolated port 8134 test fixture. Refresh/reconnect to load the update; no live physical cue was exercised.

## 2026-10-08 — Remove recurring slowdown between red-marker feedback packets

- The previous cascaded low-pass filter provided intermediate frames but treated each sparse pose as a stationary endpoint. At 500 ms feedback intervals, a constant 100-unit/s input produced repeated displayed speeds from 14.04 to 208.01 units/s. The physical controller polls at 500 ms and the bridge republishes at 200 ms, so counting changing frames alone did not detect this defect.
- Replaced XYZ display easing with bounded, timestamped position playback. The physical bridge preserves the relay measurement's `last_feedback` as `position_at`; duplicate publications cannot pretend to be new measurements. The virtual arm timestamps its own pose snapshot. Linear interpolation follows source time with 750 ms physical / 250 ms virtual buffering, maintaining steady speed through normal packet jitter without predicting unmeasured movement. Stops and reversals follow measured samples; underruns hold and resume without a catch-up jump. Stale/session/visibility changes reset playback; invalid timestamps fall back to the current raw pose. Robot commands, arrival checks, green/cyan targets and dashed-route progress remain unchanged.
- Validation: 78 JS tests and 49 Python tests passed, plus both fake-relay bridge suites and physical-control smoke. Added regressions for constant speed, jitter, duplicates, old packets, stops/reversals, missing timestamps and underrun recovery. Both real-browser player views showed 100.00–100.00 units/s under jittered 500 ms synthetic physical feedback, with 34/36 displayed positions versus 7/8 virtual feedback positions and correct path disappearance. Native touch checks passed for both teams, both rotations, normal/fine X/Y and height. Updated that test to wait for the rendered indicator instead of advancing its playback clock. Syntax and whitespace checks passed; no physical motion was issued.
- Activated after the current game reached overrun and two fresh checks confirmed Green stationary/idle and both pumps off. Saved private state at `/tmp/arm-playback-pre-restart.json`; replaced only verified workspace hub PID 35885 with PID 36473 using the existing interpreter. Both teams serve exact bundle SHA-256 prefix `e178a477bff59f03`. Game is setup, both cameras/cue maps are ready, arms are disconnected/disabled/pump off, and startup has no traceback/module-load failure. Removed the isolated test fixture. Refresh and reconnect to load the fix.

## 2026-10-08 — Simplify cue dropdowns and lighten the cue panel

- Cue piece and destination options now show only their ID numbers; removed cached, missing, camera-wait, outside-reach and inward-offset text from option labels. Existing disabled choices, candidate metadata and movement validation remain in place. Moved the live cue status message immediately above the bottom transport buttons. The panel background is black at 20% opacity, matching 80% transparency without fading its text or controls.
- Validation: all 32 existing cue selection/start-feedback tests passed after updating label expectations. Real-browser checks passed for both teams at 844×390, 390×844 and 640×320: numeric labels, status above transport, visible buttons, black background alpha 0.2 and full-opacity content. Inspected settled screenshots in `/tmp/cue-panel-{green,purple}-844.png` and `/tmp/cue-panel-green-390.png`. Syntax and whitespace checks passed. No physical motion was issued.
- Activated using the earlier interruption authorization after two fresh checks confirmed Green idle/stationary and both pumps off. Saved private state at `/tmp/cue-panel-pre-restart.json`; replaced only verified workspace hub PID 36727 with PID 37072 using its existing interpreter. Both teams serve the exact updated JS bundle (SHA-256 prefix `3634da8e894fcb7f`), CSS and new status/button ordering. Game returned from running to setup, both camera/cue maps are ready, arms are disconnected/disabled/pump off, and startup has no traceback/module-load failure. Stopped the isolated fixture; refresh/reconnect required.

## 2026-10-08 — Keep fresh ArUco detections visible during cue-map holds

- Player diagnostics for run `2c0e4eeb021548bc850b31e9bd5fd120` recorded camera-map holds during source hover/pickup lasting approximately 151 ms and 193 ms before recovery. The player renderer required the entire cue target map to be ready and otherwise removed every ArUco label. Independent live sampling found fresh camera evidence (100 samples, maximum frame age 408 ms), while fixed IDs 38/54 entered quarantine. Delivery diagnostics showed no unavailable generated states or stream errors in that run. This established a display blackout path from brief acquisition-map validation holds, without requiring the camera itself to stop detecting.
- The mobile facade now carries the existing owner's `photon.board.camera-markers` v1 envelope as `mobile_camera.tracking`, preserving frame timestamps and adding a projection timestamp. Current detections remain available even if level alignment fails. Players retain valid cue-map labels and supplement them with independently fresh detections during holds. Fixed memory still requires a ready map; malformed/stale inputs and expired movable sightings disappear. No held-map poses are cached, no extra camera sampler was added, and display evidence cannot clear a hold or authorize movement.
- Validation: 29 JS tests, 57 Python tests, persistent-video/camera-notice smoke checks and both real-browser startup/tracking regressions passed. Browser coverage confirms both teams keep visible labels through cue-map and alignment holds while motion remains unavailable, and still expire/recover on true feed staleness. Source/candidate validation and calibration/virtual paths retain their existing behavior. Syntax and whitespace checks passed; tests issued no physical motion.
- Activated using existing interruption authorization after two fresh checks confirmed Green idle/stationary and both pumps off. Saved private state at `/tmp/aruco-display-pre-restart.json`; replaced only verified workspace hub PID 41645 with PID 42120 using the existing interpreter. Both teams serve exact bundle SHA-256 prefix `751a47801ea2ced5` and publish ready independent tracking with 15 current detections. Game is setup, camera/cue maps ready, arms disconnected/disabled/pump off, no startup traceback/module-load failure. Stopped the isolated fixture. Refresh/reconnect required; no live physical cue was exercised.

## 2026-10-08 — Align red-marker stops and tighten fixed-target activation

- The previous 750 ms physical display buffer explains the marker continuing after the arm stops. Mobile bridge controllers now reuse the existing non-overlapping status poll at 100 ms, immediately publish accepted feedback and interpolate with a 150 ms physical buffer. Ordinary controller polling stays at 500 ms. Additive `position_settled` telemetry flushes display playback to the actual measured position: two fresh idle XYZ poses 60–350 ms apart must agree within 0.05 mm per axis, with unchanged relay session and motion epoch. Idle mode alone is insufficient. The virtual owner marks actual joint arrival. Duplicate/old measurements cannot invent or replay a stop; presentation never finishes toward an unmeasured goal or changes motion authority.
- Run `2c0e4eeb021548bc850b31e9bd5fd120` placed 100 at 47/socket_08 at simulation time 432.851, followed by repeated replenishments. The later saved camera positions were 100=(0.6301,0.4915), 47=(0.6801,0.4928), approximately 0.050017 apart. Fixed-target activation uses camera proximity plus 0.55 s dwell with an available arm and pump off, without requiring a completed cue movement. These positions are consistent with camera jitter crossing the old 0.05 boundary. The owner now uses 0.04, a 20% smaller radius; Atom-on-Atom cover retains its independent 0.05 overlap radius. Arm reach and turret firing range are unchanged.
- Validation: 37 JS tests, 104 focused Python tests, both team fake-relay bridge suites and physical-control smoke passed. A real Board-to-Game regression reproduces stationary 100 activating 47 with the old radius and rejects it under the new radius, while accepting a closer placement. Both real-browser player views maintained 100.00 units/s under jittered 100 ms synthetic physical feedback and stopped without a display tail at the measured mid-route endpoint; virtual routes erased correctly (34/32 displayed positions versus 9/8 feedback positions). Poll tests verify no overlapping requests and lock recovery after errors. Syntax/whitespace checks passed. A broader framework run also passed 47 tests but retains one unrelated existing failure: its extraction test expects a literal Board preview URL that the current Y presentation has already replaced with multiplexed SSE. No physical movement was issued.
- Activated while the game remained in setup, after twice checking both arms disconnected/disabled and both pumps off. Saved private state at `/tmp/arm-endpoint-pre-restart.json`; replaced only verified workspace hub PID 42120 with PID 42662 using its existing interpreter. Both teams serve the exact tested bundle (`d7af1b51e1d2c338`), controller and bridge. After camera warm-up, camera/cue mapping is ready and the live Board publishes placement distance 0.04. No startup traceback/module-load failure. Stopped the isolated port 8134 fixture. Refresh player pages and reconnect; physical endpoint timing still needs observation during the next actual move.

## 2026-10-08 — Persistent Atom turret health and damage buff

- Implemented the approved Atom buff plan within Board → Game → shared SSE → Laser Tag Y. Fresh camera occupancy sustains green glow, 2× health capacity and 2× weapon damage. Removal preserves the health percentage; a confirmed return heals once to the doubled maximum. Camera loss, pump changes and reacquisition cannot manufacture healing or field repair. Covered-marker holds beyond 120 seconds and same-Atom recovery use Board-owned retained associations, invalidated by source/geometry changes.
- Game applies the multiplier once after upgrades/links, including direct, chain, splash and applied burn damage. L4 pairs share health and each firing position receives doubled damage. Committed Mortar/burn damage follows existing attack timing. Virtual pickup/release, relocation, core placement and the new Lift selected Atom control use Game-owned transitions. Both displays show a persistent marker-clipped green halo, two health rows and ×2; selected details show Health ×2 · Damage ×2.
- Validation: 15 Atom-specific tests, 205 Photon tests and 102 mobile Python tests passed, alongside the Atom/deployment renderer checks and a real-browser virtual fixture covering both views, all 28 L4 firing units, lift/return/transfer and reconnect. Updated replacement tests to include actual removal and legacy Z parity to compare unbuffed combat. Fixed the previously documented stale preview-URL extraction assertion to match the existing Board frame/SSE contract.
- Inspected browser screenshots. A 40-second two-display stress replay with 1,000 enemies, 16 primaries, 12 companions, active buffs, row transitions and peak effects measured median 60 FPS and minimum 44 FPS on both views, zero samples at/below 30 FPS, no long tasks/browser errors, and 88/88 assets loaded per view. Report/screenshots: `../output/atom-tower-buff/`; implementation details: `docs/ATOM_TOWER_BUFF_IMPLEMENTATION.md`.
- No physical movement or live-hub restart/reset was performed. Load the modules at the next planned hub restart/new game and refresh both displays. Actual camera/projector placement, hold, pickup and return timing still requires the supervised physical check.

## 2026-10-09 — Consolidate current development and prepare the GitHub checkpoint

**Trigger and evidence:** the user requested an up-to-date development log and
GitHub push. Reviewed the working-tree changes against `53bb9c8`, the existing
October 2–8 entries, current module specifications and implementation notes.
The detailed entries already recorded the recent work, but the opening summary
still described September's Green-only mobile implementation as uncommitted.
Updated that summary and the outstanding-work notes to reflect both players,
the committed baseline and the latest source behavior. Historical test counts,
live process IDs and activation reports remain dated evidence, not a claim about
the installation at publication time.

**Current checkpoint and retained decisions:**

- Calibration now derives per-arm heights from captured points, completes from
  saved evidence when offline, and permits explicit saved-rig/current-camera
  association with a precision warning. Reconnect, unlock and replacement
  connections invalidate stale motion intent; floor/ceiling limits remain
  relay-owned and connecting alone does not send a servo target.
- Webcam identity and frame freshness distinguish the selected device from a
  working connection. Shared corrected-camera markers, cue targets, Y preview
  frames and camera-only occupancy remain separate contracts. Size/geometry
  rejection and fixed-marker quarantine hold uncertain acquisition while
  independently fresh detections can remain visible. Covered-target validation
  requires spatially distributed, stable reference evidence.
- Physical cues refresh preparation on every new run and preserve an acquired
  endpoint only for the same operation and mapping identity. Pause, manual
  recovery, failed-pickup detection, repeated Play and cleanup refusals have
  explicit behavior. Clear view rows retain direction and distance; their
  movement uses the existing guarded planner. Cyan pickup markers, numeric
  selectors and transport feedback describe this same program.
- Mobile delivery diagnostics separate state generation, server transmission
  and player connection/input evidence. Tracking starts before arm/artwork
  readiness. Red position markers interpolate measured timestamps, settle on
  confirmed feedback and erase the completed checked path; this presentation
  does not generate motion coordinates or authorize movement.
- Core completion uses the opposing Atom's confirmed cover of the armed Atom.
  Atom turret occupancy now grants the Game-owned 2× health/damage bonus with
  one restorative heal per confirmed return. Board observation and Game combat
  state remain distinct, including L4 shared health, weapon timing and camera
  dropout recovery. Both Y views consume the same authoritative bonus fields.

**Verification correction:** the complete JavaScript run exposed a stale
`relay_z_limits.test.js` VM fixture using `radiusMin`/`radiusMax` after the
controller adopted `gameRadiusMin`/`gameRadiusMax`. Updated the fixture to the
current 220–439 mm owner bounds and checked the reach label alongside the
existing height-range, invalid-input and no-new-target assertions. No runtime
motion behavior changed in this publication pass.

**Fresh verification on October 9:**

- `/Users/kaur/miniconda3/bin/python -m unittest discover -s tests -p 'test_*.py'`:
  **666 passed**. The initial `.venv/bin/python` run passed 665 runnable tests
  but could not import the existing artwork smoke test because that environment
  lacks Pillow. Reran complete discovery with the existing project runtime,
  which already supplies Flask, NumPy, OpenCV and Pillow; all tests passed.
- `node --test tests/*.test.js`: **205 passed** after the fixture correction.
- `node tests/atom_buff_renderer.cjs` and
  `node tests/turret_deployment_renderer.cjs`: passed.
- `node tests/mobile_arm_bridge_smoke.cjs` for Green and
  `MOBILE_TEST_TEAM=purple node tests/mobile_arm_bridge_smoke.cjs`: passed;
  `node tests/mobile_physical_smoke.cjs`: passed. These use fake hardware.
- Native Focus Lock bundle signature verification and Git whitespace checks
  passed. No new real-browser stress replay or physical game was performed in
  this pass; the previous browser measurements retain their October 8 date.

**Publication scope:** code, shared assets, specifications, tests and this
journal on the existing `photon-engine-phase-4` branch, targeting its configured
`fork` remote at `kaurkallasz/manual-override`. The remote was verified at
`53bb9c8` before publication. As in the previous checkpoint, local hub
credentials/settings, live camera/arm calibration models, calibration lesson
data, projection session state and the robot command log stay outside the
commit. The existing native Focus Lock app update includes its new camera
inventory library and matching signature resources. Source and build script
remain in the same module.

**Operational status and remaining work:** this pass does not restart the hub,
reset a game, refresh a phone or issue a hardware command. October 8 records
the most recent Atom-buff browser/stress evidence in
[`docs/ATOM_TOWER_BUFF_IMPLEMENTATION.md`](docs/ATOM_TOWER_BUFF_IMPLEMENTATION.md).
That entry still calls for a planned restart/new game, refreshed displays and
supervised physical placement, long hold, pickup and return checks. Confirm
physical red-marker stop timing and both players' refreshed hosted/local
controls during that installation check. The existing Ponytail audit's legacy
module cleanup remains outstanding; this checkpoint does not claim a completed
repository-wide refactor or a hardware release.

**Ownership:** the user requested the log update and publication. OpenAI Codex
performed this consolidation, the test-fixture correction and publication
checks. Attribution for earlier implementation remains as recorded in its
original entry; this summary does not assign a new author to those changes.
