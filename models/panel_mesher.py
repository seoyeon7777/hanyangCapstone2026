"""
2D 패턴 패널 → 3D 쉘 메쉬(OBJ) 조립.

앞/뒤를 몸통 원통에 감싸고, 내부를 격자 삼각화한다.
OBJ는 Blender 기본 임포트(Y-up)에 맞게 저장한다. 단위 cm → m.
"""

from __future__ import annotations

import json
import math
import os
from typing import Any

import numpy as np
from scipy.spatial import Delaunay

from models.pattern_draft import Pattern, Panel, Point


def _body_radius_at_chest(chest_circ_cm: float) -> float:
    return chest_circ_cm / (2.0 * math.pi)


def _point_in_poly(x: float, y: float, poly: list[Point]) -> bool:
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-18) + xi):
            inside = not inside
        j = i
    return inside


def _tessellate_panel(panel: Panel, spacing_cm: float = 2.0) -> tuple[list[Point], list[list[int]], dict[str, int]]:
    """패널 내부를 격자+Delaunay로 삼각화. 경계 정점 유지."""
    boundary = panel.vertices_cm
    xs = [p[0] for p in boundary]
    ys = [p[1] for p in boundary]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    pts: list[Point] = []
    # boundary first
    for p in boundary:
        pts.append((round(p[0], 4), round(p[1], 4)))

    # interior grid
    x = min_x + spacing_cm
    while x < max_x:
        y = min_y + spacing_cm
        while y < max_y:
            if _point_in_poly(x, y, boundary):
                # keep away from boundary to avoid duplicates
                if min(math.hypot(x - bx, y - by) for bx, by in boundary) > spacing_cm * 0.35:
                    pts.append((round(x, 4), round(y, 4)))
            y += spacing_cm
        x += spacing_cm

    arr = np.array(pts, dtype=np.float64)
    if len(pts) < 3:
        return pts, [], dict(panel.landmarks)

    tri = Delaunay(arr)
    faces: list[list[int]] = []
    for simplex in tri.simplices:
        cx = float(arr[simplex, 0].mean())
        cy = float(arr[simplex, 1].mean())
        if _point_in_poly(cx, cy, boundary):
            faces.append([int(simplex[0]), int(simplex[1]), int(simplex[2])])

    # landmarks → nearest tessellated vertex
    lm: dict[str, int] = {}
    for name, idx in panel.landmarks.items():
        tx, ty = boundary[idx]
        best_i, best_d = 0, 1e18
        for i, (px, py) in enumerate(pts):
            d = (px - tx) ** 2 + (py - ty) ** 2
            if d < best_d:
                best_d, best_i = d, i
        lm[name] = best_i

    return pts, faces, lm


def _wrap_points(
    pts2d: list[Point],
    chest_circ_cm: float,
    side: str,
) -> list[list[float]]:
    """2D (x,y) → 3D Z-up cm. front:+Y, back:-Y."""
    r = _body_radius_at_chest(chest_circ_cm)
    half_circ = chest_circ_cm / 2.0
    out: list[list[float]] = []
    for x, y in pts2d:
        u = x / max(half_circ, 1e-6)
        theta = u * math.pi
        if side == "front":
            X = r * math.sin(theta)
            Y = r * math.cos(theta)
        else:
            X = r * math.sin(theta)
            Y = -r * math.cos(theta)
        out.append([X, Y, y])
    return out


