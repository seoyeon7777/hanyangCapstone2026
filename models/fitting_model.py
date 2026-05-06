# S/M/L 아바타 기준 치수 (팀원 아바타 확정되면 수정)
AVATAR_STANDARDS = {
    "S": {"height_max": 163, "weight_max": 55},
    "M": {"height_max": 170, "weight_max": 70},
    "L": {"height_max": 999, "weight_max": 999}
}

# 의상 기본 치수 기준 (기본 .blend 파일 기준)
BASE_MEASUREMENTS = {
    "tshirt": {
        "shoulder": 44,
        "sleeve":   25,
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
    "shoulder": 10,
    "sleeve":   15,
    "chest":    20,
    "waist":    20,
    "hip":      20,
    "inseam":   15
}


def match_avatar(height, weight):
    """
    키/몸무게를 받아 S/M/L 반환
    """
    bmi = weight / ((height / 100) ** 2)

    if bmi < 18.5:
        return "S"
    elif bmi < 25:
        return "M"
    else:
        return "L"


def calc_shape_keys(garment_type, measurements):
    """
    입력받은 치수와 기본 치수의 차이를
    Shape Key 값(0~1)으로 변환
    나중에 Blender에서 이 값으로 의류 변형
    """
    base = BASE_MEASUREMENTS.get(garment_type, {})
    shape_keys = {}

    for key, input_value in measurements.items():
        if key not in base:
            continue

        diff = input_value - base[key]
        max_range = SHAPE_KEY_RANGE.get(key, 10)

        # 양수면 늘어남, 음수면 줄어듦
        # -1 ~ 1 사이 값으로 변환
        value = max(-1.0, min(1.0, diff / max_range))
        shape_keys[key] = round(value, 3)

    return shape_keys


# 원단별 탄성 (0~1, 높을수록 잘 늘어남)
FABRIC_ELASTICITY = {
    "cotton":    0.1,   # 면 - 잘 안 늘어남
    "polyester": 0.3,   # 폴리에스터
    "linen":     0.05,  # 린넨 - 거의 안 늘어남
    "wool":      0.25,  # 울
    "denim":     0.05,  # 데님 - 거의 안 늘어남
    "knit":      0.7,   # 니트 - 잘 늘어남
    "silk":      0.15   # 실크
}

def calc_fabric_elasticity(fabric: dict) -> float:
    """
    원단 비율을 받아 전체 탄성값 계산
    fabric = {"cotton": 70, "polyester": 30}
    """
    if not fabric:
        return 0.1  # 기본값 (면 기준)

    total_elasticity = 0.0
    total_ratio      = 0.0

    for fabric_type, ratio in fabric.items():
        elasticity    = FABRIC_ELASTICITY.get(fabric_type, 0.1)
        total_elasticity += elasticity * ratio
        total_ratio      += ratio

    if total_ratio == 0:
        return 0.1

    return total_elasticity / total_ratio  # 가중평균


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


# 핏 정확도 계산
def calc_fit_score(shape_keys):
    """
    shape_keys 값으로 피팅 정확도 계산
    shape_key가 0에 가까울수록 기본 치수와 같다는 뜻 → 높은 점수
    """
    if not shape_keys:
        return 100
    
    # 각 치수 차이의 평균
    avg_diff = sum(abs(v) for v in shape_keys.values()) / len(shape_keys)
    
    # 0~1 차이를 100점 만점으로 변환
    score = int((1 - avg_diff) * 100)
    return max(0, min(100, score))

