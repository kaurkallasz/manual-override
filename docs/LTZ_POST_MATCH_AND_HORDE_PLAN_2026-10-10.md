**LTZ score integration and level 4 horde plan**

Prepared 10 October 2026. **Proposed for approval; no gameplay, pricing, player data or hardware changes have been made.**

Extend the existing LTZ progression system so both Mobile LTZ players automatically receive a clear match result and the illustrated upgrade shop after every match. Put editable upgrade prices in Game Settings, and balance the campaign so the full-wave reference path funds the complete L4 loadout before the first Cue match, where a developed four-row defense faces 1,000 simultaneously living orcs. Players may instead finish early through the center stack, trading future kill earnings for a win and a smaller bonus based on remaining center health.

The user confirmed **three wins per control tier**. Joint → XYZ → Targeting → Cue therefore requires nine qualifying wins to enter tier 4, followed by three Cue wins for full control mastery. A control tier, a wave within a match, and a weapon upgrade level remain separate concepts.

The user confirmed that **phones and tablets will be used in landscape mode**. Landscape is the primary layout for gameplay, results, upgrades and readiness. Design for the limited height of a landscape phone as well as the larger tablet viewport.

The user confirmed the intended economic choice: **ending early means fewer kills and fewer resources for upgrades**. Both clearing all waves and the opposing-player double stack at the center should win. The stack should also award a health-dependent bonus. The user also requires **larger orcs to be worth more** and a **visible, satisfying live score increase for every earned increment**. The formula, enemy values and balancing procedure below are proposed settings, pending approval.

**Current implementation and gaps**

| Area | What exists | Required change |
| --- | --- | --- |
| LTZ Score | Both teams have identical illustrated L2–L4 upgrade cards, shutter reveals, saved profiles, purchases, mastery, statistics and history. The page already uses Photon Progress v2. | Reuse the art and card design in a shared responsive shop. Replace duplicated client price formulas and fixed price text with the server catalog. |
| Mobile LTZ | Both teams share `journey.js`; it already opens upgrades during the Game-owned 30-second interval, supports purchases, and shows history. Its shop is currently a list of text buttons. | Add the illustrated shop and a dedicated latest-match receipt: outcome, kills, credits earned, saved balance, time, mastery and new unlocks. |
| Laser Tag Y | Already presents Game's participants/save status, forwards commands, links to score pages, and uses upgraded live-map artwork. Settings redirect to Photon Game. | Add a compact match summary, both players' readiness and upgrade status, and clear next-match information. Keep purchasing on the phones/Score pages. |
| Credits and victories | Progress already commits one credit per confirmed co-op kill to each registered real profile. The engine already wins on either all waves cleared or core detonation. | Preserve both win paths; replace flat kill credits with configurable enemy values, a live weighted score and a separately itemized core-preservation bonus. Keep versioned rules and transactional receipts. |
| Prices | Hard-coded independently in Progress `store.py`, both `score.js` copies, mobile `journey.js`, and Score explanatory text. | One authoritative catalog with 15 editable prices: five tracks × three upgrades. |
| Orc schedule | Game already has per-tier immutable presets, count/pace controls, exact schedule calculations, a 1,000-active cap and a bounded pressure queue. | Tune actual concurrent population and persist peak/saturation telemetry. Scheduled match totals alone do not establish on-screen density. |
| Preview consistency | Score's configuration feed calculates from the global settings draft; Start resolves the selected tier preset. The observed Score page displayed 5,271/5,959/6,876 scheduled orcs while saved progression presets use approximately 1,088/1,170/1,250. | Publish one resolved next-match preview from the same preset selection and rounding used by Start. Label settings-draft previews separately. |
| Dual turrets | L4 companions already work at 12 eligible sockets; four central sockets stay single. | Make this benefit visible in shop/ready screens and validate it with earned purchases and the new horde presets. |
| Current live Score view | Green was using the built-in test profile with practice Cue access and zero earned credits. | Retain an explicit practice badge and zero rewards. Use real profiles in isolated reward tests; do not convert practice history to earnings. |

The August `GAME_SPEC.md` and `TECH_SPEC.md` describe an earlier Laser Tag Z design with eight structures, tower XP and several currencies. The later module specifications and September/October journal describe the current Photon owners, 16 primary placements, one persistent LTZ credit currency and between-match purchases. This plan follows the current implementation and requirements; it does not reinstate the earlier XP, research or eight-structure design.

**Module structure to retain**

| Owner | Responsibility in this change |
| --- | --- |
| Photon Game | Combat, real kills, enemy reward values, cumulative live score, victory method, center-health evidence, bonus calculation, result delivery, tier presets, next-match preview, shared journey/deadline, readiness and frozen loadouts. Owns Game Settings and next-run bonus rules. |
| Photon Progress | Player identities, balances, ledger, purchases, mastery and results. Also owns the price catalog and purchase receipts because those must commit consistently with spending. |
| Mobile LTZ API | Authenticated, team-filtered projection and command forwarding through existing endpoints and SSE. |
| LTZ Score and shared Mobile UI | Display live score feedback, cards, receipts and countdowns; submit purchase intent. No credit, price or unlock authority in browser storage. |
| Laser Tag Y | Present Game's live score, result and next-match summary; continue linking to Game Settings. |
| Photon Level | Existing authored geometry, companion eligibility and gameplay artwork. |
| Board, Auto PP Cal 2, LTX and Relay | Existing physical observations, accepted calibration and sole robot-control path. |

