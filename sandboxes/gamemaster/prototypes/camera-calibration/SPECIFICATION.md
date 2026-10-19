# Camera Calibration

`preview_frame()` exposes `hhh.camera-frame` v1 to authenticated presentation
adapters: status, coordinate_space (`corrected-camera-normalized`), frame_at,
width, height and cached JPEG bytes. The existing shared encoder produces the
image; consumers do not open devices, copy lens calibration or access internals.
Unavailable or older-than-two-second frames return no JPEG. This supplements
`preview_snapshot()` and its existing corrected-stream endpoint.

`preview_frame(mobile=True)` selects the same frame as a cached JPEG bounded to
1920×1080, preserving aspect ratio without upscaling. The existing encoder
prepares it once for all players. Normalized registration and full-resolution
tracking remain unchanged; the response dimensions describe the preview only.
