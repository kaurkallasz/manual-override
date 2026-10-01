Shared Mobile LTZ presentation assets for Green and Purple. Each player's
`mobile-ltz/prototype.py` freezes this same bundle at hub initialization and
supplies `data-mobile-team` in HTML. Runtime state belongs to the team-specific
module, game arm and LTX frame; these frontend files have no global Python state.

`arm-bridge.js` is served by both LTX modules and uses the existing controller's
`TEAM`, calibration, relay and guarded command path. Camera-normalized points
remain in the original camera frame. `Viewport` alone applies the selected
0°/180° presentation and inverse input transform. XYZ sliders, arrows and
measured-position markers follow that viewport direction; height stays upright.
Their readouts and command payloads retain canonical coordinates.

Regression checks:

- `python -m unittest discover -s tests -p 'test_mobile_*.py'`
- `node tests/mobile_viewport.test.js`
- `node tests/mobile_arm_bridge_smoke.cjs`
- `MOBILE_TEST_TEAM=purple node tests/mobile_arm_bridge_smoke.cjs`
- `node tests/mobile_xyz_steps_smoke.cjs`
- Against `python tests/mobile_ltz_fixture.py --port 8117`, run
  `node tests/mobile_xyz_direction_browser.cjs` for both teams' native touch,
  rotation, fine ranges and marker alignment, then
  `node tests/mobile_xyz_controls_browser.cjs` for calibrated fake-robot controls.
