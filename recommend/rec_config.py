"""C 파트(추천 피드) 설정값 모음.

비중·점수를 바꿀 때는 이 파일만 고치면 된다.
※ 이름을 config.py로 하지 않은 이유
   1) .gitignore에 config.py가 있어 커밋되지 않음
   2) services/blender_runner.py가 blender/config.py를 `from config import`로 읽어서 이름이 겹침
"""

# ── 최종 점수 비중 (합 = 1.0) ────────────────────────────────
W_BODY  = 0.60   # 체형 적합도 (B 파트 매칭 점수)
W_PREF  = 0.25   # 취향 점수 (클릭·찜·구매 학습)
W_TREND = 0.15   # 시즌·인기 점수

# 트렌드 점수 안에서의 비중
W_SEASON     = 0.5
W_POPULARITY = 0.5

# 취향 기록이 없는 신규 사용자(콜드 스타트)의 취향 점수
PREF_DEFAULT = 0.5

# ── 체형 판정 ────────────────────────────────────────────────
# 1위와 2위 비율 차이가 이 값 이상이면 단일형, 미만이면 혼합형
SINGLE_TYPE_GAP = 0.10

# ── 태그 점수 (스타일 가이드를 숫자로 바꾼 표) ─────────────────
TAG_GOOD  = +2   # 이 골격에 어울림
TAG_AVOID = -3   # 이 골격이 피해야 함

# 체형 적합도 0~1 변환: body = 0.5 + 가중합 / (2 * BODY_SCALE)
# 어울림 태그 4개(+8)면 1.0, 피해야 함 태그 1개(-3)면 약 0.31
BODY_SCALE = 8

# 골격별 어울림/피해야 함 태그 (골격3타입 스타일가이드 기준)
STYLE_TAGS = {
    "S": {  # 스트레이트: 탄탄함 + 직선성, 미니멀하게 몸에 맞게
        "good": {"collar", "slim_fit", "firm_fabric", "vertical_seam",
                 "round_neck", "u_neck", "cropped", "h_line", "center_press",
                 "straight_leg", "tailored", "knee_above", "wrap"},
        "avoid": {"high_neck", "ruffle", "oversized", "boxy", "padding",
                  "waist_tight"},
    },
    "W": {  # 웨이브: 부드러움 + 허리 강조, 가볍게 곡선을 살려서
        "good": {"puff_sleeve", "ruffle", "cropped", "soft_fabric",
                 "high_waist", "a_line", "waist_emphasis", "wrap", "slim_fit"},
        "avoid": {"oversized", "boxy", "shoulder_pad", "stiff_fabric",
                  "thick_fabric", "low_waist", "padding"},
    },
    "N": {  # 내추럴: 볼륨감 + 여유로운 핏, 넉넉하게
        "good": {"oversized", "boxy", "drop_shoulder", "thick_fabric",
                 "loose_fit", "wide", "washing", "long"},
        "avoid": {"tight", "skinny", "slim_fit", "chiffon"},
    },
}

# 계절 이름 (items.json의 seasons 값과 같아야 함)
SEASONS = ("spring", "summer", "fall", "winter")
