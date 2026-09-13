# Kling VIDEO 3.0 turret-install prompts — sliding elevator v2

Use the shared new hatch start frame for all four turret types, paired with the matching existing turret end frame. This replaces the hinged trapdoor brief; historical prompts are in [KLING_TURRET_INSTALL_PROMPTS_V1_TRAPDOOR.md](KLING_TURRET_INSTALL_PROMPTS_V1_TRAPDOOR.md).

## Reference roles

- **Primary:** `Screenshot 2026-09-06 at 12.43.10 PM.png`, the smaller opening. Nearly closed, flat interlocking panels reveal a narrow dark slot.
- **Motion reference:** `Screenshot 2026-09-06 at 12.43.19 PM.png`, the larger opening. Use only to understand how the opening widens. Do not reproduce the figure, camera angle or scene.
- The game sprites and gunmetal floor establish the overhead view, materials and placement. Instructions here implement the user's request; the screenshots are visual references.

## Upload settings and files

Select **VIDEO 3.0 → Start & End Frames-to-Video**, **3 seconds**, **1:1**, **Multi-Shot off**, and audio off for the visual sprite pass. Generate one turret per clip. Kling's official guide documents start/end-frame support, single-shot mode and durations from 3 to 15 seconds: [Kling VIDEO 3.0 Model User Guide](https://kling.ai/quickstart/klingai-video-3-model-user-guide) (checked 2026-09-06).

All files below are under `normalized/structures/runtime/kling-keyframes/`.

**Transparent master start:** [turret-elevator-install-first-v2.png](normalized/structures/runtime/kling-keyframes/turret-elevator-install-first-v2.png).

**Upload this start:** [turret-elevator-install-first-v2-black.png](normalized/structures/runtime/kling-keyframes/kling-upload-v2/turret-elevator-install-first-v2-black.png). Use the matching black-matte end below. These upload copies have an opaque black exterior; transparency is restored during sprite extraction, so Kling is never asked to animate a checkerboard.

| Turret | Start upload | End upload |
| --- | --- | --- |
| Machine gun | Shared `turret-elevator-install-first-v2-black.png` | [machine-gun-install-last-v2-black.png](normalized/structures/runtime/kling-keyframes/kling-upload-v2/machine-gun-install-last-v2-black.png) |
| Flamethrower | Shared `turret-elevator-install-first-v2-black.png` | [flamethrower-install-last-v2-black.png](normalized/structures/runtime/kling-keyframes/kling-upload-v2/flamethrower-install-last-v2-black.png) |
| Mortar | Shared `turret-elevator-install-first-v2-black.png` | [mortar-install-last-v2-black.png](normalized/structures/runtime/kling-keyframes/kling-upload-v2/mortar-install-last-v2-black.png) |
| Tesla coil | Shared `turret-elevator-install-first-v2-black.png` | [tesla-coil-install-last-v2-black.png](normalized/structures/runtime/kling-keyframes/kling-upload-v2/tesla-coil-install-last-v2-black.png) |

Masters and upload copies are 1024×1024, centered at (512,512), with a nominal 896×896 installation footprint. End-frame masters retain the existing exact runtime cover/base/head artwork. First-frame hardware is a new design; inspect the docking transition for rim-detail changes rather than assuming reference conditioning guarantees identical pixels.

## Three-second choreography

These are direction targets. Conform the final export to 24 fps / 72 frames after reviewing the generated motion; prompting alone cannot guarantee exact beat timing or pixel identity.

| Time | Frames at 24 fps | Action |
| --- | --- | --- |
| 0.000–0.625 s | 0–14 | Start with the narrow slot. Flat panels retract left/right into pockets beneath the stationary frame; the opaque black shaft widens. No turret visible yet. |
| 0.625–1.750 s | 15–41 | A complete, rigid turret and lift deck appear deep inside the shaft at about 55% of their final apparent size. They rise vertically toward the fixed overhead camera, growing smoothly to 100%. |
| 1.750–2.125 s | 42–50 | Deck docks at ground level, covers the black shaft, and locks. The doors remain parked beneath the rim. |
| 2.125–2.750 s | 51–65 | At full size, the upper mechanism performs a short calibration rotation and returns to final aim. Status lights boot from dim amber to the end-frame state. |
| 2.750–3.000 s | 66–71 | Hold the exact final pose for six frames. No movement. |

The camera and ground rim keep a constant size and position. **Only the rising assembly changes apparent size because it approaches the camera.** Use a fixed overhead perspective view with restrained depth. Do not retain the previous “orthographic” or blanket “no scaling” constraints: either would contradict the requested effect. The mechanism is already assembled below ground; it does not grow new components.

## Machine gun

