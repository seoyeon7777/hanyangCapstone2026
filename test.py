from models.fitting_model import match_avatar, calc_shape_keys, calc_fit_score, calc_pressure

# 테스트 입력값
height       = 172
weight       = 68
garment_type = "T-shirt"
measurements = {
    "shoulder": 45,
    "sleeve":   28,
    "chest":    102
}

# 계산
avatar_size               = match_avatar(height, weight)
shape_keys                = calc_shape_keys(garment_type, measurements)
fit_score                 = calc_fit_score(shape_keys)
pressure_data, fit_result = calc_pressure(shape_keys)

# 출력
print("아바타 사이즈: ", avatar_size)
print("옷 기본 사이즈 조정 수치: ", shape_keys)
print("피팅 정확도 점수 (0~100): ", fit_score)
print("전체 핏 평가 (too_tight/tight/good/loose): ", fit_result)
print("어깨/가슴/팔길이 압박 수치: ", pressure_data)