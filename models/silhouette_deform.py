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


def extract_foreground(mask_path: str) -> np.ndarray:
    """마스크/사진에서 전경 bool 배열 추출.

    - 의미 있는 알파 → 알파 임계
    - 불투명 RGB → 가장자리 색 거리 + 밝기 후보
    """
    from PIL import Image

    img = Image.open(mask_path)
    has_alpha = img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)
    arr = np.array(img.convert("RGBA"))
    rgb = arr[:, :, :3].astype(np.float64)
    alpha = arr[:, :, 3]
    gray = rgb.mean(axis=2)
    h, w = gray.shape

    if has_alpha and float(alpha.max()) >= 10 and float(alpha.mean()) < 250:
        return (alpha > 30).astype(bool)

    # 테두리 색을 배경으로 추정
    border = np.concatenate([
        rgb[0, :, :], rgb[-1, :, :], rgb[:, 0, :], rgb[:, -1, :],
    ], axis=0)
    bg = border.mean(axis=0)
    dist = np.linalg.norm(rgb - bg[None, None, :], axis=2)
    dthr = max(28.0, float(np.percentile(dist, 55)) * 0.55)
    by_border = dist > dthr

    bright = gray > 40
    dark = gray < 215
    cov_b, cov_d = float(bright.mean()), float(dark.mean())
    cand = []
    cov_border = float(by_border.mean())
    if 0.02 <= cov_border <= 0.92:
        cand.append((abs(cov_border - 0.35), by_border))
    if 0.02 <= cov_b <= 0.92:
        cand.append((abs(cov_b - 0.35), bright))
    if 0.02 <= cov_d <= 0.92:
        cand.append((abs(cov_d - 0.35), dark))
    if cand:
        cand.sort(key=lambda t: t[0])
        fg = cand[0][1]
    else:
        fg = bright if cov_b < cov_d else dark
    return fg.astype(bool)


def mask_width_profile(mask_path: str, bins: int = 48) -> dict[str, Any]:
    """알파/밝은 픽셀 기준 세로 밴드별 half-width (정규화 0~1)."""
    fg = extract_foreground(mask_path)
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


def mesh_width_profile(verts: np.ndarray, bins: int = 48, axis: int = 0) -> dict[str, Any]:
    """메쉬 Y-밴드별 half-width (axis=0 → X, axis=2 → Z)."""
    v = np.asarray(verts, dtype=np.float64)
    if v.size == 0:
        return {"half_widths": [0.0] * bins, "bins": bins, "axis": axis}
    y = v[:, 1]
    y0, y1 = float(y.min()), float(y.max())
    dy = max(y1 - y0, 1e-9)
    hw = []
    for i in range(bins):
        lo = y0 + (i / bins) * dy
        hi = y0 + ((i + 1) / bins) * dy
        band = v[(y >= lo) & (y <= hi + 1e-12)]
        if len(band) < 2:
            hw.append(0.0)
        else:
            hw.append(0.5 * float(band[:, axis].max() - band[:, axis].min()))
    for i in range(1, bins):
        if hw[i] <= 1e-9:
            hw[i] = hw[i - 1]
    for i in range(bins - 2, -1, -1):
        if hw[i] <= 1e-9:
            hw[i] = hw[i + 1]
    return {
        "half_widths": hw,
        "bins": bins,
        "axis": axis,
        "active_bands": int(sum(1 for x in hw if x > 1e-6)),
    }


def mesh_waist_halfwidth(verts: np.ndarray, *, top_frac: float = 0.12) -> float:
    """상의/스커트 상단(허리/어깨) 밴드 X half-width."""
    v = np.asarray(verts, dtype=np.float64)
    if v.size == 0:
        return 0.0
    y = v[:, 1]
    y0, y1 = float(y.min()), float(y.max())
    dy = max(y1 - y0, 1e-9)
    band = v[y >= (y1 - top_frac * dy)]
    if len(band) < 2:
        band = v
    return 0.5 * float(band[:, 0].max() - band[:, 0].min())


def mesh_leg_profiles(verts: np.ndarray, bins: int = 24) -> dict[str, Any]:
    """메쉬 Y-밴드에서 좌/우 다리 half-width·중심 (X=0 기준 분할)."""
    v = np.asarray(verts, dtype=np.float64)
    if v.size == 0:
        z = [0.0] * bins
        return {"left_leg_hw": z, "right_leg_hw": z, "left_leg_cx": z, "right_leg_cx": z,
                "separation": z, "bins": bins}
    y = v[:, 1]
    y0, y1 = float(y.min()), float(y.max())
    dy = max(y1 - y0, 1e-9)
    cx0 = 0.5 * (float(v[:, 0].min()) + float(v[:, 0].max()))
    left_hw, right_hw, left_cx, right_cx, sep = [], [], [], [], []
    for i in range(bins):
        lo = y0 + (i / bins) * dy
        hi = y0 + ((i + 1) / bins) * dy
        band = v[(y >= lo) & (y <= hi + 1e-12)]
        if len(band) < 2:
            left_hw.append(0.0); right_hw.append(0.0)
            left_cx.append(cx0); right_cx.append(cx0); sep.append(0.0)
            continue
        left = band[band[:, 0] <= cx0]
        right = band[band[:, 0] > cx0]
        if len(left) >= 2:
            left_hw.append(0.5 * float(left[:, 0].max() - left[:, 0].min()))
            left_cx.append(float(left[:, 0].mean()))
        else:
            left_hw.append(0.0); left_cx.append(cx0)
        if len(right) >= 2:
            right_hw.append(0.5 * float(right[:, 0].max() - right[:, 0].min()))
            right_cx.append(float(right[:, 0].mean()))
        else:
            right_hw.append(0.0); right_cx.append(cx0)
        sep.append(max(0.0, float(right_cx[-1] - left_cx[-1])))
    return {
        "left_leg_hw": left_hw,
        "right_leg_hw": right_hw,
        "left_leg_cx": left_cx,
        "right_leg_cx": right_cx,
        "separation": sep,
        "bins": bins,
    }


