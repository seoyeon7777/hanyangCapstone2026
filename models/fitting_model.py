import numpy as np

# S/M/L 아바타 신체 치수 (cm)
# 어깨: 엑셀 기준 (S≤43, M=44~47, L≥48) / 가슴·소매: 한국 여성 표준 체형 기준
AVATAR_BODY_MEASUREMENTS = {
    "S": {"shoulder": 40, "chest": 83, "sleeve": 56, "waist": 66, "hip": 88,  "inseam": 72},
    "M": {"shoulder": 45, "chest": 88, "sleeve": 58, "waist": 70, "hip": 93,  "inseam": 74},
    "L": {"shoulder": 49, "chest": 94, "sleeve": 60, "waist": 76, "hip": 99,  "inseam": 76},
}

# 의상 기본 치수 기준 (Basis 상태 기본값)
# sleeve: 반팔티 소매 길이 기준 (신체 팔 길이 아님)
# length: 총기장 (어깨~밑단)
BASE_MEASUREMENTS = {
    "tshirt": {
        "shoulder": 44,
        "sleeve":   20,   # 반팔 소매 길이 기준 (~20cm)
        "chest":    100,
        "length":   65,   # 총기장 기준 (~65cm)
    },
    "pants": {
        "waist":  80,
        "hip":    96,
        "inseam": 76
    }
}

# Shape Key 최대 변형 범위 (cm) — 압박도·핏스코어 계산용 (calc_shape_keys)
SHAPE_KEY_RANGE = {
    "shoulder": 30,
    "sleeve":   30,
    "chest":    30,
    "waist":    30,
    "hip":      30,
    "inseam":   30,
    "length":   30,
}

# ── Blender export 전용 기준 (calc_export_shape_keys) ─────────────────────────
#
# Basis 모델 실측치 (blend 파일의 shape key 0 상태 기준)
# sleeve: Basis가 긴 소매(~60cm)임 — sleeve_min=1.0 적용 시 ~19cm 단소매
EXPORT_BASE_MEASUREMENTS = {
    "tshirt": {
        "shoulder": 44,   # M 아바타 어깨(45)와 거의 동일
        "sleeve":   20,   # Basis 단소매 실측 (~20cm)
        "chest":    100,  # Basis 가슴둘레
        "length":   65,   # Basis 총기장
    },
    "pants": {
        "waist":  80,
        "hip":    96,
        "inseam": 76,
    }
}

# Blender shape key 최대 변화량 (cm) — blend 파일 실측 기준
# 참고 데이터:
#   sleeve_min=41.19 / sleeve_max=43.03
#   length_min=53.00 / length_max=86.30
#   chest_min=27.50  / chest_max=22.73
#   waist_min=22.05  / waist_max=18.91
#   shoulder_min=15.25 / shoulder_max=10.47
EXPORT_SHAPE_KEY_RANGE = {
    "shoulder": 13,   # 평균 ~12.9 (min15.3 / max10.5)
    "sleeve":   42,   # 평균 ~42.1 (min41.2 / max43.0)
    "chest":    25,   # 평균 ~25.1 (min27.5 / max22.7)
    "waist":    20,   # 평균 ~20.5 (min22.1 / max18.9)
    "length":   55,   # 절충값 (min53 / max86 — 축소 한계 기준)
    "hip":      30,
    "inseam":   30,
}

# 의류 치수 기준 사이즈표 (팀원 추가 — 총평/적합도 텍스트 생성용)
CLOTHING_SIZE_STANDARD = {
    "tshirt": {
        "S":   {"chest": (0,   97),  "shoulder": (0,   44)},
        "M":   {"chest": (97,  103), "shoulder": (44,  46)},
        "L":   {"chest": (103, 109), "shoulder": (46,  48)},
        "XL":  {"chest": (109, 999), "shoulder": (48,  999)},
    },
    "pants": {
        "S":  {"waist": (0,   70),  "hip": (0,   88)},
        "M":  {"waist": (70,  76),  "hip": (88,  94)},
        "L":  {"waist": (76,  82),  "hip": (94,  100)},
        "XL": {"waist": (82,  999), "hip": (100, 999)},
    }
}

