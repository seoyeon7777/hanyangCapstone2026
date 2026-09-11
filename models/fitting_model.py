import numpy as np

# S/M/L 아바타 신체 치수 (cm)
# 어깨: 엑셀 기준 (S≤43, M=44~47, L≥48) / 가슴·소매: 한국 여성 표준 체형 기준
AVATAR_BODY_MEASUREMENTS = {
    "S": {"shoulder": 40, "chest": 83, "sleeve": 56, "waist": 66, "hip": 88,  "inseam": 72},
    "M": {"shoulder": 45, "chest": 88, "sleeve": 58, "waist": 70, "hip": 93,  "inseam": 74},
    "L": {"shoulder": 49, "chest": 94, "sleeve": 60, "waist": 76, "hip": 99,  "inseam": 76},
}

# ── Blender export 전용 기준 (calc_export_shape_keys) ─────────────────────────
#
# Basis 라벨 치수 (사이즈표/사용자 입력 cm).
# mesh 실측은 MEASURE_BASE_MESH_CM (garment_measure) — cloth_top.blend 프로브.
# length 만 mesh AABB 가 라벨보다 큼 (scale≈1.78). 나머지는 ≈1:1.
EXPORT_BASE_MEASUREMENTS = {
    "tshirt": {
        "shoulder": 44,
        "sleeve":   20,
        "chest":    100,
        "length":   65,
    },
    "hoodie": {
        "shoulder": 46,
        "sleeve":   58,
        "chest":    110,
        "length":   70,
    },
    "jacket": {
        # AI-Hub 여성 자켓 field_tape 중앙값 근처 (hoodie 남성/오버핏 기준보다 작음)
        "shoulder": 43,
        "sleeve":   55,
        "chest":    96,
        "length":   64,
    },
    "pants": {
        "waist":  72,
        "hip":    96,
        "inseam": 74,
        "length": 98,
    },
    "skirt": {
        "waist":  72,
        "hip":    96,
        "length": 55,
    },
}

# Shape key=1.0 일 때 라벨 cm 변화량 (cloth_top.blend 프로브 기반)
# 구버전 단일 RANGE(shoulder13/sleeve42/chest25/length55)는 과대 → shapekey 과소 적용.
EXPORT_SHAPE_KEY_RANGE_MIN = {
    "shoulder": 3.98,
    "sleeve":   12.61,
    "chest":    16.06,
    "length":   13.36,
    "waist":    15.84,
    "hip":      8.74,
    "inseam":   13.32,
}
EXPORT_SHAPE_KEY_RANGE_MAX = {
    "shoulder": 3.84,
    "sleeve":   11.41,
    "chest":    7.85,
    "length":   20.06,
    "waist":    20.16,
    "hip":      28.81,
    "inseam":   25.0,  # probe max was noisy; clamp for stable calib
}

# 하위 호환: 평균 range
EXPORT_SHAPE_KEY_RANGE = {
    k: round((EXPORT_SHAPE_KEY_RANGE_MIN[k] + EXPORT_SHAPE_KEY_RANGE_MAX[k]) / 2.0, 2)
    for k in EXPORT_SHAPE_KEY_RANGE_MIN
}

# 의류별 RANGE 오버라이드 (cloth_*_ground_truth.json 프로브)
EXPORT_SHAPE_KEY_RANGE_BY_GARMENT = {
    "skirt": {
        "min": {"waist": 14.4, "hip": 17.28, "length": 7.7},
        "max": {"waist": 18.01, "hip": 26.89, "length": 9.9},
    },
    # hoodie/jacket: 반팔 top 메쉬 + 긴소매 라벨 스케일(≈2.8x) → sleeve RANGE 확대
    "hoodie": {
        "min": {"sleeve": 36.57},
        "max": {"sleeve": 33.10},
    },
    "jacket": {
        "min": {"sleeve": 34.68},
        "max": {"sleeve": 31.39},
    },
}


