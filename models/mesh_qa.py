"""메쉬 QA 휴리스틱 (Blender 없이 OBJ 검사)."""

from __future__ import annotations

import math
import os
from typing import Any, Optional

import numpy as np

from models.fitting_model import load_obj


def inspect_obj(path: str, *, ref_path: Optional[str] = None) -> dict[str, Any]:
    """NaN, AABB 폭발, 붕괴, (옵션) 토폴로지 보존 검사."""
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

    # 토폴로지 휴리스틱
    n_v = int(len(verts))
    n_f = int(len(faces))
    invalid_idx = False
    if n_f:
        invalid_idx = bool((faces < 0).any() or (faces >= n_v).any())
    edge_count: dict[tuple[int, int], int] = {}
    for f in faces:
        ids = [int(f[0]), int(f[1]), int(f[2])]
        for a, b in ((ids[0], ids[1]), (ids[1], ids[2]), (ids[2], ids[0])):
            e = (a, b) if a < b else (b, a)
            edge_count[e] = edge_count.get(e, 0) + 1
    boundary_edges = sum(1 for c in edge_count.values() if c == 1)
    nonmanifold_edges = sum(1 for c in edge_count.values() if c > 2)

    # degenerate / tiny faces (cross-product area)
    deg_faces = 0
    min_face_area = None
    if n_f:
        areas = []
        for f in faces:
            a, b, c = verts[int(f[0])], verts[int(f[1])], verts[int(f[2])]
            area = float(0.5 * np.linalg.norm(np.cross(b - a, c - a)))
            areas.append(area)
            if area < 1e-10:
                deg_faces += 1
        min_face_area = float(min(areas)) if areas else 0.0

    report: dict[str, Any] = {
        "ok": True,
        "path": path,
        "n_verts": n_v,
        "n_faces": n_f,
        "finite": bool(finite),
        "extents": [round(float(x), 4) for x in extents],
        "volume_proxy": round(volume_proxy, 6),
        "center": [round(float(x), 4) for x in center],
        "boundary_edges": int(boundary_edges),
        "nonmanifold_edges": int(nonmanifold_edges),
        "degenerate_faces": int(deg_faces),
        "min_face_area": round(float(min_face_area), 8) if min_face_area is not None else None,
        "issues": [],
    }
    if not finite:
        report["ok"] = False
        report["issues"].append("nan_or_inf")
    if invalid_idx:
        report["ok"] = False
        report["issues"].append("invalid_face_index")
    if nonmanifold_edges > 0:
        report["issues"].append("nonmanifold_edges")
        # soft — open garments OK; nonmanifold is warning-ish
        if nonmanifold_edges > max(8, n_f // 20):
            report["ok"] = False

    if float(extents.max()) > 50.0:
        report["ok"] = False
        report["issues"].append("aabb_too_large")
    if float(extents.min()) < 1e-4:
        report["ok"] = False
        report["issues"].append("aabb_collapsed")
    if deg_faces > 0:
        report["issues"].append("degenerate_faces")
        if deg_faces > max(2, n_f // 50):
            report["ok"] = False

    if ref_path and os.path.exists(ref_path):
        ref, ref_faces = load_obj(ref_path)
        if ref.size:
            ref_ext = (ref.max(axis=0) - ref.min(axis=0)).astype(float)
            ratio = float(np.max(extents / np.maximum(ref_ext, 1e-6)))
            report["extent_ratio_vs_ref"] = round(ratio, 3)
            if ratio > 3.5 or ratio < 0.25:
                report["ok"] = False
                report["issues"].append("extent_drift")
            ref_c = 0.5 * (ref.min(axis=0) + ref.max(axis=0))
            drift = float(np.linalg.norm(center - ref_c))
            report["center_drift"] = round(drift, 4)
            if drift > max(float(ref_ext.max()) * 0.6, 0.5):
                report["issues"].append("center_drift")
            # topology vs ref
            report["same_vert_count"] = int(len(ref)) == n_v
            report["same_face_count"] = int(len(ref_faces)) == n_f
            topo_ok = report["same_vert_count"] and report["same_face_count"]
            if topo_ok and n_f and ref_faces.size:
                topo_ok = bool(np.array_equal(faces, ref_faces))
            report["topology_match"] = bool(topo_ok)
            if not topo_ok:
                report["issues"].append("topology_mismatch")
                report["ok"] = False

    return report