All sibling access continues through enabled hub modules and documented named contracts with integer versions. Missing/incompatible producers show unavailable. No sibling-file imports, second simulation, independent browser timer or robot driver is introduced. Persistence and cross-owner calls remain outside the simulation tick; do not hold a Progress transaction while calling another owner.

Use small files by responsibility for the catalog, result projection and shared shop. Follow the October structure proposal's 800-line warning/1,000-line ceiling for new maintained files, and extract touched responsibilities instead of growing the oversized Game entry point, renderer or mobile coordinator. Consolidating the Score presentation and mobile bundle assembly is in scope; the separate repository-wide refactor is not a prerequisite for this feature.

**Player flow after a match**

1. Game finishes the attempt and stops gameplay/motion through the existing lifecycle. Both phones show **Saving result** until Progress confirms the terminal receipt. Never show pending kills as already spendable or add the full match reward twice after checkpoints.
2. The saved receipt opens automatically on both phones. Its header shows victory method/outcome, match kills, weighted kill credits with an enemy-type breakdown, core-preservation bonus, total earned credits, current available balance, active duration, current tier and `n/3` wins. A stack victory also shows the center-health percentage used for its bonus. A failed/aborted/interrupted run shows the banked kill reward and no completion/bonus. Practice shows kills with **0 credits · Practice**.
3. The illustrated upgrade cards sit directly below a compact receipt header. Keep the current weapon art, tier colors and unlock reveal. On landscape phones, use a short track label above the L2–L4 cards and scroll vertically between tracks; keep the balance and shared countdown visible without consuming much height. Landscape tablets can retain the mockup's left-hand track labels and three upgrade columns. Keep purchase buttons reachable without horizontal page scrolling or text shrinking. Account for display cutouts, browser bars and the on-screen keyboard. Use readable text, large touch targets, keyboard controls and reduced-motion support.
4. A successful purchase displays the actual paid amount, remaining balance and new owned level from its receipt. Cards explain damage/health, field capacity, and the L4 companion benefit. Distinguish **Owned**, **Buy**, **Need N credits**, **Requires L3**, **Unavailable** and **Practice only**. Highlight the current side's two assigned weapon roles while retaining all four persistent weapon tracks for players who change sides.
5. Statistics/history remain below upgrades, loaded separately from combat updates. Reconnect restores the latest result and shop using the run/intermission ID; it cannot repeat a reward or restart the deadline. A returning phone can still read a missed receipt after the purchasing window has closed.
6. Preserve the shared **30-second** ordinary upgrade window. At its end, Progress reserves both profile revisions/loadouts and Game moves both players to Ready; Start still requires the existing player and physical-readiness checks. Purchase-versus-expiry races resolve transactionally. The timer never starts a robot or a cue.
7. Preserve the current post-XYZ calibration sequence: Green first, Purple second, with the waiting player able to shop. Show a compact result in the active lesson without covering calibration controls. Do not restart the shared timer after calibration. This work must not replace or alter the accepted standalone PP Cal 2 rig/procedure.
8. Extend the same result presentation to practice/test matches, which currently return to the lobby: show a dismissible practice receipt with purchases disabled for test profiles and no automatic scored reward/window. Real scored losses receive the ordinary saved-results/shop flow.

Y's operator view shows the same match result, each participant's control/owned loadout and Ready state, plus the next preset and actual scheduled count. The external projection keeps its battlefield and ArUco markers readable; any result overlay stays out of marker areas and yields to the existing calibration projection.

**Enemy values and satisfying live score**

The user additionally requested converting the breaker into a red-accented ranged archer. Its [separate implementation plan](LTZ_RANGED_BREAKER_IMPLEMENTATION_PLAN_2026-10-10.md) is pending approval; current audit findings describe the existing melee class. Recheck combat balance under that proposed revision before finalizing the weighted reward catalog.

Weighted rewards use the existing enemy class IDs; the separate ranged-breaker proposal owns its combat and artwork changes. The [release and sprite audit](LTZ_ORC_RELEASE_AND_SPRITE_AUDIT_2026-10-10.md) confirms that breakers have distinct hammer-carrying sprites but the same render size as grunts; only brutes are enlarged. Historical class counts are reconstructed, not directly logged. Proposed starting values:

| Existing class | Player-facing description | Credits per confirmed kill |
| --- | --- | ---: |
| `grunt` | Regular orc | 1 |
| `runner` | Runner | 1 |
| `breaker` | Breaker (tougher, regular size) | 2 |
| `brute` | Large brute | 10 |

Add **Orc rewards** to Game Settings. Each type has an integer value, with proposed bounds of 1–1,000; validate that the large brute is worth more than every smaller class. Values are tuning candidates, separate from upgrade prices. Freeze the reward table and revision at match start. Reward by authoritative enemy class, not current sprite size, zoom, remaining health or a global health multiplier. Both registered players receive the full co-op reward once, preserving the existing shared-kill rule; do not imply individual kill ownership.

