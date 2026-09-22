# Arm sliders and position illustration

J2 and J3 use separate native range sliders, with Elbow above Shoulder and the Fine tune switch alongside them on the right. The panel has no heading row. The white version 01 technical sketch anchors its base so the shoulder half-circle’s right edge aligns with the slider panel’s right edge above the sliders and is a read-only illustration that previews the full slider-selected pose, with its pedestal hidden and a goniometer at each hinge. It accepts no pointer or keyboard controls; map gestures pass through it. The horizontal anchor uses the measured slider-panel edge and the shoulder-guide radius. This exact alignment takes priority over containing the full enlarged arm at extreme poses. The sketch and joint-guide radii render at 2× their original scale. The base, scale and vertical position stay fixed throughout both slider and telemetry movement; only a resize or changed limits can reframe the drawing.

- **Shoulder · J2** and **Elbow · J3** choose target angles within runtime limits. J2’s sketch bearing is −120° + J2, so moving its slider right swings the elbow right. The confirmed red link and goniometer use the same mapping.
- Normal steps are 0.5°; the visible **Fine tune 10×** switch uses 0.05°. The slider readout is the target, while the sketch smoothly previews the full selected angle independently of the slow command progression. While previewing, the caption says Target preview and thin glowing red link overlays and slider ticks mark confirmed positions. At rest it returns to confirmed telemetry.
- Targets approach at up to 12°/s with a 200 ms ramp and at most 1.2° lead over confirmed telemetry. Releasing a slider retains its selected target. Each joint keeps its own selected goal and motion progress; editing the other slider does not replace it. Selected goals and issued commands remain separate from arriving telemetry, including after a joint reaches its goal.
- Stop, stale telemetry, pointer cancellation, lost focus and backgrounding cancel the pending approach. The existing serialized 80 ms sender remains the only command path.
- J3 uses the existing absolute forearm convention and the tool stays vertical. The active joint's goniometer brightens while approaching its target.
- Red slider ticks use two 90 ms smoothing stages, preserving continuous position and velocity between telemetry packets (about 180 ms of visual lag during steady movement). Each tick has a thin bright core and a symmetric gradient halo. Smoothing is presentation only, resets on invalid telemetry, suspension or long frame gaps, and never feeds arm commands.

- Fine tune also zooms each slider to one tenth of its full range around the selected target (11° for J2, 13° for J3 with current limits). The window stays fixed during adjustment and shifts inward at physical limits. Both modes keep the same panel height; the square switch indicates zoom without extra range labels. Toggle off to restore the full range, or off/on to center a new window. Red ticks use the same scale; arrows indicate confirmed positions outside the zoom window. Zoom never changes goals or command limits.

`joint-rig.js` supplies geometry, motion limiting and the illustration. At startup/export it is bundled into `mobile.js`, preserving the six-file hosted client contract. No new hosted script route or PHP deployment is required.

## Verification

```sh
node --test tests/mobile_joint_rig.test.js
.venv/bin/python -m unittest discover -s tests -p 'test_mobile*.py'
.venv/bin/python tests/mobile_ltz_fixture.py
```

Nineteen geometry/motion/rendering tests and 20 Python tests pass. Rendering tests verify minimum/maximum slider poses with stationary telemetry, endpoint clamps, invalid previews, independent targets, stale-packet retention, small out-of-order telemetry, actual-position overlays, and absence of input elements in the illustration. Indicator tests cover sparse packets, continuous movement, convergence, reversals, frame-rate independence, independent joints, and suspension resets. The hosted regression checks that the helper is bundled before the player starts.

Chrome checks use the isolated virtual fixture at http://127.0.0.1:8117/s/green/p/mobile-ltz/: independent slider adjustment, sketch transforms following confirmation, 0.05° precision, Stop, and phone layouts. Standalone browser smoke scripts are updated and syntax checked separately. No physical robot is used.

The main hub freezes the client at startup. Restart it after UI changes, then refresh the phone page. This revision supersedes the earlier direct head/elbow drag interaction.

## Base rotation dial

The J1 dial has a fixed semicircular scale and a square movable target selector matching the arm slider thumbs. Tap or drag the arc to select an angle; clockwise still decreases J1, preserving the robot control convention. The readout is the selected target. A separate glowing red needle follows confirmed J1 telemetry with the same smoothing used by the joint slider indicators. The target remains independent of late telemetry until Stop or suspension clears it. Both use runtime joint limits, and commands continue through the existing serialized sender.

## Gripper buttons

Suck and Blow are compact toggle buttons inside the base semicircle, below the base-angle readout, replacing the Base rotation label and the old vertical three-position switch. Only one can be active. Press the active button again for pump off; there is no separate Off button. The pending choice appears immediately, both buttons wait for the existing serialized pump-command acknowledgement, and the server-confirmed mode then becomes authoritative. Older telemetry cannot roll back a newer acknowledgement. Stop and suspension clear the selection. The controls are siblings of the base slider, so clicking them cannot rotate the base.
