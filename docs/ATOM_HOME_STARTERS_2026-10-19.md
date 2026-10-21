# Atom homes and starter defenses — 2026-10-19

The human approved the plan and then clarified that revealing the second home
at L4 must also deploy the other weapon type. OpenAI Codex implemented that plan.

## Delivered behavior

- The old yellow staging box and static 100–103 dots are gone.
- Green has glowing homes below the old area; Purple is mirrored diagonally into
  the upper-left. The numbers follow the configured/saved starting Atoms.
- L1–L3 show one home and one deployed turret per player. L4 shows both homes and
  both weapon types. Each turret uses its owner's earned upgrade for that weapon.
- Setup previews reflect the upcoming saved level. Both GM Start and phone
  countdown honor the selected home Atom. Explicit automatic camera detection
  remains available.
- Starter weapons aim, fire, score kills and take contact/ranged damage normally.
  They cannot be rebuilt during a match. Browser reload does not restore them;
  a new match creates fresh starters.
- Starters are separate from construction sockets: no ring, row barrier, links,
  occupancy buff or L4 companion. Existing Atom placement still builds ordinary
  turrets. No additional robot-control path was introduced.

## Ownership and geometry

Photon Level owns the hidden Tiled home objects and their validation. Game owns
visibility, previews, combat and lifetime. Laser Tag Y/shared mobile UI consumes
the public state for rendering and aim. The optional contract fields preserve
legacy maps without homes.

Revision 21 moves the homes inward at the human's request, keeping all sixteen
construction sockets and the other fourteen Tiled layers unchanged. Pad/pod
footprints are 56/72 px. Green pad centers are (1464,768)/(1464,832), with turret
centers (1396,760)/(1396,840), across the road at the outer edge of the lower inner
area. Purple pads are (340,128)/(340,192) and turrets (272,120)/(272,200), at the
inner/right edge of its current upper-left area. Both pairs are vertical; this
supersedes revision 20's exact rotational symmetry. Reserved footprints clear
all normal markers, pods and eligible companions. Numbers draw above barriers.

## Verification

Fresh final Python run: **113 passed** in approximately 12 seconds:

```sh
PYTHONPATH=tests .venv/bin/python -m unittest \
  test_starter_defenses test_event_game test_event_reset test_photon_companions \
  test_mobile_turret test_ranged_breakers test_ranged_delivery \
  test_results_replay_heatmap test_photon_level_editor \
  test_photon_module_isolation test_start_readiness test_player_continue
```

Fresh mobile JavaScript run: **7 passed**:

```sh
node --test tests/mobile_turret_continuity.test.js
```

The isolated Chrome fixture verified L1/L3/L4 visibility and upgrades, operator
selection/aim, rejected rebuilding, destruction surviving browser reload, and a
full L4 board with sixteen primary turrets, twelve companions and four starters.
It captured 1920×1080 and 1366×768 views with no page errors. Test data/hardware
were temporary fakes. Results and images are in
`output/atom-homes-2026-10-19/`; `screen-l4.png` shows the four-home layout.

Tiled 1.12.2 successfully round-tripped the final TMJ and produced its native map
raster. The production level parser and editor validations passed. The separate
skill's legacy modular audit confirmed component usage (18 ground tiles, 61 road
tiles, six road assets, full ground coverage, no visible reference images), but
reports three stale-policy errors: it still requires four approaches/four spawns
and eight structures while this existing production map uses two/two/sixteen.
Those existing paths and socket counts were not changed.

The older `test_operator_turrets` suite still has three failures. Each was
reproduced against the original HEAD Python source before these changes: pending
operator departure expectation, physical-priority expectation, and an API fixture
without available Progress. This task does not claim a clean full-repository run.
Baseline output is saved as `output/atom-homes-2026-10-19/operator-baseline.txt`.
`git diff --check` passed.

## Live activation

The existing hub was verified in setup/lobby with both robot connections
disconnected, then restarted with the same Conda Python and repository launcher.
The updated hub reports ready, lobby/setup, homes 100/102 and two noncombat
starter previews. No match, robot movement, calibration change or progression
mutation was issued. Existing local configuration/calibration edits were retained.
