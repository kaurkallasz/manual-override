# MCAM1

A Gamemaster tab for **XIAO USB Webcam LL Bulk**, ported from the Camera Studio
work in the 3D printing Lab project. Open `/s/gamemaster/#mcam1` or the module at
`/s/gamemaster/p/mcam1/`.

The hub Mac owns this camera's capture and USB serial controls. The browser uses
same-origin HTTP and SSE: no Chrome extension, Web Serial chooser, localhost-only
browser camera access, or separate Camera Studio server is needed. Existing
Webcam / game perception remains independently owned by its module.

## Use

1. Connect the XIAO and choose **Start preview**.
2. **Connect USB controls** reads the installed firmware and all 22 settings.
3. Turn auto exposure / auto gain off to enable their manual sliders. Release a
   slider to send it; the displayed result is read back from the sensor.
4. Save/load a browser preset, capture a still, or record up to five minutes.
   Stills and recordings include enabled AI overlays. Downloads are local.

The OV3660 lens is fixed focus; software cannot adjust optical focus. Use
480 × 320 / 30 fps as the initial mode (the prior hardware test's preferred
balance), 320 × 240 / 30 fps for smaller frames, or 640 × 480 / 15 fps for detail.
Night mode can lower frame rate. Prior optical latency measurements do not
measure this hub preview's additional processing/network latency.

The installed `ai-v1` firmware optionally detects people on the ESP32-S3.
Confidence, overlap filtering, detection rate, box limit and expiry are exposed.
Boxes are asynchronous observations, never game truth. Old observations and
frames are cleared on loss of signal. MCAM1 does not recalibrate or change game
camera selection.

## Setup and lifecycle

