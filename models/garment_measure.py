"""의류 OBJ/메쉬에서 cm 치수를 재측정한다.

cloth_top.blend 프로브 결과 기준:
- Blender OBJ export 는 Y-up (length shape key 가 Y 를 움직임)
- chest: 몸통 단면 convex-hull 둘레의 1/2  (basis ≈ 99.5 ≈ 라벨 100)
- shoulder: 어깨 높이 full-width 의 1/2     (basis ≈ 46.6 ≈ 라벨 44)
- sleeve: max|x| − 어깨솔기 half-width      (basis ≈ 20.6 ≈ 라벨 20)
- length: Y 방향 AABB                       (basis ≈ 115.4, 라벨 65 → scale≈1.78)

캘리브레이션은 라벨 cm 로 비교하므로 measure_garment_* 결과는
`to_label_cm()` 으로 변환해 사용한다.
"""

from __future__ import annotations

from typing import Optional
import numpy as np

from models.fitting_model import load_obj, EXPORT_BASE_MEASUREMENTS

try:
    from scipy.spatial import ConvexHull
    _HAS_SCIPY = True
except ImportError:  # pragma: no cover
    _HAS_SCIPY = False


# cloth_top.blend basis 를 본 측정 공식으로 잰 값 (mesh-cm)
# scripts/probe 로 재생성 가능: assets/clothing/cloth_top_ground_truth.json
MEASURE_BASE_MESH_CM = {
    "tshirt": {
        "shoulder": 46.58,
        "chest": 99.54,
        "sleeve": 20.57,
        "length": 115.40,
    },
}


def detect_up_axis(verts: np.ndarray) -> int:
    """up 축 인덱스.

    cloth_top 처럼 소매 때문에 X 가 더 길어도, 아바타 위에 올려둔 메쉬는
    up 축 mid-point 가 origin 에서 멀리 떨어져 있다 (Y≈3.2m).
    """
    v = np.asarray(verts, dtype=np.float64)
    mins = v.min(axis=0)
    maxs = v.max(axis=0)
    size = maxs - mins
    mid = (mins + maxs) * 0.5
    longest = float(size.max())
    scores = []
    for i in range(3):
        long_enough = size[i] >= 0.35 * longest
        scores.append(abs(float(mid[i])) if long_enough else abs(float(mid[i])) * 0.05)
    # tie-break: prefer Y then Z then X (Blender OBJ → Y-up 흔함)
    best = int(np.argmax(scores))
    if scores[1] >= scores[best] * 0.98:
        return 1
    return best


def to_y_up(verts: np.ndarray, up_axis: Optional[int] = None) -> np.ndarray:
    """up 축을 Y(index 1)로 맞춘 복사본 반환."""
    v = np.asarray(verts, dtype=np.float64)
    up = detect_up_axis(v) if up_axis is None else up_axis
    if up == 1:
        return v.copy()
    if up == 2:  # Z-up → (X, Z, -Y) roughly; keep X, map Z→Y, Y→Z
        return np.column_stack([v[:, 0], v[:, 2], v[:, 1]])
    # X-up
    return np.column_stack([v[:, 1], v[:, 0], v[:, 2]])


def _auto_to_meters(verts: np.ndarray) -> np.ndarray:
    """이미 cm 스케일(대각선>5)이면 m 로 되돌림."""
    mins = verts.min(axis=0)
    maxs = verts.max(axis=0)
    diag = float(np.linalg.norm(maxs - mins))
    if diag >= 5.0:
        return verts * 0.01
    return verts


def measure_garment_verts(
    verts: np.ndarray,
    garment_type: str = "tshirt",
) -> dict[str, Optional[float]]:
    """버텍스 → mesh-cm 치수 dict (라벨 cm 아님)."""
    if verts is None or len(verts) == 0:
        return {}

    v = _auto_to_meters(np.asarray(verts, dtype=np.float64))
    v = to_y_up(v)
    x, y, z = v[:, 0], v[:, 1], v[:, 2]
    ymin, ymax = float(y.min()), float(y.max())
    yspan = max(ymax - ymin, 1e-9)

    g = (garment_type or "tshirt").lower()
    lower = g in {"pants", "skirt", "shorts"}

    length = yspan * 100.0

    if lower:
        # 1차 근사 — 하의 템플릿 추가 시 재프로브
        y_w = ymin + 0.95 * yspan
        y_h = ymin + 0.70 * yspan
        waist = _half_hull_perimeter(v, y_w, 0.02, 0.30)
        hip = _half_hull_perimeter(v, y_h, 0.02, 0.30)
        return {
            "length": round(length, 2),
            "waist": round(waist, 2) if waist is not None else None,
            "hip": round(hip, 2) if hip is not None else None,
            "inseam": round(length * 0.85, 2),
        }

    # shoulder: half full-width @ 88% height
    y_sh = ymin + 0.88 * yspan
    band = v[np.abs(y - y_sh) < 0.012]
    shoulder = None
    if len(band) >= 10:
        shoulder = float((band[:, 0].max() - band[:, 0].min()) * 100.0 / 2.0)

    # chest: half hull perimeter @ 57% height, torso core
    chest = _half_hull_perimeter(v, ymin + 0.57 * yspan, 0.02, 0.25)

    # sleeve: max|x| - shoulder seam half-width
    sleeve = _sleeve_length(v)

    return {
        "length": round(float(length), 2),
        "shoulder": round(shoulder, 2) if shoulder is not None else None,
        "chest": round(chest, 2) if chest is not None else None,
        "sleeve": round(sleeve, 2) if sleeve is not None else None,
    }