def shape_key_range_for(garment_type: str, key: str, *, positive: bool) -> float:
    """라벨 cm → Shape Key 변환용 range. positive=True면 MAX(키 증가 방향)."""
    g = (garment_type or "").lower()
    ov = EXPORT_SHAPE_KEY_RANGE_BY_GARMENT.get(g) or {}
    side = "max" if positive else "min"
    if key in (ov.get(side) or {}):
        return float(ov[side][key])
    if positive:
        return float(EXPORT_SHAPE_KEY_RANGE_MAX.get(key, EXPORT_SHAPE_KEY_RANGE.get(key, 10.0)))
    return float(EXPORT_SHAPE_KEY_RANGE_MIN.get(key, EXPORT_SHAPE_KEY_RANGE.get(key, 10.0)))


def match_avatar(height, weight):
    if height <= 157:
        return "S"
    elif height <= 168:
        return "M"
    else:
        return "L"


def normalize_garment_measurements_for_wear(
    measurements: dict,
    *,
    garment_type: str = "tshirt",
    height: float = 165,
    weight: float = 55,
) -> tuple[dict, list[str]]:
    """사이즈표/입력 치수를 아바타 착용용 라벨 cm으로 정규화.

    - 한국 쇼핑몰 흔한 가슴·허리·엉덩이 *단면* → 둘레(×2) 자동 판별
    - 상의: 슬림/베이비티는 타이트 착용을 유지 (과도한 ease·기장 하한 금지)
    - 어깨만 아바타에 맞춰 메쉬가 몸에서 뜨지 않게 보정
    """
    out = {k: float(v) for k, v in (measurements or {}).items() if v is not None}
    notes: list[str] = []
    if not out:
        return out, notes

    g = (garment_type or "tshirt").lower()
    avatar = AVATAR_BODY_MEASUREMENTS[match_avatar(height, weight)]
    lower = g in {"pants", "skirt", "shorts", "trousers"}

    def _maybe_double_flat(key: str, lo: float = 28.0, hi: float = 58.0) -> None:
        v = out.get(key)
        if v is None:
            return
        # 성인 둘레로는 거의 안 나오는 작은 값 → 단면으로 간주
        if lo <= v <= hi:
            new_v = round(v * 2.0, 1)
            notes.append(f"{key} 단면→둘레 자동환산 {v}→{new_v}")
            out[key] = new_v

    if not lower:
        _maybe_double_flat("chest", 32.0, 58.0)
        # 니트/슬림 티: 차트 둘레를 존중. 아바타보다 너무 작을 때만
        # 극단 수축 방지용 soft floor (ease 없음 — 베이비티는 타이트가 정상).
        if "chest" in out:
            soft_floor = float(avatar["chest"]) - 4.0
            if out["chest"] < soft_floor:
                notes.append(
                    f"착용 soft-floor: chest {out['chest']}→{soft_floor} "
                    f"(avatar {avatar['chest']}-4)"
                )
                out["chest"] = soft_floor
        if "shoulder" in out:
            floor_s = float(avatar["shoulder"]) - 1.0
            if out["shoulder"] < floor_s:
                notes.append(f"shoulder 착용 보정 {out['shoulder']}→{floor_s}")
                out["shoulder"] = floor_s
        if "length" in out and g in {"tshirt", "tee", "top", "shirt", "blouse"}:
            # 크롭/베이비티 기장 유지. 템플릿 붕괴만 막는 soft min.
            if out["length"] < 48.0:
                notes.append(f"length soft-floor {out['length']}→48")
                out["length"] = 48.0
    else:
        _maybe_double_flat("waist", 28.0, 55.0)
        _maybe_double_flat("hip", 30.0, 60.0)
        if "waist" in out:
            floor_w = float(avatar["waist"]) + 2.0
            if out["waist"] < floor_w:
                notes.append(f"착용 ease: waist {out['waist']}→{floor_w}")
                out["waist"] = floor_w
        if "hip" in out:
            floor_h = float(avatar["hip"]) + 2.0
            if out["hip"] < floor_h:
                notes.append(f"착용 ease: hip {out['hip']}→{floor_h}")
                out["hip"] = floor_h

    return out, notes


def calc_export_shape_keys(garment_type, measurements):
    """
    입력 치수(라벨 cm) → Shape Key (-1~1).
    음수 오차 → RANGE_MIN / {key}_min, 양수 오차 → RANGE_MAX / {key}_max.
    """
    garment_base = EXPORT_BASE_MEASUREMENTS.get(garment_type, {})
    shape_keys   = {}

    for key, input_value in measurements.items():
        if input_value is None:
            continue
        base_val = garment_base.get(key)
        if base_val is None:
            continue

        diff = float(input_value) - float(base_val)
        max_range = shape_key_range_for(garment_type, key, positive=(diff >= 0))
        value = diff / max_range if max_range else 0.0
        shape_keys[key] = round(max(-1.0, min(1.0, value)), 3)

    return shape_keys


