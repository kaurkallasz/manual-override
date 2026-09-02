"""Photon Art: immutable browser assets and their versioned manifest."""

import os

from flask import Blueprint, jsonify, send_from_directory

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "assets")

MANIFEST = {
    "name": "Photon Art",
    "description": "Input: none at runtime. Output: immutable map, marker, unit, and effect assets by stable ID.",
    "group": "Photon Engine",
    "default_page": "",
    "pages": [{"path": "", "label": "Art"}],
}
bp = Blueprint("photon_art", __name__)


def _asset_manifest():
    assets = {
        "map/ground/gunmetal-clean": "game-art/z-pixel-v2/normalized/ground/gunmetal-clean.png",
        "map/ground/concrete-cracked": "game-art/z-pixel-v2/normalized/ground/concrete-cracked.png",
        "map/ground/service-panels": "game-art/z-pixel-v2/normalized/ground/service-panels.png",
        "map/ground/energy-conduits": "game-art/z-pixel-v2/normalized/ground/energy-conduits.png",
        "map/roads/straight-horizontal": "game-art/z-pixel-v2/normalized-seam-safe/roads/straight-horizontal.png",
        "map/roads/junction-cross": "game-art/z-pixel-v2/normalized-seam-safe/roads/junction-cross.png",
        "map/roads/junction-t-esw": "game-art/z-pixel-v2/normalized-seam-safe/roads/junction-t-esw.png",
        "map/roads/corner-wn": "game-art/z-pixel-v2/normalized-seam-safe/roads/corner-wn.png",
        "map/roads/core-access-plaza": "game-art/z-pixel-v2/normalized-seam-safe/roads/core-access-plaza.png",
        "map/roads/seam-cap-vertical": "game-art/z-pixel-v2/normalized/roads/straight-horizontal.png",
        "map/objectives/target-shared-active": "game-art/z-pixel-v2/normalized/objectives/target-shared-active.png",
        "map/structures/photon-detonator-upgraded-l5": "game-art/z-pixel-v2/normalized/structures/photon-detonator-upgraded-l5.png",
    }
    for tower_type in ("machine_gun", "flamethrower", "mortar", "tesla_coil"):
        filename = tower_type.replace("_", "-")
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


def art_snapshot():
    return {
        "contract": "photon.art", "version": 2, "status": "ready",
        "sprites": {
            "enemy": "enemy.svg",
            "tower": "tower.svg",
            "core": "core.svg",
        },
        "packs": {
            "laser_tag_z_runtime": {
                "root": "game-art/",
                "description": (
                    "Immutable tower, enemy, and combat-effect images copied "
                    "from the proven Laser Tag Z presentation."
                ),
            },
        },
        "assets": _asset_manifest(),
    }


@bp.route("/")
def index():
    return send_from_directory(HERE, "index.html")


@bp.route("/api/manifest")
def manifest_api():
    return jsonify(art_snapshot())


@bp.route("/assets/<path:filename>")
def asset(filename):
    response = send_from_directory(ASSETS, filename)
    response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return response
