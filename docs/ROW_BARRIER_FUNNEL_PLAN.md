# Row barriers and two-entry funnel — implementation plan

Status: implemented in the workspace. See ROW_BARRIER_VALIDATION_2026-09-05.md for verification and rollout details.
Prepared: 2026-09-05, against Photon Level layout revision 17.

## Intended gameplay

Add four row barriers alongside the existing automatic turret-to-turret force fields, as confirmed by the user. Each barrier activates when all three assigned turrets have completed activation and remain alive. It closes the vertical crossings along that row, leaving one end open. Destroying any participating turret drops that entire row barrier and reopens its crossings. Each row operates independently.

| Row, top to bottom | Turret marker IDs, left to right | Stable socket membership | Open end |
| --- | --- | --- | --- |
| Outer top | 40, 42, 44 | socket_01, socket_03, socket_05 | Right |
| Inner top | 41, 43, 45 | socket_02, socket_04, socket_06 | Left |
| Inner bottom | 49, 51, 55 | socket_10, socket_12, socket_16 | Left |
| Outer bottom | 53, 52, 46 | socket_14, socket_13, socket_07 | Right |

The middle band of four turrets is outside this mechanic. Use explicit socket membership because the current rows have slightly different turret heights and nonconsecutive IDs. Preserve the user's authored turret positions.

Orcs spawn only at the left ends of the outer top and outer bottom roads. Both grunts and Brutes follow these entrances and the same barrier rules.

With all four barriers active, the routes are mirrored:

```text
Top entrance   → → → → → → → → → → → → → ↓
Outer top      ===========================  right gap
               ↓ ← ← ← ← ← ← ← ← ← ← ← ← ←
Inner top      left gap  ===================
               → → → → → → ↓
                           CORE
               → → → → → → ↑
Inner bottom   left gap  ===================
               ↑ ← ← ← ← ← ← ← ← ← ← ← ← ←
Outer bottom   ===========================  right gap
Bottom entrance→ → → → → → → → → → → → → ↑
```

Each stream traverses the two barriers on its own side, then approaches the shared central core from above or below.

Recommended defaults for behavior not explicitly specified:

- Restore a row automatically when its third operational turret is restored through the normal activation process.
- Give the new row barriers no independent health, hit-count wear, or extra damage. Their power depends on the three turrets. Existing links retain their current damage, durability, and destruction behavior.
- Treat a missing/destroyed turret as unpowered. Use authoritative turret state; a transient marker-detection dropout must not independently toggle a completed activation.
- Preserve wave totals, timing, grunt/Brute statistics, and the current Brute ratio. Split the current equal spawn weighting evenly between top and bottom.

## Findings that affect implementation

The current map already has four left-side entrances: outer/inner top and outer/inner bottom. Remove spawning from the inner two; their roads remain useful for transit.

The middle lanes currently lack the westbound graph connections required for the zigzag. Merely closing crossings leaves both outer entrances without a route when all four barriers are powered. Both the Level parser and Game runtime also currently require exactly four spawn groups.

Game routing currently treats ordinary force fields as finite route penalties. New row barriers require strict edge exclusions: a high cost alone can still allow an orc to choose a closed crossing. Initial spawn routes, rerouting, and physical movement all need the same authoritative barrier state.

A read-only graph experiment added the proposed westbound connections in memory and checked two entrances across all 16 barrier combinations: all 32 reachability checks passed. With all barriers powered, each graph route measured 4,160 px versus 1,280 px with no row barriers, approximately 3.25 times longer. These are centerline distances; ordinary links, combat, collision, and rounded movement were not simulated. No production map or game state was changed by this check.

## Implementation sequence

### 1. Author the rows and winding routes in Photon Level

Owned files: `sandboxes/gamemaster/prototypes/photon-level/assets/tiled/levels/z-pixel-first-map.tmj`, its `.waves.json` sidecar, `level_contract.py`, `level_layout.py`, and `prototype.py`.

- Add four named row descriptors with the socket memberships above, barrier geometry, opening geometry, and controlled directed edge IDs. Keep editable topology and geometry in Tiled; do not infer grouping every frame from turret coordinates.
- Extend each barrier across the playable crossings to the board boundary, apart from its designated end gap. Connecting only the first and last turret would leave unintended routes around the ends.
- Add westbound connections along the top middle lane: node 92 → 87 → 85 → a new junction at (80, 240). Connect that junction through the left gap to node 96. Mirror this below: 94 → 90 → 88 → a new junction at (80, 720) → 97. Allocate real Tiled object IDs during implementation.
- Split existing left-side paths at the new junctions so the route graph shares explicit intersections. Preserve eastbound options and legal shortcuts for when a row loses power.
- Keep spawn nodes 80 (`top_outer`) and 83 (`bottom_outer`). Convert 81 and 82 to transit nodes and remove their spawning metadata. Update every wave's lane weights and any stale spawn/route labels. When migrating unequal weights, combine the two previous top weights and the two previous bottom weights.
- Keep all 16 sockets usable. Reconcile the legacy eight-structure map metadata with the current 16-turret game, since powering all four rows requires 12 turrets.
- Verify road artwork and modular ports at the new turns; change components only where the authored road geometry requires it. Validate gap clearance using actual grunt and Brute collision bodies.
- Extend layout-edit validation so moved sockets cannot silently invalidate row membership, barrier geometry, or route clearance.

The following existing crossings become unavailable while their associated row is powered:

