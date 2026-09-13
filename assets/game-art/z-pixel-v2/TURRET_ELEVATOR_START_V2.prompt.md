# Turret elevator start frame v2

Created 2026-09-06 using the built-in imagegen tool. One shared first frame serves machine gun, flamethrower, mortar and Tesla coil. Smaller-opening screenshot is primary; the wider opening is a mechanical motion reference.

The first generation produced an RGB image with a painted checkerboard. A built-in background-extraction edit produced real RGBA alpha. Only that extracted source is used by the project. Standard keyframe export discards alpha below 8, snaps alpha at or above 248 to opaque, fits the square hatch to 896×896 on a 1024×1024 canvas, and creates separate black-matte upload copies. The opaque shaft is retained.

Preserved generated source: `source-sheets/kling-keyframes/turret-elevator-install-first-source-v2.png`.

Final master: `normalized/structures/runtime/kling-keyframes/turret-elevator-install-first-v2.png`.

## Generation prompt

```text
Use case: stylized-concept.
Asset type: one universal first keyframe for a 3-second tower-defense turret elevator installation animation. Generate one square 1024x1024 PNG with a genuinely transparent exterior (real alpha).
Reference roles: first image (12.43.10, smaller narrow opening) is the PRIMARY mechanical and opening-proportion reference. Second image (12.43.19, wider opening) only demonstrates how the same sliding panels continue opening; do not copy its large open state or humanoid. Third image (existing machine-gun first frame) supplies square canvas alignment, dark metal palette, top-down pixel-art language and four small cyan corner anchors. Fourth image (gunmetal ground tile) supplies the subtly textured dark flat map-ground surface. Fifth image (installed machine gun) only supplies final square footprint registration, not a turret to include.
Primary request: a ground-level high-tech elevator hatch just beginning to open, integrated into the game's gunmetal ground. Direct overhead top-down view, square aligned with canvas, absolutely no oblique/isometric camera. Keep a single low-profile square perimeter rim centered, approximately x64 to x960 and y64 to y960, with clear transparent padding outside. Inside that rim are broad flat dark graphite metal floor panels, largely CLOSED. Two opposing segmented flat elevator door leaves have slid horizontally apart a very small distance, revealing one narrow rectangular opaque almost-black shaft slot in the center, about 100px wide and 300px tall. The rest of the split follows subtle stepped/interlocking panel seams and is almost shut, similar to the smaller-opening reference. Show recessed sliding rails on left and right and slim inner bevels that suggest the shaft descends beneath the floor. No hinges. Each leaf remains parallel to the ground and retracts into a side pocket under the stationary rim.
Materials: restrained worn gunmetal-grey ground texture, crisp pixel-art edges and readable chunky pixel shading, fine scratches, small bolts, very restrained amber status accents on latches and tiny cyan corner markers that fit existing tower sprites. Mostly flat functional floor panels, not a raised ornate turret pedestal. Closed panels occupy most of the installation. No turret, no elevator platform, no weapon visible yet. The central narrow slot must be opaque black, not transparent. All floor-panel faces and hardware opaque; only exterior beyond the square rim has true alpha 0, with no baked ground beyond the rim. Keep empty corners genuinely transparent. Do not draw checkerboard squares, black backdrop, colored key backdrop, drop shadows outside the rim, words, letters, numbers, logos, watermarks, arrows, schematic labels, humans, debris, glowing energy in the opening, hinges, a flipped-up trapdoor, or a multi-panel sheet. One polished production game sprite, no surrounding scenery.
```

## Exterior-alpha edit prompt

```text
Use case: background-extraction. Edit target: the provided newly generated top-down hatch sprite. Preserve the existing hatch exactly: the two nearly closed dark steel interlocking floor doors, narrow black central opening, all rail details, cyan corner lights, proportions, texture, and overhead view. Remove ONLY the white/light-gray checkerboard outside the outer square metal hatch rim. Return a PNG with actual RGBA transparency: every background pixel beyond the outer perimeter alpha=0, no colored backdrop and no drawn checkerboard. Preserve the narrow central BLACK SHAFT completely OPAQUE, alpha=255; preserve all dark metal pixels, the entire interior footprint and black seams. This is selective exterior background extraction, not removing black inside the hatch. Requested output square 1024x1024, align hatch center at (512,512), maximum mechanical footprint 896x896, transparent padding. No new design or changed geometry.
```
