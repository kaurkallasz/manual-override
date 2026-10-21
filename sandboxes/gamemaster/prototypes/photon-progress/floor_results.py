"""Bounded saved field artwork; no camera frames, remote URLs or live state."""
import json
import re
from ltz_records import finite, integer


def validate_floor(value):
    if value is None:
        return  # Legacy recordings may have only heatmap geometry.
    if not isinstance(value, dict) or type(value.get('version')) is not int or value['version'] != 1:
        raise ValueError('Invalid replay floor')
    integer(value.get('revision'), 1)
    if len(json.dumps(value)) > 250000:
        raise ValueError('Replay floor is too large')
    assets, layers = value.get('assets'), value.get('layers')
    if not isinstance(assets, dict) or not 1 <= len(assets) <= 128:
        raise ValueError('Invalid replay floor artwork')
    for key, path in assets.items():
        if (not isinstance(key, str) or not 1 <= len(key) <= 160
                or not isinstance(path, str) or len(path) > 512
                or not re.fullmatch(r'[A-Za-z0-9_-][A-Za-z0-9_./-]*\.(?:png|webp|jpg|jpeg)\?v=[a-f0-9]{64}', path)
                or '..' in path.split('?')[0].split('/')):
            raise ValueError('Invalid replay floor asset path')
    if not isinstance(layers, list) or not 1 <= len(layers) <= 64:
        raise ValueError('Invalid replay floor layers')
    count = 0
    for layer in layers:
        if not isinstance(layer, dict) or finite(layer.get('opacity')) > 1:
            raise ValueError('Invalid replay floor opacity')
        items = layer.get('items')
        if not isinstance(items, list):
            raise ValueError('Invalid replay floor items')
        count += len(items)
        if count > 512:
            raise ValueError('Too many replay floor items')
        for item in items:
            if (not isinstance(item, dict) or item.get('kind') != 'sprite'
                    or not isinstance(item.get('asset_id'), str) or item['asset_id'] not in assets):
                raise ValueError('Invalid replay floor sprite')
            for key in ('origin_x', 'origin_y', 'draw_x', 'draw_y', 'rotation_degrees'):
                if abs(finite(item.get(key), -1000000)) > 1000000:
                    raise ValueError('Invalid replay floor transform')
            for key in ('width', 'height'):
                if not 0 < finite(item.get(key)) <= 100000:
                    raise ValueError('Invalid replay floor size')
            source = item.get('source')
            if source is not None:
                if not isinstance(source, list) or len(source) != 4:
                    raise ValueError('Invalid replay floor crop')
                for i, part in enumerate(source):
                    if finite(part) > 100000 or (i > 1 and part <= 0):
                        raise ValueError('Invalid replay floor crop')
