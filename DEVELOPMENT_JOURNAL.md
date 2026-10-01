# HHH Gamemaster development journal

Last updated: 2026-10-01, including the approved mobile progression/calibration implementation in the working tree after `2ea92b5`. Earlier entries preserve their original evidence and attribution. The original historical reconstruction was made on 2026-08-29 through `9d22a3a`.

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

The active tower-defence implementation is now the modular Photon stack: Level owns authored content, Board publishes physical observations, Game owns the simulation, Progress owns saved player progression, and Laser Tag Y presents the game. Laser Tag Z remains the rollback/reference implementation. Commit `cd00d97` records the progression, row barriers, L4 companions, and artwork described in the September 5–8 entries.

The current uncommitted continuation adds Green mobile LTZ as another presentation of that same Game, with a restricted hosted gateway and Game-owned virtual practice arm. Joint, Cartesian XYZ, Targeting, and Cue controls share session and progression checks. Mobile turret aiming also supports physical play through corrected-camera registration; that presentation does not acquire robot control. Shared enemy rendering now uses timestamped interpolation and bounded route guidance. These additions have focused deterministic coverage, but this journal update does not establish a deployed-phone or physical-installation release.

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
- The earlier Laser Tag Z and Photon work now has Git checkpoints through `cd00d97`. The mobile modules, gateway, virtual controls, camera presentation, and shared motion changes reviewed on September 22 remain working-tree changes; a checkpoint alone does not establish installation acceptance.
- Laser Tag Z server simulation state is process memory. The external screen can reconnect to the current process, but a process restart does not resume an in-progress defence run.
- Ordinary force-field links preserve activation history while the objective ring is spatial and order-independent. This is intentional, but diagnostics and the connection contract must continue to make the distinction visible.
- The deterministic ring solver explores spatial subsets from sixteen down to eight. Current pruning and tests keep the authored sixteen-socket level tractable; a materially larger socket set would require a new performance decision.
- Phase 4 deliberately retains Laser Tag Z's legacy map/parser as a read-only rollback fixture. It is duplicate code, not a second mutable authority, and should be removed only after a live installation trial confirms Photon Level startup, editing, restart, and in-run revision deferral.
- Phase 5 deliberately retains Z's direct Webcam/Calibration/Relay reader only for standalone operation when Photon Board is absent or disabled. Remove it only after a live trial confirms corrected marker freshness, arm-state propagation, pump-off gating, and Board failure diagnostics.
- Phase 6 deliberately retains the proven simulation in both Laser Tag Z and Photon Game. Photon Game is the new modular owner used by Y; remove Z's rollback copy only after production presentation parity and a complete live game prove the new Level → Board → Game chain.
- Phase 8 completed the deterministic authority cleanup after direct Z parity. Z remains unchanged as the requested rollback/reference implementation. A full physical Game → Y trial is still needed to prove camera-derived Board placement, all four weapons, ring/core completion, failure handling, and external display continuity before declaring an installation release.
- The former Level/Art normalized-image duplication is resolved: Level owns one shared authored content package for Tiled editing and runtime delivery, and Game forwards its versioned asset descriptor to Y.
- Mobile virtual geometry deliberately reaches the full map and is not calibrated physical MG400 geometry. Virtual practice does not award permanent progression; cues do not resume automatically after session loss.
- Hosted delivery and physical-camera alignment require installation checks beyond isolated fixtures. Bounded prediction cannot reconstruct unseen collisions or arbitrarily long network outages. Publishing a new frozen mobile UI requires a main-hub restart, which must account for the in-memory game run.

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
