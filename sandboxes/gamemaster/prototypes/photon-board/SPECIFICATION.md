# Photon Board

Owns physical-observation truth and nothing else.

- Input: enabled Webcam, Camera Calibration, and Relay public APIs; or authenticated `POST /api/simulation` test observations.
- Output: `board_snapshot()`, `GET /api/board`, or sampled `GET /api/events` SSE; contract `photon.board`, version `1`.
- Invalid or uncorrected camera evidence returns `status: unavailable` and no tags.
- It never issues robot commands and does not know game rules or level geometry.
