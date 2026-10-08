# Atom tower health and damage buff — approval plan

**Status:** Approved by the user's instruction to implement; implemented in the working tree. See `ATOM_TOWER_BUFF_IMPLEMENTATION.md` for verification and activation notes.
**Prepared:** 8 October 2026.
**Scope:** Persistent green glow, doubled tower health and doubled weapon damage while an Atom occupies the tower's ArUco marker, with one full health restoration when an Atom returns.

## Intended gameplay

A valid Atom placement activates the turret as it does today. While that Atom remains on the turret's ArUco marker, the turret keeps glowing green and has twice its normal maximum health and weapon damage. Moving the Atom away removes the glow and returns the turret to normal health capacity and damage for subsequent attacks. The installed turret remains in place and continues operating.

Returning an Atom to an existing living turret restores its health once and reapplies both the double-health and double-damage bonuses. Remaining on the marker does not continuously heal the turret: enemies can damage and destroy it while buffed. A destroyed turret follows the existing replacement rule on a new valid placement; an Atom that never left cannot repeatedly resurrect it.

Apply this behavior to both teams and all four turret types. The buff glow is green for both teams; existing team identity stays visible. Preserve the current rule that an eligible Atom can replenish an existing turret without changing that turret's type or owner. An L4 turret and its companion retain one shared health pool, show the same buff state, and each deal twice their normal weapon damage while buffed.

| Event | Health, damage and visual result |
| --- | --- |
| First valid placement | Normal deployment, full doubled health, doubled weapon damage, persistent green glow |
| Atom stays on the marker | Doubled health capacity and weapon damage remain; incoming damage accumulates normally; glow continues |
| Atom moves away | Glow stops; normal health capacity and damage for subsequent attacks return; turret continues firing |
| Confirmed return to a living turret | Restore to full doubled health once; doubled weapon damage and green glow resume |
| Atom moves from turret A to turret B | A loses its buff; B gains its buff after valid placement; both installed turrets remain |
| Turret destroyed while occupied | Shared health becomes zero, glow stops, normal destruction behavior applies |
| Camera evidence becomes unavailable | Suspend both bonuses and glow; reacquisition alone cannot grant another heal |

### Approved health calculation

“Normal health” means the turret's current maximum after its existing weapon-level and link bonuses. Apply one additional multiplier: **2 while occupied, 1 otherwise**. Multiple observations or overlapping Atom candidates never multiply it beyond 2.

Preserve the health percentage when removing or suspending the buff, matching the existing treatment of changing link and upgrade capacity. Only a valid new placement/return restores health.

Example with a normal maximum of 100 HP:

1. Place the Atom: **200/200 HP**.
2. Take 50 damage: **150/200 HP**.
3. Remove the Atom: **75/100 HP**.
4. Return the Atom through a new valid placement: **200/200 HP**.

If tracking is interrupted at 150/200, the tower temporarily becomes 75/100. Reacquiring the same stationary Atom restores the multiplier to 150/200, without healing. Further damage during the interruption remains reflected in the percentage.

### Approved damage calculation

Apply **2× normal weapon damage while occupied, 1× otherwise**, after the existing weapon-level, link and weapon-specific modifiers. For example, an attack that normally deals 30 damage deals 60 while buffed and returns to 30 for attacks made after removal. Repeated observations or multiple Atom candidates never stack the presence bonus beyond 2×.

Cover Machine Gun hits, Flamethrower direct damage and applied burn damage, Mortar splash damage, and Tesla Coil hits including chain targets. Preserve each weapon's existing falloff, chain, splash and burn-combination rules. Fire rate, range, splash radius, chain count and effect duration stay at their existing values. The bonus belongs to turret weapons; it does not multiply force-field or core damage.

Use the existing attack timing: capture the multiplier once when an attack fires or applies a burn. Mortar rounds already launched and burns already applied retain their committed damage through their normal lifetime. Removal stops the bonus for subsequent attacks; it does not rewrite attacks already in flight or multiply their damage again at impact. Both health and damage bonuses use the same authoritative occupancy state.