def _sleeve_mesh_tessellated(
    panel: Panel,
    attach: list[float],
    outward: list[float],
) -> tuple[list[list[float]], list[list[int]], dict[str, list[float]], float]:
    pts2d, faces, lm = _tessellate_panel(panel, spacing_cm=1.5)
    cap = panel.vertices_cm[panel.landmarks["cap_top"]]

    def nrm(v):
        l = math.sqrt(sum(c * c for c in v)) or 1.0
        return [c / l for c in v]

    out_v = nrm(outward)
    up_v = [0.0, 0.0, 1.0]
    right = [
        up_v[1] * out_v[2] - up_v[2] * out_v[1],
        up_v[2] * out_v[0] - up_v[0] * out_v[2],
        up_v[0] * out_v[1] - up_v[1] * out_v[0],
    ]
    right = nrm(right)

    verts_3d: list[list[float]] = []
    for x, y in pts2d:
        lx = x - cap[0]
        ly = y - cap[1]
        verts_3d.append([
            attach[0] + out_v[0] * (-ly) + right[0] * lx,
            attach[1] + out_v[1] * (-ly) + right[1] * lx,
            attach[2] + out_v[2] * (-ly) + right[2] * lx,
        ])

    landmarks_3d = {name: verts_3d[i] for name, i in lm.items() if i < len(verts_3d)}
    sleeve_len = abs(
        panel.vertices_cm[panel.landmarks["underarm_l"]][1]
        - panel.vertices_cm[panel.landmarks["hem_l"]][1]
    )
    return verts_3d, faces, landmarks_3d, sleeve_len


def assemble_pattern_mesh(
    pattern: Pattern,
    output_obj: str,
    landmarks_json: str | None = None,
) -> dict[str, Any]:
    chest = float(pattern.targets_cm["chest"])
    front = pattern.panels["front"]
    back = pattern.panels["back"]

    front_pts, front_faces, front_lm_idx = _tessellate_panel(front, spacing_cm=2.0)
    back_pts, back_faces, back_lm_idx = _tessellate_panel(back, spacing_cm=2.0)
    front_v = _wrap_points(front_pts, chest, "front")
    back_v = _wrap_points(back_pts, chest, "back")
    front_lm = {k: front_v[i] for k, i in front_lm_idx.items()}
    back_lm = {k: back_v[i] for k, i in back_lm_idx.items()}

    all_verts: list[list[float]] = []
    all_faces: list[list[int]] = []
    groups: dict[str, tuple[int, int]] = {}

    def add_mesh(name: str, verts: list[list[float]], faces: list[list[int]]):
        base = len(all_verts)
        all_verts.extend(verts)
        for f in faces:
            all_faces.append([base + f[0], base + f[1], base + f[2]])
        groups[name] = (base, len(verts))

    add_mesh("front", front_v, front_faces)
    add_mesh("back", back_v, back_faces)

    sleeve_len_cm = 0.0
    sleeve_l_lm: dict[str, list[float]] = {}
    if "sleeve_l" in pattern.panels:
        attach_l = list(front_lm["shoulder_l"])
        attach_l[0] -= 1.5
        sv, sf, sleeve_l_lm, sleeve_len_cm = _sleeve_mesh_tessellated(
            pattern.panels["sleeve_l"], attach_l, outward=[-1.0, 0.2, 0.0]
        )
        add_mesh("sleeve_l", sv, sf)
    if "sleeve_r" in pattern.panels:
        attach_r = list(front_lm["shoulder_r"])
        attach_r[0] += 1.5
        sv, sf, _, _ = _sleeve_mesh_tessellated(
            pattern.panels["sleeve_r"], attach_r, outward=[1.0, 0.2, 0.0]
        )
        add_mesh("sleeve_r", sv, sf)

    shoulder_arc = abs(
        front_pts[front_lm_idx["shoulder_r"]][0] - front_pts[front_lm_idx["shoulder_l"]][0]
    )
    length_cm = abs(
        0.5 * (front_pts[front_lm_idx["neck_l"]][1] + front_pts[front_lm_idx["neck_r"]][1])
        - front_pts[front_lm_idx["hem_cf"]][1]
    )

    shoulder_mid = [
        0.5 * (front_lm["shoulder_l"][0] + front_lm["shoulder_r"][0]),
        0.5 * (front_lm["shoulder_l"][1] + front_lm["shoulder_r"][1]),
        0.5 * (front_lm["shoulder_l"][2] + front_lm["shoulder_r"][2]),
    ]
    landmarks_cm: dict[str, list[float]] = {
        "shoulder_l": front_lm["shoulder_l"],
        "shoulder_r": front_lm["shoulder_r"],
        "shoulder_mid": shoulder_mid,
        "neck_l": front_lm["neck_l"],
        "neck_r": front_lm["neck_r"],
        "chest_l": front_lm["chest_l"],
        "chest_r": front_lm["chest_r"],
        "chest_back_l": back_lm["chest_l"],
        "chest_back_r": back_lm["chest_r"],
        "hem_cf": front_lm["hem_cf"],
        "neck_cf": front_lm["neck_cf"],
        "hsp_mid": [
            0.5 * (front_lm["neck_l"][0] + front_lm["neck_r"][0]),
            0.5 * (front_lm["neck_l"][1] + front_lm["neck_r"][1]),
            0.5 * (front_lm["neck_l"][2] + front_lm["neck_r"][2]),
        ],
        "chest_circumference": [chest, 0.0, 0.0],
        "shoulder_arc": [shoulder_arc, 0.0, 0.0],
        "length_surface": [length_cm, 0.0, 0.0],
        "sleeve_surface": [sleeve_len_cm, 0.0, 0.0],
    }
    if sleeve_l_lm:
        landmarks_cm["sleeve_hem"] = [
            0.5 * (sleeve_l_lm["hem_l"][0] + sleeve_l_lm["hem_r"][0]),
            0.5 * (sleeve_l_lm["hem_l"][1] + sleeve_l_lm["hem_r"][1]),
            0.5 * (sleeve_l_lm["hem_l"][2] + sleeve_l_lm["hem_r"][2]),
        ]
        landmarks_cm["sleeve_underarm"] = [
            0.5 * (sleeve_l_lm["underarm_l"][0] + sleeve_l_lm["underarm_r"][0]),
            0.5 * (sleeve_l_lm["underarm_l"][1] + sleeve_l_lm["underarm_r"][1]),
            0.5 * (sleeve_l_lm["underarm_l"][2] + sleeve_l_lm["underarm_r"][2]),
        ]

    os.makedirs(os.path.dirname(os.path.abspath(output_obj)) or ".", exist_ok=True)
    _write_obj_blender_yup(output_obj, all_verts, all_faces)

    if landmarks_json:
        with open(landmarks_json, "w", encoding="utf-8") as f:
            json.dump({"unit": "cm", "landmarks": landmarks_cm, "groups": groups}, f, indent=2)

    return {
        "obj_path": output_obj,
        "landmarks_cm": landmarks_cm,
        "vertex_count": len(all_verts),
        "face_count": len(all_faces),
        "chest_arc_cm": chest,
    }


