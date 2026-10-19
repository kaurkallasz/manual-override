**Archer visibility fixed in the open display**

The live external screen at `localhost:8000/s/gamemaster/p/laser-tag-y/screen`
still had `tower-defence-view.js?v=17` loaded. That page predates the archer
renderer, even though its SSE feed continued receiving ranged combat. Refreshing
that display loaded revision 19. The operator's embedded Y view at the LAN
address already had revision 19. No live game was started, reset or restarted.

The selected presets for all four next-match control tiers are ranged Breaker
archer candidates. The idle engine's default `melee` setting is not the selected
next-match preset: Start freezes the selected tier's settings. Archers replace
breakers; the first authored breaker group is wave 3. With the saved 300-second
initial delay and 95-second interval, its first release is at 490 seconds (8:10).

**Previous match: recorded facts**

Run `9b96bb28543146a3bdf6f0d9121be15d`, started 10 October at 23:14:25 Tallinn,
ended overrun after 708.808 simulation seconds. Its saved settings select ranged
breakers at range 220, draw 0.5 seconds and firing interval 1.5 seconds. It placed
four Green machine-gun turrets and enabled L4 practice upgrades after Start.
The match's frozen pacing remained tier 1.

| Enemy | Released | Combat kills | Remaining |
| --- | ---: | ---: | ---: |
| Grunt | 141 | 83 | 58 |
| Runner | 37 | 37 | 0 |
| Archer / breaker | 47 | 0 | 47 |
| Brute | 2 | 1 | 1 |
| Total | 227 | 121 | 106 |

The recorded archers fired 4,740 arrows, with 4,729 hits and no shield blocks or
misses. They dealt 9,362.602 damage to the core (93.6% of its starting 10,000 HP)
and 1,654.8 to turrets. No archers were killed. These are measured counters from
the saved attempt, not estimates based on wave mix. Eleven shots had not resolved
when the run ended.

**Crowd reconstruction and its limits**

The event log does not contain enemy position history, frame timing or physical
Atom occupancy. It cannot establish exactly where each historical enemy piled
up. `tools/replay_orc_crowding.py` reconstructs the saved settings, timed loadout,
four placements, aim change and refill in isolated engines with the matching
map revision 19 and 0.1-second steps. Two assumptions bracket unrecorded Atom
behavior: lift after each placement, or retain until the next recorded placement.
Neither touches live data, player records or hardware.

Both reconstructions show all 47 archers holding firing positions by 600 seconds:
44 aim at the core, two at socket 10's main turret, and one at its companion.
All 47 survive. Median nearest-neighbor distance among living enemies is about
5.07 pixels at that point; 46 enemies have another within 10 pixels. The normal
collision diameter is 4.4 pixels plus 0.05 pixels padding, while the shared
renderer allocates about 29.3 pixels per normal sprite. Closely packed stationary
archers therefore overlap visually. Ranged combat intentionally stops them for
aim/recovery instead of walking into melee range.

No melee enemy was stationary below 1 pixel/second or road-blocked for at least
100 steps in the sampled frames (500, 550, 600, 650, 700 seconds and finish).
Reconstructed overruns at 702.7 and 703.2 seconds are close to the recorded 708.8,
but do not constitute exact replay. The evidence points to surviving stationary
archers accumulating near firing range, with overlapping sprites, rather than a
demonstrated general pathfinding deadlock. The old display would make those
shooters look like stationary hammer orcs and omit their arrows.

Crowd radii, ranged behavior, damage and match balance were not changed by this
visibility fix. Spacing shooters farther apart would be a gameplay change and
should be compared against the saved trace before tuning it. In particular, the
47 surviving archers' core damage is a balance concern independent of visibility.

**Verification and reproduction**

- `PYTHONPATH=tests .venv/bin/python -m unittest test_ranged_breakers test_ranged_delivery`: 24 passed.
- `node tests/ranged_breaker_renderer.cjs`: pose, slicing, flight-time and fallback checks passed.
- Real-browser fixture: Y operator, Y external screen, landscape phone and tablet all drew archer atlas sprites onto the visible canvas, loaded all 89 assets, showed arrow flights, and produced no JavaScript errors. This verifies local browser layouts, not physical mobile hardware.
- Strengthened `tests/ranged_breaker_browser.cjs` to track the atlas through the orientation cache to actual visible draw calls. Checking only combat metadata would miss the reported failure.
- Repaired the isolated export test's fixture to copy its existing shared UI dependency.
- Screenshots and browser metrics: `../output/archer-visibility-2026-10-10/` (relative to the repository root).

Offline reconstruction command, using an exported attempt JSON and the local
read-only event log:

```sh
.venv/bin/python tools/replay_orc_crowding.py /tmp/previous-orc-game-20261010.json sandboxes/gamemaster/prototypes/photon-game/data/runs.jsonl /tmp/previous-orc-crowding-replay.json
```

Sources: the selected run in Photon Progress's SQLite `attempts` table, Game's
`data/runs.jsonl`, the selected Level presets, and the loaded script URLs in the
user's two actual game views. Historical evidence was read without modification.
