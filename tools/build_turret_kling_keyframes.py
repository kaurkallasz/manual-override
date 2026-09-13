#!/usr/bin/env python3
"""Build square elevator first/last keyframes for Kling turret-install videos.

The last keyframe is composed from the exact runtime socket cover, turret base,
and turret head. One image-generated sliding hatch serves all four turrets.
Exports include RGBA masters and opaque black-matte Kling upload copies.
Legacy v1 first frames remain available for the original trapdoor videos.
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "assets" / "game-art" / "z-pixel-v2"
RUNTIME = PACK / "normalized" / "structures" / "runtime"
SOURCES = PACK / "source-sheets" / "kling-keyframes"
OUTPUT = PACK / "normalized" / "structures" / "runtime" / "kling-keyframes"
MANIFEST = PACK / "kling-turret-install-keyframes.json"
PROMPTS = PACK / "KLING_TURRET_INSTALL_PROMPTS.md"
FIRST_SOURCE = SOURCES / "turret-elevator-install-first-source-v2.png"
FIRST_FRAME = OUTPUT / "turret-elevator-install-first-v2.png"
UPLOAD = OUTPUT / "kling-upload-v2"

CANVAS_SIZE = 1024
CONTENT_SIZE = 896
TOWER_FRAME_SIZE = 112
TOWER_ART_SIZE = 88
ALPHA_CUTOFF = 8

TOWER_TYPES = {
    "machine-gun": {"head_version": 1},
    "flamethrower": {"head_version": 1},
    "mortar": {"head_version": 1},
    "tesla-coil": {"head_version": 2},
}


def clean_alpha(image: Image.Image) -> Image.Image:
    image = image.convert("RGBA")
    alpha = image.getchannel("A").point(
        lambda value: 0 if value < ALPHA_CUTOFF else value
    )
    image.putalpha(alpha)
    return image


def square_canvas(
    image: Image.Image, *, source_is_pixel_art: bool, square_footprint: bool = False
) -> Image.Image:
    image = clean_alpha(image)
    bounds = image.getchannel("A").getbbox()
    if not bounds:
        raise RuntimeError("keyframe source must contain visible pixels")
    cropped = image.crop(bounds)
    scale = min(CONTENT_SIZE / cropped.width, CONTENT_SIZE / cropped.height)
    resampling = (
        Image.Resampling.NEAREST
        if source_is_pixel_art
        else Image.Resampling.LANCZOS
    )
    size = (
        max(1, round(cropped.width * scale)),
        max(1, round(cropped.height * scale)),
    )
    if square_footprint:
        size = (CONTENT_SIZE, CONTENT_SIZE)
    resized = cropped.resize(size, resampling)
    frame = Image.new("RGBA", (CANVAS_SIZE, CANVAS_SIZE), (0, 0, 0, 0))
    frame.alpha_composite(
        resized,
        ((CANVAS_SIZE - resized.width) // 2, (CANVAS_SIZE - resized.height) // 2),
    )
    return clean_alpha(frame)


def save_upload(image: Image.Image, path: Path) -> None:
    """Use an explicit backdrop instead of relying on video-input alpha."""
    matte = Image.new("RGBA", image.size, (0, 0, 0, 255))
    matte.alpha_composite(image.convert("RGBA"))
    matte.convert("RGB").save(path, optimize=True)


def active_runtime_frame(tower_type: str, head_version: int) -> Image.Image:
    cover = Image.open(RUNTIME / "tower-socket-cover-v1.png").convert("RGBA")
    cover = cover.resize(
        (TOWER_FRAME_SIZE, TOWER_FRAME_SIZE), Image.Resampling.NEAREST
    )
    base = Image.open(RUNTIME / f"{tower_type}-base-v1.png").convert("RGBA")
    head = Image.open(
        RUNTIME / f"{tower_type}-head-v{head_version}.png"
    ).convert("RGBA")
    base = base.resize((TOWER_ART_SIZE, TOWER_ART_SIZE), Image.Resampling.NEAREST)
    head = head.resize((TOWER_ART_SIZE, TOWER_ART_SIZE), Image.Resampling.NEAREST)
    inset = (TOWER_FRAME_SIZE - TOWER_ART_SIZE) // 2
    cover.alpha_composite(base, (inset, inset))
    cover.alpha_composite(head, (inset, inset))
    return clean_alpha(cover)


def build() -> dict[str, object]:
    if not FIRST_SOURCE.is_file():
        raise RuntimeError(f"missing elevator hatch source: {FIRST_SOURCE}")
    source = Image.open(FIRST_SOURCE).convert("RGBA")
    if source.getchannel("A").getextrema()[0] != 0:
        raise RuntimeError("elevator source must have a genuinely transparent exterior")
    # Generated extraction leaves alpha 253 on solid black shaft pixels.
    # Snap nearly opaque pixels to 255, retaining antialiasing at the perimeter.
    source.putalpha(source.getchannel("A").point(
        lambda value: 255 if value >= 248 else value
    ))
    OUTPUT.mkdir(parents=True, exist_ok=True)
    UPLOAD.mkdir(parents=True, exist_ok=True)
    first = square_canvas(
        source, source_is_pixel_art=False, square_footprint=True
    )
    first.save(FIRST_FRAME, optimize=True)
    first_upload = UPLOAD / "turret-elevator-install-first-v2-black.png"
    save_upload(first, first_upload)
    assets: list[dict[str, object]] = []
    for tower_type, config in TOWER_TYPES.items():
        last_path = OUTPUT / f"{tower_type}-install-last-v1.png"
        last = square_canvas(
            active_runtime_frame(tower_type, config["head_version"]),
            source_is_pixel_art=True,
        )
        last.save(last_path, optimize=True)
        last_upload = UPLOAD / f"{tower_type}-install-last-v2-black.png"
        save_upload(last, last_upload)

        assets.append(
            {
                "tower_type": tower_type.replace("-", "_"),
                "first_source": str(FIRST_SOURCE.relative_to(ROOT)),
                "first_frame": str(FIRST_FRAME.relative_to(ROOT)),
                "first_upload": str(first_upload.relative_to(ROOT)),
                "last_frame": str(last_path.relative_to(ROOT)),
                "last_upload": str(last_upload.relative_to(ROOT)),
                "canvas_size": [CANVAS_SIZE, CANVAS_SIZE],
                "content_size_px": CONTENT_SIZE,
                "pivot": [0.5, 0.5],
                "duration_s": 3.0,
            }
        )

    manifest = {
        "schema_version": 2,
        "motion": "sliding_floor_doors_then_perspective_elevator_rise_then_boot_rotation",
        "aspect_ratio": "1:1",
        "duration_s": 3.0,
        "canvas_size": [CANVAS_SIZE, CANVAS_SIZE],
        "runtime_target": {"fps": 24, "frame_count": 72, "hold_final_frames": 6},
        "alpha": {
            "master": "RGBA PNG",
            "exterior": "transparent",
            "shaft_and_mechanisms": "opaque",
            "upload": "RGB PNG with black exterior matte",
            "video_delivery": "native alpha is not assumed; matte only the exterior",
        },
        "perspective": {
            "camera": "fixed direct-overhead perspective",
            "ground_footprint_scale": 1.0,
            "rising_assembly_start_scale": 0.55,
            "rising_assembly_end_scale": 1.0,
            "fixed_pivot": [0.5, 0.5],
        },
        "timeline": [
            {"frames": [0, 14], "time_s": [0, 0.625], "stage": "sliding_doors_open"},
            {"frames": [15, 41], "time_s": [0.625, 1.75], "stage": "perspective_elevator_rise"},
            {"frames": [42, 50], "time_s": [1.75, 2.125], "stage": "platform_dock"},
            {"frames": [51, 65], "time_s": [2.125, 2.75], "stage": "boot_rotation"},
            {"frames": [66, 71], "time_s": [2.75, 3], "stage": "active_hold"},
        ],
        "prompt_file": str(PROMPTS.relative_to(ROOT)),
        "assets": assets,
    }
    temporary_manifest = MANIFEST.with_suffix(".json.tmp")
    temporary_manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    temporary_manifest.replace(MANIFEST)
    return manifest


if __name__ == "__main__":
    print(json.dumps(build(), indent=2))
