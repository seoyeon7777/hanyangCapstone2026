from models.fitting_model import match_avatar, calc_shape_keys, calc_fit_score, calc_pressure

# 테스트 입력값
height       = 150
weight       = 40
garment_type = "tshirt"
measurements = {
    "shoulder": 46,   # 기본 44보다 2cm 큼
    "sleeve":   28,   # 기본 25보다 3cm 큼
    "chest":    105   # 기본 100보다 5cm 큼
}
fabric = {"cotton": 70, "polyester": 30}

# 계산
avatar_size               = match_avatar(height, weight)
shape_keys                = calc_shape_keys(garment_type, measurements)
fit_score                 = calc_fit_score(shape_keys)
pressure_data, fit_result = calc_pressure(shape_keys, fabric)

# 출력
print("아바타 사이즈: ", avatar_size)
print("옷 기본 사이즈 조정 수치: ", shape_keys)
print("피팅 정확도 점수 (0~100): ", fit_score)
print("전체 핏 평가 (too_tight/tight/good/loose): ", fit_result)
print("탄성 반영 압박:", pressure_data)