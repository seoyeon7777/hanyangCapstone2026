"""
티셔츠 2D 패턴 제도기.

앞/뒤/소매 패널을 cm 단위 polyline + landmark + seam 인덱스로 출력한다.
제도식은 재측정 루프가 닫히도록 목표 치수에 직접 구속한다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict
from typing import Any

from models.garment_spec import GarmentSpec


Point = tuple[float, float]


@dataclass
class Panel:
    name: str
    vertices_cm: list[Point]
    landmarks: dict[str, int]
    seams: dict[str, list[int]]
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Pattern:
    category: str
    panels: dict[str, Panel]
    targets_cm: dict[str, float]
    draft_params: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "targets_cm": self.targets_cm,
            "draft_params": self.draft_params,
            "panels": {k: v.to_dict() for k, v in self.panels.items()},
        }


def _neck_dims(neckline: str) -> tuple[float, float, float]:
    """(half_neck_width, front_drop, back_drop) cm."""
    table = {
        "crew": (8.0, 8.0, 2.5),
        "round": (8.5, 9.0, 2.5),
        "vneck": (7.5, 14.0, 2.5),
        "boat": (11.0, 4.0, 3.0),
    }
    return table.get(neckline, table["crew"])


def draft_tshirt(
    spec: GarmentSpec,
    overrides: dict[str, float] | None = None,
) -> Pattern:
    """
    목표 의류 치수(target_garment_cm)로 티셔츠 패턴 제도.

    overrides: 보정 루프에서 넣는 목표 치수 덮어쓰기
      {"chest": ..., "shoulder": ..., "sleeve": ..., "length": ...}
    """
    errors = spec.validate()
    if errors:
        raise ValueError("; ".join(errors))

    targets = spec.target_garment_cm()
    if overrides:
        targets = {**targets, **overrides}

    chest = float(targets["chest"])
    shoulder = float(targets["shoulder"])
    sleeve_len = float(targets["sleeve"])
    length = float(targets["length"])
    neckline = spec.construction.get("neckline", "crew")

    half_chest = chest / 2.0          # 앞판(또는 뒤판) 가로폭
    half_shoulder = shoulder / 2.0
    neck_w, neck_front, neck_back = _neck_dims(neckline)

    # 암홀 깊이: 가슴 기반 + 최소값 (성인 상의 전형 범위)
    scye_depth = max(18.0, min(26.0, chest * 0.22 + 2.0))
    # 소매통(이두 폭) — 암홀과 길이 매칭용
    sleeve_width = max(14.0, chest * 0.18 + 2.0)
    # 어깨 경사 — 총기장은 목옆점(HSP)→헴 기준이므로 HSP를 y=length에 둔다.
    shoulder_drop = 3.0

    draft_params = {
        "half_chest": half_chest,
        "half_shoulder": half_shoulder,
        "neck_w": neck_w,
        "neck_front": neck_front,
        "neck_back": neck_back,
        "scye_depth": scye_depth,
        "sleeve_width": sleeve_width,
        "shoulder_drop": shoulder_drop,
        "sleeve_len": sleeve_len,
        "length": length,
    }

    front = _draft_bodice(
        name="front",
        half_chest=half_chest,
        half_shoulder=half_shoulder,
        neck_w=neck_w,
        neck_drop=neck_front,
        scye_depth=scye_depth,
        length=length,
        shoulder_drop=shoulder_drop,
        is_front=True,
    )
    back = _draft_bodice(
        name="back",
        half_chest=half_chest,
        half_shoulder=half_shoulder,
        neck_w=neck_w,
        neck_drop=neck_back,
        scye_depth=scye_depth,
        length=length,
        shoulder_drop=shoulder_drop,
        is_front=False,
    )
    sleeve_l = _draft_sleeve(
        name="sleeve_l",
        sleeve_len=sleeve_len,
        sleeve_width=sleeve_width,
        scye_depth=scye_depth,
        side="left",
    )
    sleeve_r = _draft_sleeve(
        name="sleeve_r",
        sleeve_len=sleeve_len,
        sleeve_width=sleeve_width,
        scye_depth=scye_depth,
        side="right",
    )

    return Pattern(
        category="tshirt",
        panels={"front": front, "back": back, "sleeve_l": sleeve_l, "sleeve_r": sleeve_r},
        targets_cm=dict(targets),
        draft_params=draft_params,
    )


def _sample_quad_bezier(p0: Point, p1: Point, p2: Point, n: int) -> list[Point]:
    pts = []
    for i in range(n + 1):
        t = i / n
        u = 1 - t
        x = u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0]
        y = u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1]
        pts.append((x, y))
    return pts


def _draft_bodice(
    name: str,
    half_chest: float,
    half_shoulder: float,
    neck_w: float,
    neck_drop: float,
    scye_depth: float,
    length: float,
    shoulder_drop: float,
    is_front: bool,
) -> Panel:
    """
    중심선(x=0) 기준 반쪽을 제도한 뒤 미러링해 전체 앞/뒤판 생성.
    y=0 헴, y=length 네크 상단 근처.
    """
    # 반쪽 주요점 (오른쪽)
    hem_cf = (0.0, 0.0)
    hem_side = (half_chest / 2.0, 0.0)
    side_chest = (half_chest / 2.0, length - scye_depth)
    # 어깨 끝점 x = half_shoulder → L/R 거리가 목표 어깨폭
    shoulder_x = half_shoulder
    # 총기장 = 목옆점→헴. 목옆점을 y=length에 고정하고 어깨끝은 경사만큼 낮춤
    neck_side = (neck_w, length)
    shoulder_y = length - shoulder_drop
    neck_cf = (0.0, length - neck_drop)

    # 암홀 곡선: shoulder → side_chest
    ah_ctrl = (
        shoulder_x + (side_chest[0] - shoulder_x) * 0.55,
        shoulder_y - (shoulder_y - side_chest[1]) * 0.35,
    )
    armhole = _sample_quad_bezier(
        (shoulder_x, shoulder_y), ah_ctrl, side_chest, n=8
    )

    # 네크 곡선: neck_cf → neck_side
    nk_ctrl = (neck_w * 0.55, length - neck_drop * (0.35 if is_front else 0.2))
    neck_curve = _sample_quad_bezier(neck_cf, nk_ctrl, neck_side, n=6)

    # 반쪽 외곽 (CF 헴 → 사이드 헴 → 사이드업 → 암홀역 → 어깨 → 네크 → CF)
    right_boundary: list[Point] = []
    right_boundary.append(hem_cf)
    right_boundary.append(hem_side)
    right_boundary.append(side_chest)
    # armhole: side_chest → shoulder (armhole sampled shoulder→side, so reverse)
    for p in reversed(armhole[:-1]):  # exclude duplicate side_chest
        right_boundary.append(p)
    # armhole[0] is shoulder — now neck from neck_side down to neck_cf
    # neck_curve: neck_cf → neck_side; we need shoulder → neck_side → neck_cf
    right_boundary.append(neck_side)
    for p in reversed(neck_curve[:-1]):  # exclude neck_side duplicate; keep toward neck_cf
        right_boundary.append(p)
    right_boundary.append(neck_cf)

    # Build full panel: right side (skip CF duplicates carefully) + mirrored left
    # right_boundary goes hem_cf → ... → neck_cf
    # Mirror: take right points with x>0, flip to -x, reverse order for closed loop continuity
    verts: list[Point] = []
    # Right half excluding final neck_cf (added once)
    for p in right_boundary[:-1]:
        verts.append(p)
    verts.append(neck_cf)
    # Left half: mirror of right without CF points, reversed
    # right_boundary[1:-1] are non-CF
    for p in reversed(right_boundary[1:-1]):
        verts.append((-p[0], p[1]))

    # Deduplicate consecutive identical points
    clean: list[Point] = []
    for p in verts:
        if not clean or (abs(clean[-1][0] - p[0]) > 1e-6 or abs(clean[-1][1] - p[1]) > 1e-6):
            clean.append((round(p[0], 4), round(p[1], 4)))
    if clean and (abs(clean[0][0] - clean[-1][0]) < 1e-6 and abs(clean[0][1] - clean[-1][1]) < 1e-6):
        clean.pop()
    verts = clean

    def find_near(x: float, y: float) -> int:
        best_i, best_d = 0, 1e18
        for i, (px, py) in enumerate(verts):
            d = (px - x) ** 2 + (py - y) ** 2
            if d < best_d:
                best_d, best_i = d, i
        return best_i

    landmarks = {
        "hem_cf": find_near(0.0, 0.0),
        "hem_l": find_near(-half_chest / 2.0, 0.0),
        "hem_r": find_near(half_chest / 2.0, 0.0),
        "side_l": find_near(-half_chest / 2.0, length - scye_depth),
        "side_r": find_near(half_chest / 2.0, length - scye_depth),
        "shoulder_l": find_near(-shoulder_x, shoulder_y),
        "shoulder_r": find_near(shoulder_x, shoulder_y),
        "neck_l": find_near(-neck_w, length),
        "neck_r": find_near(neck_w, length),
        "neck_cf": find_near(0.0, length - neck_drop),
        "chest_l": find_near(-half_chest / 2.0, length - scye_depth),
        "chest_r": find_near(half_chest / 2.0, length - scye_depth),
    }

    seams = {
        "side_l": _index_polyline(verts, landmarks["hem_l"], landmarks["side_l"]),
        "side_r": _index_polyline(verts, landmarks["hem_r"], landmarks["side_r"]),
        "shoulder_l": _index_polyline(verts, landmarks["neck_l"], landmarks["shoulder_l"]),
        "shoulder_r": _index_polyline(verts, landmarks["neck_r"], landmarks["shoulder_r"]),
        "armhole_l": _index_polyline(verts, landmarks["shoulder_l"], landmarks["side_l"]),
        "armhole_r": _index_polyline(verts, landmarks["shoulder_r"], landmarks["side_r"]),
        "hem": _index_polyline(verts, landmarks["hem_l"], landmarks["hem_r"]),
        "neck": _index_polyline(verts, landmarks["neck_l"], landmarks["neck_r"]),
    }

    return Panel(
        name=name,
        vertices_cm=verts,
        landmarks=landmarks,
        seams=seams,
        meta={"half_chest": half_chest, "length": length, "scye_depth": scye_depth},
    )


def _draft_sleeve(
    name: str,
    sleeve_len: float,
    sleeve_width: float,
    scye_depth: float,
    side: str,
) -> Panel:
    """간단한 단소매: 직사각형+캡 곡선. 길이는 underarm 기준."""
    # cap height ~ 0.4 * scye_depth for short sleeve knit
    cap_h = max(4.0, scye_depth * 0.35)
    half_w = sleeve_width / 2.0
    # y=0 hem, y=sleeve_len underarm length; cap extends above
    hem_l = (-half_w, 0.0)
    hem_r = (half_w, 0.0)
    under_l = (-half_w, sleeve_len)
    under_r = (half_w, sleeve_len)
    cap_top = (0.0, sleeve_len + cap_h)

    left_cap = _sample_quad_bezier(under_l, (-half_w * 0.6, sleeve_len + cap_h * 0.85), cap_top, n=6)
    right_cap = _sample_quad_bezier(cap_top, (half_w * 0.6, sleeve_len + cap_h * 0.85), under_r, n=6)

    verts: list[Point] = [hem_l, under_l]
    verts.extend(left_cap[1:])
    verts.extend(right_cap[1:])
    verts.append(hem_r)
    # close implicitly

    clean: list[Point] = []
    for p in verts:
        if not clean or (abs(clean[-1][0] - p[0]) > 1e-6 or abs(clean[-1][1] - p[1]) > 1e-6):
            clean.append((round(p[0], 4), round(p[1], 4)))
    verts = clean

    def find_near(x: float, y: float) -> int:
        best_i, best_d = 0, 1e18
        for i, (px, py) in enumerate(verts):
            d = (px - x) ** 2 + (py - y) ** 2
            if d < best_d:
                best_d, best_i = d, i
        return best_i

    landmarks = {
        "hem_l": find_near(-half_w, 0.0),
        "hem_r": find_near(half_w, 0.0),
        "underarm_l": find_near(-half_w, sleeve_len),
        "underarm_r": find_near(half_w, sleeve_len),
        "cap_top": find_near(0.0, sleeve_len + cap_h),
        "hem_cf": find_near(0.0, 0.0),
    }
    # hem_cf may not exist on boundary — add midpoint if needed
    if min((verts[landmarks["hem_l"]][0]) ** 2, 1) >= 0:
        # insert hem center into landmark by nearest on hem edge
        landmarks["hem_cf"] = find_near(0.0, 0.0)

    seams = {
        "underarm_l": _index_polyline(verts, landmarks["hem_l"], landmarks["underarm_l"]),
        "underarm_r": _index_polyline(verts, landmarks["hem_r"], landmarks["underarm_r"]),
        "cap": _index_polyline(verts, landmarks["underarm_l"], landmarks["underarm_r"]),
        "hem": _index_polyline(verts, landmarks["hem_l"], landmarks["hem_r"]),
    }
    return Panel(
        name=name,
        vertices_cm=verts,
        landmarks=landmarks,
        seams=seams,
        meta={"sleeve_len": sleeve_len, "sleeve_width": sleeve_width, "side": side, "cap_h": cap_h},
    )


def _index_polyline(verts: list[Point], i0: int, i1: int) -> list[int]:
    """두 랜드마크 사이 경계 인덱스 (짧은 쪽 호)."""
    n = len(verts)
    if n == 0:
        return []
    if i0 == i1:
        return [i0]

    def walk(a: int, b: int, step: int) -> list[int]:
        out = [a]
        cur = a
        for _ in range(n):
            cur = (cur + step) % n
            out.append(cur)
            if cur == b:
                break
        return out

    fwd = walk(i0, i1, 1)
    rev = walk(i0, i1, -1)
    return fwd if len(fwd) <= len(rev) else rev


def draft_pattern(spec: GarmentSpec, overrides: dict[str, float] | None = None) -> Pattern:
    if spec.category in ("tshirt", "top", "shirt"):
        return draft_tshirt(spec, overrides=overrides)
    raise NotImplementedError(f"pattern draft not implemented for category={spec.category}")
