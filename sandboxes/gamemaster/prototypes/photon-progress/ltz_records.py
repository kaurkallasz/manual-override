"""Strict serialization and legacy record normalization owned by Progress."""
import hashlib
import json
import math

def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def integer(value, low=0, high=1000000000):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'expected an integer between {low} and {high}')
    return value


def identifier(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 160 or not all(c.isalnum() or c in '-_:.' for c in value):
        raise ValueError('invalid identifier')
    return value


def finite(value, low=0):
    if type(value) not in (int, float) or not math.isfinite(value) or value < low:
        raise ValueError('invalid numeric value')
    return value


def fingerprint(value):
    return hashlib.sha256(encoded(value).encode()).hexdigest()


def normalize_legacy_tracks(value):
    if isinstance(value, list):
        return [normalize_legacy_tracks(item) for item in value]
    if not isinstance(value, dict):
        return value
    value = {key: normalize_legacy_tracks(item) for key, item in value.items()}
    if 'damage-photon' in value:
        old = value.pop('damage-photon')
        if isinstance(old,dict):
            if 'damage-tesla-coil' in value and value['damage-tesla-coil']!=old:raise ValueError('conflicting legacy track')
            value['damage-tesla-coil']=old
        else:value['damage-tesla-coil'] = max(integer(old,1,4), integer(value.get('damage-tesla-coil', 1), 1, 4))
    if value.get('track') == 'damage-photon':
        value['track'] = 'damage-tesla-coil'
    return value