def _half_hull_perimeter(
    v: np.ndarray, y0: float, half_band: float, x_limit: float
) -> Optional[float]:
    core = v[(np.abs(v[:, 1] - y0) < half_band) & (np.abs(v[:, 0]) < x_limit)]
    if len(core) < 8:
        return None
    if _HAS_SCIPY:
        try:
            hull = ConvexHull(core[:, [0, 2]])
            return float(hull.area * 100.0 / 2.0)
        except Exception:
            pass
    # fallback: 2*(w+d)/2 = w+d
    w = float(core[:, 0].max() - core[:, 0].min())
    d = float(core[:, 2].max() - core[:, 2].min())
    return (w + d) * 100.0


def _sleeve_length(v: np.ndarray) -> Optional[float]:
    y = v[:, 1]
    top = v[y > np.percentile(y, 85)]
    if len(top) < 8:
        return None
    zmed = float(np.median(top[:, 2]))
    seam = top[np.abs(top[:, 2] - zmed) < 0.05]
    if len(seam) < 8:
        return None
    sh_half = float((seam[:, 0].max() - seam[:, 0].min()) * 50.0)  # *100/2
    max_x = float(np.abs(v[:, 0]).max() * 100.0)
    return max(0.0, max_x - sh_half)


def measure_garment_obj(obj_path: str, garment_type: str = "tshirt") -> dict[str, Optional[float]]:
    verts, _faces = load_obj(obj_path)
    return measure_garment_verts(verts, garment_type=garment_type)


def mesh_to_label_cm(
    measured_mesh: dict[str, Optional[float]],
    garment_type: str = "tshirt",
) -> dict[str, Optional[float]]:
    """mesh-cm → 사용자 라벨 cm.

    scale = MEASURE_BASE_MESH / EXPORT_BASE_LABEL
    label = mesh / scale
    """
    g = "tshirt" if (garment_type or "tshirt").lower() not in {"pants", "skirt", "shorts"} else garment_type
    base_mesh = MEASURE_BASE_MESH_CM.get(g) or MEASURE_BASE_MESH_CM.get("tshirt", {})
    base_label = EXPORT_BASE_MEASUREMENTS.get(g) or EXPORT_BASE_MEASUREMENTS.get("tshirt", {})
    out: dict[str, Optional[float]] = {}
    for k, mesh_val in measured_mesh.items():
        if mesh_val is None:
            out[k] = None
            continue
        bm = base_mesh.get(k)
        bl = base_label.get(k)
        if bm and bl and bm > 1e-6:
            out[k] = round(float(mesh_val) * (float(bl) / float(bm)), 2)
        else:
            out[k] = round(float(mesh_val), 2)
    return out


def measure_garment_obj_label(obj_path: str, garment_type: str = "tshirt") -> dict[str, Optional[float]]:
    """OBJ → 라벨 cm (캘리브레이션/QA용)."""
    return mesh_to_label_cm(measure_garment_obj(obj_path, garment_type), garment_type)


def measurement_errors(
    target: dict[str, float],
    measured: dict[str, Optional[float]],
    keys: Optional[list[str]] = None,
) -> dict[str, float]:
    keys = keys or list(target.keys())
    err = {}
    for k in keys:
        if k not in target or target[k] is None:
            continue
        m = measured.get(k)
        if m is None:
            continue
        err[k] = round(float(target[k]) - float(m), 3)
    return err


def max_abs_error(errors: dict[str, float]) -> float:
    if not errors:
        return 0.0
    return float(max(abs(v) for v in errors.values()))
