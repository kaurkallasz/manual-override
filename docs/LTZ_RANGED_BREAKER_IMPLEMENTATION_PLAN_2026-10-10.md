**Ranged breaker implementation plan**

Prepared 10 October 2026. **Approved by the user, including tower-first targeting and shield-blocked arrows. Implementation and validation are recorded in [the implementation report](LTZ_RANGED_BREAKER_REPORT_2026-10-10.md). Production activation remains a separate idle deployment step; previous presets are preserved.**

Convert the existing breaker into a red-accented orc archer: it follows the existing route, stops when a tower or the center base is in range, draws its bow, fires a visible arrow, and resumes moving when no valid target remains. Keep `breaker` as its internal class so existing waves, history and proposed rewards remain connected. Call it **Breaker archer** in player-facing descriptions. This extends the [LTZ integration and economy plan](LTZ_POST_MATCH_AND_HORDE_PLAN_2026-10-10.md).

**Current implementation and implications**

- Breakers currently have 130 base health, movement speed 50 and base contact damage of 10 per second. They have separate hammer-carrying walk sprites but the same render size as grunts. The [previous-game audit](LTZ_ORC_RELEASE_AND_SPRITE_AUDIT_2026-10-10.md) reconstructs breakers as about 28.5% of one historical practice cohort, so converting the class can substantially change difficulty; those counts are inferred, not directly logged.
- Game moves every living enemy through shared particle/collision routines. The existing `attacking` flag means admission to the core basin, where enemies orbit and apply continuous core damage. It must not be repurposed to mean drawing a bow.
- Tower damage currently comes from swept enemy contact, with one shared health pool for a primary and its L4 companion. Destruction updates links, ring membership and row barriers. Ranged hits must use the same damage/destruction behavior.
- Existing projectiles are mortar rounds. Y and its mobile renderer assume mortar origins and effects, so enemy arrows must have an explicit separate projection and render pass rather than being inserted into that array without a discriminator.
- Full-wave victory currently checks that scheduled groups, living enemies and the pressure queue are exhausted. It does not account for hostile arrows because none exist yet.

**Combat behavior proposed for approval**

1. **Move:** follow the existing path and row routing. At a bounded target-scan cadence, look for living, placed defense pods in range with an unblocked firing line. Prefer the nearest eligible tower body; use stable IDs to break equal-distance ties. Primary and companion bodies are valid aim points but count as one defense health pool. A placed tower is targetable during activation as it is under current contact damage; destroyed and absent towers are not.
2. **Stop and aim:** if there is an eligible tower, stop voluntary movement and face it. If there is no tower target, consider the center base using the same range and visibility rules. Hold a valid selected target to avoid switching between equally close towers each frame. Take approximately 0.5 seconds to draw the bow before the first shot, giving players time to react.
3. **Fire and recover:** release one arrow with a visible flight, then recover before drawing the next. Remain stopped while a valid target is available. Use an explicit Game-owned `move → aim → recover` combat state with shot timestamps and facing; release is an event, not a second source of damage. Raw core-basin state remains independent.
4. **Recheck:** revalidate at release. If the target is destroyed, replaced, out of the retention range or shielded, cancel the unlaunched shot and select another target or resume movement. Acquire at the configured range and retain to 110% of it to avoid movement/aim jitter at the boundary. Retargeting does not bypass the shot cooldown and requires a fresh draw.
5. **Crowd interaction:** stopped archers remain normal collision participants and can be slightly displaced by crowd separation. Suppress road/orbit locomotion during aim/recovery, but retain collision and barrier constraints. Revalidate after displacement; do not pin an invulnerable obstacle into the road or let shooting bypass row routing. When the target disappears, the archer continues from its actual position.
6. **Damage:** in ranged mode, breakers deal damage only through arrow impacts. Exclude them from both tower-contact damage and continuous core-basin damage, including at point-blank range. They still receive tower, burn and force-field damage through existing rules. Do not add new status immunities or interpret the current electrical visual effect as a new stun mechanic.

The target choice is nearest exposed tower before the core, not a new pathfinding search for a distant target. If no target has a firing line, the breaker continues along the legal route; it does not stop forever aiming through a barrier.

**Arrows, protection and terminal outcomes**

