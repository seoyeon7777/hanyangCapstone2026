"""하의/상의 공용 재측정 + 라벨 cm 변환."""

from __future__ import annotations

from typing import Optional
import numpy as np

from models.fitting_model import load_obj, EXPORT_BASE_MEASUREMENTS

try:
    from scipy.spatial import ConvexHull
    _HAS_SCIPY = True
except ImportError:  # pragma: no cover
    _HAS_SCIPY = False


# cloth_top / cloth_pants 프로브 기반 mesh-cm
MEASURE_BASE_MESH_CM = {
    "tshirt": {
        "shoulder": 46.58,
        "chest": 99.54,
        "sleeve": 20.57,
        "length": 115.40,
    },
    "hoodie": {
        "shoulder": 46.58,
        "chest": 99.54,
        "sleeve": 20.57,
        "length": 115.40,
    },
    # rebuild_pants_ground_truth.py 로 갱신
    "pants": {
        "waist": 42.5,
        "hip": 52.08,
        "inseam": 60.0,
        "length": 155.0,
    },
    "skirt": {
        "waist": 39.50,
        "hip": 57.01,
        "length": 85.00,
    },
}


def detect_up_axis(verts: np.ndarray) -> int:
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
    best = int(np.argmax(scores))
    # Prefer longest axis if clearly dominant (pants Z-up export)
    long_axis = int(np.argmax(size))
    if size[long_axis] >= 1.2 * max(size[j] for j in range(3) if j != long_axis):
        return long_axis
    if scores[1] >= scores[best] * 0.98:
        return 1
    return best


def to_y_up(verts: np.ndarray, up_axis: Optional[int] = None) -> np.ndarray:
    v = np.asarray(verts, dtype=np.float64)
    up = detect_up_axis(v) if up_axis is None else up_axis
    if up == 1:
        return v.copy()
    if up == 2:
        return np.column_stack([v[:, 0], v[:, 2], v[:, 1]])
    return np.column_stack([v[:, 1], v[:, 0], v[:, 2]])


def _auto_to_meters(verts: np.ndarray) -> np.ndarray:
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
    if verts is None or len(verts) == 0:
        return {}

    v = _auto_to_meters(np.asarray(verts, dtype=np.float64))
    v = to_y_up(v)
    x, y, z = v[:, 0], v[:, 1], v[:, 2]
    ymin, ymax = float(y.min()), float(y.max())
    yspan = max(ymax - ymin, 1e-9)
    length = yspan * 100.0

    g = (garment_type or "tshirt").lower()
    if g in {"pants", "skirt", "shorts", "trousers"}:
        return _measure_lower(v, ymin, ymax, yspan, length)

    y_sh = ymin + 0.88 * yspan
    band = v[np.abs(y - y_sh) < 0.012]
    shoulder = None
    if len(band) >= 10:
        shoulder = float((band[:, 0].max() - band[:, 0].min()) * 100.0 / 2.0)
    chest = _half_hull_perimeter(v, ymin + 0.57 * yspan, 0.02, 0.25)
    sleeve = _sleeve_length(v)
    return {
        "length": round(float(length), 2),
        "shoulder": round(shoulder, 2) if shoulder is not None else None,
        "chest": round(chest, 2) if chest is not None else None,
        "sleeve": round(sleeve, 2) if sleeve is not None else None,
    }


def _ring_stats(v: np.ndarray, y0: float, half_band: float):
    band = v[np.abs(v[:, 1] - y0) <= half_band]
    if len(band) < 4:
        return None, False, 0
    width = float(band[:, 0].max() - band[:, 0].min())
    xs = band[:, 0]
    # 이족: 중앙 갭 + 좌우 클러스터 (통짜 링은 중앙에 버텍스 있음)
    near0 = int(np.sum(np.abs(xs) < 0.035))
    neg = int(np.sum(xs < -0.05))
    pos = int(np.sum(xs > 0.05))
    bip = near0 <= 1 and neg >= 3 and pos >= 3
    return width, bip, len(band)