def _write_obj_blender_yup(path: str, verts_cm_zup: list[list[float]], faces: list[list[int]]) -> None:
    """
    Z-up cm → Blender Y-up meters.
    (x, y, z)_zup → (x, z, -y)_blender / 100
    """
    with open(path, "w", encoding="utf-8") as f:
        f.write("# pattern-assembled garment for Blender (Y-up meters)\n")
        for x, y, z in verts_cm_zup:
            f.write(f"v {x/100.0:.6f} {z/100.0:.6f} {-y/100.0:.6f}\n")
        for a, b, c in faces:
            f.write(f"f {a+1} {b+1} {c+1}\n")


def save_pattern_svg(pattern: Pattern, path: str, scale: float = 4.0) -> None:
    panels = list(pattern.panels.values())
    x_offset = 0.0
    parts = []
    width = 0.0
    height = 0.0
    for panel in panels:
        xs = [p[0] for p in panel.vertices_cm]
        ys = [p[1] for p in panel.vertices_cm]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        local = []
        for x, y in panel.vertices_cm:
            px = (x - min_x + x_offset) * scale
            py = (max_y - y) * scale
            local.append(f"{px:.2f},{py:.2f}")
        parts.append(
            f'<g id="{panel.name}"><polygon fill="#f5f5f5" stroke="black" stroke-width="1" points="{" ".join(local)}"/>'
            f'<text x="{(x_offset)*scale+10}" y="16" font-size="12">{panel.name}</text></g>'
        )
        x_offset += (max_x - min_x) + 8.0
        width = x_offset * scale
        height = max(height, (max_y - min_y) * scale + 20)
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height:.0f}">'
        + "".join(parts)
        + "</svg>"
    )
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(svg)