Arrows are straight, non-homing, single-target projectiles. Game fixes origin, target body/placement generation, aim point, damage, launch time and travel speed at release. Simulation time controls their motion and impact; Y only draws the published flight. A released arrow continues after its shooter dies. Killing the archer before release cancels the shot. Document and test a consistent tick order so a released shot is not retroactively cancelled by a later tower hit in the same tick.

Give each installed defense an instance/generation identity in addition to its socket-based `placement_id`: the current placement ID is reused when the socket is replaced. An arrow aimed at a destroyed installation must not damage a new tower installed in that socket. Replenishing the same surviving installation retains its identity. A hit on either companion body damages the shared primary pool exactly once and uses the normal destruction/reconciliation path. Missing targets consume the arrow without damage or retargeting.

**Proposed protection rule:** active force-field segments and powered row barriers block hostile arrows. An arrow can hit an exposed tower body before reaching a barrier; target endpoints must use the actual pod boundary, so a tower powering a row is not made invulnerable by its own barrier. Intersections use Game's gameplay geometry, not image pixels or camera-marker exclusions. Rows stay without a health/wear counter. For this first version, arrow blocks also do not consume ordinary force-field contact-hit capacity; changing shield wear is a separate balance decision. Emit a small block spark so protection is visible.

Check line of fire at acquisition/release and sweep each arrow's traveled segment against currently active shields during flight. A shield activated before an arrow reaches it can intercept it; a shield activated behind it cannot. Dead/disconnected/broken fields cease blocking through the existing authoritative field state. No splash, piercing, friendly fire or random accuracy is added in this first version. A shallow visual arc, if used, must not imply that arrows can bypass the stated blocking rules.

- Pause freezes aim, cooldown, flight and damage using `sim_time`; resume continues once without catch-up volleys.
- Reset clears enemy combat state, arrows, impact effects and IDs for that run. Terminal defeat stops further damage and shot creation.
- An accepted center double stack preserves the existing detonation protection: cancel breaker windups, clear/neutralize hostile arrows, and apply no later hostile damage. Freeze the proposed center-health bonus before the purge, as in the economy plan.
- For an all-wave win, require no living enemies, no remaining scheduled/deferred spawns **and no damaging arrows in flight**. Finish outstanding flights first. If the last arrow destroys the core, the result is defeat; otherwise award one all-wave win after the final arrow resolves. Harmless retained visual effects do not delay victory.
- Missing UI packets, hidden browser tabs or renderer frame rate never change damage, kill credit or victory.

**Initial tuning in Game Settings**

Add a **Breaker archer** section. Values below are candidates for simulation and playtesting, not applied settings. Distances are unzoomed map units and range is measured from enemy center to target center; arrow collision/endpoint uses the target body boundary.

| Setting | Proposed start | Validation / meaning |
| --- | ---: | --- |
| Attack mode | Ranged in the candidate preset | Explicit `melee` / `ranged` enum; legacy presets migrate to melee for an unchanged comparison |
| Acquisition range | 220 | 50–450 map units; retention range is 110% |
| Bow draw duration | 0.5 s | 0.2–1.5 s and less than the shot interval |
| Interval between releases | 1.5 s | 0.75–6 s; cooldown cannot be reset by target switching |
| Base damage to a tower per arrow | 12 | 0–250; apply the existing tower-damage multiplier once |
| Base damage to the core per arrow | 12 | 0–250; apply the existing core-damage multiplier once |
| Arrow travel speed | 420 | 200–1,200 map units/s |

Retain 130 base health, speed 50, normal body size and existing collision radius initially, with current global health/speed multipliers. Twelve damage every 1.5 seconds is 8 base damage per second, below the existing 10 contact DPS because range should increase attack uptime. Under the current progression multipliers (0.35 tower and 0.18 core), that is 4.2 damage per tower hit or 2.16 per core hit. These are initial tuning hypotheses, not a claim of equivalent difficulty.

Freeze attack mode and all numeric settings at Start and record the combat-rule revision. Extend settings validation and persisted-preset migration explicitly for the new enum and keys; reject invalid/non-finite values and inconsistent draw/cadence combinations. Old files must continue loading with their previous tuning. Create a separately named **Breaker archer candidate** preset family for all four control tiers. Do not mutate old preset revisions or change an ongoing match. Activation after the implementation review selects ranged candidate presets for subsequent matches; the preserved melee presets provide rollback.

