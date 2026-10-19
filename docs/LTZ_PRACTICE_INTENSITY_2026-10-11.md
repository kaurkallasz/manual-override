# Practice unlocks select saved spawn intensity

Game Master Start already chose the selected control tier's saved preset.
Changing Unlocks during a match updated control access and defense upgrades,
but left the active spawning tier/settings unchanged.

An explicit control selection now resolves the current map's selected tier
preset and updates remaining practice spawns immediately. Existing enemies,
deferred spawns and completed groups are preserved. Unfinished groups restart
their remaining release clock at the new rate, without releasing a backlog
all at once. The remaining fraction of the next-wave delay is rescaled.
Reapplying the same selection leaves those clocks alone. Clearing the override
restores the roster's tier. Reset/Start continues to load the full saved preset.

The Game Master panel now labels L1–L4, previews the selected saved intensity,
and reports the active tier, orc total, wave gap and release pace. A match
switched partway through can have a different total than a fresh match,
because enemies already released are retained.

Practice receipts keep their original credit weights/revision and cumulative
kill validation, while allowing their spawn count to change. Practice still
earns no player credits or mastery. Scored attempts keep frozen schedules,
strict count limits and the live-unlock prohibition.

## Verification

- 199 Python checks passed across practice intensity, presets, LTZ integration,
  admin/economy, control journey, Mobile LTZ, Photon framework, horde, ranged
  enemies and progress. The five new intensity cases also passed after limiting
  intensity-change telemetry to the latest 16 entries.
- Browser checks passed for L2, L3 and L4 both in setup and during one running
  practice match. Each selected the exact saved count, gap and pace; the run ID
  stayed unchanged, with no JavaScript errors.
- Unit cases additionally exercise partially released groups, queued enemies,
  completed groups, pause, downgrades, initial-delay changes, repeated Apply,
  invalid command atomicity and saving a victory above its original spawn budget.
- Reloaded the live hub while it was in setup with both arms disconnected,
  then refreshed and verified Game Master. Camera tracking resumed ready.

Live selected presets at rollout were the existing Breaker archer candidates:

| Control | Fresh-match orcs | Wave gap | Release pace |
| --- | ---: | ---: | ---: |
| L1 Joint | 1,009 | 95.0 s | 1.00× |
| L2 Cartesian XYZ | 1,088 | 88.0 s | 1.08× |
| L3 Targeting | 1,170 | 81.9 s | 1.16× |
| L4 Cue autonomy | 1,250 | 76.6 s | 1.24× |

These are saved values, not hardcoded replacements. Future saved selections
are resolved when applying the control tier.

```sh
PYTHONPATH=tests .venv/bin/python -m unittest test_practice_intensity
PYTHONPATH=tests .venv/bin/python tests/ltz_admin_fixture.py --port 56054
# In another shell with Playwright available:
node tests/practice_intensity_browser.cjs
```

Browser screenshot/results: `../../output/control-intensity-2026-10-11/`.
