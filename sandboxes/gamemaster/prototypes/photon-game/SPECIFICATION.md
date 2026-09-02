# Photon Game

Owns gameplay truth, run lifecycle, settings, simulation, and run events.

- Input: `photon.level` v1 or v2, optional `photon.board` v1, and validated operator commands through `apply_command()` or `POST /api/command`.
- Output: `game_snapshot()` / `GET /api/state` and `game_events()` / `GET /api/events`, contract `photon.game`, version `1`.
- State changes happen in Python. Browsers never advance enemies or calculate damage.
- Physical evidence fails closed. Simulation observations are labeled. Run events stay in module-local ignored `data/`.
- It knows no renderer, sprite, camera implementation, or robot command API.
