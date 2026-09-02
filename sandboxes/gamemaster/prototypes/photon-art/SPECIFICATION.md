# Photon Art

Owns static visual assets and nothing else.

- Input: repository changes only; there is no runtime mutation route.
- Output: `art_snapshot()` or `GET /api/manifest`, contract `photon.art`, version `2`, plus immutable files under `assets/`.
- Manifest file paths are relative to the module's `assets/` route. A consuming
  presentation supplies its own mounted URL prefix rather than importing files.
- The `laser_tag_z_runtime` pack preserves the proven Z tower, enemy, and combat-effect images without moving rendering behavior into this repository.
- Games must remain usable when this optional module is missing by drawing simple Canvas fallbacks.