def _measure_lower(
    v: np.ndarray, ymin: float, ymax: float, yspan: float, length: float
) -> dict[str, Optional[float]]:
    ys = np.unique(np.round(v[:, 1], 4))
    if len(ys) < 2:
        ys = np.linspace(ymin, ymax, 10)
    half = max(0.04, yspan * 0.035)

    stats = []
    for y0 in ys:
        w, bip, n = _ring_stats(v, float(y0), half)
        stats.append({"y": float(y0), "w": w, "bip": bip, "n": n})

    # 기본: max Y = 허리쪽, min Y = 발목 (프로시저럴/대부분 템플릿)
    # 이족이 max 끝에만 있으면 뒤집힌 것으로 본다.
    _, bip_hi, _ = _ring_stats(v, ymax, half)
    _, bip_lo, _ = _ring_stats(v, ymin, half)
    if bip_hi and not bip_lo:
        ankle_y, waist_side = ymax, "low"
    else:
        ankle_y, waist_side = ymin, "high"

    torso = [s for s in stats if s["w"] and not s["bip"]]
    legs = [s for s in stats if s["bip"]]
    # bipodal 미검출 시: 하단 40%를 다리, 상단을 몸통으로
    if not legs:
        if waist_side == "high":
            cut = ymin + 0.40 * yspan
            legs = [s for s in stats if s["y"] <= cut]
            torso = [s for s in stats if s["y"] > cut]
        else:
            cut = ymax - 0.40 * yspan
            legs = [s for s in stats if s["y"] >= cut]
            torso = [s for s in stats if s["y"] < cut]

    if waist_side == "high":
        torso = sorted(torso, key=lambda s: s["y"], reverse=True)
        legs = sorted(legs, key=lambda s: s["y"])
    else:
        torso = sorted(torso, key=lambda s: s["y"])
        legs = sorted(legs, key=lambda s: s["y"], reverse=True)

    waist_y = torso[0]["y"] if torso else (ymax if waist_side == "high" else ymin)
    hip_y = waist_y
    if len(torso) >= 2:
        # 허리 다음 링 중 가장 넓은 쪽을 엉덩이
        hip_y = max(torso[1:4], key=lambda s: s["w"] or 0)["y"]

    if legs:
        crotch_y = legs[-1]["y"] if waist_side == "high" else legs[-1]["y"]
        # 다리 구간에서 허리에 가장 가까운 링 = 가랑이
        crotch_y = min(legs, key=lambda s: abs(s["y"] - waist_y))["y"]
    else:
        crotch_y = float(np.median(ys))

    xspan = float(np.abs(v[:, 0]).max()) + 0.08
    waist = _half_hull_perimeter(v, waist_y, half, xspan)
    hip = _half_hull_perimeter(v, hip_y, half, xspan)
    inseam = abs(crotch_y - ankle_y) * 100.0
    if inseam < 1.0:
        # fallback: 전체 기장의 65%
        inseam = length * 0.65

    return {
        "length": round(float(length), 2),
        "waist": round(waist, 2) if waist is not None else None,
        "hip": round(hip, 2) if hip is not None else None,
        "inseam": round(float(inseam), 2),
    }


def _half_hull_perimeter(
    v: np.ndarray, y0: float, half_band: float, x_limit: float
) -> Optional[float]:
    core = v[(np.abs(v[:, 1] - y0) < half_band) & (np.abs(v[:, 0]) < x_limit)]
    if len(core) < 6:
        # relax x limit
        core = v[np.abs(v[:, 1] - y0) < half_band]
    if len(core) < 6:
        return None
    if _HAS_SCIPY and len(core) >= 8:
        try:
            hull = ConvexHull(core[:, [0, 2]])
            return float(hull.area * 100.0 / 2.0)
        except Exception:
            pass
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
    sh_half = float((seam[:, 0].max() - seam[:, 0].min()) * 50.0)
    max_x = float(np.abs(v[:, 0]).max() * 100.0)
    return max(0.0, max_x - sh_half)


def measure_garment_obj(obj_path: str, garment_type: str = "tshirt") -> dict[str, Optional[float]]:
    verts, _faces = load_obj(obj_path)
    return measure_garment_verts(verts, garment_type=garment_type)


def mesh_to_label_cm(
    measured_mesh: dict[str, Optional[float]],
    garment_type: str = "tshirt",
) -> dict[str, Optional[float]]:
    g = (garment_type or "tshirt").lower()
    if g in {"trousers"}:
        g = "pants"
    if g not in MEASURE_BASE_MESH_CM and g not in {"pants", "skirt", "shorts"}:
        g = "tshirt" if g not in {"hoodie"} else g
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
