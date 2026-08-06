"""P2 — Neural garment reconstruction adapter.

백엔드:
  - stub: neural mesh 없음 → skipped
  - synthetic: 테스트용 closed mesh (GPU 불필요)
  - onnx / torch: 실런타임 (가중치 없으면 skip)

retarget methods:
  - passthrough: 템플릿 복사 (ok=false — 성공 위장 금지)
  - vertex_morph: neural AABB envelope → 템플릿 정점 X/Z 모프 (faces 유지)
  - icp_morph: similarity(centroid+scale) 정렬 후 vertex_morph
"""

from __future__ import annotations

import os
import shutil
from typing import Any, Callable, Optional

import numpy as np

from models.fitting_model import load_obj


class NeuralNotAvailable(RuntimeError):
    pass


class NeuralError(RuntimeError):
    pass


BackendFn = Callable[..., dict[str, Any]]
_BACKENDS: dict[str, BackendFn] = {}


def register_backend(name: str, fn: BackendFn) -> None:
    _BACKENDS[name.lower()] = fn


def list_backends() -> list[str]:
    return sorted(_BACKENDS.keys())


def _write_obj(path: str, verts: np.ndarray, faces: np.ndarray) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for v in verts:
            f.write(f"v {float(v[0]):.6f} {float(v[1]):.6f} {float(v[2]):.6f}\n")
        for face in faces:
            f.write("f " + " ".join(str(int(i) + 1) for i in face) + "\n")


def _backend_stub(
    *,
    images: dict[str, Optional[str]],
    garment_type: str,
    output_dir: str,
    **_kw: Any,
) -> dict[str, Any]:
    return {
        "ok": False,
        "backend": "stub",
        "mesh_path": None,
        "skipped": True,
        "reason": "P2 stub — neural reconstruction not implemented; using template path",
        "images": {k: bool(v and os.path.exists(v)) for k, v in (images or {}).items()},
        "garment_type": garment_type,
    }


def _backend_synthetic(
    *,
    images: dict[str, Optional[str]],
    garment_type: str,
    output_dir: str,
    min_views: int = 1,
    flare: float = 1.18,
    **_kw: Any,
) -> dict[str, Any]:
    """결정적 closed mesh — 의류 타입별 엔벨로프 (테스트용, 실모델 아님)."""
    os.makedirs(output_dir, exist_ok=True)
    present = [k for k, v in (images or {}).items() if v and os.path.exists(v)]
    if len(present) < int(min_views):
        raise NeuralError(f"synthetic backend needs ≥{min_views} views, got {len(present)}")

    g = (garment_type or "").lower()
    path = os.path.join(output_dir, "synthetic_neural.obj")

    # garment-specific envelope params (y from 0=hem to h=waist/neck)
    if g in ("pants", "shorts", "trousers"):
        h = 1.1
        ys = (0.0, 0.35 * h, 0.55 * h, h)
        # ankle / mid / crotch / waist half-widths
        ws = (0.28, 0.30, 0.46, 0.44)
        ds = (0.14, 0.15, 0.18, 0.17)
        bipodal = True
        style = "pants_bipodal"
    elif g in ("skirt",):
        h = 1.05
        ys = (0.0, 0.5 * h, h)
        ws = (0.42 * float(flare), 0.48 * float(flare), 0.40)
        ds = (0.16, 0.17, 0.15)
        bipodal = False
        style = "skirt_aline"
    elif g in ("hoodie", "sweatshirt", "jacket", "coat"):
        h = 1.0
        ys = (0.0, 0.45 * h, 0.75 * h, h)
        ws = (0.48, 0.55, 0.62, 0.50)  # hem / chest / sleeve-bulge / neck
        ds = (0.20, 0.22, 0.24, 0.18)
        bipodal = False
        style = "hoodie_bulky" if g in ("hoodie", "sweatshirt") else "jacket_bulky"
    else:
        h = 1.0
        ys = (0.0, 0.5 * h, h)
        ws = (0.42, 0.50, 0.48)
        ds = (0.16, 0.18, 0.15)
        bipodal = False
        style = "top_taper"

    n_ring = 8
    rings = []
    for yi, y in enumerate(ys):
        w = ws[yi]
        d = ds[yi]
        t = yi / max(len(ys) - 1, 1)
        ring = []
        for ang in np.linspace(0, 2 * np.pi, n_ring, endpoint=False):
            x = w * np.cos(ang)
            z = d * np.sin(ang)
            if bipodal and t < 0.55:
                # 하단: 좌/우 다리 쪽으로 밀어 bipodal 엔벨로프
                lat = 0.20 * (1.0 - t / 0.55)
                x = x + (lat if x >= 0 else -lat)
            ring.append([x, y, z])
        rings.append(ring)
    verts = np.array([p for ring in rings for p in ring], dtype=np.float64)
    faces = []
    n_levels = len(rings)
    for r in range(n_levels - 1):
        for i in range(n_ring):
            a = r * n_ring + i
            b = r * n_ring + (i + 1) % n_ring
            c = (r + 1) * n_ring + (i + 1) % n_ring
            d = (r + 1) * n_ring + i
            faces.append([a, b, c])
            faces.append([a, c, d])
    for i in range(1, n_ring - 1):
        faces.append([0, i, i + 1])
    top0 = (n_levels - 1) * n_ring
    for i in range(1, n_ring - 1):
        faces.append([top0, top0 + i + 1, top0 + i])
    _write_obj(path, verts, np.array(faces, dtype=np.int32))
    return {
        "ok": True,
        "backend": "synthetic",
        "mesh_path": path,
        "skipped": False,
        "views": present,
        "garment_type": garment_type,
        "style": style,
        "n_verts": int(len(verts)),
        "n_faces": int(len(faces)),
        "reason": f"synthetic closed mesh ({style}) for contract tests",
    }


