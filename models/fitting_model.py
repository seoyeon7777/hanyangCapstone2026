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
        "shoulder": 45,   # S 사이즈 기준
        "sleeve":   20,   # S 사이즈 기준 (반팔 소매 길이)
        "chest":    100,  # S 사이즈 기준 (가슴둘레 = 단면 50 × 2)
        "length":   67    # S 사이즈 기준 (총장)
    },
    "pants": {
        "waist":  80,
        "hip":    96,
        "inseam": 76
    }
}

# 의류 치수 기준 사이즈표 (옷 자체 치수 기준, cm)
# 가슴둘레 = 가슴단면 × 2 기준, 어깨너비 보조
# 각 구간은 인접 사이즈 중간값으로 설정
CLOTHING_SIZE_STANDARD = {
    "tshirt": {
        "XXS": {"chest": (0,   91),  "shoulder": (0,   42)},
        "XS":  {"chest": (91,  97),  "shoulder": (42,  44)},
        "S":   {"chest": (97,  103), "shoulder": (44,  46)},
        "M":   {"chest": (103, 109), "shoulder": (46,  48)},
        "L":   {"chest": (109, 115), "shoulder": (48,  50)},
        "XL":  {"chest": (115, 121), "shoulder": (50,  52)},
        "XXL": {"chest": (121, 128), "shoulder": (52,  54)},
        "3XL": {"chest": (128, 999), "shoulder": (54,  999)},
    },
    "pants": {
        "S":  {"waist": (0,   72)},
        "M":  {"waist": (72,  80)},
        "L":  {"waist": (80,  88)},
        "XL": {"waist": (88,  999)},
    }
}


def match_clothing_size(garment_type, measurements):
    """
    입력된 의류 치수로 S/M/L/XL 사이즈 판별.
    가슴둘레(또는 허리) 우선, 어깨너비 보조.
    """
    standard = CLOTHING_SIZE_STANDARD.get(garment_type)
    if not standard:
        return None

    chest    = measurements.get("chest")
    shoulder = measurements.get("shoulder")
    waist    = measurements.get("waist")

    scores = {size: 0 for size in standard}

    for size, ranges in standard.items():
        for key, (lo, hi) in ranges.items():
            val = measurements.get(key)
            if val is not None and lo <= val < hi:
                # 가슴/허리는 2점, 어깨는 1점 (우선순위 반영)
                scores[size] += 2 if key in ("chest", "waist") else 1

    best = max(scores, key=lambda s: scores[s])
    # 점수가 모두 0이면 판별 불가
    if scores[best] == 0:
        return None
    return best


# Shape Key 최대 변형 범위 (cm)
SHAPE_KEY_RANGE = {
    "shoulder": 30,
    "sleeve":   30,
    "chest":    30,
    "waist":    30,
    "hip":      30,
    "inseam":   30,
    "length":   30    # 기장 최대 변형 범위 (±30cm)
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


def calc_shape_keys(garment_type, measurements):
    """
    입력된 의류 치수와 BASE_MEASUREMENTS(S 사이즈 기준) 차이를 Shape Key 값(-1~1)으로 변환.
    Blender에서 옷 메쉬를 얼마나 변형할지 결정하는 용도.
    - shape_key = 0: Basis(S 사이즈) 상태 그대로
    - shape_key > 0: Basis보다 큰 사이즈로 변형
    - shape_key < 0: Basis보다 작은 사이즈로 변형
    """
    garment_base = BASE_MEASUREMENTS.get(garment_type, {})
    shape_keys   = {}

    for key, input_value in measurements.items():
        base_val = garment_base.get(key)
        if base_val is None:
            continue

        diff      = input_value - base_val
        max_range = SHAPE_KEY_RANGE.get(key, 10)
        value     = max(-1.0, min(1.0, diff / max_range))
        shape_keys[key] = round(value, 3)

    return shape_keys


def calc_ease(garment_type, measurements, avatar_size):
    """
    (실제 여유분 - 적정 여유분) / range 로 핏 편차 계산.
    - 0에 가까울수록 레귤러핏 기준 이상적인 핏
    - 양수: 적정보다 큰 옷 (루즈), 음수: 적정보다 작은 옷 (타이트)
    """
    avatar_base = AVATAR_BODY_MEASUREMENTS.get(avatar_size, {})
    ideal       = IDEAL_EASE.get(garment_type, {})
    BODY_FIT_KEYS = {"chest", "shoulder", "waist", "hip", "inseam"}

    ease = {}
    for key, input_value in measurements.items():
        if key not in BODY_FIT_KEYS:
            continue
        body_val = avatar_base.get(key)
        if body_val is None:
            continue

        actual_ease = input_value - body_val           # 실제 여유분 (cm)
        ideal_ease  = ideal.get(key, 0)                # 적정 여유분 (cm)
        deviation   = actual_ease - ideal_ease         # 적정 대비 편차

        max_range = SHAPE_KEY_RANGE.get(key, 10)
        value     = max(-1.0, min(1.0, deviation / max_range))
        ease[key] = round(value, 3)

    return ease


# 레귤러핏 기준 적정 여유분 (옷치수 - 신체치수, cm)
# ease가 이 값에 가까울수록 핏이 좋다고 판단
IDEAL_EASE = {
    "tshirt": {"chest": 15, "shoulder": 2},
    "pants":  {"waist":  8, "hip": 12},
}

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


def calc_pressure(ease, fabric: dict = {}):
    """
    ease(여유분 비율) + 원단 탄성을 반영한 압박 계산.
    ease > 0: 여유로운 핏, ease < 0: 타이트한 핏
    """
    elasticity    = calc_fabric_elasticity(fabric)
    pressure_data = {}

    for region, value in ease.items():
        # 탄성이 높을수록 압박이 줄어듦
        adjusted_value = value * (1 - elasticity)

        # adjusted_value: 0=적정핏, 양수=루즈, 음수=타이트
        if adjusted_value > 0.5:
            level = "loose"       # 많이 큰 옷
        elif adjusted_value > 0.2:
            level = "comfortable" # 약간 여유
        elif adjusted_value >= -0.2:
            level = "good"        # 적정 핏
        elif adjusted_value >= -0.5:
            level = "tight"       # 약간 타이트
        else:
            level = "too_tight"   # 많이 타이트

        pressure_data[region] = {
            "value": round(adjusted_value, 3),
            "level": level
        }

    # 전체 핏 평가
    values = [v * (1 - elasticity) for v in ease.values()]
    avg    = sum(values) / len(values) if values else 0

    if avg > 0.5:
        fit_result = "loose"
    elif avg > 0.2:
        fit_result = "comfortable"
    elif avg >= -0.2:
        fit_result = "good"
    elif avg >= -0.5:
        fit_result = "tight"
    else:
        fit_result = "too_tight"

    return pressure_data, fit_result


def calc_fit_score(ease, fabric: dict = {}):
    """
    ease(여유분 비율) + 원단 탄성을 반영한 피팅 정확도 계산.
    ease가 0에 가까울수록(옷이 몸에 딱 맞을수록), 탄성이 높을수록 점수 올라감
    """
    if not ease:
        return 100

    elasticity = calc_fabric_elasticity(fabric)

    avg_diff = sum(abs(v) * (1 - elasticity) for v in ease.values()) / len(ease)

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