# 원단별 탄성 (0~1, 높을수록 잘 늘어남)
FABRIC_ELASTICITY = {
    "cotton":    0.15,
    "polyester": 0.04,
    "linen":     0.02,
    "wool":      0.3,
    "denim":     0.02,
    "knit":      0.7,
    "silk":      0.02,
    "nylon":     0.1,
    "acrylic":   0.1,
    "rayon":     0.02,
    "spandex":   0.9,
    "cashmere":  0.15,
    "chiffon":   0.02,
}

# 원단별 굽힘 강성 (낮을수록 드레이프성 높음)
FABRIC_BENDING = {
    "cotton":    25.0,
    "polyester": 20.0,
    "linen":     8.0,
    "wool":      20.0,
    "denim":     80.0,
    "knit":      5.0,
    "silk":      4.0,
    "nylon":     20.0,
    "acrylic":   60.0,
    "rayon":     5.0,
    "spandex":   4.0,
    "cashmere":  8.0,
    "chiffon":   5.0,
}


def calc_fabric_elasticity(fabric: dict) -> float:
    if not fabric:
        return 0.15
    total_elasticity = 0.0
    total_ratio      = 0.0
    for fabric_type, ratio in fabric.items():
        elasticity       = FABRIC_ELASTICITY.get(fabric_type, 0.1)
        total_elasticity += elasticity * ratio
        total_ratio      += ratio
    if total_ratio == 0:
        return 0.15
    return total_elasticity / total_ratio


def calc_fabric_bending(fabric: dict) -> float:
    if not fabric:
        return 25.0
    total_bending = 0.0
    total_ratio   = 0.0
    for fabric_type, ratio in fabric.items():
        bending       = FABRIC_BENDING.get(fabric_type, 25.0)
        total_bending += bending * ratio
        total_ratio   += ratio
    if total_ratio == 0:
        return 25.0
    return total_bending / total_ratio


# ── OBJ 로드 ──────────────────────────────────────────────
def load_obj(path):
    vertices, faces = [], []
    with open(path, encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split()
            if not parts:
                continue
            if parts[0] == "v":
                vertices.append([float(parts[1]), float(parts[2]), float(parts[3])])
            elif parts[0] == "f":
                idx = [int(p.split("/")[0]) - 1 for p in parts[1:]]
                faces.append([idx[0], idx[1], idx[2]])
                if len(idx) == 4:
                    faces.append([idx[0], idx[2], idx[3]])
    return np.array(vertices, dtype=np.float32), np.array(faces, dtype=np.int32)


# ── 압박도 계산 (시뮬레이션 결과용) ──────────────────────
def calc_pressure_map(sim_verts, avatar_verts, fabric_elasticity=0.1):
    """
    시뮬레이션 후 옷-아바타 버텍스 거리 기반 압박도 계산.
    거리가 작을수록 압박이 큼.
    """
    try:
        from scipy.spatial import KDTree
        tree = KDTree(avatar_verts)
        dists, _ = tree.query(sim_verts)
    except ImportError:
        # scipy 없으면 브루트포스 최근접
        import numpy as np
        dists = np.sqrt(((sim_verts[:, None, :] - avatar_verts[None, :, :]) ** 2).sum(axis=2)).min(axis=1)


    max_dist        = 0.05
    pressure_values = np.clip(1.0 - dists / max_dist, 0, 1) * (1 - fabric_elasticity)
    avg             = float(pressure_values.mean())

    if avg > 0.7:
        fit_result = "too_tight"
    elif avg > 0.4:
        fit_result = "tight"
    elif avg > 0.2:
        fit_result = "good"
    elif avg > 0.05:
        fit_result = "comfortable"
    else:
        fit_result = "loose"

    return {
        "avg_pressure": round(avg, 3),
        "fit_result":   fit_result,
        "per_vertex":   pressure_values.tolist(),
    }