```text
Create one continuous 3-second top-down strategy-game installation animation between the supplied start and end images. Show the machine-gun turret from the end frame, with its exact receiver, paired barrels, armored base and orange details. Fixed direct-overhead perspective camera, square framing, center pivot locked. The ground frame stays fixed in screen position and size throughout. Keep the exterior matte pure black, without scenery or shadows beyond the rim.

0.00–0.625s: Begin with the small central opening exactly as in the start frame. The two flat interlocking floor-door leaves slide left and right into recessed pockets beneath the stationary rim, widening an opaque black underground shaft. Panels stay parallel to the ground. No turret is visible until the doors clear the opening.
0.625–1.75s: Reveal the complete rigid turret on an elevator deck deep in the shaft at roughly 55% of its final apparent size. Raise the deck vertically toward the fixed camera; the turret and deck smoothly increase to 100% as their distance to the camera decreases. Keep the center fixed. Occlude all below-ground parts behind the shaft lip. The ground rim never scales.
1.75–2.125s: Ease the deck into its final ground-level dock and lock the base. The deck conceals the dark shaft. Doors remain retracted underneath the perimeter.
2.125–2.75s: At full size, boot the status lights from dim amber to the colors shown in the end frame. Only the weapon head sweeps clockwise about 40 degrees, then returns to the exact end-frame aim. The base stays docked. No firing, muzzle flash, ammunition or recoil.
2.75–3.00s: Hold completely still in the supplied final silhouette, scale, position, orientation, lighting and detail.

Preserve the supplied game-art style and rigid mechanical identity. No camera zoom, movement, tilt, shake, cuts, hinged trapdoor, rising door panels, growing new parts, stretching, melting, duplicates, people, text, UI, checkerboard, scenery or particles. The apparent size increase belongs only to the elevator assembly approaching the camera.
```

## Flamethrower

```text
Create one continuous 3-second top-down strategy-game installation animation between the supplied start and end images. Show the flamethrower turret from the end frame, with its exact broad nozzle, two orange fuel chambers and armored base. Fixed direct-overhead perspective camera, square framing, center pivot locked. The ground frame stays fixed in screen position and size throughout. Keep the exterior matte pure black, without scenery or shadows beyond the rim.

0.00–0.625s: Begin with the small central opening exactly as in the start frame. The two flat interlocking floor-door leaves slide left and right into recessed pockets beneath the stationary rim, widening an opaque black underground shaft. Panels stay parallel to the ground. No turret is visible until the doors clear the opening.
0.625–1.75s: Reveal the complete rigid turret on an elevator deck deep in the shaft at roughly 55% of its final apparent size. Raise the deck vertically toward the fixed camera; the turret and deck smoothly increase to 100% as their distance to the camera decreases. Keep the center fixed. Occlude all below-ground parts behind the shaft lip. The ground rim never scales.
1.75–2.125s: Ease the deck into its final ground-level dock and lock the base. The deck conceals the dark shaft. Doors remain retracted underneath the perimeter.
2.125–2.75s: At full size, boot the status lights from dim amber to the colors shown in the end frame. Only the nozzle head sweeps clockwise about 40 degrees, then returns to the exact end-frame aim. The fuel housings and base stay docked. No ignition, flame, fuel spray, smoke or heat distortion.
2.75–3.00s: Hold completely still in the supplied final silhouette, scale, position, orientation, lighting and detail.

Preserve the supplied game-art style and rigid mechanical identity. No camera zoom, movement, tilt, shake, cuts, hinged trapdoor, rising door panels, growing new parts, stretching, melting, duplicates, people, text, UI, checkerboard, scenery or particles. The apparent size increase belongs only to the elevator assembly approaching the camera.
```

## Mortar

```text
Create one continuous 3-second top-down strategy-game installation animation between the supplied start and end images. Show the mortar turret from the end frame, with its exact heavy tube, cradle and armored base. Fixed direct-overhead perspective camera, square framing, center pivot locked. The ground frame stays fixed in screen position and size throughout. Keep the exterior matte pure black, without scenery or shadows beyond the rim.

0.00–0.625s: Begin with the small central opening exactly as in the start frame. The two flat interlocking floor-door leaves slide left and right into recessed pockets beneath the stationary rim, widening an opaque black underground shaft. Panels stay parallel to the ground. No turret is visible until the doors clear the opening.
0.625–1.75s: Reveal the complete rigid turret on an elevator deck deep in the shaft at roughly 55% of its final apparent size. Raise the deck vertically toward the fixed camera; the turret and deck smoothly increase to 100% as their distance to the camera decreases. Keep the center fixed. Occlude all below-ground parts behind the shaft lip. The ground rim never scales.
1.75–2.125s: Ease the deck into its final ground-level dock and lock the base. The deck conceals the dark shaft. Doors remain retracted underneath the perimeter.
2.125–2.75s: At full size, boot the status lights from dim amber to the colors shown in the end frame. Only the tube and rotating cradle sweep clockwise about 40 degrees, then return to the exact end-frame aim. The base stays docked. No shell, firing, muzzle flash, smoke or recoil.
2.75–3.00s: Hold completely still in the supplied final silhouette, scale, position, orientation, lighting and detail.

Preserve the supplied game-art style and rigid mechanical identity. No camera zoom, movement, tilt, shake, cuts, hinged trapdoor, rising door panels, growing new parts, stretching, melting, duplicates, people, text, UI, checkerboard, scenery or particles. The apparent size increase belongs only to the elevator assembly approaching the camera.
```