Do not change wave counts, the every-41st brute replacement, three-wins-per-tier progression or the 1,000-active cap for this feature. The proposed breaker reward remains 2 credits initially under the separately approved weighted-reward work; current live flat rewards stay unchanged until that work is implemented. Reassess reward value only after logging the ranged class's actual difficulty, survival and upgrade timing.

**Red archer artwork and presentation**

Replace the ranged breaker's hammer with a clearly readable bow and quiver. Preserve green skin, the existing top-down pixel-art style, normal body scale and visual pivot. Add strong red accents on shoulder/helmet trim, arm wraps or a sash and arrow fletching. Red is an enemy-class cue; do not reuse the Green/Purple ownership palette. The bow silhouette and stopped draw pose identify the class even when color is difficult to distinguish.

Produce four walking frames plus aim/draw, release and recovery poses (the aim and draw can be separate poses where needed). Keep frame bounds and pivots consistent so rotating the existing 16-direction sprite cache does not make the archer jump or clip. Keep the original hammer assets for the melee comparison preset; each run's published combat/art variant selects the appropriate set. This approval pass does not generate or replace artwork.

Photon Level owns and publishes the versioned archer assets and their content hashes. Publish an additive archer presentation variant and pose IDs through its existing asset contract; keep existing walk IDs available for compatible legacy presentation. Game forwards the descriptor and authoritative pose/state/timing. Missing archer art uses a recognizable code-native bow/red-accent fallback and an asset diagnostic, never a client gameplay decision.

Y and the shared Mobile renderer use the same pose selection and arrow effect. Extend the sprite cache key with variant/pose, keep rotation/facing consistent with the target, and publish a hold motion guide while aiming or recovering so client interpolation does not slide a firing archer down the road. Resume the normal road/orbit guide when it moves. Use a thin arrow shaft with red fletching and restrained impact/block flashes, legible at actual landscape phone scale without covering controls or ArUco markers. Health bars and proposed weighted-score pulses continue through the existing shared UI.

**Module and performance scope**

| Owner | Planned work |
| --- | --- |
| Photon Game | Small owned `ranged_enemies.py` helper for target selection, state and arrow lifecycle; focused integration into movement, damage and victory; shared damage/destruction helper; settings, preset migration and telemetry |
| Photon Level | Archer sprite assets, variant/pose manifest entries and hashes; no damage or AI logic |
| Laser Tag Y / shared renderer | Archer poses, authoritative hold motion and enemy-arrow effects on both displays and Mobile |
| Mobile LTZ delivery | Include new assets/helpers in the existing allowed asset paths and frozen renderer bundle; verify local/exported/hosted delivery |
| Photon Progress | No ranged AI. Consume raw kills and any weighted rewards through the already planned result contract |

Respect named/integer-version public contracts and enabled-module checks. No sibling-file access, second simulation, additional robot driver or calibration changes. Make new fields additive under the current contract only if old consumers remain safe; if a consumer would silently misrender ranged combat, version/feature-check it and require a matching renderer before activating the candidate.

The current Game engine and Y renderer are approximately 4,865 and 3,101 lines. Put the new state machine/arrow behavior and presentation helpers in focused files rather than adding large blocks to those owners. Follow the existing structure plan's 800-line warning and 1,000-line ceiling for new maintained files; a repository-wide refactor is not a prerequisite.

Scan the at-most-28 defense bodies with shared geometry, rather than every other enemy. Retain a valid target between scans, scan on a staggered approximately 0.2-second cadence, and invalidate promptly on topology/placement changes. Keep simulation arrow storage bounded using the validated maximum flight duration, minimum shot interval, minimum first-draw time and 1,000 enemy cap, including arrows retained after shooter deaths and replacement spawns; never drop authoritative damage to meet a display budget. Render/cache reusable arrow shapes, cap decorative trails/impact effects, and shorten retained effect history at dense populations. Avoid per-arrow log writes on the tick.

**Balance evidence and acceptance**

Add actual per-class scheduled, released and killed counters as specified in the economy plan. Also log breaker aim time, shots, hits, shield blocks, misses/cancellations, damage to towers versus core, deaths before release, time stopped and tower/core destruction caused by arrows. Record attack mode, combat/reward revisions, loadouts and terminal reason. Log bounded aggregates through the existing off-tick pipeline, with individual events reserved for an explicit diagnostic capture.

