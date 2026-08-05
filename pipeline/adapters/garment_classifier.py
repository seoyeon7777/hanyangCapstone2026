"""경량 의류 분류기 — 이미지 특징 + 선형 가중치 (외부 ML 의존 없음).

features:
  aspect, fill_ratio, top_width_ratio, bottom_width_ratio,
  bipodal_score, brightness, saturation
"""

from __future__ import annotations

import json
import math
import os
from typing import Any, Optional

LABELS = ("tshirt", "hoodie", "jacket", "pants", "skirt", "shorts", "dress")

# hand-tuned softmax weights: bias + features
# order: aspect, fill, top_w, bot_w, bipodal, bright, sat
_WEIGHTS = {
    "tshirt": {
        "bias": 0.8,
        "w": [-1.2, 0.3, 0.6, 0.2, -1.5, 0.1, 0.2],
    },
    "hoodie": {
        "bias": 0.2,
        "w": [0.8, 0.4, 0.5, 0.3, -1.0, -0.1, 0.1],
    },
    "jacket": {
        "bias": 0.0,
        "w": [0.4, 0.2, 0.7, 0.4, -0.8, -0.2, -0.1],
    },
    "pants": {
        "bias": -0.2,
        "w": [2.2, 0.1, -0.8, 0.9, 2.5, 0.0, 0.0],
    },
    "skirt": {
        "bias": -0.4,
        "w": [0.6, 0.2, -0.5, 1.4, -0.5, 0.1, 0.3],
    },
    "shorts": {
        "bias": -0.3,
        "w": [0.2, 0.1, -0.4, 0.8, 1.5, 0.0, 0.1],
    },
    "dress": {
        "bias": -0.5,
        "w": [1.4, 0.3, 0.2, 0.6, -0.8, 0.0, 0.2],
    },
}


def extract_features(image_path: str) -> Optional[list[float]]:
    try:
        from PIL import Image
        import numpy as np
    except ImportError:
        return None
    if not image_path or not os.path.exists(image_path):
        return None

    img = Image.open(image_path).convert("RGBA")
    arr = np.array(img)
    alpha = arr[:, :, 3]
    rgb = arr[:, :, :3].astype(np.float32)
    if alpha.max() > 10:
        fg = alpha > 30
    else:
        gray = rgb.mean(axis=2)
        h, w = gray.shape
        crop = gray[h // 12: h - h // 12, w // 12: w - w // 12]
        # pad back
        fg = np.zeros_like(gray, dtype=bool)
        fg[h // 12: h - h // 12, w // 12: w - w // 12] = crop < 245

    if not fg.any():
        return None

    ys, xs = np.where(fg)
    y0, y1 = int(ys.min()), int(ys.max())
    x0, x1 = int(xs.min()), int(xs.max())
    bh = max(1, y1 - y0)
    bw = max(1, x1 - x0)
    aspect = bh / float(bw)
    fill = float(fg.sum()) / float(fg.size)

    # top/bottom width ratios within bbox
    def band_width(t0, t1):
        yy0 = y0 + int(bh * t0)
        yy1 = y0 + int(bh * t1)
        band = fg[yy0:max(yy0 + 1, yy1), x0:x1 + 1]
        if not band.any():
            return 0.0
        cols = np.any(band, axis=0)
        if not cols.any():
            return 0.0
        ii = np.where(cols)[0]
        return float(ii.max() - ii.min() + 1) / float(bw)

    top_w = band_width(0.05, 0.25)
    bot_w = band_width(0.75, 0.95)

    # bipodal-ish: bottom band has center gap
    yy0 = y0 + int(bh * 0.78)
    yy1 = y0 + int(bh * 0.95)
    band = fg[yy0:max(yy0 + 1, yy1), x0:x1 + 1]
    bipodal = 0.0
    if band.any():
        cols = np.any(band, axis=0).astype(np.int32)
        mid = len(cols) // 2
        left = cols[: mid - max(1, len(cols) // 20)].sum()
        right = cols[mid + max(1, len(cols) // 20):].sum()
        center = cols[mid - max(1, len(cols) // 25): mid + max(1, len(cols) // 25)].sum()
        if left > 3 and right > 3 and center <= max(1, left * 0.15):
            bipodal = 1.0
        elif left > 3 and right > 3:
            bipodal = 0.4

    fg_rgb = rgb[fg]
    bright = float(fg_rgb.mean() / 255.0)
    # crude saturation
    mx = fg_rgb.max(axis=1)
    mn = fg_rgb.min(axis=1)
    sat = float(((mx - mn) / (mx + 1e-6)).mean())

    # normalize aspect around 1.2
    return [
        float(np.clip((aspect - 1.0) / 1.5, -1.5, 2.5)),
        float(np.clip(fill * 4.0, 0, 2)),
        float(np.clip(top_w, 0, 1.5)),
        float(np.clip(bot_w, 0, 1.5)),
        bipodal,
        float(np.clip(bright, 0, 1)),
        float(np.clip(sat, 0, 1)),
    ]


def _softmax(scores: dict[str, float]) -> dict[str, float]:
    m = max(scores.values())
    ex = {k: math.exp(v - m) for k, v in scores.items()}
    s = sum(ex.values()) or 1.0
    return {k: ex[k] / s for k in ex}


def classify_from_features(feats: list[float]) -> dict[str, Any]:
    scores = {}
    for label, cfg in _WEIGHTS.items():
        s = float(cfg["bias"])
        for wi, fi in zip(cfg["w"], feats):
            s += wi * fi
        scores[label] = s
    probs = _softmax(scores)
    best = max(probs, key=probs.get)
    return {
        "label": best,
        "confidence": round(float(probs[best]), 3),
        "source": "feature_model",
        "probs": {k: round(v, 3) for k, v in sorted(probs.items(), key=lambda x: -x[1])[:4]},
        "features": feats,
    }


def classify_image_ml(image_path: str) -> Optional[dict[str, Any]]:
    feats = extract_features(image_path)
    if not feats:
        return None
    return classify_from_features(feats)


def load_custom_weights(path: str) -> None:
    """선택: JSON 가중치로 _WEIGHTS 덮어쓰기."""
    global _WEIGHTS
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict) and data:
        _WEIGHTS = data
