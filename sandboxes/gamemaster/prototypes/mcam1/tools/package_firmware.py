"""Package already-compiled XIAO camera firmware; never builds or opens USB."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mcam1_firmware import COMPATIBILITY, LAYOUT, TARGET, validate_bundle


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-dir', type=Path, required=True,
                        help='Directory with bootloader.bin, partitions.bin, firmware.bin')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--model', help='Name of the model already embedded in firmware.bin')
    parser.add_argument('--class-name', action='append', default=[], help='Repeat for each class label')
    args = parser.parse_args()
    if bool(args.model) != bool(args.class_name):
        parser.error('--model and at least one --class-name must be supplied together')
    if args.output.exists():
        parser.error('Output already exists; choose a new release filename')
    images = {name:(args.build_dir / name).read_bytes() for name in LAYOUT.values()}
    manifest = dict(target=TARGET, variant='bulk', revision=args.revision, flash_layout=LAYOUT,
                    mcam1=COMPATIBILITY, sha256={name:hashlib.sha256(raw).hexdigest() for name,raw in images.items()})
    if args.model:
        manifest['ai'] = dict(model=args.model, classes=args.class_name)
    with tempfile.TemporaryDirectory(prefix='mcam1-package-') as temp:
        archive = Path(temp) / 'firmware.zip'
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as output:
            output.writestr('manifest.json', json.dumps(manifest, indent=2)+'\n')
            for name, raw in images.items():
                output.writestr(name, raw)
        info, _ = validate_bundle(archive)
        with args.output.open('xb') as destination:
            destination.write(archive.read_bytes())
    print(f"Validated {info['revision']}: {info['application_bytes']} application bytes")
    print(f"Application SHA-256: {info['application_sha256']}")
    print(f'Created {args.output}. No USB device was opened.')


if __name__ == '__main__':
    main()