register_backend("stub", _backend_stub)
register_backend("synthetic", _backend_synthetic)


def _backend_onnx(
    *,
    images: dict[str, Optional[str]],
    garment_type: str,
    output_dir: str,
    **kw: Any,
) -> dict[str, Any]:
    from pipeline.adapters.neural_backends.onnx_backend import make_onnx_backend
    from pipeline.adapters.neural_backend import NeuralRequest

    backend = make_onnx_backend(**kw)
    res = backend.reconstruct(
        NeuralRequest(
            images=images or {},
            garment_type=garment_type,
            output_dir=output_dir,
            options=kw,
        )
    )
    return {
        "ok": res.ok,
        "backend": res.backend,
        "mesh_path": res.mesh_path,
        "skipped": res.skipped,
        "reason": res.reason,
        "meta": res.meta,
        "garment_type": garment_type,
        "images": {k: bool(v and os.path.exists(v)) for k, v in (images or {}).items()},
    }


register_backend("onnx", _backend_onnx)


def _backend_torch(
    *,
    images: dict[str, Optional[str]],
    garment_type: str,
    output_dir: str,
    **kw: Any,
) -> dict[str, Any]:
    from pipeline.adapters.neural_backends.torch_backend import make_torch_backend
    from pipeline.adapters.neural_backend import NeuralRequest

    backend = make_torch_backend(**kw)
    res = backend.reconstruct(
        NeuralRequest(
            images=images or {},
            garment_type=garment_type,
            output_dir=output_dir,
            options=kw,
        )
    )
    return {
        "ok": res.ok,
        "backend": res.backend,
        "mesh_path": res.mesh_path,
        "skipped": res.skipped,
        "reason": res.reason,
        "meta": res.meta,
        "garment_type": garment_type,
        "images": {k: bool(v and os.path.exists(v)) for k, v in (images or {}).items()},
    }


register_backend("torch", _backend_torch)


