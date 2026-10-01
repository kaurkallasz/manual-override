# Camera Calibration

Gamemaster-only OpenCV chessboard calibration for the shared Webcam prototype.
The default is 15×9 **inner corners**, producing 16×10 cells. The target is
letterboxed as needed so those cells remain physically square on any display.
One scan automatically shifts a smaller checkerboard through nine screen
positions while keeping every cell square. These samples cover the lens field
without moving the fixed camera or display. Calculate the lens model after the
scan. The resulting camera matrix and distortion
coefficients are saved in `calibration.json`.
Corner samples automatically retry slightly inward when a physical screen edge
blocks one or two squares. Up to three positions may be skipped because the
remaining samples overlap; at least six detected patterns are required.

The controller launches `screen.html` as a clean browser window for the physical
display beneath the camera. It renders the exact configured chessboard
at the largest square-cell size the display can fit, supports fullscreen and
inversion, and contains no camera or operator UI.

The preview uses OpenCV `calibrateCamera`, `getOptimalNewCameraMatrix`, and
`undistort`. It deliberately shares Webcam's raw frame rather than opening a
second `VideoCapture`. The corrected output matrix is recentered so the raw
image's geometric centre remains at the same pixel after undistortion.
OpenCV's cached `initUndistortRectifyMap` result is the fixed remapping mesh used
by the preview, corrected stream, and tag-coordinate correction.

## Programmatic output

`corrected_tag_snapshot(tags, detections)` accepts Webcam's raw value arrays and
publishes the named `hhh.camera-correction` version 1 contract. A ready output
contains corrected tracked tags, corrected immediate detections, frame
dimensions, and `corrected: true`. Missing or invalid calibration publishes an
explicit unavailable output with empty tag arrays. It does not apply game rules
or issue a robot command.

Camera Calibration consumes Webcam's public `hhh.webcam.camera`,
`hhh.webcam.frame`, `hhh.webcam.tags`, and `hhh.webcam.controls` v1 outputs through
enabled hub discovery. Disabled, stale, or malformed inputs are unavailable;
there is no private capture/tracker access. The correction callback is installed
at `hub_init` and removed at `hub_stop`. Lens JSON uses atomic replacement.