## Current structure and relevant behavior

- **Photon Board** owns corrected physical observations. Its `photon.board.placement` v1 relationships already provide marker association, dwell, timestamps and relation identity. This activation evidence depends on fresh, enabled, connected arm feedback with the pump off. Its fixed-marker memory expires after 120 seconds, so it is unsuitable as the sole long-lived occupancy signal.
- **Photon Game** owns placements, health, damage and replenishment in `photon_game_runtime/engine.py`. Placements are keyed by socket; one Atom can activate several persistent turrets. `_replenish_tower()` already restores health and connected fields. `_sync_tower_link_bonuses()` preserves health percentage as capacity changes. `physical_relation_tokens` suppress repeated activation for an unchanged relation, but are cleared when evidence disappears.
- **L4 companions** copy parent-owned health through `photon_game_runtime/companions.py`. They are additional firing positions, not additional placements or buff recipients.
- **Laser Tag Y** renders Game snapshots in `tower-defence-view.js` on the operator and external displays. It already has a brief green deployment flash and a brief team-colored replenishment pulse. Neither currently represents persistent Atom presence.
- **Virtual play** already uses Game placement commands and Game-owned mobile arm pickup/release state. These paths need the same occupancy transitions as physical play.

Continue the existing Board → Game → SSE → display flow and module ownership rules in `AGENTS.md`. Keep the current activation contracts, map geometry, robot-control path, and shared SSE transport. Preserve unrelated working-tree changes.

## Implementation sequence

### 1. Publish continuous occupancy evidence from Photon Board

Owned files: `photon-board/board_tracking.py`, `prototype.py`, and `SPECIFICATION.md`; a Board-local helper may be used if it keeps the tracker clear.

- Add a small, separately versioned occupancy descriptor alongside the existing cached Board observations, proposed as `photon.board.occupancy` v1. It reports physical relationships only: movable ID, fixed-marker ID, occupancy episode, present/confirmed-departed/unavailable state, source epoch, revision and evidence timestamps. It assigns no tower, team, health or gameplay action.
- Keep `photon.board.placement` v1 and Atom-on-Atom core stacking semantics intact. Game still requires the existing valid placement evidence for installation, replacement and a restorative return. Occupancy evidence alone cannot activate a new turret.
- Use fresh corrected camera detections and a unique marker association. Reuse the current fixed-marker overlap distance (0.04 normalized) and stable acquisition window (0.55 seconds); require at least three distinct frames for a new occupancy episode. Conflicting Atom/marker candidates produce an explicit ambiguous/unavailable result.
- Continue a confirmed occupation while the Atom remains freshly observed over its retained marker anchor, even when the covered fixed marker passes the placement tracker's 120-second memory limit. The same Atom may reacquire that established association after occlusion through a fresh stable window, without another heal. This retained anchor must not become evidence for an unrelated new placement. Source or geometry changes invalidate it.
- End presence when fresh evidence shows departure. Missing detections alone mean unknown, not confirmed movement. Allow at most the existing 0.35-second short tracking grace, then publish unavailable and suspend the buff. Stale camera input, sampler failure or changed camera/correction geometry also invalidates authority. Recovery requires fresh consistent evidence.
- Keep continuous camera presence independent of unrelated arm motion, pump changes and relay availability. Separate the new descriptor's camera validity from the existing arm-gated placement status in the producer and consumer adapters; do not relax activation requirements.
- Advance this state in the existing Board sampler. HTTP reads, display count and SSE reconnects must not advance dwell or manufacture another episode.

### 2. Add authoritative buff and return handling to Photon Game

Owned files: `photon-game/prototype.py`, `photon_game_runtime/engine.py`, `photon_game_runtime/companions.py`, and `SPECIFICATION.md`.

