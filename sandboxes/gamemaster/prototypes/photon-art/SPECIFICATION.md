# Photon Art

Owns static visual assets and nothing else.

- Input: repository changes only; there is no runtime mutation route.
- Output: `art_snapshot()` or `GET /api/manifest`, contract `photon.art`, version `1`, plus immutable files under `assets/`.
- Games must remain usable when this optional module is missing by drawing simple Canvas fallbacks.
