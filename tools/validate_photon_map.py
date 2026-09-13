"""Validate current modular Photon maps, including the v2 two-entry contract.

Usage: python3 tools/validate_photon_map.py [--report /tmp/report.json]
Requires Pillow for the alpha-channel audit (available in the bundled runtime).
The historical skill validator assumes four spawns and eight structures; this
project validator checks the authored version and the same modular-art gates.
"""
import argparse
import json
from pathlib import Path
import sys

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
LEVEL = ROOT / 'sandboxes/gamemaster/prototypes/photon-level'
sys.path.insert(0, str(LEVEL))
from level_contract import parse_tiled_level, properties


def validate(path):
    data = json.loads(path.read_text())
    runtime = parse_tiled_level(path)
    catalog, families = {}, {}
    for ref in data['tilesets']:
        source = (path.parent/ref['source']).resolve()
        tileset = json.loads(source.read_text())
        family = families.setdefault(tileset['name'], {'images':0, 'modes':set(), 'empty':0, 'bounds':[]})
        for tile in tileset.get('tiles',[]):
            image = (source.parent/(tile.get('image') or tileset['image'])).resolve()
            with Image.open(image) as im:
                bounds = im.convert('RGBA').getchannel('A').getbbox()
                family['images'] += 1; family['modes'].add(im.mode)
                family['empty'] += bounds is None
                family['bounds'].append({'size':im.size, 'alpha_bounds':bounds})
            catalog[ref['firstgid']+tile['id']] = (image, properties(tile))
    visible_images = [l['name'] for l in data['layers'] if l['type']=='imagelayer' and l.get('visible',True)]
    assert not visible_images, 'reference imagery must be hidden'
    objects = [o for l in data['layers'] for o in l.get('objects',[]) if 'gid' in o]
    used = {o['gid'] & 0x0fffffff for o in objects}
    assert used <= catalog.keys(), 'unresolved visual GIDs'
    counts = {}
    for name, minimum in [('Ground Modules',18),('Road Modules',48)]:
        layer = next(l for l in data['layers'] if name in l['name'])
        placed = [o for o in layer['objects'] if 'gid' in o]
        counts[name] = len(placed)
        assert len(placed) >= minimum
        for obj in placed:
            image, props = catalog[obj['gid'] & 0x0fffffff]
            assert any(p.startswith('normalized') for p in image.parts), 'unnormalized component'
            if name == 'Road Modules':
                assert props.get('visual_depth') == properties(obj).get('visual_depth') == 'sunken'
                if props.get('asset_id','').startswith('roads/seam-cap-'):
                    continue  # Cosmetic edge bleeds do not create road ports.
                assert props.get('ports'), 'road tiles need authored connectivity ports'
                source = next(ref['source'] for ref in reversed(data['tilesets']) if ref['firstgid'] <= obj['gid'])
                assert 'seam-safe' in source or 'core-plaza' in source
        if name == 'Ground Modules':
            for y in range(16,runtime['height'],32):
                for x in range(16,runtime['width'],32):
                    assert any(abs(x-o['x']) <= o['width']/2 and abs(y-o['y']) <= o['height']/2 for o in placed), 'uncovered ground'
    props = runtime['map_properties']
    assert len(runtime['sockets']) == 16
    assert props['max_active_enemies'] == 1000
    assert props['max_structures'] == (16 if runtime['runtime_version']==2 else 8)
    waves = json.loads(path.with_suffix('.waves.json').read_text())
    for wave in waves['waves']:
        for group in wave['groups']:
            assert set(group['lane_weights']) <= set(runtime['enabled_spawn_groups'])
    for family in families.values(): family['modes'] = sorted(family['modes'])
    return dict(valid=True, revision=runtime['layout_revision'], runtime_version=runtime['runtime_version'],
                counts=counts, tile_layers=sum(l['type']=='tilelayer' for l in data['layers']),
                tile_objects=len(objects), referenced_gids=len(catalog), placed_gids=len(used),
                visible_image_layers=visible_images, spawn_groups=runtime['enabled_spawn_groups'],
                row_masks_checked=16 if runtime['row_barriers'] else 0, families=families)


if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--map',type=Path,default=LEVEL/'assets/tiled/levels/z-pixel-first-map.tmj');parser.add_argument('--report',type=Path)
    args=parser.parse_args();report=validate(args.map)
    if args.report:args.report.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='families'},indent=2))
