"""MCAM1's bounded bundle validation and single-device flash jobs. No import I/O."""
import copy
import hashlib
import importlib.metadata
import json
from pathlib import Path, PurePosixPath
import re
import struct
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import zipfile

MAX_UPLOAD = 32 * 1024 * 1024
MAX_EXPANDED = 64 * 1024 * 1024
TARGET = 'Seeed Studio XIAO ESP32S3 Sense, OV3660, 8MB flash/8MB PSRAM'
LAYOUT = {'0x0': 'bootloader.bin', '0x8000': 'partitions.bin', '0x10000': 'firmware.bin'}
PARTITIONS = [('nvs', 1, 2, 0x9000, 0x6000), ('factory', 0, 0, 0x10000, 0x400000)]
COMPATIBILITY = dict(schema=1, board='seeed-xiao-esp32s3-sense', sensor='OV3660',
                     flash_bytes=8388608, psram_bytes=8388608, controls_protocol=1, ai_protocol=1)


def label(value, maximum=100):
    return isinstance(value, str) and 0 < len(value) <= maximum and all(ord(c) >= 32 for c in value)


def tool_error():
    try:
        if importlib.metadata.version('esptool') == '5.4.0':
            return None
    except importlib.metadata.PackageNotFoundError:
        pass
    return 'Install MCAM1 requirements.txt in the hub environment (esptool 5.4.0 required).'


def validate_bundle(path):
    """Read a ZIP without extracting user paths; return metadata and flash bytes.

    Checks integrity and declared compatibility, not publisher authenticity or
    whether a custom model actually works. Only the established factory layout
    is supported; arbitrary flash offsets and executable build scripts are not.
    """
    if path.stat().st_size > MAX_UPLOAD:
        raise ValueError('Firmware ZIP exceeds 32 MiB')
    if tool_error():
        raise RuntimeError(tool_error())
    from esptool.bin_image import LoadFirmwareImage
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            if not entries or len(entries) > 100 or sum(e.file_size for e in entries) > MAX_EXPANDED:
                raise ValueError('Bundle has too many files or exceeds 64 MiB expanded')
            names = set()
            for entry in entries:
                name = entry.filename
                p = PurePosixPath(name)
                if (name in names or p.is_absolute() or '..' in p.parts or '\\' in name
                        or '\x00' in name or ':' in name or (entry.external_attr >> 16) & 0o170000 == 0o120000
                        or entry.flag_bits & 1):
                    raise ValueError('Unsafe, duplicate, linked or encrypted ZIP entry')
                names.add(name)
            manifests = [e for e in entries if PurePosixPath(e.filename).name == 'manifest.json']
            if len(manifests) != 1 or manifests[0].file_size > 128 * 1024:
                raise ValueError('Expected one manifest.json, at most 128 KiB')
            manifest = json.loads(archive.read(manifests[0]))
            if not isinstance(manifest, dict):
                raise ValueError('Invalid firmware manifest')
            if manifest.get('target') != TARGET or manifest.get('variant') != 'bulk':
                raise ValueError('Only XIAO ESP32S3 Sense / OV3660 / 8MB bulk firmware is supported')
            if 'mcam1' in manifest and manifest['mcam1'] != COMPATIBILITY:
                raise ValueError('Unsupported MCAM1 board or protocol declaration')
            if manifest.get('flash_layout') != LAYOUT or not label(manifest.get('revision')):
                raise ValueError('Expected bootloader, partition table and application at the MCAM1 offsets')
            ai = manifest.get('ai')
            if ai is not None and (not isinstance(ai, dict) or not label(ai.get('model'), 64)
                    or not isinstance(ai.get('classes'), list) or not 1 <= len(ai['classes']) <= 80
                    or not all(label(c, 64) for c in ai['classes'])):
                raise ValueError('AI metadata needs a model name and class labels')
            hashes = manifest.get('sha256')
            if not isinstance(hashes, dict) or not set(LAYOUT.values()) <= hashes.keys() or len(hashes) > 50:
                raise ValueError('Manifest must contain SHA-256 hashes for all three flash images')
            prefix = str(PurePosixPath(manifests[0].filename).parent)
            prefix = '' if prefix == '.' else prefix + '/'
            binaries = {}
            for name, digest in hashes.items():
                if not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}', name) or not isinstance(digest, str) or not re.fullmatch(r'[a-f0-9]{64}', digest):
                    raise ValueError('Invalid filename or SHA-256 in manifest')
                content = archive.read(prefix + name)
                if hashlib.sha256(content).hexdigest() != digest:
                    raise ValueError(f'SHA-256 mismatch: {name}')
                if name in LAYOUT.values():
                    binaries[name] = content
            for name, limit in [('bootloader.bin', 0x8000), ('firmware.bin', 0x400000)]:
                raw = binaries[name]
                if not 24 <= len(raw) <= limit or raw[0] != 0xe9 or int.from_bytes(raw[12:14], 'little') != 9:
                    raise ValueError(f'{name}: expected an ESP32-S3 image fitting its partition')
                image = LoadFirmwareImage('esp32s3', raw)
                if (image.checksum != image.calculate_checksum() or not image.append_digest
                        or image.stored_digest != image.calc_digest or image.flash_size_freq >> 4 != 3):
                    raise ValueError(f'{name}: invalid checksum, digest or 8MB flash header')
            table = binaries['partitions.bin']
            if len(table) != 3072:
                raise ValueError('Expected a 3072-byte ESP-IDF partition table')
            parsed, md5_at = [], None
            for offset in range(0, len(table), 32):
                entry = table[offset:offset+32]
                if entry[:2] == b'\xeb\xeb':
                    if entry[2:16] != b'\xff'*14 or entry[16:] != hashlib.md5(table[:offset]).digest():
                        raise ValueError('Invalid partition-table MD5')
                    md5_at = offset
                    break
                if entry[:2] != b'\xaa\x50':
                    raise ValueError('Malformed partition table')
                _, kind, subtype, start, size, name, flags = struct.unpack('<HBBII16sI', entry)
                if flags:
                    raise ValueError('Encrypted or flagged partitions are unsupported')
                parsed.append((name.rstrip(b'\0').decode('ascii'), kind, subtype, start, size))
            if parsed != PARTITIONS or md5_at is None or table[md5_at+32:] != b'\xff'*(len(table)-md5_at-32):
                raise ValueError('Requires the MCAM1 NVS + 4 MiB factory layout; OTA/data partitions are unsupported')
            info = dict(revision=manifest['revision'], target=TARGET, ai=ai,
                        application_bytes=len(binaries['firmware.bin']),
                        application_sha256=hashes['firmware.bin'],
                        bundle_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                        layout=LAYOUT, compatibility='Validated images, hashes and partition layout')
            return info, binaries
    except (zipfile.BadZipFile, KeyError, UnicodeError, TypeError, struct.error, EOFError) as exc:
        raise ValueError(f'Invalid firmware bundle: {exc}') from exc


