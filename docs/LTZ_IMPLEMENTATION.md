# LTZ progression implementation — 2026-09-05

Implemented the LTZ Score plan in Photon Game and its Laser Tag Y presentation.

## Using it

1. Restart the hub when ready to load the new Photon Progress module. Keep Photon
   Progress enabled with Photon Game, Photon Level, Photon Board and the relay.
2. In each participating team's **LTZ Score** tab, create or load a saved player.
   Use **Open player controls** for the LTZ version of the existing controller.
3. The Gamemaster sets four orc percentages in **Photon Game → Game settings**.
   Defaults are 100%, 115%, 130%, 150%, applied once after the global count factor.
   The form previews exact per-wave and total counts before saving.
4. Start a physical **Scored game** from Laser Tag Y. Virtual play is practice.
   Profiles and upgrades are frozen until the attempt ends. Reset banks earned
   kills and records an aborted attempt without a win.
5. Three wins with the selected control unlock the next method. Select the new
   method in LTZ Score when ready. Buy weapon or field upgrades between games.
6. Player statistics, mastery, history graph and result details are below the
   upgrades table. The Gamemaster view links to each player's performance.
7. Use **Photon Progress** to export or preview/import portable progress backups.

## Implementation

- Photon Progress owns durable profiles, transactional credits/purchases,
  mastery, result history, side authorization and backup validation.
- Game freezes the roster, settings and loadouts; its background progress writer
  checkpoints every 30 seconds and uses an atomic terminal-result outbox.
- Defeats and aborts retain kills. Three wins per tier are nonconsecutive and
  unlock controls without spending credits. Nine wins reach Cue Autonomy;
  twelve complete all four mastery counters.
- Control visibility and the existing relay check the saved active tier.
  Player motion stays on the existing connection and retains calibration guards.
- Higher tiers increase scheduled orcs. Group rounding matches the simulation;
  scored Start rejects settings whose rounded totals fail to strictly increase.
  Overflow remains scheduled when the active and deferred caps are full.
- All four weapon upgrades change authoritative damage/health and on-map art.
  Mixed-owner force fields use the weaker endpoint's upgrade. Field capacity
  and visible ribbon width increase without changing collision/marker geometry.
- Twelve generated upgrade atlases supply independent bases and aiming heads;
  a three-row energy atlas supplies field levels 2–4. Both game views use the
  same renderer and Level-owned asset contract. Provenance is beside the art.
- Both teams own their LTZ presentation files. Tesla Coil is the visible and
  canonical name, with explicit legacy key/asset aliases.
- History separates practice and scored play and groups comparable settings and
  loadouts. Completion time excludes pauses; interrupted time is unavailable.

## Verification and operational limits

The Python Photon regression suite, LTZ integration tests, controller adapter
check and browser smoke tests were run against temporary data. Browser checks
cover profile creation/load/reload, tier selection, graph accessibility and all
upgraded weapon layers on both map views. Screenshots were visually inspected
at desktop and mobile sizes. No real players were credited and no robot was
moved or venue hub restarted.

Run Python checks from the repository root:

```sh
.venv/bin/python -m unittest discover -s tests -p 'test_photon_*.py'
.venv/bin/python -m unittest discover -s tests -p 'test_ltz_integration.py'
node tests/ltz_control_ui.cjs
```

For browser checks, start `tests/ltz_browser_fixture.py` with the project Python,
then run `tests/ltz_browser.cjs` with Playwright on `NODE_PATH`. The fixture uses
an OS-assigned localhost port and a temporary database. It cannot connect to
hardware. Stop it after the test.

A hard crash restores saved progress and banked rewards; it does not resume
in-flight physics. Kills after the last 30-second checkpoint can be lost if the
process dies before the terminal outbox is written. Portable backups reject
conflicting records rather than silently overwriting newer player progress.

## Gamemaster virtual testing

Enable **Virtual play** in Laser Tag Y, then open **Virtual Atom controls →
Virtual test unlocks**. Select **Use test unlocks**, choose each turret's
availability/level and the Force Field level, then **Apply test unlocks**.
**Unlock all L4** provides a one-click preview of every top upgrade; **All base
levels** returns to L1. Uncheck the override and apply to restore player levels.

Upgrade changes apply immediately, including during paused/running virtual
practice. Locks prevent new placements; already placed turrets remain until
Reset. Selections survive refresh/reset for the current module session. They
never spend credits, grant mastery, or affect physical play.

Validated with 156 Photon tests, 12 LTZ integration tests, and
`tests/virtual_upgrades_browser.cjs` against `tests/virtual_upgrades_fixture.py`.
The browser exercised individual locks/levels, live changes, the external view,
refresh/reset retention and hiding the panel in physical mode. The fixture has
no robot modules and uses only temporary files.