- Validate the new descriptor through the enabled Board public contract boundary, including integer version, identity, uniqueness, source and freshness. Missing or invalid occupancy produces an explicit unavailable buff state.
- Track the currently occupying Atom separately from the Atom that originally installed the turret. Key buffs by socket and enforce at most one occupied socket per Atom and one 2× buff per turret. Resolve conflicting evidence conservatively rather than selecting arbitrary candidates.
- Reconcile current occupancy on every accepted sample, even when placement-event deduplication skips an already consumed relation. A changed multiplier must be applied once; repeated samples cannot heal, reset weapons, repair fields or multiply health/damage again.
- Track restorative visits separately from transient relation IDs. A new full heal requires the ordinary valid placement gate plus a first visit or a confirmed departure-and-return. Pump toggles, camera gaps, changed relation IDs, source restarts and reconnects alone cannot count as a return. Preserve a bounded record of the last accepted visit across temporary input loss; clear it at the appropriate game reset boundary.
- Incorporate the presence multiplier into the same authoritative capacity calculation as upgrades and links. Preserve percentage on capacity changes. On a valid restorative placement, reconcile the final doubled maximum and then refill once through the existing replenishment path. Preserve that path's connected-field repair and cooldown behavior; persistent presence must not repeat them.
- Apply the same presence state as a separate 2× damage multiplier in the existing weapon attack calculation, after upgrade/link scaling, exactly once. Cover direct, chain, splash and applied burn damage. Preserve committed projectile/burn values, existing burn-combination rules, and kill/score accounting. Keep the presence multiplier separate from the link multiplier so it cannot accidentally increase force-field or core damage.
- Clear the buff on destruction. Reacquiring evidence for an Atom that never departed cannot replace a destroyed turret. Keep existing type/owner rules when a subsequent valid placement does replace it.
- Copy buff state to the L4 companion from its parent, double each weapon's outgoing damage once, and apply incoming contact damage once to their shared health pool. Keep buff state independent of link count, row-barrier membership and core-ring participation.
- Continue presence reconciliation while paused so removal cannot leave a stale bonus on resume. Preserve current placement/phase gates. Reconcile or clear state coherently across Start, reset, level reload, source changes and virtual/physical mode switches.

### 3. Give virtual play the same presence lifecycle

Owned files: Game's existing virtual command handling and `photon_game_runtime/mobile_arm.py`, plus the existing virtual-control UI only where needed.

- Route virtual placement and release through the same Game-owned buff/return transitions. Picking up an Atom removes its current tower buff; placing it elsewhere transfers occupancy without deleting previously installed towers.
- Support the equivalent removal action in the existing Gamemaster virtual Atom controls. A repeated command that leaves an Atom on the same socket cannot count as another restorative visit.
- Preserve team authorization, control progression, command validation and practice-only reward rules. Use the existing virtual pickup/release path for Joint, XYZ, Targeting and Cue modes.

### 4. Publish and render the persistent glow and doubled health bar

Owned files: Game's public tower snapshot; `laser-tag-y/prototype.py`, `tower-defence-view.js`, `index.html`, `screen.html`, and `SPECIFICATION.md` where forwarding or script revisions require updates.

- Publish explicit buff status, occupying Atom ID, health and damage multipliers, and normal health maximum alongside authoritative `hp` and `max_hp`. Include explicit clearing in incremental updates and complete state on reconnect. The browser never infers the buff from tag positions or `replenished_at`.
- Keep the existing deployment and replenishment cues, then sustain a soft green halo while the server reports an active buff. Stop it on removal, unavailability or destruction. Preserve marker keep-out areas, black/white ArUco contrast, team colors and upgrade readability.
- Show doubled health as **two equal health-bar segments/rows within the existing pod width**, with a small **×2** indicator. Together they represent the doubled capacity and drain with actual health. Return to the ordinary single bar when unbuffed. This avoids extending the bar across neighboring markers or L4 companions.
- In the existing selected-turret details, describe the active Atom bonus as **Health ×2 · Damage ×2**, using the authoritative state. Clear both indicators when the buff ends.
- Show matching health and buff status on the L4 pair. Keep the persistent glow visible at reduced effect quality using cached artwork or inexpensive drawing; avoid adding per-frame geometry work or another animation/event loop.
- Confirm consistent presentation on both the Gamemaster view and external screen, including fresh connections and reconnects. Update both renderer asset versions together.

