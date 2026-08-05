"""P1 — 정면 실루엣 마스크로 메쉬 가로폭 보정.

세그 마스크의 높이별 폭 프로파일을 읽어, OBJ의 X 스케일을
밴드별로 부드럽게 맞춘다. (완전한 윤곽 디폼은 아니고 1차 근사)
"""

from __future__ import annotations

import os
from typing import Any, Optional

import numpy as np

from models.fitting_model import load_obj


def mask_width_profile(mask_path: str, bins: int = 48) -> dict[str, Any]:
    """알파/밝은 픽셀 기준 세로 밴드별 half-width (정규화 0~1)."""
    from PIL import Image

    img = Image.open(mask_path).convert("RGBA")
    arr = np.array(img)
    alpha = arr[:, :, 3] if arr.shape[2] == 4 else np.ones(arr.shape[:2], dtype=np.uint8) * 255
    # rembg 등: 알파 우선, 없으면 밝기
    if alpha.max() < 10:
        gray = arr[:, :, :3].mean(axis=2)
        fg = gray > 30
    else:
        fg = alpha > 30

    h, w = fg.shape
    # 세로로 bins개 밴드
    ys = np.linspace(0, h, bins + 1).astype(int)
    half_widths = []
    centers = []
    for i in range(bins):
        y0, y1 = ys[i], max(ys[i] + 1, ys[i + 1])
        band = fg[y0:y1, :]
        cols = np.any(band, axis=0)
        if not cols.any():
            half_widths.append(0.0)
            centers.append(0.5)
            continue
        xs = np.where(cols)[0]
        x0, x1 = int(xs.min()), int(xs.max())
        half_widths.append(((x1 - x0) * 0.5) / max(w * 0.5, 1e-6))
        centers.append(((x0 + x1) * 0.5) / max(w, 1))
    # 이미지 y=0이 위 → 메쉬 up 축과 맞추려면 뒤집음
    half_widths = half_widths[::-1]
    centers = centers[::-1]
    return {
        "half_widths": half_widths,
        "centers": centers,
        "bins": bins,
        "image_size": [w, h],
    }


def _smooth_1d(vals: list[float], passes: int = 2) -> np.ndarray:
    a = np.array(vals, dtype=np.float64)
    for _ in range(passes):
        pad = np.pad(a, 1, mode="edge")
        a = 0.25 * pad[:-2] + 0.5 * pad[1:-1] + 0.25 * pad[2:]
    return a


def deform_obj_by_silhouette(
    obj_path: str,
    mask_path: str,
    output_path: str,
    *,
    strength: float = 0.45,
    bins: int = 48,
    min_scale: float = 0.75,
    max_scale: float = 1.35,
) -> dict[str, Any]:
    """마스크 폭 프로파일로 X 좌표 스케일. strength=0이면 복사만."""
    verts, faces = load_obj(obj_path)
    if verts.size == 0:
        raise ValueError(f"empty OBJ: {obj_path}")

    profile = mask_width_profile(mask_path, bins=bins)
    target_hw = _smooth_1d(profile["half_widths"])

    ys = verts[:, 1]
    y0, y1 = float(ys.min()), float(ys.max())
    dy = max(y1 - y0, 1e-6)

    # 메쉬 자체 밴드 half-width
    mesh_hw = np.zeros(bins, dtype=np.float64)
    counts = np.zeros(bins, dtype=np.float64)
    for v in verts:
        bi = int(np.clip((v[1] - y0) / dy * (bins - 1e-6), 0, bins - 1))
        mesh_hw[bi] = max(mesh_hw[bi], abs(float(v[0])))
        counts[bi] += 1
    # 빈 밴드 보간
    for i in range(bins):
        if counts[i] == 0:
            mesh_hw[i] = mesh_hw[i - 1] if i else 0.0
    mesh_hw = _smooth_1d(mesh_hw.tolist())
    mesh_hw = np.maximum(mesh_hw, 1e-6)

    # 타겟: 메쉬 평균 half-width * 마스크 상대폭 / 마스크 평균
    mask_mean = float(np.mean(target_hw[target_hw > 0.05])) if np.any(target_hw > 0.05) else 1.0
    mesh_mean = float(np.mean(mesh_hw))
    desired = mesh_hw.copy()
    for i in range(bins):
        rel = float(target_hw[i] / max(mask_mean, 1e-6))
        desired[i] = mesh_mean * rel

    scales = desired / mesh_hw
    scales = np.clip(scales, min_scale, max_scale)
    # strength로 1.0과 블렌드
    scales = 1.0 + (scales - 1.0) * float(np.clip(strength, 0.0, 1.0))
    scales = _smooth_1d(scales.tolist(), passes=1)

    out = verts.copy()
    for i, v in enumerate(out):
        bi = int(np.clip((v[1] - y0) / dy * (bins - 1e-6), 0, bins - 1))
        # 이웃 밴드 선형 보간
        t = ((v[1] - y0) / dy) * (bins - 1)
        i0 = int(np.floor(t))
        i1 = min(bins - 1, i0 + 1)
        frac = t - i0
        s = (1 - frac) * scales[i0] + frac * scales[i1]
        out[i, 0] = v[0] * s

    _write_obj(output_path, out, faces)
    max_delta = float(np.max(np.abs(out[:, 0] - verts[:, 0])))
    return {
        "ok": True,
        "path": output_path,
        "strength": strength,
        "bins": bins,
        "max_abs_x_delta": round(max_delta, 5),
        "scale_min": round(float(scales.min()), 4),
        "scale_max": round(float(scales.max()), 4),
        "source_obj": obj_path,
        "mask": mask_path,
    }


def _write_obj(path: str, verts: np.ndarray, faces: np.ndarray) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("# silhouette_deform\n")
        for v in verts:
            f.write(f"v {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n")
        for face in faces:
            f.write(f"f {face[0]+1} {face[1]+1} {face[2]+1}\n")