# 레귤러핏 기준 적정 여유분 (옷치수 - 신체치수, cm) — 팀원 추가
IDEAL_EASE = {
    "tshirt": {"chest": 15, "shoulder": 2},
    "pants":  {"waist": 4, "hip": 6},
}


def match_avatar(height, weight):
    """키/몸무게로 S/M/L 매칭 (BMI 기반)"""
    bmi = weight / ((height / 100) ** 2)
    if bmi <= 19.1:
        return "S"
    elif bmi <= 21.5:
        return "M"
    else:
        return "L"


def match_clothing_size(garment_type, measurements):
    """
    입력된 의류 치수로 S/M/L/XL 사이즈 판별 (팀원 추가).
    가슴둘레(또는 허리) 우선, 어깨너비 보조.
    """
    standard = CLOTHING_SIZE_STANDARD.get(garment_type)
    if not standard:
        return None

    scores = {size: 0 for size in standard}

    for size, ranges in standard.items():
        for key, (lo, hi) in ranges.items():
            val = measurements.get(key)
            if val is not None and lo <= val < hi:
                scores[size] += 2 if key in ("chest", "waist") else 1

    max_score  = max(scores.values())
    candidates = [s for s, v in scores.items() if v == max_score]

    if len(candidates) == 1:
        return candidates[0]

    size_order = list(standard.keys())
    return max(candidates, key=lambda s: size_order.index(s))


def calc_ease(garment_type, measurements, avatar_size):
    """
    (실제 여유분 - 적정 여유분) / range 로 핏 편차 계산 (팀원 추가).
    총평·적합도 텍스트 생성 전용 — 압박도 계산에는 shape_keys 사용.
    """
    avatar_base = AVATAR_BODY_MEASUREMENTS.get(avatar_size, {})
    ideal       = IDEAL_EASE.get(garment_type, {})
    BODY_FIT_KEYS = {"chest", "shoulder", "waist", "hip"}

    ease = {}
    for key, input_value in measurements.items():
        if key not in BODY_FIT_KEYS:
            continue
        body_val = avatar_base.get(key)
        if body_val is None:
            continue

        actual_ease = input_value - body_val
        ideal_ease  = ideal.get(key, 0)
        deviation   = actual_ease - ideal_ease

        max_range = SHAPE_KEY_RANGE.get(key, 10)
        value     = max(-1.0, min(1.0, deviation / max_range))
        ease[key] = round(value, 3)

    return ease


def calc_scale(garment_type, measurements):
    """입력 치수 기반으로 의류 전체 스케일 계산"""
    base = BASE_MEASUREMENTS.get(garment_type, {})
    if not base:
        return 1.0

    ratios = []
    for key, input_value in measurements.items():
        if key in base and input_value:
            ratios.append(input_value / base[key])

    if not ratios:
        return 1.0

    return round(sum(ratios) / len(ratios), 3)


def calc_shape_keys(garment_type, measurements, avatar_size=None):
    """
    의류 치수와 기준 치수의 차이를 Shape Key 값(-1~1)으로 변환.

    기준 결정 규칙:
    - 신체 핏 관련 치수 (chest, waist, hip, shoulder, inseam):
        avatar_size가 있으면 AVATAR_BODY_MEASUREMENTS 기준 (몸에 얼마나 맞는지)
    - 의류 고유 치수 (sleeve 등):
        항상 BASE_MEASUREMENTS 기준 (옷 자체 크기 조정)
    """
    avatar_base  = AVATAR_BODY_MEASUREMENTS.get(avatar_size, {}) if avatar_size else {}
    garment_base = BASE_MEASUREMENTS.get(garment_type, {})

    GARMENT_ONLY_KEYS = {"sleeve", "length"}

    shape_keys = {}

    for key, input_value in measurements.items():
        if key in GARMENT_ONLY_KEYS:
            base_val = garment_base.get(key)
        else:
            base_val = avatar_base.get(key) or garment_base.get(key)

        if base_val is None:
            continue

        diff      = input_value - base_val
        max_range = SHAPE_KEY_RANGE.get(key, 10)
        value     = max(-1.0, min(1.0, diff / max_range))
        shape_keys[key] = round(value, 3)

    return shape_keys


