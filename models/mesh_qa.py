"""메쉬 QA 휴리스틱 (Blender 없이 OBJ 검사)."""

from __future__ import annotations

import math
import os
from typing import Any, Optional

import numpy as np

from models.fitting_model import load_obj


def inspect_obj(path: str, *, ref_path: Optional[str] = None) -> dict[str, Any]:
    """NaN, AABB 폭발, 붕괴 등 검사."""
    if not path or not os.path.exists(path):
        return {"ok": False, "error": "missing", "path": path}

    verts, faces = load_obj(path)
    if verts.size == 0:
        return {"ok": False, "error": "empty", "path": path}

    finite = np.isfinite(verts).all()
    mins = verts.min(axis=0)
    maxs = verts.max(axis=0)
    extents = (maxs - mins).astype(float)
    volume_proxy = float(np.prod(np.maximum(extents, 1e-6)))
    center = 0.5 * (mins + maxs)

    report: dict[str, Any] = {
        "ok": True,
        "path": path,
        "n_verts": int(len(verts)),
        "n_faces": int(len(faces)),
        "finite": bool(finite),
        "extents": [round(float(x), 4) for x in extents],
        "volume_proxy": round(volume_proxy, 6),
        "center": [round(float(x), 4) for x in center],
        "issues": [],
    }
    if not finite:
        report["ok"] = False
        report["issues"].append("nan_or_inf")

    if float(extents.max()) > 50.0:
        report["ok"] = False
        report["issues"].append("aabb_too_large")
    if float(extents.min()) < 1e-4:
        report["ok"] = False
        report["issues"].append("aabb_collapsed")

    if ref_path and os.path.exists(ref_path):
        ref, _ = load_obj(ref_path)
        if ref.size:
            ref_ext = (ref.max(axis=0) - ref.min(axis=0)).astype(float)
            ratio = float(np.max(extents / np.maximum(ref_ext, 1e-6)))
            report["extent_ratio_vs_ref"] = round(ratio, 3)
            if ratio > 3.5 or ratio < 0.25:
                report["ok"] = False
                report["issues"].append("extent_drift")
            # 중심 이동
            ref_c = 0.5 * (ref.min(axis=0) + ref.max(axis=0))
            drift = float(np.linalg.norm(center - ref_c))
            report["center_drift"] = round(drift, 4)
            if drift > max(float(ref_ext.max()) * 0.6, 0.5):
                report["issues"].append("center_drift")
                # hard fail은 아님 — 경고용

    return report