Game counts each confirmed enemy death once, including its frozen value and whether it was a combat or center-purge kill. Track **raw kills**, **weighted kill score/credits** and **center bonus** independently. Extend the existing internal checkpoint/result contract with cumulative weighted credits, per-type kill counts and reward revision; Progress awards only the uncommitted credit delta. Retries, overlapping weapon damage, purge effects and disconnects cannot pay twice. Live presentation comes from Game's authoritative cumulative score, while spendable wallet values come from Progress's persisted receipts. Logging and persistence stay outside the simulation tick.

Publish the frozen schedule's counts and credit value using the exact resolved spawn types, including the engine's periodic replacement with brutes, group rounding and pressure-queue behavior. Summing the authored group labels alone can miss those replacements. A full-clear reward is the sum of all scheduled enemy values, not simply the scheduled enemy count.

During play, show a compact **Match score · credits** counter in the landscape HUD on both phones/tablets and the Y display, with a smaller separate kill count. Keep the score visible alongside center health without covering aiming controls, calibration or ArUco markers. Show the saved wallet separately when needed; earning score never requires opening the post-match shop. In practice, label the counter **Practice score · 0 banked credits** so the same visual feedback does not promise spendable rewards.

- Every newly received positive score increment starts feedback on the next animation frame: a brief approximately 120–200 ms count-up, a restrained scale/glow pulse and a visible `+N` credit label. The number settles at the exact server total without overshooting. Use stable-width numerals so the HUD does not jump as digits change.
- Make higher-value deaths noticeably stronger: a brute can show **Large brute +10** with a larger, longer-lived accent than a regular `+1`. An unobtrusive enemy-value legend in the wave/ready view teaches the difference. Keep text and numerals meaningful without relying on color alone.
- For simultaneous or very rapid kills, combine increments into rolling 150–250 ms bursts such as **+27 · 7 kills**, retaining the complete summed value and type subtotals. No earned increase is discarded. The counter continues toward the newest authoritative total; do not queue one animation per orc or let feedback lag behind the match. Limit floating labels to a small reusable pool; phones can use the HUD burst alone, while Y can show sparse death-position labels outside protected areas.
- Use the existing SSE/state delivery with run ID and monotonic score sequence/cumulative totals. Deduplicate updates and recover missed values from the latest snapshot. Reconnecting, changing orientation or reopening the app restores the current score once without replaying historical kill celebrations. An interrupted animation retargets from its displayed value to the new total, then settles to the final receipt at match end.
- Award and animate the center bonus once after the saved result confirms it, as a separate **Center health bonus +N** line before the final earned total. Shopping subtracts from wallet balance, not the completed match score. Feedback does not block controls, readiness or the shared shopping deadline. Reduced-motion mode uses an immediate number change and short highlight; any score sound is optional and rate-limited during bursts.

**Editable prices in Game Settings**

Add an **Upgrade prices** section to the existing Photon Game Settings page, reachable from Y's Settings button. Each weapon and Force Field has separate L2, L3 and L4 incremental prices. Show the total cost to max each track and all five tracks, plus a clearly labelled affordability estimate for the selected progression presets.

Control tiers stay free and require three wins. Companions remain part of the L4 weapon purchase; no separate companion fee or per-socket purchase is added.

Game's settings facade calls Progress's public economy operations; Progress stores catalog revisions in its existing SQLite database. Pricing has an explicit **Save upgrade prices** action and save status, separate from simulation settings/preset saves, so one successful save never implies another owner has committed. Player APIs cannot edit the catalog.

- Validate the complete five-track catalog server-side: integer credit prices in a proposed range of 0–100,000, explicit zero meaning free, no unknown tracks, no negative/fractional/boolean values. Purchases remain sequential; higher-level prices need not be artificially ordered.
- Stage operator changes during play or an open shop window. Activate the pending catalog when Game opens the next shared shop, or immediately in an unreserved lobby. Bind an intermission to an immutable catalog revision for both players; retries/restart preserve that binding. Stage/activate calls are idempotent by revision and intermission ID.
- Publish catalog revision, exact next-upgrade price, affordability and blocked reason through Progress's projection. Both Score and Mobile use these values. Send expected player revision, catalog revision, track/level and operation ID with purchase intent; never trust a submitted cost.
- In one Progress transaction, check phase/reservation, profile/revisions, prerequisites and balance; deduct credits, install the upgrade and save a receipt containing price and catalog revision. Repeating a committed operation returns its original receipt even after prices change. A stale uncommitted quote is rejected and refreshed before another deliberate purchase.
- Migrate existing installations to a catalog containing today's prices first. Preserve earned levels, balances, lifetime scores, mastery and historical purchase amounts. Offer the proposed balance catalog below for explicit operator selection; do not silently reprice old purchases or issue retroactive refunds.
- Include current/pending catalogs and open-window bindings in backup/recovery. A corrupt catalog makes buying unavailable rather than substituting client prices. Price-only changes do not alter combat stats or invalidate historical combat comparisons; record economy revision separately.

**Proposed starting economy**

These values are balance proposals for the new campaign, not applied settings.