def normalize_halfwidth_profile(half_widths: list[float] | np.ndarray) -> np.ndarray:
    """활성 밴드 평균으로 나눠 shape-only 프로파일."""
    a = np.asarray(half_widths, dtype=np.float64)
    active = a[a > 1e-6]
    mean = float(active.mean()) if active.size else 1.0
    if mean <= 1e-9:
        mean = 1.0
    return a / mean


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
    length_fit: bool = True,
    garment_type: str = "",
) -> dict[str, Any]:
    """정면 X 디폼 + (옵션) 측면 Z·Y길이 + 하의 bipodal 다리 분리."""
    verts, faces = load_obj(obj_path)
    if verts.size == 0:
        raise ValueError(f"empty OBJ: {obj_path}")

    gtype = (garment_type or "").lower()
    is_skirt = gtype in ("skirt",)
    is_pants = gtype in ("pants", "shorts", "trousers")

    profile = mask_width_profile(mask_path, bins=bins)
    quality = mask_quality_score(profile)
    # 전경이 프레임 전체면 품질 강등
    if float(profile.get("coverage") or 0) >= 0.96:
        quality = min(quality, 0.15)

    use_bipodal = False
    if is_skirt:
        # 스커트: 다리 분리 금지
        bipodal = "off"
    if bipodal is True or bipodal == "force":
        use_bipodal = True
    elif bipodal in (False, "off", "0", "false", "no"):
        use_bipodal = False
    elif bipodal == "auto":
        use_bipodal = is_pants and float(profile.get("bipodal_score") or 0) >= 0.35

    # 스커트: 허리(상단 밴드) 스케일 클램프를 위해 프로파일 상단 평탄화
    if is_skirt:
        hw = list(profile.get("half_widths") or [])
        if hw:
            top_n = max(2, len(hw) // 8)
            # 상단(허리)은 밴드 평균으로 고정해 waist drift 완화
            waist_ref = float(np.mean(hw[-top_n:])) if top_n else float(hw[-1])
            for i in range(len(hw) - top_n, len(hw)):
                hw[i] = waist_ref * 0.55 + hw[i] * 0.45
            profile = dict(profile)
            profile["half_widths"] = hw
        # 허리 근처 edge-snap 약화
        edge_snap = float(edge_snap) * 0.45

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

    length_report = None
    if length_fit:
        # 마스크 bbox 세로 점유율 → 약한 길이 스케일 (앵커: 상의=어깨/상단, 하의=허리)
        try:
            fg = extract_foreground(mask_path)
            cov = float(fg.mean()) if fg.size else 0.0
            if cov >= 0.96 or cov < 0.02 or not fg.any():
                length_report = {
                    "ok": False,
                    "skipped": True,
                    "reason": "full_frame_or_empty",
                    "occupancy": round(cov, 3),
                }
            else:
                ys_i = np.where(fg.any(axis=1))[0]
                occ = (ys_i.max() - ys_i.min() + 1) / max(fg.shape[0], 1)
                target = float(np.clip(0.85 + occ * 0.35, 0.90, 1.10))
                scale_y = 1.0 + (target - 1.0) * float(np.clip(strength, 0, 1)) * 0.45
                y_lo = float(out[:, 1].min())
                y_hi = float(out[:, 1].max())
                # 스커트/바지: 허리(상단) 고정, 상의: 어깨(상단) 고정
                if is_skirt or is_pants:
                    anchor = y_hi
                    out[:, 1] = anchor + (out[:, 1] - anchor) * scale_y
                    anchor_mode = "waist_top"
                else:
                    anchor = y_hi
                    out[:, 1] = anchor + (out[:, 1] - anchor) * scale_y
                    anchor_mode = "shoulder_top"
                length_report = {
                    "ok": True,
                    "occupancy": round(float(occ), 3),
                    "scale_y": round(float(scale_y), 4),
                    "anchor": anchor_mode,
                }
        except Exception as e:
            length_report = {"ok": False, "error": str(e)}

    if smooth_iters > 0:
        out = _laplacian_smooth(out, faces, iterations=int(smooth_iters), lam=0.28)

    _write_obj(output_path, out, faces)
    max_dx = float(np.max(np.abs(out[:, 0] - verts[:, 0])))
    max_dz = float(np.max(np.abs(out[:, 2] - verts[:, 2])))
    max_dy = float(np.max(np.abs(out[:, 1] - verts[:, 1])))
    return {
        "ok": True,
        "path": output_path,
        "strength": strength,
        "bins": bins,
        "edge_snap": snap_w,
        "mask_quality": quality,
        "max_abs_x_delta": round(max_dx, 5),
        "max_abs_y_delta": round(max_dy, 5),
        "max_abs_z_delta": round(max_dz, 5),
        "length_fit": length_report,
        "scale_min": round(float(scales_x.min()), 4),
        "scale_max": round(float(scales_x.max()), 4),
        "shift_abs_max": round(float(np.max(np.abs(shifts_x))), 5),
        "edge_snap_abs_max": round(float(max(edge_deltas) if edge_deltas else 0.0), 5),
        "depth": depth_report,
        "bipodal": bool(use_bipodal),
        "bipodal_score": profile.get("bipodal_score"),
        "garment_type": gtype or None,
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
