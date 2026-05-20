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
BASE_MEASUREMENTS = {
    "tshirt": {
        "shoulder": 44,
        "sleeve":   20,   # 반팔 소매 길이 기준 (~20cm)
        "chest":    100
    },
    "pants": {
        "waist":  80,
        "hip":    96,
        "inseam": 76
    }
}

# Shape Key 최대 변형 범위 (cm)
SHAPE_KEY_RANGE = {
    "shoulder": 30,
    "sleeve":   30,
    "chest":    30,
    "waist":    30,
    "hip":      30,
    "inseam":   30
}


def match_avatar(height, weight):
    """
    키/몸무게로 S/M/L 매칭 (BMI 기반)
    """
    bmi = weight / ((height / 100) ** 2)

    if bmi <= 19.1:
        return "S"
    elif bmi <= 21.5:
        return "M"
    else:
        return "L"


def calc_scale(garment_type, measurements):
    """
    입력 치수 기반으로 의류 전체 스케일 계산
    Shape Key 대신 전체 크기 비율로 변형
    """
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

    # sleeve처럼 의류 고유 치수는 BASE 기준으로만 비교
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

        # 양수: 의류가 기준보다 큼(여유), 음수: 기준보다 작음(타이트)
        value = max(-1.0, min(1.0, diff / max_range))
        shape_keys[key] = round(value, 3)

    return shape_keys


# 원단별 탄성 (0~1, 높을수록 잘 늘어남) - 신축성 기반
FABRIC_ELASTICITY = {
    "cotton":    0.15,  # 면 - 약간의 신축성
    "polyester": 0.04,  # 폴리에스터 - 신축성 없음
    "linen":     0.02,  # 린넨 - 신축성 없음, 복원력 매우 낮음
    "wool":      0.3,   # 울 - 약간의 신축성, 복원력 중간
    "denim":     0.02,  # 데님 - 신축성 없음
    "knit":      0.7,   # 니트 - 신축성 좋음
    "silk":      0.02,  # 실크 - 신축성 없음
    "nylon":     0.1,   # 나일론 - 약간의 신축성
    "acrylic":   0.1,   # 아크릴 - 약간의 신축성
    "rayon":     0.02,  # 레이온 - 신축성 없음
    "spandex":   0.9,   # 스판덱스 - 신축성 매우 좋음
    "cashmere":  0.15,  # 캐시미어 - 약간의 신축성
    "chiffon":   0.02,  # 쉬폰 - 신축성 없음
}

# 원단별 굽힘 강성 (낮을수록 잘 흘러내림 = 드레이프성 높음)
FABRIC_BENDING = {
    "cotton":    25.0,  # 드레이프성 중간~낮음
    "polyester": 20.0,  # 드레이프성 중간
    "linen":     8.0,   # 드레이프성 높음
    "wool":      20.0,  # 드레이프성 중간
    "denim":     80.0,  # 드레이프성 낮음 (뻣뻣)
    "knit":      5.0,   # 드레이프성 높음
    "silk":      4.0,   # 드레이프성 높음
    "nylon":     20.0,  # 드레이프성 중간
    "acrylic":   60.0,  # 드레이프성 낮음
    "rayon":     5.0,   # 드레이프성 높음
    "spandex":   4.0,   # 드레이프성 높음
    "cashmere":  8.0,   # 드레이프성 높음
    "chiffon":   5.0,   # 드레이프성 높음
}


def calc_fabric_elasticity(fabric: dict) -> float:
    """
    원단 비율을 받아 전체 탄성값 계산 (신축성 기반)
    fabric = {"cotton": 70, "polyester": 30}
    """
    if not fabric:
        return 0.15  # 기본값 (면 기준)

    total_elasticity = 0.0
    total_ratio      = 0.0

    for fabric_type, ratio in fabric.items():
        elasticity       = FABRIC_ELASTICITY.get(fabric_type, 0.1)
        total_elasticity += elasticity * ratio
        total_ratio      += ratio

    if total_ratio == 0:
        return 0.15

    return total_elasticity / total_ratio  # 가중평균


def calc_fabric_bending(fabric: dict) -> float:
    """
    원단 비율을 받아 굽힘 강성 계산 (드레이프성 반영)
    낮을수록 잘 흘러내림
    fabric = {"cotton": 70, "polyester": 30}
    """
    if not fabric:
        return 25.0  # 기본값 (면 기준)

    total_bending = 0.0
    total_ratio   = 0.0

    for fabric_type, ratio in fabric.items():
        bending       = FABRIC_BENDING.get(fabric_type, 25.0)
        total_bending += bending * ratio
        total_ratio   += ratio

    if total_ratio == 0:
        return 25.0

    return total_bending / total_ratio  # 가중평균


def calc_pressure(shape_keys, fabric: dict = {}):
    """
    shape_keys + 원단 탄성을 반영한 압박 계산
    """
    elasticity    = calc_fabric_elasticity(fabric)
    pressure_data = {}

    for region, value in shape_keys.items():
        # 탄성이 높을수록 압박이 줄어듦
        adjusted_value = value * (1 - elasticity)

        if adjusted_value > 0.6:
            level = "high"
        elif adjusted_value > 0.3:
            level = "medium"
        elif adjusted_value > 0:
            level = "low"
        elif adjusted_value > -0.3:
            level = "comfortable"  # 약간 여유
        else:
            level = "loose"        # 많이 여유

        pressure_data[region] = {
            "value": round(adjusted_value, 3),
            "level": level
        }

    # 전체 핏 평가
    values = [v * (1 - elasticity) for v in shape_keys.values()]
    avg    = sum(values) / len(values) if values else 0

    if avg > 0.6:
        fit_result = "too_tight"
    elif avg > 0.3:
        fit_result = "tight"
    elif avg > 0:
        fit_result = "good"
    elif avg > -0.3:
        fit_result = "comfortable"
    else:
        fit_result = "loose"

    return pressure_data, fit_result


def calc_fit_score(shape_keys, fabric: dict = {}):
    """
    shape_keys + 원단 탄성을 반영한 피팅 정확도 계산
    shape_key가 0에 가까울수록, 탄성이 높을수록 점수 올라감
    """
    if not shape_keys:
        return 100

    elasticity = calc_fabric_elasticity(fabric)

    avg_diff = sum(abs(v) * (1 - elasticity) for v in shape_keys.values()) / len(shape_keys)

    score = int((1 - avg_diff) * 100)
    return max(0, min(100, score))


# ── OBJ 로드 ──────────────────────────────────────────────
def load_obj(path):
    """OBJ 파일에서 vertices, faces 로드"""
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


# ── 압박도 계산 ───────────────────────────────────────────
def calc_pressure_map(sim_verts, avatar_verts, fabric_elasticity=0.1):
    """
    시뮬레이션 후 옷-아바타 버텍스 거리 기반 압박도 계산.
    거리가 작을수록 압박이 큼.
    반환: dict { avg_pressure, fit_result, per_vertex }
    """
    from scipy.spatial import KDTree
    tree = KDTree(avatar_verts)
    dists, _ = tree.query(sim_verts)

    max_dist = 0.05
    pressure_values = np.clip(1.0 - dists / max_dist, 0, 1) * (1 - fabric_elasticity)

    avg = float(pressure_values.mean())

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
