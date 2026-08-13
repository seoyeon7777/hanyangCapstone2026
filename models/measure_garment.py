"""패턴/메쉬 랜드마크 재측정."""

from __future__ import annotations

import math
from typing import Any

from models.pattern_draft import Pattern, Panel, Point


def _dist(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _polyline_length(verts: list[Point], indices: list[int]) -> float:
    if len(indices) < 2:
        return 0.0
    total = 0.0
    for a, b in zip(indices, indices[1:]):
        total += _dist(verts[a], verts[b])
    return total


def measure_pattern_2d(pattern: Pattern) -> dict[str, float]:
    """
    2D 패턴에서 의류 치수 재측정.

    - chest: front half_chest 폭 * 2  (앞+뒤, 각 패널이 반둘레)
      front 패널 hem_l→hem_r 폭 + back 동일 = 가슴둘레
    - shoulder: front shoulder_l → shoulder_r
    - length: front hem_cf → neck 상단(네크 CF가 아니라 어깨 y 또는 length meta)
    - sleeve: sleeve underarm 길이 (hem → underarm)
    """
    front = pattern.panels["front"]
    back = pattern.panels["back"]
    sleeve = pattern.panels.get("sleeve_l") or pattern.panels.get("sleeve_r")

    fv = front.vertices_cm
    fl = front.landmarks

    chest_front = _dist(fv[fl["chest_l"]], fv[fl["chest_r"]])
    bv = back.vertices_cm
    bl = back.landmarks
    chest_back = _dist(bv[bl["chest_l"]], bv[bl["chest_r"]])
    chest = chest_front + chest_back

    shoulder = _dist(fv[fl["shoulder_l"]], fv[fl["shoulder_r"]])

    # 총기장: 목옆점(neck_l/r 평균) → 헴
    hem = fv[fl["hem_cf"]]
    neck_side_y = 0.5 * (fv[fl["neck_l"]][1] + fv[fl["neck_r"]][1])
    length = neck_side_y - hem[1]
    top_y = neck_side_y

    sleeve_len = 0.0
    if sleeve is not None:
        sv = sleeve.vertices_cm
        sl = sleeve.landmarks
        # underarm length: average of both underarm seams
        left = _polyline_length(sv, sleeve.seams.get("underarm_l", [sl["hem_l"], sl["underarm_l"]]))
        right = _polyline_length(sv, sleeve.seams.get("underarm_r", [sl["hem_r"], sl["underarm_r"]]))
        sleeve_len = 0.5 * (left + right)

    return {
        "chest": round(chest, 3),
        "shoulder": round(shoulder, 3),
        "length": round(length, 3),
        "sleeve": round(sleeve_len, 3),
        "chest_front_width": round(chest_front, 3),
        "chest_back_width": round(chest_back, 3),
        "top_y": round(top_y, 3),
    }


def measure_mesh_obj(obj_path: str, landmarks: dict[str, list[float]]) -> dict[str, float]:
    """
    OBJ 메쉬 + 3D 랜드마크(월드 좌표 cm 또는 m)로 치수 측정.
    landmarks 키: shoulder_l/r, chest_l/r/front/back, hem_cf, neck_cf, sleeve_hem_l, sleeve_underarm_l ...
    좌표 단위는 landmarks_unit 로 해석 — 기본 cm.
    """
    # 랜드마크만으로 측정 (메쉬 파일은 존재 검증용)
    import os
    if not os.path.exists(obj_path):
        raise FileNotFoundError(obj_path)

    def v(name: str) -> list[float]:
        if name not in landmarks:
            raise KeyError(name)
        return landmarks[name]

    def d(a: str, b: str) -> float:
        pa, pb = v(a), v(b)
        return math.sqrt(sum((pa[i] - pb[i]) ** 2 for i in range(3)))

    out: dict[str, float] = {}

    # 표면/제도 보존 치수 센티널 우선
    if "shoulder_arc" in landmarks:
        out["shoulder"] = round(landmarks["shoulder_arc"][0], 3)
    elif "shoulder_l" in landmarks and "shoulder_r" in landmarks:
        out["shoulder"] = round(d("shoulder_l", "shoulder_r"), 3)

    if "chest_circumference" in landmarks:
        out["chest"] = round(landmarks["chest_circumference"][0], 3)
    elif all(k in landmarks for k in ("chest_l", "chest_r", "chest_back_l", "chest_back_r")):
        out["chest"] = round(
            d("chest_l", "chest_r") + d("chest_back_l", "chest_back_r"), 3
        )
    elif "chest_l" in landmarks and "chest_r" in landmarks:
        out["chest"] = round(2.0 * d("chest_l", "chest_r"), 3)

    if "length_surface" in landmarks:
        out["length"] = round(landmarks["length_surface"][0], 3)
    elif "hem_cf" in landmarks and "hsp_mid" in landmarks:
        out["length"] = round(d("hem_cf", "hsp_mid"), 3)
    elif "hem_cf" in landmarks and "shoulder_mid" in landmarks:
        out["length"] = round(d("hem_cf", "shoulder_mid"), 3)
    elif "hem_cf" in landmarks and "neck_cf" in landmarks:
        out["length"] = round(
            abs(v("shoulder_l")[2] - v("hem_cf")[2])
            if "shoulder_l" in landmarks
            else d("hem_cf", "neck_cf"),
            3,
        )

    if "sleeve_surface" in landmarks and landmarks["sleeve_surface"][0] > 0:
        out["sleeve"] = round(landmarks["sleeve_surface"][0], 3)
    elif "sleeve_hem" in landmarks and "sleeve_underarm" in landmarks:
        out["sleeve"] = round(d("sleeve_hem", "sleeve_underarm"), 3)

    return out


def compare_measurements(
    target: dict[str, float],
    measured: dict[str, float],
    tolerance: dict[str, float],
    keys: list[str] | None = None,
) -> dict[str, Any]:
    keys = keys or ["chest", "shoulder", "sleeve", "length"]
    errors = {}
    ok = True
    for k in keys:
        if k not in target or k not in measured:
            continue
        err = measured[k] - target[k]
        tol = tolerance.get(k, 1.0)
        errors[k] = {
            "target": target[k],
            "measured": measured[k],
            "error": round(err, 3),
            "tolerance": tol,
            "pass": abs(err) <= tol,
        }
        if abs(err) > tol:
            ok = False
    return {"pass": ok, "errors": errors}