| Track | Current L2 / L3 / L4 | Proposed L2 | Proposed L3 | Proposed L4 | Proposed L1→L4 total |
| --- | --- | ---: | ---: | ---: | ---: |
| Machine Gun | 250 / 500 / 750 | 200 | 400 | 600 | 1,200 |
| Flamethrower | 250 / 500 / 750 | 200 | 400 | 600 | 1,200 |
| Mortar | 250 / 500 / 750 | 200 | 400 | 600 | 1,200 |
| Tesla Coil | 250 / 500 / 750 | 200 | 400 | 600 | 1,200 |
| Force Field | 1,000 / 2,000 / 3,000 | 500 | 1,000 | 1,500 | 3,000 |
| All five tracks | **12,000 total** | **1,300 across tracks** | **2,600 across tracks** | **3,900 across tracks** | **7,800** |

The existing provisional presets schedule 1,009 / 1,088 / 1,170 orcs at tiers 1–3. Under the current flat one-credit rule, nine full clears earn each player `3 × (1,009 + 1,088 + 1,170) = 9,801` credits. That baseline leaves a 2,199-credit shortfall against today's 12,000 catalog, or 2,001 credits of headroom against the proposed 7,800 catalog. Its full-clear milestones are all L2 after two wins, L3 after four, and L4 after eight. With larger orcs worth more, 9,801 becomes a lower bound for those same schedules: recalculate exact weighted rewards and upgrade timing from the resolved class mix before choosing final prices. The old 79.6% kill-count threshold is no longer a valid weighted affordability measure. Keep 7,800 as a candidate to review against that new report; do not silently raise prices to cancel the larger-orc reward. Purchases remain the player's choice.

This calculation assumes both profiles start at tier 1, earn full co-op rewards, and clear the reference schedules. Early core victories deliberately produce fewer total credits even after their bonus; a player can reach Cue with a weaker loadout. Do not compensate for that choice with automatic upgrades or lower personal prices. Mixed-tier partners and losses also change the earning path. Validate affordability for the full-wave reference path and record the intentional shortfall for early finishers. The two players have separate balances; each receives the same team reward once.

**Two victory paths and the core preservation bonus**

The engine already implements an all-wave win: the core must remain alive, the configured final wave must have launched, every scheduled group must be accounted for, and both living enemies and the deferred pressure bank must be empty. Expose this as **All waves survived** in Y, Mobile and results. Merely reaching the last wave or the end of its timer does not win while enemies remain.

Keep the existing center victory: after a valid completed ring, one player's Atom arms the center and the opposing player's confirmed stack initiates detonation. Expose this as **Center stack victory**. Both paths award one qualifying win toward the current tier, never two, with no requirement to reach the 1,000-orc peak first. Core destruction remains defeat. Preserve existing server ordering for same-tick events and record one immutable victory method; animation completion, repeated camera evidence and reconnect cannot create another award.

Proposed starting formula, per registered real player:

```text
V = total credit value of all scheduled orcs under the frozen reward table
C = confirmed weighted kill credits at finalization, including real core-purge kills
H = clamp(core health at accepted second stack / frozen maximum core health, 0, 1)
R = max(0, V - C)                     # kill credit value forgone by ending early

health_bonus = floor(V × 0.20 × H²)
bonus_limit  = floor(R × 0.50)
stack_bonus  = min(health_bonus, bonus_limit)
total_earned = C + stack_bonus
```

Only a successful, reward-eligible center-stack victory receives the bonus. All-wave victories earn their confirmed kill credits without this bonus. Defeat, abort, interruption, practice, virtual tests and operator-assisted practice receive no stack bonus. Capture health when the second stack is accepted, before detonation changes the battlefield, and freeze it in the terminal result. Future repairs cannot change that captured value. Existing purge deaths remain real kills worth their frozen per-type credit value; unreleased/cancelled orcs are neither kills nor automatic currency. Log combat kills and purge kills separately without double-counting enemies hit by both.

The cap preserves the user's choice: the bonus can replace at most half the credits forgone by ending early. For `C < V`, `C + bonus < V`, so a full clear of the same finite schedule pays more total credits. A stronger core increases the bonus until the forgone-kill cap binds. If the stack purges every remaining scheduled enemy, `R = 0`: the player already earns the full kill reward and receives no additional stack bonus. This avoids making a last-second stack strictly better than an otherwise identical full clear.

Illustrative match with **1,000 credits of scheduled enemy value** and 400 earned kill credits. Those credit totals can represent a mix of small and large orcs and are separate from both raw kill counts and the 1,000-concurrently-alive target:

| Center health at stack | Kill credits | Stack bonus | Total earned per player |
| --- | ---: | ---: | ---: |
| 100% | 400 | 200 | 600 |
| 80% | 400 | 128 | 528 |
| 50% | 400 | 50 | 450 |
| 25% | 400 | 12 | 412 |
| Full-wave clear | 1,000 | 0 | 1,000 |

With 900 earned kill credits and 100% center health, the same formula caps the bonus at 50, for 950 total. Use deterministic server rounding and validation; the browser displays Game's projection rather than calculating spendable rewards. During play, show current core health and a labelled **Estimated stack reward now** from Game, accounting for the expected purge of currently living enemies. The final receipt remains authoritative if kills or health change before the stack.

