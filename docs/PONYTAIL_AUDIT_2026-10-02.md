# Ponytail audit — 2 October 2026

The current Mobile LTZ design is leaner than the older prototypes: both teams
share presentation code, use native controls and the existing transport, and
delegate gameplay, calibration and physical execution to their owners. The
largest avoidable complexity is retained duplicate controllers and presentation
files. Whole-repository architectural compliance is **partial**, because some
legacy player prototypes still violate the module rules.

## Basis and scope

Applied the user-supplied [Ponytail audit skill](https://github.com/DietrichGebert/ponytail/blob/e3ba2aa6f1e6f0bc4d69eb09c9f0d0a93af56156/skills/ponytail-audit/SKILL.md),
its [review rules](https://github.com/DietrichGebert/ponytail/blob/e3ba2aa6f1e6f0bc4d69eb09c9f0d0a93af56156/skills/ponytail-review/SKILL.md)
and [base rules](https://github.com/DietrichGebert/ponytail/blob/e3ba2aa6f1e6f0bc4d69eb09c9f0d0a93af56156/skills/ponytail/SKILL.md).
The reference was read at commit `e3ba2aa6f1e6f0bc4d69eb09c9f0d0a93af56156`;
no plugin, hook or dependency was installed.

Reviewed the working tree based on `2ea92b5`, including the pending progression
and calibration implementation. Inventory covered 287 Python, JavaScript, HTML,
CSS, PHP and CJS files (109,393 physical lines before this audit's regression
test). Scanned routes, imports, dependency manifests, lifecycle starts and exact
file duplicates across that tree. Read the Mobile LTZ control/calibration flow
and its owner boundaries in more depth. This is a broad structural audit with
targeted flow review, not a line-by-line correctness certification of all files.

Ponytail findings below concern complexity only. Architectural and correctness
observations are separated afterward. Removal estimates are conservative
planning estimates, not measured refactoring results. None of the proposed
deletions or consolidations was applied.

## Ranked simplification opportunities

- **shrink:** Consolidate the 5,241-line older Auto Pickup controller with the existing 5,339-line shared controller; they contain 5,136 matching lines. Reuse the shared implementation with the existing path/team distinctions, preserve the older game's behavior and asset routes, and verify both entry points. Approximately 5,000 lines removable. [Older controller](../sandboxes/green/prototypes/auto-pickup-game/controller.html), [shared controller](../shared/robot_controls/controller.html).
- **delete:** Remove two unserved legacy pages: Purple's local `auto-pickup-game/controller.html` (1,622 lines) and Green's old `calibrate.html` (1,132 lines). Purple's route serves Green's controller instead; `/calibrate` serves `calibrate2.html`. No source references to the old calibration filename were found, and these blueprints expose no generic file route. Replacement: nothing; retain route regression checks. [Purple routing](../sandboxes/purple/prototypes/auto-pickup-game/prototype.py#L13), [Green routing](../sandboxes/green/prototypes/auto-pickup-game/prototype.py#L32).
- **shrink:** Share the three byte-identical 627-line Cartesian test pages through shared presentation assets, retaining separate authenticated team routes. Approximately 1,200 lines removable after routing changes. [Cartesian page](../sandboxes/gamemaster/prototypes/cartesian-xyz-test/index.html).
- **shrink:** Share the three byte-identical 481-line Playfield Areas controller pages; keep each module's mutable state separate. Approximately 900 lines removable. [Playfield presentation](../sandboxes/gamemaster/prototypes/playfield-areas/controller.html).
- **shrink:** Share the two byte-identical 863-line Pickup Game player pages through presentation assets. Approximately 800 lines removable. [Green Pickup Game](../sandboxes/green/prototypes/pickup-game/controller.html), [Purple Pickup Game](../sandboxes/purple/prototypes/pickup-game/controller.html).
- **shrink:** Share the identical LTZ Score HTML (620 lines) and JavaScript (114 lines). Keep Green/Purple routes and authorization distinct, as Mobile LTZ already does. Approximately 700 lines removable. [Score page](../sandboxes/green/prototypes/ltz-score/index.html), [score script](../sandboxes/green/prototypes/ltz-score/score.js).
- **shrink:** Share the identical 626-line Green/Purple Joint Angles pages. Approximately 600 lines removable; retain the robot limits, validation and per-team controller state. [Green joint page](../sandboxes/green/prototypes/joint-angles-test/index.html), [Purple joint page](../sandboxes/purple/prototypes/joint-angles-test/index.html).
- **shrink:** Reuse `shared/robot_controls/calibrate2.html` for the older calibration presenters; Green's 145-line copy is identical. Approximately 100 lines removable while also removing Purple's sibling-file dependency. [Shared Cal 2](../shared/robot_controls/calibrate2.html), [Purple presenter](../sandboxes/purple/prototypes/auto-pp-cal-2/prototype.py#L5).
- **shrink:** Centralize the pure mobile bundle assembly/rendering functions used by both 103-line Mobile LTZ adapters and the exporter. The adapters have 99 matching lines, and helper concatenation is repeated in all three places. Keep blueprint identity, team and live state local; use a small shared function rather than a new framework. Approximately 60 lines removable. [Green builder](../sandboxes/green/prototypes/mobile-ltz/prototype.py#L17), [Purple builder](../sandboxes/purple/prototypes/mobile-ltz/prototype.py#L17), [exporter](../tools/mobile-ltz/export.py#L38).

net: -12,000 lines, -0 deps possible. This is a rounded estimate across the
independent findings above, subject to preserving behavior and route tests.

## How Mobile LTZ stacks up

| Area | Assessment | Evidence and limit |
| --- | --- | --- |
| Reuse between players | Good, with a small remaining duplication | `shared/mobile_ltz` and `shared/robot_controls` serve both teams. Python bundle adapters and older controllers still duplicate implementation. |
| Dependencies and native features | Good | Plain HTML/CSS/JavaScript, native range/select/date controls and SVG; existing Flask/stdlib delivery. OpenCV and NumPy serve real camera/calibration requirements. No verified removable runtime dependency. |
| Gameplay authority | Good on reviewed paths | Mobile submits commands; Game sequences play, Progress owns profiles/rewards/history, and Cal 2 owns measurements/receipts. The shared countdown is server-owned. |
| Hardware boundaries | Preserve | Mobile embeds the existing LTX controller and uses the Relay path. Origin/session/revision checks, exclusive calibration, current sensor data and acknowledged stops are necessary behavior, not excess abstraction. |
| Calibration complexity | Mostly justified | Six ground points, four raised samples, cached marker positions, saved rigs, Purple orientation and manual GM entry are explicit requirements. Persistent receipts and atomic writes address real restart/retry cases. |
| Networking | Justified | Native EventSource is used locally. The fetch-based direct stream supports required headers and the hosted path; watchdog/recovery logic has regressions. Do not replace it blindly with a second native reconnect loop. |
| Rendering complexity | Mixed | Compact code does not necessarily mean simpler code. Journey's hand-maintained render signature omitted height state and caused a reproducible stale button; see the correction below. |
| Evidence | Strong automated coverage; physical acceptance outstanding | Current unit suites pass and the new regression covers both teams. No real robot motion or successful physical calibration was performed for this audit. |

Do not merge Game, Progress, Cal 2 and Relay merely to reduce file count: they
own different state and failure boundaries. Likewise, the tests around
cross-team access, stale feedback, stop acknowledgement, idempotent rewards and
restart recovery protect real requirements. Ponytail does not justify removing
them. The older Laser Tag Z engine and live direct-driver tools were not counted
as dead code simply because newer modules exist; their entry points remain.

## Separate architectural and correctness review

1. **Legacy lifecycle and persistence violations remain.** Both player-owned
   Playfield Areas modules start a saver thread at import, have no shutdown
   path for that thread, and write JSON in place while swallowing write errors.
   These conflict with `AGENTS.md`. The newer Gamemaster owner has lifecycle and
   atomic persistence support; that does not make the old copies compliant.
   [Green lines 444–488](../sandboxes/green/prototypes/playfield-areas/prototype.py#L444)
   and [Purple counterpart](../sandboxes/purple/prototypes/playfield-areas/prototype.py#L444).
   This is an open legacy issue, outside the current Mobile LTZ owner path.
2. **Legacy sibling-file reads remain.** Purple Auto Pickup serves files inside
   Green's module, and Purple Auto PP Cal 2 does the same. Green Auto Pickup's
   calibration route also reads its Cal 2 sibling. These violate the declared
   file-ownership rule. Use the existing shared presentation directory or an
   owner-served public descriptor while keeping route identities intact.
   [Purple Auto Pickup](../sandboxes/purple/prototypes/auto-pickup-game/prototype.py#L14),
   [Purple Cal 2](../sandboxes/purple/prototypes/auto-pp-cal-2/prototype.py#L5),
   [Green Auto Pickup](../sandboxes/green/prototypes/auto-pickup-game/prototype.py#L15).
3. **Completion refresh bug found and fixed before this push.** Once the shared
   countdown reached zero, a transport-height-only update did not change
   Journey's render signature. The completion button could remain disabled.
   Updates arriving while the save request was busy could also leave that
   disabled state displayed. Added both height values to the signature and
   rerendered when a save finishes. The isolated browser regression failed
   before the fix and now passes for Green and Purple, including the in-flight
   update case. [Journey UI](../shared/mobile_ltz/journey.js#L57),
   [regression](../tests/mobile_journey_render_browser.cjs).

The reviewed new path uses enabled module discovery, named integer-versioned
contracts, explicit unavailable states, owner-local persistence and the existing
SSE mechanism. That is supported by the focused contract/isolation tests; it
does not establish that every historical prototype satisfies those rules.

## Verification and next work

- `python -m unittest discover -s tests -p 'test_*.py'`: **475 passed** using the
  existing project runtime and bundled dependencies.
- `node --test tests/*.test.js`: **46 passed**.
- `node tests/mobile_journey_render_browser.cjs`: **both teams passed**, using
  real journey rendering with synthetic state and no camera/robot.
- `node tests/mobile_calibration_browser.cjs`: **both teams passed again after
  the fix**, against the fake-arm fixture: six-plus-four measurements,
  drag/Fine tune, folded completion and return to the game.
- `git diff --check` passed. Source candidates were checked for common credential
  patterns; local credentials, machine calibration files, session stores and
  robot command logs are excluded from the publication set.

Suggested implementation order: delete confirmed unserved pages, consolidate
identical score/calibration presentation, then unify the large older controller
with the shared controller under route regressions. Address the legacy
lifecycle/persistence violations in a separate bounded change. Avoid a broad
engine rewrite or removal of sensor/stop guards. This report authorizes no such
refactor; it records the audit requested by the user.
