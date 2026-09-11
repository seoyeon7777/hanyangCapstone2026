"""의류 **제품** 실루엣 보정.

cloth_top Basis 는 아바타에 붙인 모래시계(허리 잘록 + 가슴 볼륨) 형태다.
이 모듈은 export 직후 OBJ 정점을 제품형(원통/약한 A-line)으로 펴서,
사람 착용 핏이 아니라 옷 자체 형태로 보이게 한다.

착용 시뮬(run_simulation) / 실루엣 디폼은 별도 단계에서 처리한다.
"""

from __future__ import annotations

import os
from typing import Optional


def _parse_obj_vertices(path: str) -> tuple[list[list[float]], list[str]]:
    verts: list[list[float]] = []
    lines: list[str] = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            lines.append(line)
            if line.startswith("v "):
                parts = line.split()
                verts.append([float(parts[1]), float(parts[2]), float(parts[3])])
    return verts, lines


def _write_obj_vertices(path: str, lines: list[str], verts: list[list[float]]) -> None:
    out: list[str] = []
    vi = 0
    for line in lines:
        if line.startswith("v "):
            x, y, z = verts[vi]
            out.append(f"v {x:.6f} {y:.6f} {z:.6f}\n")
            vi += 1
        else:
            out.append(line)
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(out)


def _percentile(vals: list[float], p: float) -> float:
    if not vals:
        return 0.0
    s = sorted(vals)
    i = int(max(0, min(len(s) - 1, round((len(s) - 1) * p))))
    return float(s[i])


def flatten_upper_garment_vertices(
    verts: list[list[float]],
    *,
    strength: float = 1.0,
    up_axis: int = 1,
    width_axis: int = 0,
    depth_axis: int = 2,
) -> tuple[list[list[float]], dict]:
    """상의 정점 → 제품형 실루엣.

    - 몸통(밑단~겨드랑이): |width| 을 chest/hem 엔벨로프 아래로 안 떨어지게 확장
    - 가슴 depth 피크를 완화해 '입은 가슴' 볼륨 감소
    """
    if not verts or strength <= 0:
        return verts, {"applied": False, "reason": "empty_or_zero_strength"}

    s = max(0.0, min(1.0, float(strength)))
    ups = [v[up_axis] for v in verts]
    umin, umax = min(ups), max(ups)
    span = umax - umin
    if span < 1e-6:
        return verts, {"applied": False, "reason": "degenerate"}

    def yfrac(v: list[float]) -> float:
        return (v[up_axis] - umin) / span

    # 밴드별 half-width / depth depth
    n_bins = 24
    bins_w: list[list[float]] = [[] for _ in range(n_bins)]
    bins_d: list[list[float]] = [[] for _ in range(n_bins)]
    for v in verts:
        t = yfrac(v)
        bi = min(n_bins - 1, max(0, int(t * n_bins)))
        bins_w[bi].append(abs(v[width_axis]))
        bins_d[bi].append(v[depth_axis])

    prof_w = [
        _percentile(b, 0.85) if b else 0.0 for b in bins_w
    ]
    # 가슴/어깨 쪽(상단) 폭과 밑단 폭으로 A-line 엔벨로프
    # yfrac≈0 밑단, ≈1 목 — cloth_top 기준
    hem_i = max(range(0, 4), key=lambda i: prof_w[i])
    chest_i = max(range(14, 20), key=lambda i: prof_w[i] if i < len(prof_w) else 0.0)
    hem_w = max(prof_w[hem_i], 1e-4)
    chest_w = max(prof_w[chest_i], 1e-4)

    # 몸통 구간: 밑단~겨드랑이 직전
    torso_lo, torso_hi = 0.02, 0.72
    # depth: 상체 전면 피크 완화 (bust)
    bust_lo, bust_hi = 0.55, 0.85
    depth_vals = [v[depth_axis] for v in verts if bust_lo <= yfrac(v) <= bust_hi]
    depth_med = _percentile(depth_vals, 0.50) if depth_vals else 0.0

    out: list[list[float]] = []
    n_expand = 0
    n_depth = 0
    for v in verts:
        nv = list(v)
        t = yfrac(v)
        # 목표 half-width: hem↔chest 선형, 기존보다 작지 않게
        u = max(0.0, min(1.0, t / max(torso_hi, 1e-6)))
        target_w = hem_w * (1.0 - u) + chest_w * u
        # 허리 밴드에서 특히 엔벨로프 강제
        if torso_lo <= t <= torso_hi:
            cur = abs(nv[width_axis])
            if cur < target_w and cur > 1e-5:
                scale = 1.0 + s * ((target_w / cur) - 1.0)
                nv[width_axis] *= scale
                n_expand += 1
        if bust_lo <= t <= bust_hi:
            # 앞가슴(+depth)만 중앙쪽으로
            d = nv[depth_axis]
            if d > depth_med:
                nv[depth_axis] = d + s * (depth_med - d) * 0.65
                n_depth += 1
        out.append(nv)

    meta = {
        "applied": True,
        "strength": s,
        "hem_w": round(hem_w, 4),
        "chest_w": round(chest_w, 4),
        "n_expand": n_expand,
        "n_depth": n_depth,
        "waist_before": round(min(prof_w[8:14]) if any(prof_w[8:14]) else 0.0, 4),
        "profile_w": [round(x, 4) for x in prof_w],
    }
    return out, meta


def apply_product_silhouette_obj(
    obj_path: str,
    *,
    strength: float = 1.0,
    output_path: Optional[str] = None,
) -> dict:
    """상의 OBJ에 제품 실루엣 보정을 적용해 덮어쓴다(또는 output_path에 저장)."""
    if not obj_path or not os.path.exists(obj_path):
        return {"applied": False, "reason": "missing_obj"}
    verts, lines = _parse_obj_vertices(obj_path)
    if not verts:
        return {"applied": False, "reason": "no_vertices"}
    new_verts, meta = flatten_upper_garment_vertices(verts, strength=strength)
    out = output_path or obj_path
    _write_obj_vertices(out, lines, new_verts)
    meta["obj_path"] = out
    return meta
