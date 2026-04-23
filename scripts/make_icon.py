"""Generate icon.icns for Through the Wall.

Produces all the sizes macOS wants, then stitches them with `iconutil`.
Design: dark rounded square, accent-blue arrow punching through two vertical bars
(a stylized 'through the wall'). Looks OK down to 16x16.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets"
ICONSET = OUT / "icon.iconset"
ICNS = OUT / "icon.icns"

# Palette matches the app UI
BG_TOP = (20, 23, 31)
BG_BOT = (38, 44, 60)
WALL = (70, 78, 98)
ARROW = (124, 156, 255)
HIGHLIGHT = (255, 255, 255)


def _rounded_mask(size: int, radius: int) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([(0, 0), (size, size)], radius=radius, fill=255)
    return mask


def _gradient(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size))
    px = img.load()
    for y in range(size):
        t = y / max(size - 1, 1)
        r = int(BG_TOP[0] + (BG_BOT[0] - BG_TOP[0]) * t)
        g = int(BG_TOP[1] + (BG_BOT[1] - BG_TOP[1]) * t)
        b = int(BG_TOP[2] + (BG_BOT[2] - BG_TOP[2]) * t)
        for x in range(size):
            px[x, y] = (r, g, b, 255)
    return img


def make_icon(size: int) -> Image.Image:
    # Padding so the icon doesn't fill the whole tile (Apple standard uses ~10% bleed)
    pad = round(size * 0.09)
    inner = size - pad * 2
    radius = round(inner * 0.22)

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    bg = _gradient(inner)
    bg.putalpha(_rounded_mask(inner, radius))
    img.paste(bg, (pad, pad), bg)

    # Draw on the inner tile
    layer = Image.new("RGBA", (inner, inner), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)

    # Two vertical bars (the "walls")
    bar_w = max(1, round(inner * 0.06))
    bar_h = round(inner * 0.48)
    bar_y = (inner - bar_h) // 2
    left_x = round(inner * 0.22)
    right_x = round(inner * 0.72)
    d.rounded_rectangle(
        [(left_x, bar_y), (left_x + bar_w, bar_y + bar_h)],
        radius=bar_w // 2, fill=WALL,
    )
    d.rounded_rectangle(
        [(right_x, bar_y), (right_x + bar_w, bar_y + bar_h)],
        radius=bar_w // 2, fill=WALL,
    )

    # Arrow piercing through — a horizontal bar + chevron head
    shaft_h = max(2, round(inner * 0.09))
    shaft_y = inner // 2 - shaft_h // 2
    shaft_x0 = round(inner * 0.14)
    shaft_x1 = round(inner * 0.80)
    d.rounded_rectangle(
        [(shaft_x0, shaft_y), (shaft_x1, shaft_y + shaft_h)],
        radius=shaft_h // 2, fill=ARROW,
    )
    # Arrow head
    head_size = round(inner * 0.18)
    head_cx = round(inner * 0.86)
    head_cy = inner // 2
    head_points = [
        (head_cx - head_size, head_cy - head_size),
        (head_cx + head_size // 2, head_cy),
        (head_cx - head_size, head_cy + head_size),
    ]
    d.polygon(head_points, fill=ARROW)

    # Subtle top highlight for depth
    hl = Image.new("RGBA", (inner, inner), (0, 0, 0, 0))
    hl_draw = ImageDraw.Draw(hl)
    hl_draw.rounded_rectangle(
        [(0, 0), (inner, inner // 3)],
        radius=radius, fill=(255, 255, 255, 18),
    )
    hl.putalpha(_rounded_mask(inner, radius))
    layer = Image.alpha_composite(layer, hl) if False else layer

    layer.putalpha(_rounded_mask(inner, radius))
    img.paste(layer, (pad, pad), layer)
    return img


def build():
    if ICONSET.exists():
        shutil.rmtree(ICONSET)
    ICONSET.mkdir(parents=True)

    # macOS iconset requires these exact filenames/sizes
    specs = [
        (16, "icon_16x16.png", 1),
        (32, "icon_16x16@2x.png", 2),
        (32, "icon_32x32.png", 1),
        (64, "icon_32x32@2x.png", 2),
        (128, "icon_128x128.png", 1),
        (256, "icon_128x128@2x.png", 2),
        (256, "icon_256x256.png", 1),
        (512, "icon_256x256@2x.png", 2),
        (512, "icon_512x512.png", 1),
        (1024, "icon_512x512@2x.png", 2),
    ]
    for size, name, _ in specs:
        make_icon(size).save(ICONSET / name)

    subprocess.run(
        ["iconutil", "-c", "icns", str(ICONSET), "-o", str(ICNS)],
        check=True,
    )
    print(f"Built {ICNS} ({ICNS.stat().st_size} bytes)")


if __name__ == "__main__":
    build()