### 5. Verify transitions and document the delivered behavior

Extend the existing Board, Game, mobile, companion and renderer fixtures with focused tests against isolated inputs and fake hardware.

| Area | Acceptance checks |
| --- | --- |
| Health arithmetic | Exact 2× capacity after level/link scaling; 200 → 150 → 75 → 200 example; no repeated multiplication or passive healing; upgrade/link changes preserve percentage |
| Weapon damage | Exact 2× outgoing damage after existing modifiers for all four weapons and L4 companions; direct, chain, splash and burn cases; 30 → 60 → 30 example; no doubled fire rate, repeated scaling or extra kill credit |
| Attack timing | New attacks return to normal after removal/unavailability; already launched Mortar rounds and applied burns retain committed damage; reapplying the buff cannot multiply an existing projectile or burn again |
| Physical continuity | Glow/buff remains beyond 120 seconds with the underlying marker covered; unrelated pump use or arm disconnect does not remove valid camera presence; confirmed departure removes the buff promptly |
| Return identity | First placement and real return heal once; camera flicker, stale data, relation reorder, repeated samples and source recovery do not heal or repair fields again |
| Unavailable evidence | Both bonuses suspend within the documented evidence limits; recovery restores health capacity with the remaining percentage and 2× damage for new attacks; invalid geometry, ambiguity, missing/disabled Board and malformed versions are explicit |
| Persistent placements | One Atom visiting A then B leaves both turrets installed and only B buffed; different eligible returning Atoms preserve the existing turret's type/owner rules; conflicting Atoms never produce 4× health or damage |
| Destruction and L4 | Shared pool/visuals on both pods; each weapon gets 2× outgoing damage once; no duplicate incoming contact damage or buff stacking; continuous occupancy cannot resurrect a destroyed turret; a new valid visit can replace it normally |
| Lifecycle and virtual parity | Both teams, all weapons, pickup, return, repeated commands, pause/resume, Start/reset, reload and mode switches; physical and virtual results agree |
| Presentation and transport | Persistent green glow, readable doubled bar and ×2 indicator, selected-turret health/damage bonus details, explicit clearing of both bonuses, full/reconnect snapshots, both displays, unobstructed markers and reduced-quality effects |
| Existing rules | Connected-field repair occurs only on the accepted replenish action; force-field/core damage, core stacking, links, row barriers, ownership, scoring and progression retain their established behavior |

Run the relevant Photon Board/framework, L4 companion, mobile turret, module-isolation and renderer suites, adding at least one runnable smoke test for the new non-trivial logic. Check the new mechanic against the actual Photon Game runtime; legacy Laser Tag Z tests alone are insufficient. Inspect both displays with the full L4 scene and representative enemy load using the existing performance fixtures. Record measured results and any pre-existing failures.

Update the owner specifications and `DEVELOPMENT_JOURNAL.md` after implementation. Apply the new gameplay policy at the next reset/new run so an active attempt is not changed halfway through. Physical camera/projector behavior requires a supervised placement/removal check after fixture and visual validation.

## Completion criteria and approval

A turret remains green and has twice its normal health capacity and weapon damage for the entire confirmed Atom occupation. Moving the Atom removes both bonuses without removing the turret, with committed attacks following the timing rule above. A valid return restores full doubled health once and restores doubled damage for new attacks. Companions, links, both teams and both input modes behave consistently, and tracking interruptions cannot manufacture healing.

Approval covers the gameplay above, doubled weapon damage and its attack-timing rule, percentage-preserving health removal, one-time healing on confirmed return, green glow for both teams, the two-part doubled health display, and the additive Board occupancy contract within the existing module structure. The user's instruction to implement supplied approval. Delivery and remaining physical verification are recorded in `ATOM_TOWER_BUFF_IMPLEMENTATION.md`.
