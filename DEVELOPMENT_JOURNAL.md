# HHH Gamemaster development journal

Last reconstructed: 2026-08-29, through commit `9d22a3a` plus the current uncommitted Laser Tag Z working tree on branch `codex/laser-tag-z`.

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

Laser Tag Z is the active tower-defence branch. It keeps the Laser Tag X camera, calibration, arm-visualization, relay, and safety boundaries, but gives the Gamemaster a separate server-authoritative defence simulation and an external game screen. Its editable Tiled map has sixteen fixed ArUco turret sockets, four movable Atom activators, four weapon roles, physical and virtual setup, durable turret placements, versioned force-field topology, a deterministic spatial core-ring objective, linked-group scaling, bounded dense waves, and a two-tag core purge finale. Several of those rules exist only in the current working tree and are not yet a committed baseline.

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

The Laser Tag Z changes after `9d22a3a` are still uncommitted, so Git supplies neither a human author nor an AI co-author. This reconstruction intentionally leaves their earlier ownership unresolved. OpenAI Codex is evidenced only as the author of the 2026-08-29 journal continuation and as the runner of its non-hardware test verification.

## Evidence of physical iteration

At the 2026-08-19 reconstruction, the local working setup contained 89 Laser Tag X JSONL runs from August 9–19, totaling 21,968 events, and 26 appended win records. That is historical evidence recorded by the earlier journal pass; those ignored local files are not present in the current checkout and were not recounted on 2026-08-29. The recorded event mix showed repeated real-system iteration rather than a purely paper design: release-pending and unresolved center transactions, activation blocks, late attribution, operation failures, reload recovery, and finally camera-authoritative decisions with matched operation attribution.

The repository now contains a focused 84-test Laser Tag Z suite, but the older physical-game stack still lacks a broad conventional automated suite. Specifications, runtime diagnostics, score/run logs, and physical trials therefore carry much of the Laser Tag X verification burden. Deterministic tests should still be added around state patches, recovery, event correlation, scoring, coordinate transforms, and multi-frame voting wherever hardware can be simulated.

## Known trade-offs and unfinished edges

- The browser owns high-frequency fusion state. Reload recovery can reconstruct activated targets and finale state, but not every per-tag sequence index, frozen pose, or historical binding.
- Server game state and the current diagnostic run are process memory. JSONL files are durable evidence, but a server restart does not automatically resume the previous run.
- Manual completion keeps an event running but intentionally weakens the claim that every transition was physically sensed; the diagnostic record must retain that distinction.
- Calibration is installation-specific data. Updating it is a real system change and should be paired with the physical setup and a dated journal entry.
- The current camera-authoritative rule depends on camera quality. It fails closed when corrected tracking or a valid spatial model is unavailable, and the gamemaster remains the recovery authority.
- Laser Tag Z's post-`9d22a3a` placement, topology, ring, scaling, Tesla, and combat-presentation contracts remain working-tree changes. They should not be treated as a stable release until committed and reviewed.
- Laser Tag Z server simulation state is process memory. The external screen can reconnect to the current process, but a process restart does not resume an in-progress defence run.
- Ordinary force-field links preserve activation history while the objective ring is spatial and order-independent. This is intentional, but diagnostics and the connection contract must continue to make the distinction visible.
- The deterministic ring solver explores spatial subsets from sixteen down to eight. Current pruning and tests keep the authored sixteen-socket level tractable; a materially larger socket set would require a new performance decision.
- Phase 4 deliberately retains Laser Tag Z's legacy map/parser as a read-only rollback fixture. It is duplicate code, not a second mutable authority, and should be removed only after a live installation trial confirms Photon Level startup, editing, restart, and in-run revision deferral.
- Phase 5 deliberately retains Z's direct Webcam/Calibration/Relay reader only for standalone operation when Photon Board is absent or disabled. Remove it only after a live trial confirms corrected marker freshness, arm-state propagation, pump-off gating, and Board failure diagnostics.
- Phase 6 deliberately retains the proven simulation in both Laser Tag Z and Photon Game. Photon Game is the new modular owner used by Y; remove Z's rollback copy only after production presentation parity and a complete live game prove the new Level → Board → Game chain.
- Phase 7 preserves Z's renderer logic in Y and its immutable runtime images in Photon Art, so visual behavior is duplicated during migration. Remove Z's rollback copy only after a full physical Game → Y trial proves camera-derived Board placement, all four weapons, ring/core completion, failure handling, and external display continuity.
- Photon Level and Photon Art intentionally hold separate copies of the normalized map images: Level needs local files for standalone Tiled editing, while Art owns runtime delivery. Stable asset IDs and automated coverage tests prevent this repository-boundary duplication from becoming an implicit file dependency.

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