macOS and Xcode Command Line Tools are required for native capture. Install
`requirements.txt` in the hub environment (`pyserial==3.5`, also used by the
repository's Atom tooling, and `esptool==5.4.0`). The native helper builds in a temporary directory
on first Start preview. Camera permission belongs to the hub's Terminal/Python.

Serial discovery requires VID `303a`, PID `8000`, serial `1CDBD443344C`; video
requires exactly one matching product/name. Ambiguous/missing devices fail closed.
No arbitrary device path or executable is accepted from HTTP. The firmware
utility separately discovers explicit USB targets; it does not change which
serial number owns MCAM1's preview. Reconnect stops and reopens this capture only.

`hub_init` owns resources; import performs no I/O. Start/stop/mode changes are
serialized and replace one bounded capture worker. A stalled worker reports
unavailable and is stopped. `hub_stop` closes the serial port and worker. Capture
continues across tab switches to support other authenticated viewers and API
consumers; **Stop preview** releases it globally. Hidden pages close their SSE
connection unless recording. Sensor values remain on the device until reset or
power loss; browser presets must be loaded explicitly.

## Public interfaces

- `still_snapshot()` → `hhh.camera.still`, integer version 1, uncorrected JPEG
  bytes, dimensions, capture timestamp and frame ID; unavailable after 1.5 s.
- `control_snapshot(action, name, value)` → `hhh.camera.controls`, version 1.
- `detection_snapshot(action, name, value)` → `hhh.camera.detections`, version 1;
  `transport_status` separates functioning controls from fresh AI observations.
- `POST api/capture` accepts `{action: "start", mode: "480,320,30"}` or stop.
- `POST api/controls`, `POST api/ai`: get/reset/set commands and validated integers.
- `POST api/disconnect`: closes the serial connection.
- `GET api/events`: one shared SSE snapshot containing video and status/AI.
- `GET api/frame`, `GET api/still`: fresh frame metadata / JPEG download.

Consumers must discover enabled MCAM1 via hub context and validate the contract
name and integer version. Routes inherit Gamemaster authentication.

Run `.venv/bin/python -m unittest discover -s tests -p test_mcam1.py` for the
hardware-free smoke checks.

## Firmware utility

Open **Camera firmware** at the bottom of MCAM1 (or the **firmware updates** link
at the top). This follows Atom Manager's device selection and background flash
log pattern, with a module-owned esptool worker instead of a PlatformIO rebuild.
No Chrome extension is involved.

1. Choose **Bundled ai-v1** to install/recover the release used on the test camera,
   or upload and validate a complete firmware ZIP. Uploading does not flash.
2. Release camera USB. On the target **XIAO ESP32S3 Sense / OV3660 / 8MB flash /
   8MB PSRAM**, hold BOOT, press/release RESET, then release BOOT. If necessary,
   unplug it and reconnect while holding BOOT. Refresh the device list.
3. Select that board's new USB serial/JTAG port, check the physical board, and type
   `XIAO <USB serial>` exactly as shown. Other ESP devices, including Atoms, may be
   listed: the USB PID and ESP32-S3 chip do **not** establish the board/pinout.
4. Press **Flash selected camera**. Keep USB connected and the hub running. MCAM1
   releases video/serial and rejects other capture/control commands during the job.
5. Wait for **Flash verified**. The worker checks all three written images against
   device flash, requests a reset, and releases USB. Press RESET or unplug for five
   seconds if the camera does not reappear. Reconnect controls and start preview to
   verify the camera/AI behavior separately. The preview remains bound to the
   original MCAM1 serial; flashing another unit does not reassign the game camera.

The recovery ZIP is a compact copy of the Lab's installed `ai-v1/bulk` release,
not a live dump of attached flash. Its bootloader, partition table and application
are byte-identical to that release, with the original licenses and provenance in
the manifest. The model is embedded in `firmware.bin`; debug ELF and standalone
model assets are omitted from this distribution. Application SHA-256:
`28274e6ad6c422727055f0f4f287fca45b53e6a1e22aaf88b91bed187adfff42`.

Flashing replaces bootloader at `0x0`, partition table at `0x8000` and application
at `0x10000`. It retains NVS at `0x9000` and does not erase the whole chip or back
up arbitrary prior firmware. Only the established NVS + 4 MiB factory partition
layout is accepted. Secure boot/encrypted boards and other chip/sensor profiles
are rejected. The operator confirms the physical board; the worker independently
checks ESP32-S3, chip MAC against the selected USB serial, and 8MB flash before
writing. No automatic reset/flash of a running camera or other ESP device occurs.

ZIP validation limits compressed/expanded size (32/64 MiB), entry count, paths,
duplicate/encrypted/link entries, image SHA-256, ESP32-S3 image checksums/digests,
8MB image headers, partition-table MD5 and exact layout. Images are revalidated
before launch and in the worker. Hashes establish integrity, not publisher trust,
model accuracy, PSRAM capacity or camera pinout. Only install firmware you trust.
The flash process times out after five minutes. A failed/interrupted flash needs
BOOT + RESET and another attempt. The page never treats failure as completion.
One upload and job are retained in memory/temp storage until hub shutdown; save
the flash log before restarting. A browser refresh reconnects to the existing job.

### Trained-model updates

Train/quantize for ESP32-S3 and integrate the model and its inference/postprocessing
code into the XIAO firmware before compiling. This utility does not train models,
compile firmware, convert arbitrary model formats, or flash a raw `.espdl`,
`.tflite`, `.onnx` or standalone `.bin`. Preserve the bulk UVC descriptors, controls
protocol 1, normalized detection protocol 1 and supported partition layout.
Detection replies can declare a model and default `class_name`, plus an optional
`class_name` per box (each a nonempty string of at most 64 characters). Existing
range, freshness and maximum-ten-box validation still applies. Missing or
incompatible AI replies remain explicitly unavailable.

Package a compatible, already-compiled build from the repository root:

```sh
.venv/bin/python sandboxes/gamemaster/prototypes/mcam1/tools/package_firmware.py \
  --build-dir /absolute/path/to/compiled-images \
  --output /absolute/path/to/my-camera-v2.zip \
  --revision my-camera-v2 --model my-detector-v2 \
  --class-name person --class-name target
```

The build directory must contain `bootloader.bin`, `partitions.bin`, and
`firmware.bin`; the helper validates them, adds board/protocol declarations and
hashes, and refuses to overwrite an existing output. Model names describe the
model already compiled into the application; they do not alter its binary.
Upload that ZIP in MCAM1. The original Lab release ZIP format is also accepted.
For other sensors, ESP32-CAM boards, OTA or separate model partitions, a new
reviewed profile is required; this utility deliberately exposes no arbitrary
addresses or shell commands.

Firmware HTTP routes (all inherit Gamemaster authentication):

- `GET api/firmware/state`, `GET api/firmware/events`: bundle metadata and bounded
  background-job log, with SSE updates at 2 Hz.
- `GET api/firmware/devices`: USB identities and opaque selection tokens; read-only.
- `GET api/firmware/builtin`: download the recovery ZIP.
- `POST api/firmware/upload`: multipart field `bundle`, stage/validate only.
- `POST api/firmware/flash`: JSON `bundle_id`, `device_token`, `confirmation`.

Run `.venv/bin/python -m unittest discover -s tests -p 'test_mcam1*.py'` for camera
and firmware tests. Worker tests mock esptool to verify rejection-before-write and
write/verify/reset ordering; they do not claim a physical flash was performed.

## Verified on 2026-10-11

Connected OV3660 / `ai-v1`, serial `1CDBD443344C`: all three video modes and
returning to 480 × 320 passed. Short capture samples measured 27.5 fps at
320 × 240, 28.7–29.8 fps at 480 × 320, and 14.3 fps at 640 × 480. These are
capture rates, not end-to-end latency measurements. AI reported roughly
120–124 ms inference. Brightness write/readback succeeded and the original value
was restored.

The embedded LAN dashboard displayed the live feed and confirmed a slider
change. It downloaded a readable 480 × 320 PNG and WebM recording. The original
Verbatim game camera remained live at 3840 × 2160 alongside MCAM1. The nine
hardware-free smoke checks and JavaScript syntax check passed.

Firmware utility verification: all 24 MCAM1 tests pass; the original Lab ZIP,
compact bundled ZIP and packaging-helper round trip validate. Browser upload and
selection were checked, including rejection of a running UVC camera as a flash
target even with its confirmation entered. After the idle hub reload, the main
Gamemaster page showed the utility, `ai-v1` controls read back successfully, and
480 × 320 preview + AI remained live at roughly 28–29 fps. No physical firmware
write was performed for these checks; the flash/verify sequence was exercised
with mocked esptool hardware.
