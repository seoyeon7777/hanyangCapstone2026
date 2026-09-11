"""멀티뷰 이미지 전처리 (ONNX/Torch 공통)."""

from __future__ import annotations

import os
from typing import Any, Optional

import numpy as np


VIEW_ORDER = ("front", "side", "back")


def load_views_tensor(
    images: dict[str, Optional[str]],
    *,
    size: int = 128,
    layout: str = "nchw",
    min_views: int = 1,
) -> tuple[np.ndarray, list[str]]:
    """images → float32 tensor.

    layout nchw: (1, 3*V, H, W) stacked RGB channels per view
    layout nhwc: (1, H, W, 3*V)
    """
    from PIL import Image

    present = []
    arrays = []
    for key in VIEW_ORDER:
        path = (images or {}).get(key)
        if path and os.path.exists(path):
            present.append(key)
            img = Image.open(path).convert("RGB").resize((size, size))
            arr = np.asarray(img, dtype=np.float32) / 255.0  # HWC
            arrays.append(arr)
    if len(present) < int(min_views):
        raise ValueError(f"need ≥{min_views} views, got {len(present)}")
    if not arrays:
        # zero placeholder when min_views=0 allowed — callers should check
        z = np.zeros((size, size, 3), dtype=np.float32)
        arrays = [z]
        present = ["empty"]
    stacked = np.concatenate(arrays, axis=2)  # H,W,3V
    if layout.lower() == "nchw":
        # C,H,W
        chw = np.transpose(stacked, (2, 0, 1))
        return chw[None, ...], present
    return stacked[None, ...], present


def decode_faces(faces: np.ndarray, *, one_based: bool = False) -> np.ndarray:
    f = np.asarray(faces, dtype=np.int64)
    if f.ndim == 1:
        if f.size % 3 != 0:
            raise ValueError("faces flat length not divisible by 3")
        f = f.reshape((-1, 3))
    if one_based:
        f = f - 1
    if (f < 0).any():
        raise ValueError("negative face index")
    return f.astype(np.int32)


def decode_verts(verts: np.ndarray) -> np.ndarray:
    v = np.asarray(verts, dtype=np.float64)
    if v.ndim == 1:
        if v.size % 3 != 0:
            raise ValueError("verts flat length not divisible by 3")
        v = v.reshape((-1, 3))
    if v.ndim != 2 or v.shape[1] != 3:
        raise ValueError(f"verts shape invalid: {v.shape}")
    if not np.isfinite(v).all():
        raise ValueError("non-finite vertices")
    return v
