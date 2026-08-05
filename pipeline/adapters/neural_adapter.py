"""P2 — Neural garment reconstruction adapter.

백엔드:
  - stub: neural mesh 없음 → skipped
  - synthetic: 테스트용 closed mesh (GPU 불필요)

retarget methods:
  - passthrough: 템플릿 복사 (ok=false if no neural; ok=true only as explicit passthrough copy after neural exists is still passthrough)
  - vertex_morph: neural AABB envelope → 템플릿 정점 X/Z 모프 (faces 유지)
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
    """결정적 closed mesh: Y에 따라 X/Z가 벌어지는 A-line 엔벨로프."""
    os.makedirs(output_dir, exist_ok=True)
    present = [k for k, v in (images or {}).items() if v and os.path.exists(v)]
    if len(present) < int(min_views):
        raise NeuralError(f"synthetic backend needs ≥{min_views} views, got {len(present)}")

    g = (garment_type or "").lower()
    h = 1.05 if g in ("pants", "skirt") else 1.0
    base_w = 0.42
    top_w = 0.55 * float(flare) if g == "skirt" else 0.50
    path = os.path.join(output_dir, "synthetic_neural.obj")
    # rings at y=0, 0.5h, h — 8 verts each → closed side faces
    rings = []
    for yi, y in enumerate((0.0, 0.5 * h, h)):
        t = yi / 2.0
        w = base_w * (1 - t) + top_w * t
        d = 0.18 * (1 - 0.15 * t)
        ring = []
        for ang in np.linspace(0, 2 * np.pi, 8, endpoint=False):
            ring.append([w * np.cos(ang), y, d * np.sin(ang)])
        rings.append(ring)
    verts = np.array([p for ring in rings for p in ring], dtype=np.float64)
    faces = []
    for r in range(2):
        for i in range(8):
            a = r * 8 + i
            b = r * 8 + (i + 1) % 8
            c = (r + 1) * 8 + (i + 1) % 8
            d = (r + 1) * 8 + i
            faces.append([a, b, c])
            faces.append([a, c, d])
    # caps
    for i in range(1, 7):
        faces.append([0, i, i + 1])
    top0 = 16
    for i in range(1, 7):
        faces.append([top0, top0 + i + 1, top0 + i])
    _write_obj(path, verts, np.array(faces, dtype=np.int32))
    return {
        "ok": True,
        "backend": "synthetic",
        "mesh_path": path,
        "skipped": False,
        "views": present,
        "garment_type": garment_type,
        "n_verts": int(len(verts)),
        "n_faces": int(len(faces)),
        "reason": "synthetic closed mesh for contract tests",
    }


register_backend("stub", _backend_stub)
register_backend("synthetic", _backend_synthetic)


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


def _envelope_halfwidth(verts: np.ndarray, bins: int = 24) -> np.ndarray:
    """Y-정규화 밴드별 X half-width (메쉬 단위)."""
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
        hw[i] = 0.5 * float(band[:, 0].max() - band[:, 0].min())
    # fill empties
    for i in range(bins):
        if hw[i] <= 1e-9:
            hw[i] = hw[i - 1] if i else 0.0
    for i in range(bins - 2, -1, -1):
        if hw[i] <= 1e-9:
            hw[i] = hw[i + 1]
    return np.maximum(hw, 1e-6)


def _vertex_morph(
    template_obj: str,
    neural_obj: str,
    output_path: str,
    *,
    strength: float = 0.35,
) -> dict[str, Any]:
    t_verts, t_faces = load_obj(template_obj)
    n_verts, _ = load_obj(neural_obj)
    if t_verts.size == 0 or n_verts.size == 0:
        return {"ok": False, "reason": "empty_mesh"}

    bins = 24
    t_hw = _envelope_halfwidth(t_verts, bins=bins)
    n_hw = _envelope_halfwidth(n_verts, bins=bins)
    # align neural height into template Y
    ty0, ty1 = float(t_verts[:, 1].min()), float(t_verts[:, 1].max())
    tdy = max(ty1 - ty0, 1e-9)
    tcx = 0.5 * (float(t_verts[:, 0].min()) + float(t_verts[:, 0].max()))
    tcz = 0.5 * (float(t_verts[:, 2].min()) + float(t_verts[:, 2].max()))

    strength = float(np.clip(strength, 0.0, 1.0))
    out = t_verts.copy()
    for i, v in enumerate(out):
        t = (float(v[1]) - ty0) / tdy
        bi = int(np.clip(np.floor(t * (bins - 1)), 0, bins - 1))
        bi2 = min(bins - 1, bi + 1)
        frac = (t * (bins - 1)) - bi
        th = (1 - frac) * t_hw[bi] + frac * t_hw[bi2]
        nh = (1 - frac) * n_hw[bi] + frac * n_hw[bi2]
        scale = 1.0 + (nh / th - 1.0) * strength
        scale = float(np.clip(scale, 0.85, 1.25))
        out[i, 0] = tcx + (v[0] - tcx) * scale
        out[i, 2] = tcz + (v[2] - tcz) * scale

    _write_obj(output_path, out, t_faces)
    max_dx = float(np.max(np.abs(out[:, 0] - t_verts[:, 0])))
    max_dz = float(np.max(np.abs(out[:, 2] - t_verts[:, 2])))
    return {
        "ok": True,
        "mesh_path": output_path,
        "n_verts": int(len(out)),
        "n_faces": int(len(t_faces)),
        "topology_preserved": True,
        "max_abs_x_delta": round(max_dx, 5),
        "max_abs_z_delta": round(max_dz, 5),
        "strength": strength,
        "passthrough": False,
        "method": "vertex_morph",
        "reason": "envelope morph onto template topology",
    }


def retarget_to_template(
    *,
    neural_mesh_path: Optional[str],
    template_obj_path: str,
    output_path: str,
    backend: str = "stub",
    method: str = "passthrough",
    morph_strength: float = 0.35,
) -> dict[str, Any]:
    """Neural mesh → 템플릿 토폴로지."""
    os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)
    method = (method or "passthrough").lower()
    if method not in ("passthrough", "vertex_morph"):
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

    try:
        morph = _vertex_morph(
            template_obj_path,
            neural_mesh_path,
            output_path,
            strength=morph_strength,
        )
    except Exception as e:
        return {
            "ok": False,
            "backend": backend,
            "mesh_path": None,
            "skipped": False,
            "method": "vertex_morph",
            "reason": f"vertex_morph failed: {e}",
        }
    morph["backend"] = backend
    morph["neural_mesh"] = neural_mesh_path
    morph["skipped"] = False
    return morph
