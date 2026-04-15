# S/M/L 아바타 기준 치수 (팀원 아바타 확정되면 수정)
AVATAR_STANDARDS = {
    "S": {"height_max": 163, "weight_max": 55},
    "M": {"height_max": 170, "weight_max": 70},
    "L": {"height_max": 999, "weight_max": 999}
}

# 의상 기본 치수 기준 (기본 .blend 파일 기준)
BASE_MEASUREMENTS = {
    "T-shirt": {
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