Add a **Victory rewards** section to Game Settings, alongside wave/preset tuning:

| Setting | Starting proposal | Operator meaning |
| --- | --- | --- |
| Core-preservation bonus | Enabled | Enable/disable the bonus; both victory paths remain available |
| Maximum bonus as % of scheduled enemy credit value | 20% | Potential payout at full health before the cap |
| Health curve exponent | 2 | 80% health earns 64% of the maximum; 50% earns 25% |
| Maximum share of forgone kill credits | 50% | Maintains the economic advantage of clearing all waves |

Use proposed validation bounds of 0–50% for the maximum bonus, 1–3 for the exponent, and 0–90% for the forgone-credit share. Configure enemy values in Orc rewards as described above. Store these rules in Game's versioned tier presets, initially identical across tiers; they scale naturally with each frozen schedule. Edits apply at the next match, never to a live attempt or its pending receipt. Game freezes the rule revision and facts; Progress validates and commits the bonus through the existing internal result channel in the same transaction as the final weighted kill-credit delta and mastery. The public player API cannot submit health, win evidence or bonus amounts.

Keep **lifetime kills**, **lifetime weighted kill score**, **lifetime bonus credits** and **total lifetime credits earned** separate. The current store equates all positive ledger entries with `lifetime_score` and checks `credits <= lifetime_score` during backup import. Update those invariants, schema migration, backup validation, history aggregates and UI labels before introducing bonuses: available credits reconcile against all earned credits minus purchases, while raw kills remain an enemy count and weighted kill score is the sum of frozen enemy values. Preserve existing `lifetime_score` data as the legacy raw credited-kill metric and expose explicitly named new totals rather than silently changing its meaning. Historical scored attempts retain the original one-credit rule; initialize weighted earned totals from their existing ledger without inventing enemy types or repricing old kills. Old records get zero bonus without fabricated health values or retroactive awards. Repeated terminal delivery, including recovery after a crash, uses a unique per-run/per-player bonus ledger entry.

**Balance using actual game logs**

A read-only snapshot on 10 October contained **70 saved attempts: all practice**, comprising 42 overruns, 10 aborts, 13 interruptions and five wins. The wins include one labelled full-wave clear, three labelled core activations, and one with no recorded finish reason. The full-wave example recorded 1,009 kills in about 23.9 active minutes. The labelled stack examples recorded 0/1,009 kills in 4.2 minutes, 508/1,009 in 17.7 minutes, and 291/1,250 in 10.7 minutes. These are observed attempts, not matched scored trials or a player-skill benchmark.

Neither the saved terminal receipts nor the inspected terminal JSONL events contain center health at stack. They cannot establish historical health bonuses. Under the historical flat one-credit rule and an explicitly hypothetical 100% health, the three stack examples would have bonus ceilings of 201, 201 and 250 credits. These are not weighted-reward estimates: their actual health is unknown, and a class mix must be verified before applying the new table. Do not backfill those upper bounds into player history. The zero-kill victory before the first wave is useful evidence that short repeat runs must be checked for credit-per-minute farming, even when their reward per match is smaller.

For new runs, record the following through Game's existing event/result pipeline:

- **Comparable conditions:** run ID; pseudonymous player IDs and prior experience; both frozen tiers and loadouts; shared tier; map/layout, preset, enemy-reward, bonus-rule and price-catalog revisions; physical/practice/test status and interventions. Deduplicate a co-op match when analyzing team outcomes.
- **Victory and timing:** explicit `waves_cleared` or `center_stack`; first time the ring/stack becomes eligible; stack time; first-wave time; active play, pauses, intermission and next-Start times. Keep calibration/setup time separate and include relevant elapsed time when comparing repeat-session earning rates.
- **Core and horde:** core current/max health at stack and finish; core health at each wave boundary; scheduled/released/killed/unreleased counts; per-type scheduled, combat and purge kills with their frozen credit values; living count at stack; peak alive and saturation duration. Sample a bounded health/alive timeline at approximately one-second intervals on the existing logging worker, not by writing synchronously on the simulation tick.
- **Economy and decisions:** checkpointed weighted kill credits, live score sequence, stack bonus and applied cap, total earnings, opening/closing balances, purchases and their prices, levels owned before/after, plus whether the stack option was actually available. A full clear without stack availability is not evidence that the player chose to continue over a bonus.

Begin with an **offline balance report** over an explicit log export; do not make prices or rewards adapt silently to individual players. Keep existing data intact. Unknown historical health, overrides or tiers remain unknown, and old practice runs stay outside the primary scored economy analysis.

