"""One bounded, replaceable XIAO capture process owned by MCAM1."""
import base64
from collections import deque
import os
from pathlib import Path
import select
import struct
import subprocess
import sys
import tempfile
import threading
import time

MODES = {'480,320,30': (480, 320, 30), '320,240,30': (320, 240, 30), '640,480,15': (640, 480, 15)}
DEVICE = 'XIAO USB Webcam LL Bulk'


class Capture:
    def __init__(self):
        self.lock = threading.RLock()
        self.lifecycle = threading.RLock()
        self.process = self.worker = None
        self.image = None
        self.stamp = 0
        self.sequence = 0
        self.mode = '480,320,30'
        self.error = 'Camera stopped. Start preview to connect.'
        self.times = deque(maxlen=60)
        self.directory = None
        self.helper = None

    def _build(self):
        if self.helper:
            return
        if sys.platform != 'darwin':
            raise RuntimeError('MCAM1 currently requires a macOS hub for native USB video.')
        self.directory = tempfile.TemporaryDirectory(prefix='mcam1-')
        helper = Path(self.directory.name) / 'capture'
        result = subprocess.run(['xcrun', 'swiftc', '-O', str(Path(__file__).with_name('capture.swift')),
                                 '-module-cache-path', str(Path(self.directory.name) / 'cache'), '-o', str(helper)], capture_output=True, text=True, timeout=60)
        if result.returncode:
            raise RuntimeError('MCAM1 capture helper failed to build: ' + result.stderr[-1800:])
        self.helper = str(helper)

    def start(self, mode):
        if not isinstance(mode, str) or mode not in MODES:
            raise ValueError('Choose one of the three supported XIAO capture modes.')
        with self.lifecycle:
            self.stop()
            try:
                self._build()
                process = subprocess.Popen([self.helper, *map(str, MODES[mode])], stdout=subprocess.PIPE,
                                           stderr=subprocess.PIPE, bufsize=0)
                with self.lock:
                    self.process, self.mode = process, mode
                    self.error = 'Waiting for XIAO video frames…'
                self.worker = threading.Thread(target=self._read, args=(process,), daemon=True, name='mcam1-capture')
                self.worker.start()
            except Exception as exc:
                with self.lock:
                    self.error = str(exc)
                raise

    def stop(self):
        with self.lifecycle:
            with self.lock:
                process, worker = self.process, self.worker
                self.process = self.worker = None
                self.image, self.stamp = None, 0
                self.times.clear()
                self.error = 'Camera stopped. Start preview to connect.'
            if process:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        process.kill(); process.wait(timeout=2)
                if worker:
                    worker.join(timeout=3)
                process.stdout.close(); process.stderr.close()

    def close(self):
        self.stop()
        if self.directory:
            self.directory.cleanup()
        self.helper = self.directory = None

    def _read(self, process):
        buffer = bytearray()
        last = time.monotonic()
        try:
            while process.poll() is None:
                with self.lock:
                    if self.process is not process:
                        return
                if not select.select([process.stdout], [], [], .2)[0]:
                    if time.monotonic() - last > 10:
                        raise RuntimeError('XIAO sent no frames. Close other previews, then reconnect; if needed unplug USB for five seconds.')
                    continue
                chunk = os.read(process.stdout.fileno(), 65536)
                if not chunk:
                    break
                buffer.extend(chunk)
                while len(buffer) >= 4:
                    size = struct.unpack('!I', buffer[:4])[0]
                    if not 4 <= size <= 2_000_000:
                        raise RuntimeError('Invalid XIAO frame packet')
                    if len(buffer) < size + 4:
                        break
                    jpeg = bytes(buffer[4:size + 4]); del buffer[:size + 4]
                    if not jpeg.startswith(b'\xff\xd8') or not jpeg.endswith(b'\xff\xd9'):
                        raise RuntimeError('Invalid XIAO JPEG')
                    with self.lock:
                        if self.process is not process:
                            return
                        self.image, self.stamp = jpeg, time.time()
                        self.sequence += 1
                        self.times.append(time.monotonic())
                        self.error = None
                    last = time.monotonic()
            process.wait(timeout=2)
            raise RuntimeError(process.stderr.read(8192).decode(errors='replace').strip() or 'XIAO capture disconnected.')
        except Exception as exc:
            with self.lock:
                if self.process is process:
                    self.image, self.stamp, self.error = None, 0, str(exc)
            if process.poll() is None:
                process.terminate()

    def snapshot(self, preview=False):
        with self.lock:
            ready = self.image is not None and 0 <= time.time() - self.stamp <= 1.5 and self.process is not None and self.process.poll() is None
            w, h, fps = MODES[self.mode]
            measured = (len(self.times)-1)/(self.times[-1]-self.times[0]) if ready and len(self.times)>1 else 0
            result = dict(contract='hhh.mcam1.camera', version=1, status='ready' if ready else 'unavailable',
                          device=DEVICE, mode=self.mode, running=bool(self.process and self.process.poll() is None),
                          width=w if ready else 0, height=h if ready else 0, target_fps=fps,
                          fps=round(measured, 1), frame_id=self.sequence, captured_at=self.stamp if ready else None,
                          error=None if ready else (self.error or 'No fresh XIAO frames. Reconnect the camera.'))
            if preview:
                result['preview'] = 'data:image/jpeg;base64,' + base64.b64encode(self.image).decode() if ready else None
            return result

    def still(self):
        with self.lock:
            data = self.snapshot()
            return {**data, 'image': self.image if data['status'] == 'ready' else None}