## Tesla coil

```text
Create one continuous 3-second top-down strategy-game installation animation between the supplied start and end images. Show the Tesla-coil turret from the end frame, with its exact central metallic orb, concentric conductor rings, windings and insulated base. Fixed direct-overhead perspective camera, square framing, center pivot locked. The ground frame stays fixed in screen position and size throughout. Keep the exterior matte pure black, without scenery or shadows beyond the rim.

0.00–0.625s: Begin with the small central opening exactly as in the start frame. The two flat interlocking floor-door leaves slide left and right into recessed pockets beneath the stationary rim, widening an opaque black underground shaft. Panels stay parallel to the ground. No turret is visible until the doors clear the opening.
0.625–1.75s: Reveal the complete rigid turret on an elevator deck deep in the shaft at roughly 55% of its final apparent size. Raise the deck vertically toward the fixed camera; the turret and deck smoothly increase to 100% as their distance to the camera decreases. Keep the center fixed. Occlude all below-ground parts behind the shaft lip. The ground rim never scales.
1.75–2.125s: Ease the deck into its final ground-level dock and lock the base. The deck conceals the dark shaft. Doors remain retracted underneath the perimeter.
2.125–2.75s: At full size, boot the status lights from dim amber to the colors shown in the end frame. The upper conductor assembly rotates about 40 degrees and returns to its exact final orientation while a restrained cyan-violet status pulse travels once around the rings. The base stays docked. No extra rings, attack lightning or arcs outside the installation.
2.75–3.00s: Hold completely still in the supplied final silhouette, scale, position, orientation, lighting and detail.

Preserve the supplied game-art style and rigid mechanical identity. No camera zoom, movement, tilt, shake, cuts, hinged trapdoor, rising door panels, growing new parts, stretching, melting, duplicates, people, text, UI, checkerboard, scenery or particles. The apparent size increase belongs only to the elevator assembly approaching the camera.
```

## Transparency and compositing

**Yes: each PNG frame can have different transparent regions.** Render the map first, then the RGBA installation frame. Outside the hatch use alpha 0; door faces, metal, turret, and the exposed black shaft use alpha 255. Intermediate alpha is reserved for clean antialiased edges. A transparent shaft would reveal the map; opaque black creates the underground opening.

For a floor that matches *any* map tile exactly, capture the underlying floor at activation and draw those pixels on the moving door faces with per-frame masks. The supplied sprite uses the project's gunmetal floor appearance; exterior alpha alone cannot make opaque door faces match arbitrary roads or floor textures. This dynamic floor sampling is a separate renderer step, not something a Kling prompt can guarantee.

Recommended order: existing map → opaque shaft/door back layers → rising deck and turret clipped to the shaft while underground → foreground rim. A flattened RGBA sequence can bake this occlusion. During playback, suppress the separate idle turret and opaque socket cover; restore them after the final frame.

Treat the generated clip as RGB unless its actual export is verified to contain alpha. The official guide above does not promise an alpha-video export; a transparent input PNG or the word “transparent” in a prompt is not a guarantee. Our delivery target is an **RGBA PNG sequence or sprite sheet**, with alpha explicitly produced and checked during extraction.

For black-matte clips, derive the exterior mask from the stationary perimeter. Preserve **all enclosed black shaft and mechanism pixels**. Do not globally erase black. Require the rim to stay closed; if generation breaks it, repair the matte so the mask cannot leak into the shaft. A clean chroma backdrop is an alternative only with matching chroma upload references and an appropriate extractor.

Keep one fixed canvas, center, and crop for the whole clip. Register against the stationary rim, never the growing turret. Independently fitting each frame to the turret would erase the depth effect. Resample by timestamps to exactly 72 frames at 24 fps; omit a duplicate sample at 3.000 s. At 30 fps the equivalent sequence is 90 frames.

For deterministic handoff, replace frames 66–71 with the exact runtime composite only after the preceding docking pose matches; inspect frame 65→66 for a visible snap. Check playback over the actual floor and a contrasting background, ensuring the black opening stays solid and the exterior remains clear.

## Delivery status and rebuild

This v2 package supplies the new start art, upload-ready still pairs and revised prompts. New Kling videos and final animated sprite sheets have **not** been generated by this task. Existing v2 runtime videos/sheets still depict the previous trapdoor motion. Do not relabel them as elevator animations.

The old `tools/build_turret_activation_from_videos.sh` and `tools/build_turret_activation_assets.py` are tied to the previous MP4 filenames, 73 decoded samples and timeline; update that import configuration and validate actual new clip timestamps before importing new elevator footage.

Rebuild this still-image package from the preserved generated source:

```sh
PYTHONDONTWRITEBYTECODE=1 <bundled-python> tools/build_turret_kling_keyframes.py
```

Artwork provenance and exact image prompts: [TURRET_ELEVATOR_START_V2.prompt.md](TURRET_ELEVATOR_START_V2.prompt.md). Machine-readable timing and paths: [kling-turret-install-keyframes.json](kling-turret-install-keyframes.json).