1. Run deterministic tests of both victory paths and the formula. Check the full-clear reward advantage, increasing bonus with health before the cap, zero/near-zero remaining credit value, mixed enemy types and tiers, purges, practice and idempotent recovery. Verify that raw kills, weighted score, bonus and wallet reconcile independently.
2. Use matched simulator scenarios with the same map, loadout, seed and action trace up to the point where the strategies diverge. Compare early stack, later stack and full survival, including all 28 firing units and the no-kill pre-wave finish. This checks plausibility; simulated actions do not establish human behavior.
3. Collect a first structured pilot, aiming for **30 comparable attempts per tier across at least 10 player pairs**, with deliberate examples of both finish paths. Treat sparse finish-method/loadout groups as provisional. Separate invited strategy trials from ordinary voluntary choices and identify player/pair repetition; retries are not independent new players.
4. Report median and spread for credits per match, active minute and complete repeat-session minute; win/loss rate; core health; stack timing; bonus share; rewards by enemy type and wave; next affordable upgrade; and equipment at first Cue entry. Compare within compatible cohorts, account for player experience and loadouts, and show uncertainty. Do not infer that the bonus caused a change merely because experienced players choose one path more often.
5. Use the proposed initial goals: full survival always earns more per successful match on the same schedule; early winners usually earn roughly **50–85%** of that full-clear amount, with very early/no-kill exits explicitly allowed below that range; repeated fast stacking should not exceed comparable survival's median credits per complete session minute by more than about **10%**. Those percentages are tuning hypotheses, not established observations or automatic rules. Include losses when comparing strategy returns.
6. If fast stacking dominates earnings per hour, lower the maximum bonus fraction first. If healthy early victories feel unrewarding while rates remain reasonable, raise it modestly. If center health barely affects the decision, increase the exponent; if damaged-core recoveries receive too little, lower it toward linear. Adjust the forgone-credit share only if late-stack payouts crowd out full survival. Change one reward parameter at a time, typically in five-percentage-point or 0.25-exponent steps, and hold combat settings, enemy values and upgrade prices fixed during that comparison. In a separate enemy-value trial, compare brute/heavy reward share, credit rate and upgrade timing against the frozen class mix; change one class value at a time while holding the bonus rule fixed.
7. Re-evaluate equipment at first Cue separately for survival-heavy and early-finish-heavy players. The reference survival path should fund the proposed complete loadout; an early finisher's weaker equipment is intended. Change upgrade prices only if the survival reference misses its goal, or a separately approved campaign pacing change calls for it. Account for banked kills from failed attempts; qualifying wins alone are not the complete economy.
8. Publish a proposed new preset/rule revision and a before/after report for the operator to accept. Use a subsequent comparable playtest to verify behavioral effects: recalculating bonuses on old logs shows what those old choices would have paid, not how players would choose under new incentives. Preserve old receipts and make rollback affect future matches only.

**Four rows and the 1,000-orc target**

The existing map already supplies the requested four eligible rows:

| Row | ArUco markers | L4 result |
| --- | --- | --- |
| Outer top | 40, 42, 44 | 3 primaries + 3 companions |
| Inner top | 41, 43, 45 | 3 primaries + 3 companions |
| Inner bottom | 49, 51, 55 | 3 primaries + 3 companions |
| Outer bottom | 53, 52, 46 | 3 primaries + 3 companions |
| Middle, retained exception | 48, 50, 54, 47 | 4 single primaries |

The fully populated target is **12 dual pairs across four rows plus four central singles: 28 firing units**. A companion shares its parent's health and aiming but fires independently. It does not add another row contributor, field endpoint, Atom or core-ring step. Show **eligible/installed companions** separately from **powered rows**: owning L4 does not physically place the defenses or guarantee all rows remain powered.

The current balance report is explicitly provisional and uses an assumed four-socket placement trace. Tier 4 releases 1,250 total orcs but peaks at 160 alive with base upgrades, or 158 with L4 upgrades. It does not test a fully developed 28-weapon battlefield or establish the new horde goal. October 8's 1,000-enemy/28-weapon replay measured 60 FPS median and 44 minimum on both Y displays for 40 seconds, but that is rendering evidence, not a balanced sustained match or a phone performance result.

Proposed tuning targets:

| Control tier | Target peak living orcs | Upgrade economy milestone |
| --- | ---: | --- |
| 1 Joint | Approximately 100–150 | Frequent first upgrades; all L2 affordable within this tier on the reference path |
| 2 XYZ | Approximately 250–350 | All L3 affordable; preserve the required calibration transition |
| 3 Targeting | Approximately 500–650 | Complete the L4 purchases before entering Cue |
| 4 Cue | **Reach 1,000**, with roughly 900–1,000 for at least 10 seconds in the reference encounter | Four dual rows, remaining central turrets and L4 fields in use |

Keep the hard cap at 1,000 and the existing pressure-bank bound at 2,000. Use the current count multiplier, release rate, wave overlap/gaps, first-wave delay, enemy durability and existing routing to build density. Begin testing tier 4 with a larger finite schedule, roughly 3,000–5,000 total enemies, and tune against actual kill throughput from 28 firing units, fields and the current Atom buffs. Those totals are experimental inputs, not approved final balance values. Keep lower-tier enemy counts initially near their current schedules; change release shape first. Recalculate weighted earning budgets and affordability whenever enemy totals, class mix or reward values change.

Keep exact group rounding and apply tier/global factors once. Track scheduled, released, alive, killed and deferred enemies separately; a full pressure bank leaves unaccepted spawns pending in their source groups. Never fake the on-screen population with decorative copies or increase the cap. A server-observed peak must occur in ordinary live simulation and be visible through delivered snapshots, rather than only in a synthetic rendering fixture.

