"""P1 — 정면 실루엣 마스크로 메쉬 가로폭·윤곽 보정.

세그 마스크의 높이별 폭 프로파일을 읽어 OBJ의 X 스케일/센터를
밴드별로 맞추고, 옵션으로 경계 정점 edge-snap을 적용한다.
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
    if alpha.max() < 10:
        gray = arr[:, :, :3].mean(axis=2)
        fg = gray > 30
    else:
        fg = alpha > 30

    h, w = fg.shape
    ys = np.linspace(0, h, bins + 1).astype(int)
    half_widths = []
    centers = []
    left_edges = []
    right_edges = []
    coverage = float(fg.mean())
    for i in range(bins):
        y0, y1 = ys[i], max(ys[i] + 1, ys[i + 1])
        band = fg[y0:y1, :]
        cols = np.any(band, axis=0)
        if not cols.any():
            half_widths.append(0.0)
            centers.append(0.5)
            left_edges.append(0.5)
            right_edges.append(0.5)
            continue
        xs = np.where(cols)[0]
        x0, x1 = int(xs.min()), int(xs.max())
        half_widths.append(((x1 - x0) * 0.5) / max(w * 0.5, 1e-6))
        centers.append(((x0 + x1) * 0.5) / max(w, 1))
        left_edges.append(x0 / max(w, 1))
        right_edges.append(x1 / max(w, 1))
    # 이미지 y=0이 위 → 메쉬 up 축과 맞추려면 뒤집음
    half_widths = half_widths[::-1]
    centers = centers[::-1]
    left_edges = left_edges[::-1]
    right_edges = right_edges[::-1]
    return {
        "half_widths": half_widths,
        "centers": centers,
        "left_edges": left_edges,
        "right_edges": right_edges,
        "bins": bins,
        "image_size": [w, h],
        "coverage": coverage,
        "active_bands": int(sum(1 for hw in half_widths if hw > 0.05)),
    }


def mask_quality_score(profile: dict[str, Any]) -> float:
    """0~1. 자동 실루엣 디폼 게이트용."""
    coverage = float(profile.get("coverage") or 0.0)
    bins = int(profile.get("bins") or 1)
    active = int(profile.get("active_bands") or 0)
    hw = np.array(profile.get("half_widths") or [], dtype=np.float64)
    if hw.size == 0:
        return 0.0
    active_ratio = active / max(bins, 1)
    variance = float(np.std(hw[hw > 0.05])) if np.any(hw > 0.05) else 0.0
    # 너무 균일하면(직사각) 약하게, 적당한 변화면 가점
    shape = float(np.clip(variance * 4.0, 0.0, 1.0))
    score = 0.45 * float(np.clip(coverage / 0.35, 0, 1))
    score += 0.35 * float(np.clip(active_ratio, 0, 1))
    score += 0.20 * shape
    return round(float(np.clip(score, 0, 1)), 3)


def should_auto_enable(mask_path: str, *, min_score: float = 0.42, bins: int = 48) -> dict[str, Any]:
    """마스크 품질이 충분하면 실루엣 디폼 자동 활성."""
    if not mask_path or not os.path.exists(mask_path):
        return {"enable": False, "score": 0.0, "reason": "no_mask"}
    try:
        profile = mask_width_profile(mask_path, bins=bins)
    except Exception as e:
        return {"enable": False, "score": 0.0, "reason": f"profile_error:{e}"}
    score = mask_quality_score(profile)
    ok = score >= float(min_score) and int(profile.get("active_bands") or 0) >= max(8, bins // 6)
    return {
        "enable": bool(ok),
        "score": score,
        "min_score": min_score,
        "active_bands": profile.get("active_bands"),
        "coverage": profile.get("coverage"),
        "reason": "ok" if ok else "low_quality",
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
    edge_snap: float = 0.0,
) -> dict[str, Any]:
    """마스크 폭 프로파일로 X 스케일 + 옵션 edge-snap.

    edge_snap: 0~1, 경계 정점을 마스크 left/right 윤곽으로 추가 끌어당김.
    """
    verts, faces = load_obj(obj_path)
    if verts.size == 0:
        raise ValueError(f"empty OBJ: {obj_path}")

    profile = mask_width_profile(mask_path, bins=bins)
    quality = mask_quality_score(profile)
    target_hw = _smooth_1d(profile["half_widths"])
    target_cx = _smooth_1d(profile.get("centers") or [0.5] * bins)
    target_left = _smooth_1d(profile.get("left_edges") or [0.0] * bins)
    target_right = _smooth_1d(profile.get("right_edges") or [1.0] * bins)

    ys = verts[:, 1]
    y0, y1 = float(ys.min()), float(ys.max())
    dy = max(y1 - y0, 1e-6)
    x0, x1 = float(verts[:, 0].min()), float(verts[:, 0].max())
    mesh_cx = 0.5 * (x0 + x1)
    mesh_half_span = max(0.5 * (x1 - x0), 1e-6)
    mesh_span = max(x1 - x0, 1e-6)

    mesh_hw = np.zeros(bins, dtype=np.float64)
    counts = np.zeros(bins, dtype=np.float64)
    for v in verts:
        bi = int(np.clip((v[1] - y0) / dy * (bins - 1e-6), 0, bins - 1))
        mesh_hw[bi] = max(mesh_hw[bi], abs(float(v[0]) - mesh_cx))
        counts[bi] += 1
    for i in range(bins):
        if counts[i] == 0:
            mesh_hw[i] = mesh_hw[i - 1] if i else 0.0
    mesh_hw = _smooth_1d(mesh_hw.tolist())
    mesh_hw = np.maximum(mesh_hw, 1e-6)

    mask_mean = float(np.mean(target_hw[target_hw > 0.05])) if np.any(target_hw > 0.05) else 1.0
    mesh_mean = float(np.mean(mesh_hw))
    desired = mesh_hw.copy()
    for i in range(bins):
        rel = float(target_hw[i] / max(mask_mean, 1e-6))
        desired[i] = mesh_mean * rel

    scales = desired / mesh_hw
    scales = np.clip(scales, min_scale, max_scale)
    scales = 1.0 + (scales - 1.0) * float(np.clip(strength, 0.0, 1.0))
    scales = _smooth_1d(scales.tolist(), passes=1)

    shifts = (target_cx - 0.5) * 2.0 * mesh_half_span * float(np.clip(strength, 0.0, 1.0)) * 0.35
    shifts = _smooth_1d(shifts.tolist(), passes=1)

    # 마스크 정규화 좌표 → 메쉬 X
    snap_left = mesh_cx + (target_left - 0.5) * mesh_span
    snap_right = mesh_cx + (target_right - 0.5) * mesh_span
    snap_left = _smooth_1d(snap_left.tolist(), passes=1)
    snap_right = _smooth_1d(snap_right.tolist(), passes=1)
    snap_w = float(np.clip(edge_snap, 0.0, 1.0)) * float(np.clip(strength, 0.0, 1.0))

    out = verts.copy()
    edge_deltas = []
    for i, v in enumerate(out):
        t = ((v[1] - y0) / dy) * (bins - 1)
        i0 = int(np.floor(t))
        i1 = min(bins - 1, i0 + 1)
        frac = t - i0
        s = (1 - frac) * scales[i0] + frac * scales[i1]
        sh = (1 - frac) * shifts[i0] + frac * shifts[i1]
        x = mesh_cx + (v[0] - mesh_cx) * s + sh

        if snap_w > 1e-6:
            # 외곽 정점만: |x-cx| / half_span 이 큰 쪽
            rel = abs(float(v[0]) - mesh_cx) / mesh_half_span
            if rel > 0.72:
                tl = (1 - frac) * snap_left[i0] + frac * snap_left[i1]
                tr = (1 - frac) * snap_right[i0] + frac * snap_right[i1]
                target = tl if v[0] < mesh_cx else tr
                # 밴드 경계일수록 강하게
                edge_w = snap_w * float(np.clip((rel - 0.72) / 0.28, 0, 1))
                nx = (1.0 - edge_w) * x + edge_w * target
                edge_deltas.append(abs(nx - x))
                x = nx
        out[i, 0] = x

    _write_obj(output_path, out, faces)
    max_delta = float(np.max(np.abs(out[:, 0] - verts[:, 0])))
    return {
        "ok": True,
        "path": output_path,
        "strength": strength,
        "bins": bins,
        "edge_snap": snap_w,
        "mask_quality": quality,
        "max_abs_x_delta": round(max_delta, 5),
        "scale_min": round(float(scales.min()), 4),
        "scale_max": round(float(scales.max()), 4),
        "shift_abs_max": round(float(np.max(np.abs(shifts))), 5),
        "edge_snap_abs_max": round(float(max(edge_deltas) if edge_deltas else 0.0), 5),
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
