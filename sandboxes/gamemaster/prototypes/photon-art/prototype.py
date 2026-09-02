"""Photon Art: immutable browser assets and their versioned manifest."""

import os

from flask import Blueprint, jsonify, send_from_directory

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "assets")

MANIFEST = {
    "name": "Photon Art",
    "description": "Input: none at runtime. Output: immutable educational-game sprites and a manifest.",
    "group": "Photon Engine",
    "default_page": "",
    "pages": [{"path": "", "label": "Art"}],
}
bp = Blueprint("photon_art", __name__)


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