Tune with a complete deployment trace for all four rows, realistic placement/replenishment delays, base/partial/full upgrades, mixed-tier players and a slower partner. A 1,000-orc peak caused only by deliberately withholding defenses fails the intended full-defense test. Measure completion time and survival alongside density so the target does not create an unwinnable wall or turn stronger weapons into a disadvantage.

**Victory and the horde target:** both the all-wave and center-stack paths remain valid. Players may deliberately trade the later horde's kill earnings for an earlier win and the bounded core-preservation bonus. Reaching 1,000 active orcs is a demonstrated encounter on the tier-4 survival path, not a prerequisite for a center-stack win. Do not add a minimum-wave or horde-peak gate to force players to stay.

**Delivery to Mobile LTZ**

Continue serving the local Green/Purple pages and hosted Mobile LTZ through the existing main hub, team-authenticated API and restricted gateway. Use existing `state`, `events`, `player`, `journey` and `history` routes. Extend projections with an authoritative live weighted score and sequence, explicit latest-result/save state, shop catalog, purchase eligibility and resolved next-match summary, without forwarding operator configuration or the other player's private balance.

Extract one shared Score/shop presentation and styles consumed by both Score adapters and Mobile LTZ. Keep team/session state isolated and existing Score URLs working. Bundle new JavaScript/CSS helpers into the established frozen mobile files. Consolidate bundle assembly across both team adapters and the exporter; the October audit identified that the exporter currently omits `connection-log.js`.

Reuse Level-published gameplay upgrade artwork. Put Score-only control/lock art under a shared presentation asset owner and serve it through a narrow explicit asset allowlist, including the existing mobile `assets/` delivery path. Do not have Purple or Mobile read Green's private prototype directory, embed the full desktop page as a phone iframe, or expand the gateway to arbitrary module URLs. Version the presentation assets and test exported, local and hosted URL resolution.

UI bundles are frozen at hub launch. Publish backend/UI changes during a planned idle restart and refresh both phones and Y displays; verify matching build/catalog contracts. Stale clients must receive an actionable refresh/quote error before buying, never silently fall back to the old hard-coded prices. Preserve the current accepted rig, calibration files and physical controller behavior.

**Implementation sequence after approval**

| Step | Scope | Completion evidence |
| --- | --- | --- |
| 1 | Add Progress-owned catalog, migration, transactional quoted purchases and Game Settings facade/form. | Editing each of the 15 prices changes the quoted and charged amount; rollback, stale quote, duplicate receipt and concurrency cases pass. |
| 2 | Add enemy reward settings, weighted score/checkpoints, explicit victory methods, frozen health/bonus rules and transactional bonus awards, latest-result/shop/next-match projections and intermission catalog binding. Resolve preset preview through Start's selection path. | Both wins count once; raw kills, weighted credits and bonus reconcile separately; both players see one saved result/deadline; previews equal the frozen schedule; restart and readiness races preserve credits and loadouts. |
| 3 | Share illustrated Score/shop presentation; integrate responsive live score feedback, automatic Mobile results and compact Y summary; unify bundle assembly/assets. | Both teams work in local and hosted delivery on landscape phones and tablets, with current artwork, satisfying score feedback under dense bursts and correct practice/error states. |
| 4 | Add health, strategy, reward and peak/saturation telemetry; create a separately named candidate progression preset family and offline balance report. Tune the horde with the actual engine, then compare finish strategies under controlled reward revisions. | The report distinguishes raw kills, per-type weighted credits and bonus, full-wave affordability, intentional early-finish shortfalls, earning rates, survival and the 1,000-orc encounter with all four dual rows. Existing presets remain selectable. |
| 5 | Run integration/performance checks, then a supervised two-player playtest and planned activation. Update current specifications and journal with measured outcomes. | Evidence covers the acceptance cases below; saved player/calibration data are preserved and prior presets remain available for rollback. |

Likely implementation locations are `photon-progress/{prototype.py,store.py}` plus a small owned catalog helper; `photon-game/{prototype.py,journey.py,presets.py,index.html}` plus focused result/preview helpers; `photon_game_runtime/{engine.py,settings.py}` for enemy reward accounting, live score, victory evidence, frozen bonus rules, tuning and telemetry; `mobile-ltz-api/prototype.py`; shared Score/Mobile presentation; both thin Score/Mobile adapters; Y presentation; and the existing mobile exporter. Geometry/companion generation need no redesign for this scope.

**Acceptance before activation**

