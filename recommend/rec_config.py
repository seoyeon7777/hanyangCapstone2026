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

# ── 3단계: 정렬 + 다양성 (rank) ──────────────────────────────
TOP_N = 10                # "오늘의 추천" 개수
MAX_SAME_CATEGORY_RUN = 2 # 같은 category 연속 최대 개수
MAX_SAME_REP_TAG = 3      # 상위 TOP_N 안에서 같은 대표 태그(good_tags 첫 번째) 최대 개수

# ── 4단계: 홈 섹션 (home_feed) ───────────────────────────────
CATEGORY_TOP_N = 4        # 카테고리 섹션마다 보여 줄 개수
CATEGORY_TITLES = {       # 섹션 순서 = 이 순서
    "top": "상의",
    "bottom": "하의",
    "outer": "아우터",
    "dress": "원피스",
}

# ── 5단계: 코디 조합 (outfits) ───────────────────────────────
OUTFIT_TOP_N = 3     # "추천 코디" 세트 수
OUTFIT_BONUS = 0.10  # 골격별 궁합 규칙을 만족하면 더하는 점수
# 1위 타입 기준 (상의에 필요한 태그 중 하나, 하의에 필요한 태그 중 하나)
OUTFIT_RULES = {
    "S": ({"collar", "slim_fit"}, {"straight_leg", "center_press", "h_line"}),
    "W": ({"cropped"}, {"high_waist"}),
    "N": ({"oversized", "boxy", "loose_fit"}, {"wide"}),
}

# ── 6단계: 추천 이유 + 피드백 학습 ───────────────────────────
TYPE_NAMES = {"S": "스트레이트", "W": "웨이브", "N": "내추럴"}

# 태그 → (문장 중간에 쓸 때, 문장 끝에 쓸 때). 스타일 가이드의 추천 이유를 줄인 것
REASON_TEXT = {
    "collar":         ("칼라가 목선을 세워 주고", "칼라가 목선을 세워 줘요"),
    "slim_fit":       ("몸에 맞는 핏이 라인을 정돈해 주고", "몸에 맞는 핏이 라인을 정돈해 줘요"),
    "firm_fabric":    ("탄탄한 소재가 태를 살려 주고", "탄탄한 소재가 태를 살려 줘요"),
    "vertical_seam":  ("세로 절개가 상체를 슬림하게 정리하고", "세로 절개가 상체를 슬림하게 정리해요"),
    "round_neck":     ("라운드넥이 목선을 깔끔하게 보여 주고", "라운드넥이 목선을 깔끔하게 보여 줘요"),
    "u_neck":         ("U넥이 목을 길어 보이게 하고", "U넥이 목을 길어 보이게 해요"),
    "cropped":        ("짧은 기장이 허리 위치를 올려 주고", "짧은 기장이 허리 위치를 올려 줘요"),
    "h_line":         ("H라인이 군더더기 없이 떨어지고", "H라인이 군더더기 없는 실루엣을 만들어요"),
    "center_press":   ("센터프레스 주름이 다리를 길어 보이게 하고", "센터프레스 주름이 다리를 길어 보이게 해요"),
    "straight_leg":   ("일자 핏이 다리 라인을 정리해 주고", "일자 핏이 다리 라인을 정리해 줘요"),
    "tailored":       ("각 잡힌 어깨선이 상체를 정돈하고", "각 잡힌 어깨선이 상체를 정돈해요"),
    "knee_above":     ("무릎 위 기장이 전체 균형을 잡아 주고", "무릎 위 기장이 전체 균형을 잡아 줘요"),
    "wrap":           ("랩 디자인이 허리를 은은하게 잡아 주고", "랩 디자인이 허리를 은은하게 잡아 줘요"),
    "puff_sleeve":    ("퍼프 소매가 어깨에 볼륨을 더하고", "퍼프 소매가 어깨에 볼륨을 더해요"),
    "ruffle":         ("러플이 상체에 볼륨감을 주고", "러플이 상체에 볼륨감을 줘요"),
    "soft_fabric":    ("부드러운 소재가 몸의 곡선을 살리고", "부드러운 소재가 몸의 곡선을 살려요"),
    "high_waist":     ("하이웨이스트가 다리를 길어 보이게 하고", "하이웨이스트가 다리를 길어 보이게 해요"),
    "a_line":         ("A라인이 하체 곡선과 어우러지고", "A라인이 하체 곡선과 잘 어우러져요"),
    "waist_emphasis": ("허리 라인이 실루엣을 살려 주고", "허리 라인이 실루엣을 살려 줘요"),
    "oversized":      ("여유로운 핏이 큰 프레임을 자연스럽게 감싸고", "여유로운 핏이 큰 프레임을 자연스럽게 감싸요"),
    "boxy":           ("박시한 라인이 골격의 존재감을 중화하고", "박시한 라인이 골격의 존재감을 중화해요"),
    "drop_shoulder":  ("드롭숄더가 넓은 어깨를 부드럽게 보이게 하고", "드롭숄더가 넓은 어깨를 부드럽게 보이게 해요"),
    "thick_fabric":   ("두께감 있는 소재가 프레임과 균형을 맞추고", "두께감 있는 소재가 프레임과 균형을 맞춰요"),
    "loose_fit":      ("넉넉한 핏이 편안하게 떨어지고", "넉넉한 핏이 편안하게 떨어져요"),
    "wide":           ("와이드 핏이 다리 라인을 편안하게 감싸고", "와이드 핏이 다리 라인을 편안하게 감싸요"),
    "washing":        ("워싱 소재감이 골격과 균형을 이루고", "워싱 소재감이 골격과 균형을 이뤄요"),
    "long":           ("긴 기장이 시원한 인상을 살려 주고", "긴 기장이 시원한 인상을 살려 줘요"),
}
REASON_MAX_TAGS = 2  # 이유 문장에 넣을 태그 수
REASON_FALLBACK = "지금 계절과 인기를 반영한 추천이에요."
REASON_EXCLUDED = "체형에 맞지 않는 디자인이 있어 추천에서 뺐어요."

# 반응별 태그 선호도 변화량. 결과는 -1~1로 자름
EVENT_WEIGHTS = {"click": 0.05, "like": 0.10, "purchase": 0.20, "return": -0.20}
POSITIVE_EVENTS = {"like", "purchase"}

# 재진단 안내: 최근 긍정 반응 REDIAG_WINDOW개 중 1위 타입이 피해야 할 옷이 REDIAG_RATIO 이상이면 안내
REDIAG_WINDOW = 20
REDIAG_RATIO = 0.5
REDIAG_MIN_EVENTS = 10  # 긍정 반응이 이보다 적으면 판단하지 않음 (찜 1~2개로 안내가 뜨는 것 방지)
REDIAG_MESSAGE = "최근 고른 옷이 진단 결과와 많이 달라요. 체형을 다시 진단해 볼까요?"

# ── 7단계: API ───────────────────────────────────────────────
SEASON_BY_MONTH = {12: "winter", 1: "winter", 2: "winter",
                   3: "spring", 4: "spring", 5: "spring",
                   6: "summer", 7: "summer", 8: "summer",
                   9: "fall", 10: "fall", 11: "fall"}
