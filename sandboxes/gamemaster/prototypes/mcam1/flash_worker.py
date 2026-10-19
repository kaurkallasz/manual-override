"""Isolated, bounded esptool worker. Started only by an explicit MCAM1 flash job."""
from pathlib import Path
import re
import sys
from mcam1_firmware import resolve_device, validate_bundle


def flash(bundle, token):
    # Revalidate immediately before touching USB. Never run code from the ZIP.
    _, images = validate_bundle(Path(bundle))
    target = resolve_device(token)
    from esptool.cmds import detect_chip, attach_flash, detect_flash_size, write_flash, verify_flash
    esp = None
    try:
        print('MCAM1_PHASE connecting', flush=True)
        print(f"Target: {target['port']} · USB serial {target['serial']}", flush=True)
        esp = detect_chip(target['port'], connect_mode='no-reset', connect_attempts=2)
        if esp.CHIP_NAME != 'ESP32-S3':
            raise RuntimeError(f'Expected ESP32-S3; detected {esp.CHIP_NAME}. Nothing written.')
        mac = ''.join(f'{part:02X}' for part in esp.read_mac())
        serial_mac = re.sub('[^0-9A-Fa-f]', '', target['serial']).upper()
        if serial_mac != mac:
            raise RuntimeError('Chip MAC does not match the selected USB identity. Nothing written.')
        if esp.secure_download_mode or esp.get_secure_boot_enabled() or esp.get_flash_encryption_enabled():
            raise RuntimeError('Secure boot / encrypted devices are unsupported. Nothing written.')
        esp = esp.run_stub()
        attach_flash(esp)
        size = detect_flash_size(esp)
        if size != '8MB':
            raise RuntimeError(f'Expected 8MB flash; detected {size}. Nothing written.')
        print(f'Confirmed ESP32-S3 · MAC {mac} · {size} flash. Board pinout was confirmed by operator.', flush=True)
        esp.change_baud(460800)
        segments = [(0, images['bootloader.bin']), (0x8000, images['partitions.bin']), (0x10000, images['firmware.bin'])]
        print('MCAM1_PHASE writing', flush=True)
        # Keep image headers, keep NVS; do not bypass Espressif's security checks.
        write_flash(esp, segments, flash_size='keep', compress=True, force=False, erase_all=False)
        print('MCAM1_PHASE verifying', flush=True)
        verify_flash(esp, segments, flash_size='keep')
        print('All three images verified against device flash.', flush=True)
        try:
            esp.hard_reset()
            print('Reset requested. Replug USB if the webcam does not reappear.', flush=True)
        except Exception as exc:
            print(f'Flash verified; reset unavailable ({exc}). Press RESET or replug USB.', flush=True)
        print('MCAM1_PHASE verified', flush=True)
    finally:
        if esp is not None:
            esp._port.close()


if __name__ == '__main__':
    try:
        if len(sys.argv) != 3:
            raise ValueError('Expected a validated bundle and device identity')
        flash(sys.argv[1], sys.argv[2])
    except Exception as exc:
        print(f'ERROR: {exc}', flush=True)
        sys.exit(1)