- A saved scored match with 80 grunts and 7 brutes at the proposed values gives each participant **87 kills and 150 kill credits** exactly once; earlier checkpoints are included in that 150. Any eligible stack bonus is a separate once-only award. Both victory paths advance mastery once. Loss, abort, restart, duplicate delivery, test players, purge attribution and save failure behave correctly. Backups reconcile raw kills, weighted kill score and total earned credits separately; historical flat-value receipts retain their original amounts.
- Enemy reward values freeze per run, survive restart, match exact resolved spawn classes and appear in the next-match reward preview. A settings edit cannot revalue living or dead enemies in an active attempt. Live score feedback covers isolated kills, larger-orc kills, mass purges, duplicated/missed SSE, reconnect and reduced motion. At 1,000 active orcs it remains current without an unbounded animation queue; every new credit delta is represented once, and the final displayed total equals the receipt.
- All 15 operator prices survive restart, appear identically in both shops and are charged exactly. Simultaneous phone/desktop purchases cannot overspend. Catalog activation, purchase versus Ready/deadline, stale clients and crash recovery have explicit tests.
- A fresh pair follows three wins per tier, preserves the accepted calibration boundary, can afford the complete 7,800-credit catalog on the full-wave reference path before Cue, and sees the purchased art/effects on the next map. Early finishers may intentionally enter Cue with fewer upgrades. The bonus increases with captured core health until its cap, preserves the greater reward for a full clear of the same schedule, and is assessed for repeat-session farming with matched logs.
- Both player views automatically show saved results and illustrated purchases after scored wins/losses, retain history below, recover from background/reconnect, and never restart the shared timer. Practice shows zero reward. Verify landscape phones at 667×320 and 844×390 CSS pixels, and landscape tablets at 1024×768 and 1180×820, then check actual devices. Balance, countdown, purchase actions and gameplay controls remain readable and reachable with safe areas/browser bars and no horizontal page overflow. Temporary rotation or viewport resizing cannot reset the match, shop deadline, selection or pending purchase.
- The next-match preview matches the selected preset and actual released schedule; active matches retain frozen settings/loadouts. History preserves prior rules and purchase amounts.
- With all 16 primaries and 12 companions installed, the tier-4 reference match reaches 1,000 real living orcs and delivers that state to displays, holds approximately 900–1,000 for at least 10 seconds, and remains winnable. No frame/tick exceeds the cap; no scheduled enemies or kill credits disappear at queue saturation.
- Run the dense encounter with both Y displays and both Mobile clients, heavy Tesla/flame/mortar effects and row break/recovery. Target sustained visible FPS above 30 on the tested devices, a functioning 20 Hz simulation without growing backlog, bounded memory/queue sizes and usable purchase/control feedback. Record frame percentiles, simulation tick percentiles, delivery gaps and actual devices. Prior desktop replay numbers are the baseline, not a new pass.
- Extend the existing Progress/LTZ integration, journey/presets, mobile build/team isolation, module isolation, companion/row/Atom-buff and renderer checks with temporary stores and fake hardware. Perform physical placement/refresh/calibration checks only in the supervised playtest, using the working PP Cal 2 baseline.

**Approval scope**

Approve the five implementation steps, the 7,800-credit candidate catalog, the two explicit victory paths, configurable 1/1/2/10 enemy values, live score feedback, the proposed 20%/squared-health bonus capped at 50% of forgone kill credits, the log-based balancing workflow, the tier-density targets and the existing 12-companion/four-row layout. The three-win progression, landscape devices and economic tradeoff for early wins are confirmed. Initial implementation and testing use isolated fixtures; live settings/preset selection and hub activation follow the reviewable implementation and playtest results. Early stack wins remain available without a minimum-wave or 1,000-orc gate.

**Source references**

- [Module ownership rules](../AGENTS.md) and [hub contract](../hub/README.md).
- [Current structure review](PONYTAIL_REVIEW_AND_FILE_SIZE_PLAN_2026-10-09.md).
- [Original game description](../../docs/GAME_SPEC.md), [technical specification](../../docs/TECH_SPEC.md), [LTZ score design](../../docs/LTZ_SCORE_AND_PLAYER_PROGRESS_PLAN.md), and [L4 companion layout](../../docs/L4_COMPANION_TURRETS_PLAN.md).
- [Photon Game specification](../sandboxes/gamemaster/prototypes/photon-game/SPECIFICATION.md), [Photon Progress specification](../sandboxes/gamemaster/prototypes/photon-progress/SPECIFICATION.md), and [Laser Tag Y specification](../sandboxes/gamemaster/prototypes/laser-tag-y/SPECIFICATION.md).
- [Mobile progression/calibration plan](CONTROL_PROGRESSION_CALIBRATION_PLAN.md), [implementation notes](CONTROL_PROGRESSION_IMPLEMENTATION.md), [balance report](CONTROL_BALANCE_REPORT.json), and [Mobile specification](../sandboxes/green/prototypes/mobile-ltz/SPECIFICATION.md).
- [October Atom-buff and performance evidence](ATOM_TOWER_BUFF_IMPLEMENTATION.md), [development journal](../DEVELOPMENT_JOURNAL.md), and [mobile delivery](../tools/mobile-ltz/README.md).
- Direct source review of both Score pages, Progress purchasing, Mobile `journey.js`, Game presets/journey/settings projections, mobile API and exporter; read-only visual inspection of the current Green Score page. Historical validation numbers above retain their original scope and date; this approval pass adds no runtime test claim.
- Read-only SQLite snapshot of `photon-progress/data/progress.sqlite3` and scan of `photon-game/data/runs.jsonl` on 10 October for finish methods, kill/timing examples and missing health evidence. The offline analysis neither imports runtime modules nor changes player records. Counts describe that snapshot and will change as new matches finish.