Compare melee and archer candidates with the same schedules, layout, loadouts and seeded traces. Include tier-1 first breaker wave, partially built rows, full L4 four-row defenses, early center-stack finishes and full survival. Measure health lost, turret replacements, survival, time-to-clear, credits, first-Cue equipment, actual alive peak and stopped-enemy congestion. Do not use an enemy pile-up caused only by stationary archers to declare the 1,000-orc encounter balanced.

Required checks before activation:

- Target choice, retention, correct facing, stop/draw/release/recovery, cooldown, no target, destroyed/replaced targets and resuming valid routes.
- No extra contact/core-orbit damage from ranged breakers; exactly one scaled hit per arrow, shared primary/companion health and normal row/ring destruction handling.
- Shields block correctly, including activation during flight, exposed row towers and no invisible marker-based projectile blocking. Existing field contact wear remains unchanged.
- Death before release cancels; death after release does not; pause/resume/reset, dense bursts and target generation changes cannot duplicate hits or leave stale arrows.
- Last-arrow core destruction defeats the pair; all-wave completion waits for live arrows; accepted center stack neutralizes them and preserves captured bonus health. Mastery/rewards commit once.
- Deterministic behavior across supported tick sizes, full/compact snapshots and reconnects. The displayed pose and arrow follow Game time, not browser timers.
- New/legacy settings and presets survive save/load, active runs stay frozen, rollback restores melee behavior and its artwork, and module-isolation checks pass.
- Visually inspect all archer poses, directions, red accents, target facing and arrow hit points on both Y displays and landscape phone/tablet viewports; test missing assets and stale caches.
- Run the 1,000-enemy/28-defense fixture with a realistic breaker mix and a separate worst-case archer stress scene. Measure 20 Hz simulation tick/backlog, delivered snapshot size/gaps, bounded memory/projectiles and frame-time percentiles. Use the existing >30 FPS visible target on tested devices and preserve a readable live score. If needed, reduce visual effects while keeping all authoritative shots and clear attack poses.

**Implementation order after approval**

1. Add validated settings and the isolated ranged-state/arrow helper, refactor shared damage application, and cover core mechanics with deterministic tests.
2. Integrate movement holds, damage exclusion, target generations, shield interception and victory boundaries; publish additive combat/arrow state and version checks.
3. Produce and visually review the red archer assets, publish them from Level, and implement shared Y/Mobile pose and arrow rendering with bounded caches.
4. Add telemetry and the named candidate preset family; run unit, integration, rendering, delivery and dense-scene checks using fake hardware and isolated data.
5. Review a gameplay demo and balance report, update module specifications and the journal, then select the approved candidate during an idle deployment window. Preserve legacy presets and existing player/calibration data.

**Approval requested**

Approve conversion of the existing breaker to the described red-accented archer, the stop/draw/fire behavior, tower-first targeting, shield-blocking rule, proposed initial settings, in-flight-arrow victory rules, and the five implementation steps. The prior LTZ economy/live-score plan remains a separate pending implementation scope; this feature coordinates its revisions and telemetry without silently implementing or activating that whole plan.

**Source references**

- [Module rules](../AGENTS.md), [structure review](PONYTAIL_REVIEW_AND_FILE_SIZE_PLAN_2026-10-09.md).
- [Game simulation](../sandboxes/gamemaster/prototypes/photon-game/photon_game_runtime/engine.py): `_admit_ready_particles`, `_integrate_particles`, `_damage_towers`, `step`, mortar lifecycle, `_enemy_motion_guide`, snapshot projections.
- [Game settings](../sandboxes/gamemaster/prototypes/photon-game/photon_game_runtime/settings.py), [presets](../sandboxes/gamemaster/prototypes/photon-game/presets.py), [row barriers](../sandboxes/gamemaster/prototypes/photon-game/photon_game_runtime/row_barriers.py).
- [Game specification](../sandboxes/gamemaster/prototypes/photon-game/SPECIFICATION.md), [Level specification](../sandboxes/gamemaster/prototypes/photon-level/SPECIFICATION.md), [Y specification](../sandboxes/gamemaster/prototypes/laser-tag-y/SPECIFICATION.md).
- [Level asset mapping](../sandboxes/gamemaster/prototypes/photon-level/level_assets.py), [Y/shared renderer](../sandboxes/gamemaster/prototypes/laser-tag-y/tower-defence-view.js), [Mobile renderer consumer](../shared/mobile_ltz/mobile.js), [mobile delivery](../tools/mobile-ltz/README.md).
