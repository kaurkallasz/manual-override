"""Level-owned static content; no game state or sibling dependencies."""

import hashlib
import json
import threading
from pathlib import Path
from urllib.parse import quote

_lock = threading.RLock()
_hashes = {}


def runtime_asset_paths():
    assets = {"fallback/enemy": "enemy.svg", "fallback/tower": "tower.svg", "fallback/core": "core.svg"}
    for tower_type in ("machine_gun", "flamethrower", "mortar", "tesla_coil"):
        filename = tower_type.replace("_", "-")
        for tier in (2, 3, 4):
            assets[f"tower/{tower_type}/upgrade/{tier}"] = f"upgrades/{filename}-l{tier}-atlas.png"
        for layer in ("base", "head"):
            version = 2 if tower_type == "tesla_coil" and layer == "head" else 1
            assets[f"tower/{tower_type}/{layer}"] = (
                "game-art/z-pixel-v2/normalized/structures/runtime/"
                f"{filename}-{layer}-v{version}.png"
            )
        assets[f"tower/{tower_type}/activation"] = (
            "game-art/z-pixel-v2/normalized/structures/runtime/activation/"
            f"{filename}-activation-v2.png"
        )
    assets['field/upgrade-atlas'] = 'upgrades/force-field-atlas.png'
    assets["tower/socket-cover"] = (
        "game-art/z-pixel-v2/normalized/structures/runtime/"
        "tower-socket-cover-v1.png"
    )
    for enemy_type in ("grunt", "runner", "breaker", "brute"):
        group = (
            "enemies-heavy-orcs-v2" if enemy_type == "brute"
            else "enemies-light-orcs-v2"
        )
        for frame in range(1, 5):
            assets[f"enemy/{enemy_type}/{frame}"] = (
                f"game-art/sprites/{group}/{enemy_type}-walk-{frame:02d}.png"
            )
    for effect in (
        "machine-gun-impact", "machine-gun-bullet", "flame-burn",
        "flame-gasoline", "mortar-impact", "mortar-shell", "tesla-spark",
        "tower-smoke", "tower-fire", "tower-stress-cracks",
        "tower-destruction-blast", "tower-debris", "force-field-impact",
        "force-field-zap-skeleton", "core-ring-aura",
        "core-detonation-burst", "core-purge-wave",
    ):
        version = "v3" if effect == "flame-gasoline" else "v1"
        assets[f"effect/{effect}"] = (
            "game-art/z-pixel-v2/normalized/effects/combat/"
            f"{effect}-{version}.png"
        )
    for marker_id in (38, *range(40, 56)):
        assets[f"marker/{marker_id}"] = f"aruco/{marker_id}.png"
    return assets


def asset_snapshot(root, map_assets):
    """Publish URLs, never bytes. Hash only files whose metadata changed."""
    root = Path(root).resolve()
    paths = {**runtime_asset_paths(), **{f"map/{key}": path for key, path in map_assets.items()}}
    assets, errors = {}, []
    with _lock:
        for key, relative in sorted(paths.items()):
            try:
                path = (root / relative).resolve()
                if not path.is_relative_to(root):
                    raise ValueError("asset escapes content package")
                stat = path.stat()
                signature = (stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
                previous = _hashes.get(path)
                if previous is None or previous[0] != signature:
                    digest = hashlib.sha256(path.read_bytes()).hexdigest()
                    _hashes[path] = (signature, digest)
                else:
                    digest = previous[1]
                assets[key] = f"{quote(relative, safe='/')}?v={digest}"
            except (OSError, ValueError) as exc:
                errors.append(f"{key}: {exc}")
    revision = hashlib.sha256(json.dumps(assets, sort_keys=True).encode()).hexdigest()
    return {
        "contract": "photon.level.assets", "version": 1,
        "status": "unavailable" if errors else "ready",
        "error": "; ".join(errors) if errors else None,
        "revision": revision,
        # Relative to the current sandbox mount, not a filesystem path.
        "base": "/p/photon-level/assets",
        "assets": assets,
    }