| Row | Closed edges | Preserved route around row |
| --- | --- | --- |
| Outer top | `edge_switch_top_a_down/up`, `edge_switch_top_b_down/up` | `edge_top_outer_tail`, right turn at x=1520 |
| Inner top | `edge_mid_passthrough_top_down/up`, `edge_top_turnaround` | New left junction at x=80 → node 96 |
| Inner bottom | `edge_mid_passthrough_bottom_up/down`, `edge_bottom_turnaround` | New left junction at x=80 → node 97 |
| Outer bottom | `edge_switch_bottom_a_up/down`, `edge_switch_bottom_b_up/down` | `edge_bottom_outer_tail`, right turn at x=1520 |

Validate every geometric crossing against the authored edge set, including any reverse edges added later. The table uses `down/up` shorthand for two separate edge IDs.

### 2. Publish and validate the new level contract

- Publish `photon.level.runtime` v2 with explicit enabled spawn groups and row descriptors. Update both `runtime_bundle()` and the lightweight `runtime_status()` version together.
- Update the Game consumer's contract validation and model construction to support v2. Keep an explicit v1 compatibility branch for older four-spawn levels with no row barriers.
- Validate unique row IDs, exactly three distinct existing sockets per row, valid openings, geometry, edge references, enabled spawn groups, wave weights, and route reachability for every barrier combination. Reject malformed v2 data as unavailable.
- Preserve module ownership: Game reads Level through the enabled prototype's public versioned API; the display reads Game. No production sibling-file reads or imports.

### 3. Implement authoritative barriers and routing in Photon Game

Owned files: `sandboxes/gamemaster/prototypes/photon-game/photon_game_runtime/engine.py` and `prototype.py`.

- Derive four powered flags from authoritative operational turret state. Recompute when activation completes, a turret dies or is removed, or a run resets. Publish one topology revision when effective state changes.
- Combine powered rows into a strict blocked-edge set. Apply ordinary link penalties only within the remaining legal graph. Row barriers must never become a fallback route through an otherwise impassable force field.
- Make `_spawn_enemy` choose its initial route from the current legal graph. Constrain all spawn fallbacks to enabled entrances so invalid or empty weights cannot resurrect the two removed spawn points.
- Update `_reroute_enemy` and route-progress handling to find a valid continuation from the orc's actual position and side of a barrier. On a new closure, keep an orc on its existing side and steer it toward a legal connection; never project it through a wall or teleport it to an earlier waypoint. On destruction, reopen that row's shortcuts immediately.
- Enforce barriers during movement and after crowd separation using swept crossing checks. Fast movement, low frame rates, congestion, and Brute collisions must not push enemies through powered rows. Visual clearance around marker artwork must not create a traversable hole.
- Keep existing turret targeting, link damage, and core-ring logic. New rows do not count as extra ordinary links or as core-ring completion edges. If an ordinary field lies across a designated opening, retain its existing breakable interaction while keeping the row itself impassable.
- Preserve collision-aware spawn queues at the two entrances; increased congestion must not cause spawning elsewhere or silently change wave totals.

### 4. Show the barrier state clearly

Owned files: `sandboxes/gamemaster/prototypes/laser-tag-y/tower-defence-view.js` and relevant view/state adapters.

- Render each powered row as a continuous, readable barrier with an unmistakable open end, alongside the ordinary links.
- Show activation progress such as `2/3` and a brief break effect when a contributing turret is destroyed. Keep the distinction between the whole row barrier and individual links visually clear.
- Send authoritative row states through the existing SSE channel. Cache geometry; transmit state changes without resending static map geometry each frame.
- Reuse the optimized renderer's cached artwork and inexpensive effects. Keep gameplay decisions on the server.

### 5. Verify gameplay and performance, then apply on the next run

- Test all 16 barrier combinations from both entrances, and verify the exact east–west–east route with all four rows powered.
- Test each of the 12 contributing turrets being destroyed and restored: only its row changes, and shortcuts reopen without a reset. Test partial activation and activation order.
- Test closure while enemies straddle crossings, reopening with enemies mid-edge, fast enemies, large configured Brute bodies, crowd pushing, and dense spawn queues. Assert no barrier crossing or off-road teleportation.
- Assert that every scheduled and fallback spawn uses only the outer top/bottom entrances. Check unchanged wave totals and Brute cadence.
- Regress ordinary link formation, wear and destruction, overlapping fields, core-ring completion, settings persistence, physical/virtual activation, v1 compatibility, and malformed-contract handling.
- Run the relevant Photon smoke tests, modular map validation, Tiled CLI round-trip, and native map render inspection. Visually confirm both gaps and the full winding path in the game.
- Protect the FPS work: cache routing by row state and ordinary-link topology revision, sharing routing results across enemies. Avoid a shortest-path search per enemy per frame. Bound rerouting work during mass topology changes while enforcing collisions immediately.
- Repeat the existing sustained stress scenario with 1,000 enemies, 16 turrets, Brutes, dense effects, and both display views. Include repeated row activation/breakage and all rows powered. Acceptance target: visible FPS remains above 30 in the measured scenarios, without growing simulation backlog or spawn stalls. Record hardware and measurement limits rather than claiming an unconditional FPS guarantee.
- Playtest the longer exposure time and congestion before proposing any balance changes.
- Update the Level, Game, and display specifications. Load the new map revision on the next reset/new game so an existing run retains a coherent frozen layout.

## Completion criteria

Four independent three-turret barriers produce alternating right/left openings; losing any contributing turret breaks its row; both outer left entrances remain connected to the core in every row state; existing links still function; no inner entrance spawns enemies; and the validated performance scenarios remain above 30 FPS.