def reconstruct(
    *,
    images: dict[str, Optional[str]],
    garment_type: str = "tshirt",
    output_dir: str,
    backend: str = "stub",
    min_views: int = 1,
    timeout_sec: float = 120.0,
    neural_options: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    os.makedirs(output_dir, exist_ok=True)
    backend = (backend or "stub").lower()
    fn = _BACKENDS.get(backend)
    if fn is None:
        raise NeuralNotAvailable(
            f"neural backend '{backend}' not installed — available: {list_backends()}"
        )
    opts = dict(neural_options or {})
    opts.setdefault("min_views", min_views)
    opts.setdefault("timeout_sec", timeout_sec)
    return fn(
        images=images or {},
        garment_type=garment_type,
        output_dir=output_dir,
        **opts,
    )


def _envelope_halfwidth(verts: np.ndarray, bins: int = 24, axis: int = 0) -> np.ndarray:
    """Y-정규화 밴드별 half-width (axis=0 X, axis=2 Z)."""
    y = verts[:, 1]
    y0, y1 = float(y.min()), float(y.max())
    dy = max(y1 - y0, 1e-9)
    hw = np.zeros(bins, dtype=np.float64)
    for i in range(bins):
        lo = y0 + (i / bins) * dy
        hi = y0 + ((i + 1) / bins) * dy
        band = verts[(y >= lo) & (y <= hi + 1e-12)]
        if len(band) < 2:
            continue
        hw[i] = 0.5 * float(band[:, axis].max() - band[:, axis].min())
    for i in range(bins):
        if hw[i] <= 1e-9:
            hw[i] = hw[i - 1] if i else 0.0
    for i in range(bins - 2, -1, -1):
        if hw[i] <= 1e-9:
            hw[i] = hw[i + 1]
    return np.maximum(hw, 1e-6)


def _envelope_rms(a: np.ndarray, b: np.ndarray, bins: int = 16) -> float:
    """Y-밴드 X/Z half-width RMSE (토폴로지 무관 정렬 품질)."""
    ax = _envelope_halfwidth(a, bins=bins, axis=0)
    bx = _envelope_halfwidth(b, bins=bins, axis=0)
    az = _envelope_halfwidth(a, bins=bins, axis=2)
    bz = _envelope_halfwidth(b, bins=bins, axis=2)
    return float(np.sqrt(np.mean((ax - bx) ** 2 + (az - bz) ** 2)))


def _correspondence_metrics(src: np.ndarray, dst: np.ndarray, *, sample: int = 64) -> dict[str, Any]:
    """Y-밴드 subsample NN coverage (partial match) — geometric only, not learned."""
    if src.size == 0 or dst.size == 0:
        return {"partial_match_ratio": 0.0, "mean_nn_dist": 999.0, "n_samples": 0}
    rng = np.random.default_rng(0)
    n = min(int(sample), len(src))
    idx = rng.choice(len(src), size=n, replace=False) if len(src) > n else np.arange(len(src))
    pts = src[idx]
    # scale-normalize by dst extent
    dext = float(np.linalg.norm(dst.max(axis=0) - dst.min(axis=0))) or 1.0
    thresh = 0.18 * dext
    dists = []
    hits = 0
    for p in pts:
        d = np.linalg.norm(dst - p, axis=1)
        md = float(d.min())
        dists.append(md)
        if md <= thresh:
            hits += 1
    mean_nn = float(np.mean(dists)) if dists else 999.0
    return {
        "partial_match_ratio": round(hits / max(n, 1), 4),
        "mean_nn_dist": round(mean_nn, 5),
        "nn_thresh": round(thresh, 5),
        "n_samples": int(n),
    }


def _match_y_extent(src: np.ndarray, dst: np.ndarray) -> np.ndarray:
    out = src.copy()
    sy0, sy1 = float(out[:, 1].min()), float(out[:, 1].max())
    dy0, dy1 = float(dst[:, 1].min()), float(dst[:, 1].max())
    sdy = max(sy1 - sy0, 1e-9)
    out[:, 1] = dy0 + (out[:, 1] - sy0) / sdy * (dy1 - dy0)
    return out


def _similarity_align(src: np.ndarray, dst: np.ndarray) -> tuple[np.ndarray, dict[str, Any]]:
    """Centroid + isotropic scale + XZ planar rotation (ICP-lite step)."""
    src = _match_y_extent(src, dst)
    sc = src.mean(axis=0)
    dc = dst.mean(axis=0)
    src0 = src - sc
    dst0 = dst - dc
    rs = float(np.mean(np.linalg.norm(src0, axis=1)))
    rd = float(np.mean(np.linalg.norm(dst0, axis=1)))
    if rs < 1e-9:
        rs = 1.0
    if rd < 1e-9:
        rd = 1.0
    scale = rd / rs
    aligned = src0 * scale + dc
    rot = False
    try:
        sxz = aligned[:, [0, 2]] - dc[[0, 2]]
        dxz = dst[:, [0, 2]] - dc[[0, 2]]
        h = sxz.T @ dxz
        u, _, vt = np.linalg.svd(h)
        r = vt.T @ u.T
        if np.linalg.det(r) < 0:
            vt = vt.copy()
            vt[-1, :] *= -1
            r = vt.T @ u.T
        xz = (sxz @ r.T) + dc[[0, 2]]
        aligned = aligned.copy()
        aligned[:, 0] = xz[:, 0]
        aligned[:, 2] = xz[:, 1]
        rot = True
    except Exception:
        pass
    c_err = float(np.linalg.norm(aligned.mean(axis=0) - dc))

    def _ext(v):
        return float(np.linalg.norm(v.max(axis=0) - v.min(axis=0)))

    return aligned, {
        "scale": round(float(scale), 5),
        "centroid_err": round(c_err, 6),
        "extent_src": round(_ext(src), 4),
        "extent_dst": round(_ext(dst), 4),
        "extent_aligned": round(_ext(aligned), 4),
        "xz_rotation": bool(rot),
        "rms": round(_envelope_rms(aligned, dst), 5),
    }


def _iterative_icp_align(
    src: np.ndarray,
    dst: np.ndarray,
    *,
    iters: int = 4,
) -> tuple[np.ndarray, dict[str, Any]]:
    """반복 similarity 정렬 — envelope RMSE가 개선될 때만 유지."""
    n_iters = max(1, int(iters))
    cur, meta0 = _similarity_align(src, dst)
    history = [float(meta0.get("rms") or _envelope_rms(cur, dst))]
    best = cur
    best_rms = history[0]
    for _ in range(1, n_iters):
        nxt, m = _similarity_align(cur, dst)
        rms = float(m.get("rms") or _envelope_rms(nxt, dst))
        history.append(rms)
        if rms < best_rms - 1e-7:
            best = nxt
            best_rms = rms
            cur = nxt
        else:
            break
    meta = dict(meta0)
    meta.update({
        "iters": len(history),
        "rms_before": round(history[0], 5),
        "rms_after": round(best_rms, 5),
        "rms_history": [round(x, 5) for x in history],
        "rms_improved": bool(best_rms <= history[0] + 1e-9),
    })
    meta["centroid_err"] = round(float(np.linalg.norm(best.mean(axis=0) - dst.mean(axis=0))), 6)
    corr = _correspondence_metrics(best, dst)
    meta["correspondence"] = corr
    meta["partial_match_ratio"] = corr.get("partial_match_ratio")
    return best, meta


def _vertex_morph(
    template_obj: str,
    neural_obj: str,
    output_path: str,
    *,
    strength: float = 0.35,
    depth_strength: Optional[float] = None,
    neural_verts_override: Optional[np.ndarray] = None,
) -> dict[str, Any]:
    t_verts, t_faces = load_obj(template_obj)
    if neural_verts_override is not None:
        n_verts = np.asarray(neural_verts_override, dtype=np.float64)
    else:
        n_verts, _ = load_obj(neural_obj)
    if t_verts.size == 0 or n_verts.size == 0:
        return {"ok": False, "reason": "empty_mesh"}

    bins = 24
    t_hw_x = _envelope_halfwidth(t_verts, bins=bins, axis=0)
    n_hw_x = _envelope_halfwidth(n_verts, bins=bins, axis=0)
    t_hw_z = _envelope_halfwidth(t_verts, bins=bins, axis=2)
    n_hw_z = _envelope_halfwidth(n_verts, bins=bins, axis=2)
    ty0, ty1 = float(t_verts[:, 1].min()), float(t_verts[:, 1].max())
    tdy = max(ty1 - ty0, 1e-9)
    tcx = 0.5 * (float(t_verts[:, 0].min()) + float(t_verts[:, 0].max()))
    tcz = 0.5 * (float(t_verts[:, 2].min()) + float(t_verts[:, 2].max()))

    sx_w = float(np.clip(strength, 0.0, 1.0))
    sz_w = float(np.clip(depth_strength if depth_strength is not None else strength * 0.85, 0.0, 1.0))
    out = t_verts.copy()
    scales_x, scales_z = [], []
    for i, v in enumerate(out):
        t = (float(v[1]) - ty0) / tdy
        bi = int(np.clip(np.floor(t * (bins - 1)), 0, bins - 1))
        bi2 = min(bins - 1, bi + 1)
        frac = (t * (bins - 1)) - bi
        thx = (1 - frac) * t_hw_x[bi] + frac * t_hw_x[bi2]
        nhx = (1 - frac) * n_hw_x[bi] + frac * n_hw_x[bi2]
        thz = (1 - frac) * t_hw_z[bi] + frac * t_hw_z[bi2]
        nhz = (1 - frac) * n_hw_z[bi] + frac * n_hw_z[bi2]
        scx = float(np.clip(1.0 + (nhx / thx - 1.0) * sx_w, 0.85, 1.25))
        scz = float(np.clip(1.0 + (nhz / thz - 1.0) * sz_w, 0.85, 1.30))
        scales_x.append(scx)
        scales_z.append(scz)
        out[i, 0] = tcx + (v[0] - tcx) * scx
        out[i, 2] = tcz + (v[2] - tcz) * scz

    _write_obj(output_path, out, t_faces)
    max_dx = float(np.max(np.abs(out[:, 0] - t_verts[:, 0])))
    max_dz = float(np.max(np.abs(out[:, 2] - t_verts[:, 2])))
    residual_rms = round(_envelope_rms(out, n_verts), 5)
    return {
        "ok": True,
        "mesh_path": output_path,
        "n_verts": int(len(out)),
        "n_faces": int(len(t_faces)),
        "topology_preserved": True,
        "max_abs_x_delta": round(max_dx, 5),
        "max_abs_z_delta": round(max_dz, 5),
        "strength": sx_w,
        "depth_strength": sz_w,
        "scale_x_min": round(float(min(scales_x)), 4),
        "scale_x_max": round(float(max(scales_x)), 4),
        "scale_z_min": round(float(min(scales_z)), 4),
        "scale_z_max": round(float(max(scales_z)), 4),
        "morph_residual_rms": residual_rms,
        "passthrough": False,
        "method": "vertex_morph",
        "reason": "independent X/Z envelope morph onto template topology",
    }


def retarget_to_template(
    *,
    neural_mesh_path: Optional[str],
    template_obj_path: str,
    output_path: str,
    backend: str = "stub",
    method: str = "passthrough",
    morph_strength: float = 0.35,
    morph_depth_strength: Optional[float] = None,
    icp_iters: int = 4,
    smooth_iters: int = 0,
    residual_pass: bool = True,
    residual_threshold: float = 0.08,
) -> dict[str, Any]:
    """Neural mesh → 템플릿 토폴로지."""
    os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)
    method = (method or "passthrough").lower()
    if method not in ("passthrough", "vertex_morph", "icp_morph"):
        return {
            "ok": False,
            "backend": backend,
            "mesh_path": None,
            "skipped": False,
            "reason": f"unknown retarget method: {method}",
        }

    if not template_obj_path or not os.path.exists(template_obj_path):
        return {
            "ok": False,
            "backend": backend,
            "mesh_path": None,
            "skipped": True,
            "reason": "template_obj missing",
        }

    if not neural_mesh_path or not os.path.exists(neural_mesh_path):
        shutil.copy2(template_obj_path, output_path)
        return {
            "ok": False,
            "backend": backend,
            "mesh_path": output_path,
            "skipped": True,
            "passthrough": True,
            "method": method,
            "reason": "no neural mesh — template passthrough (not a neural retarget success)",
        }

    if method == "passthrough":
        shutil.copy2(template_obj_path, output_path)
        return {
            "ok": False,
            "backend": backend,
            "mesh_path": output_path,
            "skipped": True,
            "passthrough": True,
            "method": "passthrough",
            "neural_mesh": neural_mesh_path,
            "reason": "explicit passthrough — template kept (not morph success)",
        }

    align_meta: Optional[dict[str, Any]] = None
    override = None
    try:
        if method == "icp_morph":
            t_verts, _ = load_obj(template_obj_path)
            n_verts, n_faces = load_obj(neural_mesh_path)
            override, align_meta = _iterative_icp_align(
                n_verts, t_verts, iters=int(icp_iters),
            )
            aligned_path = output_path + ".aligned.obj"
            _write_obj(
                aligned_path,
                override,
                n_faces if len(n_faces) else np.array([[0, 1, 2]], dtype=np.int32),
            )
            align_meta["aligned_mesh"] = aligned_path
        morph = _vertex_morph(
            template_obj_path,
            neural_mesh_path,
            output_path,
            strength=morph_strength,
            depth_strength=morph_depth_strength,
            neural_verts_override=override,
        )
        # residual second pass — weaker morph if envelope still mismatches
        residual_meta = {
            "applied": False,
            "threshold": float(residual_threshold),
            "rms_before": morph.get("morph_residual_rms"),
        }
        if residual_pass and float(morph.get("morph_residual_rms") or 0) > float(residual_threshold):
            mid = output_path + ".residual_mid.obj"
            shutil.copy2(output_path, mid)
            morph2 = _vertex_morph(
                mid,
                neural_mesh_path,
                output_path,
                strength=float(morph_strength) * 0.4,
                depth_strength=(
                    float(morph_depth_strength) * 0.4
                    if morph_depth_strength is not None
                    else float(morph_strength) * 0.35
                ),
                neural_verts_override=override,
            )
            if morph2.get("ok"):
                residual_meta["applied"] = True
                residual_meta["rms_after"] = morph2.get("morph_residual_rms")
                morph = morph2
                morph["max_abs_x_delta"] = round(
                    max(float(morph.get("max_abs_x_delta") or 0), float(morph2.get("max_abs_x_delta") or 0)), 5
                )
                morph["max_abs_z_delta"] = round(
                    max(float(morph.get("max_abs_z_delta") or 0), float(morph2.get("max_abs_z_delta") or 0)), 5
                )
        morph["residual"] = residual_meta

        # laplacian post-smooth (topology preserved)
        n_smooth = int(smooth_iters or 0)
        if n_smooth > 0 and morph.get("ok") and morph.get("mesh_path"):
            from models.silhouette_deform import _laplacian_smooth

            v, f = load_obj(morph["mesh_path"])
            v0 = v.copy()
            vs = _laplacian_smooth(v, f, iterations=n_smooth, lam=0.28)
            _write_obj(morph["mesh_path"], vs, f)
            morph["smooth_iters"] = n_smooth
            morph["smooth_max_delta"] = round(float(np.max(np.abs(vs - v0))), 5)
            morph["max_abs_x_delta"] = round(
                float(np.max(np.abs(vs[:, 0] - load_obj(template_obj_path)[0][:, 0]))), 5
            )
            morph["max_abs_z_delta"] = round(
                float(np.max(np.abs(vs[:, 2] - load_obj(template_obj_path)[0][:, 2]))), 5
            )
        else:
            morph["smooth_iters"] = 0

        if method == "icp_morph":
            morph["method"] = "icp_morph"
            morph["align"] = align_meta
            morph["reason"] = "iterative ICP-lite + X/Z morph (+ residual/smooth)"
    except Exception as e:
        return {
            "ok": False,
            "backend": backend,
            "mesh_path": None,
            "skipped": False,
            "method": method,
            "reason": f"{method} failed: {e}",
        }
    morph["backend"] = backend
    morph["neural_mesh"] = neural_mesh_path
    morph["skipped"] = False
    return morph
