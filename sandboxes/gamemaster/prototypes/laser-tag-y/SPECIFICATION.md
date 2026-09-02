# Laser Tag Y

Presents the game to the Gamemaster and external display. It owns no gameplay state.

- Input: `photon.game` v1 snapshots/SSE and optional `photon.art` v1; authenticated UI commands are forwarded to Photon Game.
- Output: an HTML Canvas view, operator controls, and a control-free external screen.
- If Game is missing or has the wrong contract, Y displays `unavailable`. If Art is missing, Canvas fallbacks keep the game usable.
- It does not read Level or Board directly, calculate combat, persist runs, or control hardware.
