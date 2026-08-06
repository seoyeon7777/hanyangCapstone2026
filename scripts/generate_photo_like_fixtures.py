#!/usr/bin/env python3
"""합성 photo-like 실루엣 픽스처 생성 (실사진 아님)."""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "benchmarks" / "fixtures" / "silhouette"


def _noise_bg(w: int, h: int, base=(28, 32, 40)) -> Image.Image:
    import random

    rng = random.Random(7)
    im = Image.new("RGB", (w, h), base)
    px = im.load()
    for y in range(h):
        for x in range(w):
            j = rng.randint(-12, 12)
            px[x, y] = tuple(max(0, min(255, c + j)) for c in base)
    return im.filter(ImageFilter.GaussianBlur(0.6))


def _draw_pants(im: Image.Image):
    d = ImageDraw.Draw(im)
    # torso + legs
    d.polygon([(55, 18), (105, 18), (112, 55), (48, 55)], fill=(62, 78, 120))
    d.polygon([(48, 55), (72, 55), (68, 175), (40, 175)], fill=(55, 70, 110))
    d.polygon([(88, 55), (112, 55), (120, 175), (92, 175)], fill=(55, 70, 110))
    # soft shadow
    d.ellipse([30, 170, 130, 190], fill=(18, 18, 22))


def _draw_top(im: Image.Image):
    d = ImageDraw.Draw(im)
    d.polygon([(50, 28), (110, 28), (125, 70), (105, 70), (100, 160), (60, 160), (55, 70), (35, 70)], fill=(190, 70, 70))
    d.ellipse([40, 165, 120, 185], fill=(20, 18, 16))


def _draw_top_side(im: Image.Image):
    d = ImageDraw.Draw(im)
    d.polygon([(60, 25), (95, 25), (105, 70), (100, 160), (55, 160), (50, 70)], fill=(180, 65, 65))
    d.ellipse([45, 165, 115, 185], fill=(18, 16, 14))


def _draw_skirt(im: Image.Image):
    d = ImageDraw.Draw(im)
    d.polygon([(62, 30), (98, 30), (135, 165), (25, 165)], fill=(170, 85, 120))
    d.ellipse([20, 170, 140, 190], fill=(22, 18, 20))


def _draw_pants_side(im: Image.Image):
    d = ImageDraw.Draw(im)
    # side profile: thicker torso, tapering legs
    d.polygon([(55, 20), (100, 20), (108, 60), (102, 175), (58, 175), (48, 60)], fill=(58, 72, 115))
    d.ellipse([40, 170, 120, 190], fill=(18, 18, 22))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    specs = [
        ("photo_like_pants_front.png", _draw_pants, (160, 200)),
        ("photo_like_pants_side.png", _draw_pants_side, (160, 200)),
        ("photo_like_top_front.png", _draw_top, (160, 200)),
        ("photo_like_top_side.png", _draw_top_side, (160, 200)),
        ("photo_like_skirt_front.png", _draw_skirt, (160, 200)),
    ]
    for name, drawer, size in specs:
        im = _noise_bg(*size)
        drawer(im)
        # vignette-ish darken corners
        px = im.load()
        w, h = im.size
        for y in range(h):
            for x in range(0, w, 2):
                r = math.hypot((x - w / 2) / w, (y - h / 2) / h)
                if r > 0.55:
                    f = 1.0 - min(0.35, (r - 0.55) * 0.8)
                    c = px[x, y]
                    px[x, y] = tuple(int(v * f) for v in c)
        path = OUT / name
        im.save(path)
        print("wrote", path)


if __name__ == "__main__":
    main()
