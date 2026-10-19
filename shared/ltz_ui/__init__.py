"""Shared score presentation assets. Explicit allowlist; no player/game state."""
from functools import lru_cache
import hashlib
from pathlib import Path
from flask import abort, send_from_directory
ROOT=Path(__file__).resolve().parent
ASSETS=('control-xyz-v1.png','control-click-v1.png','control-cue-v1.png','upgrade-lock-shutter-v1.png')

@lru_cache(maxsize=1)
def manifest():
    return {f'ui/ltz/{name}':f'ui/ltz/{name}?v={hashlib.sha256((ROOT/"assets"/name).read_bytes()).hexdigest()}' for name in ASSETS}

def asset_response(filename):
    if filename not in ASSETS:abort(404)
    return send_from_directory(ROOT/'assets',filename,max_age=0)
