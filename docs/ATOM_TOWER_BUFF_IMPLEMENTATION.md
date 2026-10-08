# Atom tower buff implementation

Implemented 8 October 2026 from `ATOM_TOWER_BUFF_PLAN.md`.

An Atom occupying an activated turret's marker grants continuous green glow,
double maximum health and double weapon damage. Removal preserves health
percentage and restores normal capacity/damage. A confirmed return heals once
to the doubled maximum. Installed turrets persist after the Atom leaves.

## Ownership and behavior

- Board's new module-local `board_occupancy.py` reports camera-only occupancy
  from its existing sampler. Its additive public v1 contract is independent of
  arm/pump readiness. Existing placement v1 and core stacking remain intact.
- Established marker associations survive covered-marker memory expiry. The
  same Atom can reacquire its anchor after an occlusion through fresh stable
  frames; this does not authorize a new placement or another heal. Camera or
  geometry changes discard anchors. Missing/stale/ambiguous evidence suspends
  the buff; only observed departure rearms the same socket's restorative visit.
- Game validates the contract, records visits separately from detector relation
  IDs, and owns both multipliers. Existing upgrades and links compose once.
  L4 pairs retain shared health and independent doubled weapon attacks. Mortar
  launch damage and applied burns retain their committed values.
- Virtual pickup, release, relocation and the new **Lift selected Atom** control
  use the same Game transitions. Wrong-team removal is rejected. Core placement
  removes virtual turret occupancy. Pause, reset, Start and mode changes are
  covered by fixtures.
- Laser Tag Y uses explicit authoritative fields on both displays. Green halos
  clip around marker footprints and remain visible at dense effect quality.
  Two stacked bars and a ×2 badge show health; selected-turret details show both
  bonuses. Both pages reference renderer revision 18.

## Verification

| Check | Result |
| --- | --- |
| Atom-specific Board/Game tests | 15 passed, including >120-second occupancy, dropout/recovery, pump changes, real return, destruction, all weapon damage paths, companions, field repair and mobile pickup/release |
| Photon suites | 205 passed, including contracts, isolation, companions, core stacking, row barriers, SSE and performance fixtures |
| Mobile Python suites | 102 passed |
| Renderer smoke | Persistent green halo on Purple at dense quality, two health rows, marker clipping, unavailable/removal/destruction clearing and incremental SSE passed |
| Existing deployment renderer | Passed; the brief deployment flash remains separate |
| Real-browser virtual fixture | Passed on operator and external display with 16 primaries and 12 companions; verified lift, return, transfer, details and reconnect |
| Two-display stress replay | 1,000 enemies, 16 primaries, 12 companions, active buffs, row transitions and peak effects; 40 seconds; median 60 FPS and minimum 44 FPS on each display; zero samples at/below 30 FPS, no long tasks, no browser errors and 88/88 assets loaded per display |

The browser replay measures presentation on this machine, not live physical
camera latency or a sustained hardware gameplay run. Screenshots were inspected
for the green aura, doubled bars, companion layout and readable markers.
Artifacts are in `../output/atom-tower-buff/` relative to the repository root:
`screen-active.png`, `screen-removed.png`, `operator-active.png`,
`browser-results.json`, and `performance.json`/`performance.png`.

Updated existing companion/row tests to model real departure before replacement.
Legacy Z parity now compares unbuffed combat, while dedicated tests verify the
new multiplier. Corrected a pre-existing extraction assertion to reflect the
already implemented Board preview-frame/SSE path instead of its retired URL.

## Activation and physical check

Tests use isolated fixtures and fake hardware. No robot motion was issued and
the live hub was not restarted or its current game reset. Load the changed
Python modules at the next planned hub restart, then start/reset the game and
refresh both displays. Validate a real Atom placement, a long covered-marker
hold, pickup, and return on the camera/projector before treating physical timing
as verified.

Runnable checks:

```sh
.venv/bin/python -m unittest discover -s tests -p 'test_atom_tower_buff.py'
.venv/bin/python -m unittest discover -s tests -p 'test_photon*.py'
.venv/bin/python -m unittest discover -s tests -p 'test_mobile*.py'
node tests/atom_buff_renderer.cjs
node tests/turret_deployment_renderer.cjs
```

For the browser test, start `tests/virtual_upgrades_fixture.py` and run
`tests/atom_buff_browser.cjs` with the installed Playwright modules on `NODE_PATH`.
