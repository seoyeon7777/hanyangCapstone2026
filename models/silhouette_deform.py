"""P1 — 정면/측면 실루엣으로 메쉬 가로폭(X)·깊이(Z) 보정.

- 정면 마스크 → 밴드별 X 스케일 + 센터 시프트 + edge-snap
- 측면 마스크 → 밴드별 Z 스케일 (앞뒤 두께)
- 옵션 laplacian 스무딩으로 접힘 완화
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
    left_leg_hw = []
    right_leg_hw = []
    left_leg_cx = []
    right_leg_cx = []
    bipodal_flags = []
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
            left_leg_hw.append(0.0)
            right_leg_hw.append(0.0)
            left_leg_cx.append(0.25)
            right_leg_cx.append(0.75)
            bipodal_flags.append(0.0)
            continue
        xs = np.where(cols)[0]
        x0, x1 = int(xs.min()), int(xs.max())
        half_widths.append(((x1 - x0) * 0.5) / max(w * 0.5, 1e-6))
        centers.append(((x0 + x1) * 0.5) / max(w, 1))
        left_edges.append(x0 / max(w, 1))
        right_edges.append(x1 / max(w, 1))
        # bipodal: find center gap in band
        col_mask = cols.astype(np.uint8)
        mid = len(col_mask) // 2
        # scan for empty run near center
        gap = 0
        i = mid
        while i > 0 and col_mask[i] == 0:
            gap += 1
            i -= 1
        j = mid
        while j < len(col_mask) - 1 and col_mask[j] == 0:
            gap += 1
            j += 1
        if gap >= max(3, w // 40) and col_mask[:mid].any() and col_mask[mid:].any():
            lx = np.where(col_mask[:mid])[0]
            rx = np.where(col_mask[mid:])[0] + mid
            left_leg_hw.append(((lx.max() - lx.min()) * 0.5) / max(w * 0.5, 1e-6) if len(lx) else 0.0)
            right_leg_hw.append(((rx.max() - rx.min()) * 0.5) / max(w * 0.5, 1e-6) if len(rx) else 0.0)
            left_leg_cx.append(float(lx.mean()) / w if len(lx) else 0.25)
            right_leg_cx.append(float(rx.mean()) / w if len(rx) else 0.75)
            bipodal_flags.append(1.0)
        else:
            left_leg_hw.append(0.0)
            right_leg_hw.append(0.0)
            left_leg_cx.append(0.25)
            right_leg_cx.append(0.75)
            bipodal_flags.append(0.0)
    half_widths = half_widths[::-1]
    centers = centers[::-1]
    left_edges = left_edges[::-1]
    right_edges = right_edges[::-1]
    left_leg_hw = left_leg_hw[::-1]
    right_leg_hw = right_leg_hw[::-1]
    left_leg_cx = left_leg_cx[::-1]
    right_leg_cx = right_leg_cx[::-1]
    bipodal_flags = bipodal_flags[::-1]
    bipodal_score = float(np.mean(bipodal_flags[int(bins * 0.15): int(bins * 0.55)])) if bins else 0.0
    return {
        "half_widths": half_widths,
        "centers": centers,
        "left_edges": left_edges,
        "right_edges": right_edges,
        "left_leg_hw": left_leg_hw,
        "right_leg_hw": right_leg_hw,
        "left_leg_cx": left_leg_cx,
        "right_leg_cx": right_leg_cx,
        "bipodal_flags": bipodal_flags,
        "bipodal_score": round(bipodal_score, 3),
        "bins": bins,
        "image_size": [w, h],
        "coverage": coverage,
        "active_bands": int(sum(1 for hw in half_widths if hw > 0.05)),
    }


def mask_depth_profile(mask_path: str, bins: int = 48) -> dict[str, Any]:
    """측면 마스크 → 세로 밴드별 깊이(half-depth) 프로파일.

    측면 사진에서 가로축이 앞뒤 두께에 대응한다고 가정.
    """
    return mask_width_profile(mask_path, bins=bins)


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
    shape = float(np.clip(variance * 4.0, 0.0, 1.0))
    score = 0.45 * float(np.clip(coverage / 0.35, 0, 1))
    score += 0.35 * float(np.clip(active_ratio, 0, 1))
    score += 0.20 * shape
    return round(float(np.clip(score, 0, 1)), 3)


def should_auto_enable(mask_path: str, *, min_score: float = 0.42, bins: int = 48) -> dict[str, Any]:
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


def _band_scales_from_profile(
    verts: np.ndarray,
    profile: dict[str, Any],
    axis: int,
    *,
    strength: float,
    bins: int,
    min_scale: float,
    max_scale: float,
) -> tuple[np.ndarray, np.ndarray, float]:
    """axis(0=X,2=Z)에 대한 밴드 스케일/시프트와 mesh center 반환."""
    target_hw = _smooth_1d(profile["half_widths"])
    target_cx = _smooth_1d(profile.get("centers") or [0.5] * bins)

    ys = verts[:, 1]
    y0, y1 = float(ys.min()), float(ys.max())
    dy = max(y1 - y0, 1e-6)
    a0, a1 = float(verts[:, axis].min()), float(verts[:, axis].max())
    mesh_c = 0.5 * (a0 + a1)
    mesh_half = max(0.5 * (a1 - a0), 1e-6)

    mesh_hw = np.zeros(bins, dtype=np.float64)
    counts = np.zeros(bins, dtype=np.float64)
    for v in verts:
        bi = int(np.clip((v[1] - y0) / dy * (bins - 1e-6), 0, bins - 1))
        mesh_hw[bi] = max(mesh_hw[bi], abs(float(v[axis]) - mesh_c))
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

    shifts = (target_cx - 0.5) * 2.0 * mesh_half * float(np.clip(strength, 0.0, 1.0)) * 0.35
    shifts = _smooth_1d(shifts.tolist(), passes=1)
    return scales, shifts, mesh_c


def _laplacian_smooth(verts: np.ndarray, faces: np.ndarray, *, iterations: int = 2, lam: float = 0.35) -> np.ndarray:
    """간단한 균등 라플라시안 (경계 보존 약함)."""
    if iterations <= 0 or faces.size == 0:
        return verts
    n = len(verts)
    adj: list[set[int]] = [set() for _ in range(n)]
    for f in faces:
        a, b, c = int(f[0]), int(f[1]), int(f[2])
        adj[a].update((b, c))
        adj[b].update((a, c))
        adj[c].update((a, b))
    out = verts.copy()
    for _ in range(iterations):
        nxt = out.copy()
        for i in range(n):
            if not adj[i]:
                continue
            nbrs = list(adj[i])
            mean = out[nbrs].mean(axis=0)
            nxt[i] = out[i] * (1.0 - lam) + mean * lam
            # Y는 덜 움직임 (길이 보존)
            nxt[i, 1] = out[i, 1] * 0.85 + nxt[i, 1] * 0.15
        out = nxt
    return out


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
    side_mask_path: Optional[str] = None,
    depth_strength: Optional[float] = None,
    smooth_iters: int = 1,
    bipodal: bool | str = "auto",
) -> dict[str, Any]:
    """정면 X 디폼 + (옵션) 측면 Z 디폼 + 하의 bipodal 다리 분리."""
    verts, faces = load_obj(obj_path)
    if verts.size == 0:
        raise ValueError(f"empty OBJ: {obj_path}")

    profile = mask_width_profile(mask_path, bins=bins)
    quality = mask_quality_score(profile)
    use_bipodal = False
    if bipodal is True or bipodal == "force":
        use_bipodal = True
    elif bipodal in (False, "off", "0", "false", "no"):
        use_bipodal = False
    elif bipodal == "auto":
        use_bipodal = float(profile.get("bipodal_score") or 0) >= 0.35
    scales_x, shifts_x, mesh_cx = _band_scales_from_profile(
        verts, profile, 0, strength=strength, bins=bins, min_scale=min_scale, max_scale=max_scale
    )
    left_leg_hw = _smooth_1d(profile.get("left_leg_hw") or [0.0] * bins)
    right_leg_hw = _smooth_1d(profile.get("right_leg_hw") or [0.0] * bins)
    left_leg_cx = _smooth_1d(profile.get("left_leg_cx") or [0.25] * bins)
    right_leg_cx = _smooth_1d(profile.get("right_leg_cx") or [0.75] * bins)
    bipodal_flags = np.array(profile.get("bipodal_flags") or [0.0] * bins, dtype=np.float64)


    target_left = _smooth_1d(profile.get("left_edges") or [0.0] * bins)
    target_right = _smooth_1d(profile.get("right_edges") or [1.0] * bins)
    x0, x1 = float(verts[:, 0].min()), float(verts[:, 0].max())
    mesh_span = max(x1 - x0, 1e-6)
    mesh_half_span = 0.5 * mesh_span
    snap_left = mesh_cx + (target_left - 0.5) * mesh_span
    snap_right = mesh_cx + (target_right - 0.5) * mesh_span
    snap_left = _smooth_1d(snap_left.tolist(), passes=1)
    snap_right = _smooth_1d(snap_right.tolist(), passes=1)
    snap_w = float(np.clip(edge_snap, 0.0, 1.0)) * float(np.clip(strength, 0.0, 1.0))

    ys = verts[:, 1]
    y0, y1 = float(ys.min()), float(ys.max())
    dy = max(y1 - y0, 1e-6)

    # 측면 깊이
    depth_report = None
    scales_z = None
    shifts_z = None
    mesh_cz = float(0.5 * (verts[:, 2].min() + verts[:, 2].max()))
    d_strength = float(depth_strength if depth_strength is not None else strength * 0.75)
    if side_mask_path and os.path.exists(side_mask_path) and d_strength > 1e-6:
        try:
            dprofile = mask_depth_profile(side_mask_path, bins=bins)
            scales_z, shifts_z, mesh_cz = _band_scales_from_profile(
                verts,
                dprofile,
                2,
                strength=d_strength,
                bins=bins,
                min_scale=min_scale,
                max_scale=max_scale,
            )
            depth_report = {
                "ok": True,
                "mask": side_mask_path,
                "strength": d_strength,
                "quality": mask_quality_score(dprofile),
                "scale_min": round(float(scales_z.min()), 4),
                "scale_max": round(float(scales_z.max()), 4),
            }
        except Exception as e:
            depth_report = {"ok": False, "error": str(e)}

    out = verts.copy()
    edge_deltas = []
    for i, v in enumerate(out):
        t = ((v[1] - y0) / dy) * (bins - 1)
        i0 = int(np.floor(t))
        i1 = min(bins - 1, i0 + 1)
        frac = t - i0
        sx = (1 - frac) * scales_x[i0] + frac * scales_x[i1]
        shx = (1 - frac) * shifts_x[i0] + frac * shifts_x[i1]
        x = mesh_cx + (v[0] - mesh_cx) * sx + shx

        # bipodal: 하단에 다리가 둘이면 각 다리 중심 기준으로 국소 스케일
        if use_bipodal:
            bf = (1 - frac) * bipodal_flags[i0] + frac * bipodal_flags[i1]
            if bf > 0.4:
                llc = (1 - frac) * left_leg_cx[i0] + frac * left_leg_cx[i1]
                rlc = (1 - frac) * right_leg_cx[i0] + frac * right_leg_cx[i1]
                llh = (1 - frac) * left_leg_hw[i0] + frac * left_leg_hw[i1]
                rlh = (1 - frac) * right_leg_hw[i0] + frac * right_leg_hw[i1]
                # normalize mask centers to mesh X
                left_c = mesh_cx + (llc - 0.5) * mesh_span
                right_c = mesh_cx + (rlc - 0.5) * mesh_span
                # choose nearer leg
                if abs(float(v[0]) - left_c) <= abs(float(v[0]) - right_c):
                    leg_c, leg_hw = left_c, max(llh, 0.05) * mesh_half_span
                else:
                    leg_c, leg_hw = right_c, max(rlh, 0.05) * mesh_half_span
                # scale around leg center toward desired half-width vs current distance
                cur = abs(float(v[0]) - leg_c)
                if cur > 1e-6 and leg_hw > 1e-6:
                    # blend toward mask leg width
                    target_scale = float(np.clip(leg_hw / max(cur, 1e-6), min_scale, max_scale))
                    target_scale = 1.0 + (target_scale - 1.0) * strength * bf
                    x = leg_c + (float(v[0]) - leg_c) * target_scale * (0.35 + 0.65 * sx)

        if snap_w > 1e-6:
            rel = abs(float(v[0]) - mesh_cx) / mesh_half_span
            if rel > 0.72:
                tl = (1 - frac) * snap_left[i0] + frac * snap_left[i1]
                tr = (1 - frac) * snap_right[i0] + frac * snap_right[i1]
                target = tl if v[0] < mesh_cx else tr
                edge_w = snap_w * float(np.clip((rel - 0.72) / 0.28, 0, 1))
                nx = (1.0 - edge_w) * x + edge_w * target
                edge_deltas.append(abs(nx - x))
                x = nx
        out[i, 0] = x

        if scales_z is not None and shifts_z is not None:
            sz = (1 - frac) * scales_z[i0] + frac * scales_z[i1]
            shz = (1 - frac) * shifts_z[i0] + frac * shifts_z[i1]
            out[i, 2] = mesh_cz + (v[2] - mesh_cz) * sz + shz * 0.5

    if smooth_iters > 0:
        out = _laplacian_smooth(out, faces, iterations=int(smooth_iters), lam=0.28)

    _write_obj(output_path, out, faces)
    max_dx = float(np.max(np.abs(out[:, 0] - verts[:, 0])))
    max_dz = float(np.max(np.abs(out[:, 2] - verts[:, 2])))
    return {
        "ok": True,
        "path": output_path,
        "strength": strength,
        "bins": bins,
        "edge_snap": snap_w,
        "mask_quality": quality,
        "max_abs_x_delta": round(max_dx, 5),
        "max_abs_z_delta": round(max_dz, 5),
        "scale_min": round(float(scales_x.min()), 4),
        "scale_max": round(float(scales_x.max()), 4),
        "shift_abs_max": round(float(np.max(np.abs(shifts_x))), 5),
        "edge_snap_abs_max": round(float(max(edge_deltas) if edge_deltas else 0.0), 5),
        "depth": depth_report,
        "bipodal": bool(use_bipodal),
        "bipodal_score": profile.get("bipodal_score"),
        "smooth_iters": smooth_iters,
        "source_obj": obj_path,
        "mask": mask_path,
        "side_mask": side_mask_path,
    }


def _write_obj(path: str, verts: np.ndarray, faces: np.ndarray) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("# silhouette_deform\n")
        for v in verts:
            f.write(f"v {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n")
        for face in faces:
            f.write(f"f {face[0]+1} {face[1]+1} {face[2]+1}\n")