def devices():
    from serial.tools.list_ports import comports
    result = []
    for port in comports():
        if port.vid != 0x303a or port.pid not in (0x1001, 0x8000) or not port.serial_number:
            continue
        # macOS may expose tty and cu aliases. Only list outbound/cu endpoints.
        if sys.platform == 'darwin' and not port.device.startswith('/dev/cu.'):
            continue
        identity = dict(port=port.device, serial=port.serial_number, vid=port.vid,
                        pid=port.pid, location=port.location or '')
        token = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        result.append(dict(**identity, token=token, description=port.description or 'ESP USB device',
                           flashable=port.pid == 0x1001))
    return sorted(result, key=lambda d: d['port'])


def resolve_device(token):
    matches = [device for device in devices() if device['token'] == token]
    if len(matches) != 1:
        raise ValueError('Selected USB identity changed or disappeared. Refresh and select the target again.')
    if not matches[0]['flashable']:
        raise ValueError('Put the target into download mode with BOOT + RESET, then refresh USB devices.')
    return matches[0]


class FirmwareManager:
    def __init__(self, here):
        self.here = here
        self.lock = threading.RLock()
        self.temp = tempfile.TemporaryDirectory(prefix='mcam1-firmware-')
        self.builtin_path = here / 'firmware/xiao-ai-v1-bulk.zip'
        self.builtin = self.upload = None
        self.error = tool_error()
        if not self.error:
            try:
                self.builtin, _ = validate_bundle(self.builtin_path)
                self.builtin['id'] = 'builtin'
            except Exception as exc:
                self.error = str(exc)
        self.job = dict(status='idle', phase='idle', log=[], id=None)
        self.process = self.thread = None
        self.closed = False

    def busy(self):
        with self.lock:
            return self.job['status'] == 'running'

    def snapshot(self):
        with self.lock:
            return copy.deepcopy(dict(builtin=self.builtin, upload=self.upload, error=self.error, job=self.job))

    def stage(self, stream):
        with self.lock:
            if self.closed or self.busy():
                raise RuntimeError('Firmware utility is busy or closed')
            path = Path(self.temp.name) / 'incoming.zip'
            try:
                with path.open('wb') as output:
                    total = 0
                    while chunk := stream.read(65536):
                        total += len(chunk)
                        if total > MAX_UPLOAD:
                            raise ValueError('Firmware ZIP exceeds 32 MiB')
                        output.write(chunk)
                info, _ = validate_bundle(path)
                info['id'] = uuid.uuid4().hex
                path.replace(Path(self.temp.name) / 'upload.zip')
                self.upload = info
                return copy.deepcopy(info)
            finally:
                path.unlink(missing_ok=True)

    def start(self, bundle_id, device_token, confirmation, release_camera):
        with self.lock:
            if self.closed or self.busy():
                raise RuntimeError('A firmware job is already running or the utility is closed')
            if self.error:
                raise RuntimeError(self.error)
            info = self.builtin if bundle_id == 'builtin' else self.upload
            if not info or info['id'] != bundle_id:
                raise ValueError('Select a validated firmware bundle first')
            target = resolve_device(device_token)
            if confirmation != f"XIAO {target['serial']}":
                raise ValueError('Confirm the physical XIAO target by typing XIAO followed by its USB serial')
            path = self.builtin_path if bundle_id == 'builtin' else Path(self.temp.name) / 'upload.zip'
            checked, _ = validate_bundle(path)
            if checked['bundle_sha256'] != info['bundle_sha256']:
                raise ValueError('Bundle changed since validation; select it again')
            release_camera()
            # Freeze the selected package for this job. An upload cannot replace it.
            job_path = Path(self.temp.name) / 'job.zip'
            job_path.write_bytes(path.read_bytes())
            self.job = dict(status='running', phase='connecting', id=uuid.uuid4().hex,
                            target=target, revision=info['revision'], started_at=time.time(),
                            application_sha256=info['application_sha256'], log=['Camera capture and controls released.'])
            self.thread = threading.Thread(target=self._run, args=(job_path, target), daemon=True, name='mcam1-flash')
            self.thread.start()
            return self.snapshot()

    def _run(self, bundle, target):
        process = None
        try:
            command = [sys.executable, '-u', str(self.here / 'flash_worker.py'), str(bundle), target['token']]
            with self.lock:
                if self.closed:
                    raise RuntimeError('Hub stopped before flashing started')
                self.process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                                stderr=subprocess.STDOUT, text=True, bufsize=1)
                process = self.process
            timed_out = threading.Event()
            def timeout():
                timed_out.set()
                if process.poll() is None:
                    process.kill()
            timer = threading.Timer(300, timeout)
            timer.start()
            try:
                for line in process.stdout:
                    line = re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', line).strip()[:600]
                    if not line:
                        continue
                    with self.lock:
                        if line.startswith('MCAM1_PHASE '):
                            self.job['phase'] = line.split(' ', 1)[1]
                        self.job['log'] = (self.job['log'] + [line])[-250:]
                code = process.wait()
            finally:
                timer.cancel()
                process.stdout.close()
            with self.lock:
                if code != 0 or timed_out.is_set() or self.job['phase'] != 'verified':
                    raise RuntimeError('Flash failed or timed out. Re-enter BOOT + RESET and retry; see log.')
                self.job.update(status='done', phase='verified', finished_at=time.time(), returncode=code)
        except Exception as exc:
            with self.lock:
                self.job.update(status='error', error=str(exc), finished_at=time.time())
                self.job['log'] = (self.job['log'] + [str(exc)])[-250:]
        finally:
            if process and process.poll() is None:
                process.kill()
                process.wait(timeout=3)
            with self.lock:
                if self.process is process:
                    self.process = None

    def close(self):
        with self.lock:
            self.closed = True
            process = self.process
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
        if self.thread:
            self.thread.join(timeout=5)
        self.temp.cleanup()