def calc_export_shape_keys(garment_type, measurements):
    """
    의류 3D 모델 shape key export 전용.
    입력 치수를 블렌더 Basis 모델 실측치와 비교.

    calc_shape_keys와의 차이:
      calc_shape_keys        → 아바타 체형 기준 (압박도·핏스코어 계산용)
      calc_export_shape_keys → 의류 Basis 실측 기준 (블렌더 shape key 적용용)

    Basis 실측 및 최대 변화량은 EXPORT_BASE_MEASUREMENTS / EXPORT_SHAPE_KEY_RANGE 참고.
    - sleeve: Basis 모델이 긴 소매(~60cm)이므로 BASE_MEASUREMENTS(20)와 별도 관리.
              sleeve_min(41.19cm) 적용 시 ~19cm 단소매가 됨.
    - shoulder: 최대 변화량 ~13cm (blend 실측) → range=30이면 값이 절반만 활용됨.
    - length: 최대 축소 53cm / 최대 확장 86cm → range=55로 절충.
    """
    garment_base = EXPORT_BASE_MEASUREMENTS.get(garment_type, {})
    shape_keys   = {}

    for key, input_value in measurements.items():
        if input_value is None:
            continue
        base_val = garment_base.get(key)
        if base_val is None:
            continue

        diff      = input_value - base_val
        max_range = EXPORT_SHAPE_KEY_RANGE.get(key, 10)
        value     = max(-1.0, min(1.0, diff / max_range))
        shape_keys[key] = round(value, 3)

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


def calc_pressure(shape_keys, fabric: dict = {}):
    """
    shape_keys(의류 치수와 아바타 체형의 차이) + 원단 탄성을 반영한 압박 계산.
    shape_keys > 0: 옷이 몸보다 큼(여유 있음), shape_keys < 0: 옷이 몸보다 작음(타이트)
    """
    elasticity    = calc_fabric_elasticity(fabric)
    pressure_data = {}

    for region, value in shape_keys.items():
        adjusted_value = value * (1 - elasticity)

        if adjusted_value > 0.6:
            level = "too_loose"
        elif adjusted_value > 0.3:
            level = "loose"
        elif adjusted_value > 0:
            level = "good"
        elif adjusted_value > -0.3:
            level = "tight"
        else:
            level = "too_tight"

        pressure_data[region] = {
            "value": round(adjusted_value, 3),
            "level": level
        }

    values = [v * (1 - elasticity) for v in shape_keys.values()]
    avg    = sum(values) / len(values) if values else 0

    if avg > 0.6:
        fit_result = "loose"
    elif avg > 0.3:
        fit_result = "comfortable"
    elif avg > 0:
        fit_result = "good"
    elif avg > -0.3:
        fit_result = "tight"
    else:
        fit_result = "too_tight"

    return pressure_data, fit_result


def calc_fit_score(shape_keys, fabric: dict = {}):
    """shape_keys + 원단 탄성을 반영한 피팅 정확도 계산"""
    if not shape_keys:
        return 100
    elasticity = calc_fabric_elasticity(fabric)
    avg_diff   = sum(abs(v) * (1 - elasticity) for v in shape_keys.values()) / len(shape_keys)
    score      = int((1 - avg_diff) * 100)
    return max(0, min(100, score))


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
    from scipy.spatial import KDTree
    tree = KDTree(avatar_verts)
    dists, _ = tree.query(sim_verts)

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
