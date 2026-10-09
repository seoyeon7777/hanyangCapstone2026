# CLAUDE.md — 한양대 캡스톤 2026 (가상 피팅 + 골격 맞춤 추천)

AI 코딩 도구가 이 파일만 읽고 작업을 이어갈 수 있게 정리한 문서다.
작업을 시작하기 전에 끝까지 읽고, 단계를 끝낼 때마다 **9. 진행 체크리스트**를 갱신한다.

## 1. 프로젝트 한눈에 보기

사용자가 키·몸무게·설문을 입력하면 두 가지를 해 준다.

1. **가상 피팅** (이미 구현됨): 옷 치수·소재를 받아 Blender로 S/M/L 아바타에 입혀 보고 실루엣 이미지와 총평을 보여 준다.
2. **골격 맞춤 추천** (지금 만드는 중): 사용자의 골격(스트레이트 S / 웨이브 W / 내추럴 N)에 맞는 옷을 점수로 골라 피드로 보여 준다.

## 2. 폴더 구조

```
app.py                  Flask 서버 (가상 피팅 API). 추천 API도 7단계에서 여기에 붙인다
models/fitting_model.py 아바타 매칭, shape key 계산, 압박도 계산
services/blender_runner.py  Blender 실행 (blender/config.py를 `from config import`로 읽음)
blender/                Blender 스크립트
templates/, static/     화면
recommend/              ★ C 파트 (추천 피드) — 이 폴더에서 작업
  rec_config.py         비중·태그 표 등 숫자 모음. 숫자는 여기서만 바꾼다
  fake_matching.py      B 파트가 오기 전 임시 매칭 함수 (match_score, classify_kind)
  feed.py               C 파트 본체 (final_score, score_all, rank, home_feed, …)
  test_feed.py          정답 테스트
  data/items.json       시연용 가짜 상품 30개
```

주의: `.gitignore`에 `config.py`가 있어서 그 이름의 새 파일은 커밋되지 않는다. 그래서 추천 설정 파일 이름은 `rec_config.py`다. 이름을 `config.py`로 바꾸지 말 것(blender/config.py와도 import가 겹친다).

## 3. 팀 약속 (함수 모양 — 바꾸지 말 것)

전체 흐름: 입력 → ① 체형 분류(A) → ② 옷 속성 태그 → ③ 체형 적합도(B) → ④ 최종 순위(C) → ⑤ 코디 조합(C) → ⑥ 추천 이유·학습(C)

### A 파트 출력 = body (체형 분류 결과)
```python
body = {
    "ratio":   {"S": 0.62, "W": 0.25, "N": 0.13},  # 합 1.0
    "kind":    "single",                            # 1·2위 격차 ≥ 0.10 → single, 아니면 mixed
    "primary": "S",                                 # 1위 타입
}
```
A 파트 계산 규칙 (참고): 아바타 점수표는 타입마다 최대점이 다르다(S 7 / W 9 / N 6).
원점수를 그대로 합치면 W가 항상 유리하므로, **타입별 최대점으로 나눈 뒤 세 타입 합이 1이 되게 비율로 바꾸고**,
그다음 `설문 비율 0.6 + 아바타 비율 0.4`로 합친다. 그래야 격차 10%p 규칙이 맞게 계산된다.

### B 파트 함수 = match_score(body, item)
```python
match_score(body, item) -> {
    "score": 0.0~1.0,        # 체형 적합도
    "excluded": bool,        # 단일형 + 1위 타입 피해야 할 태그 있음 → True
    "good_tags": [...],      # 1위 타입 기준 어울림 태그
    "avoid_tags": [...],     # 1위 타입 기준 피해야 함 태그
}
```
지금은 `recommend/fake_matching.py`의 임시 구현을 쓴다. B 코드가 오면 `feed.py`의 import 한 줄만 바꾼다.

### item (상품) 형식
```json
{"id": "t01", "name": "칼라 셔츠", "category": "top|bottom|outer|dress",
 "tags": ["collar", "slim_fit", "firm_fabric"],
 "seasons": ["spring", "fall"], "popularity": 0.8}
```

## 4. C 파트 알고리즘 명세

### 4-1. 체형 적합도 (임시, B 파트 몫)
- 태그 점수: 골격별로 어울림 태그 +2, 피해야 함 태그 −3 (`rec_config.STYLE_TAGS`)
- 가중합 = Σ ratio[t] × 태그점수[t]
- body = clamp(0.5 + 가중합 / 16, 0, 1)
- 단일형이면 1위 타입의 피해야 함 태그가 하나라도 있는 옷은 **제외**. 혼합형이면 제외하지 않고 가중합으로 점수만 깎인다.

### 4-2. 최종 점수 `final_score` (2단계, 완료)
- 최종 = 0.60 × 체형 + 0.25 × 취향 + 0.15 × 트렌드
- 취향 = 아이템 태그 중 pref(태그→−1~1)에 있는 값들의 평균을 0.5 + 평균/2로 변환. 기록이 없으면 0.5
- 트렌드 = 0.5 × (지금 계절이면 1 아니면 0) + 0.5 × popularity
- 제외된 옷은 score 0.0, excluded True

### 4-3. 정렬 + 다양성 `rank(scored, top_n=10)` (3단계, 완료)
- 입력은 score_all() 결과, 반환은 상위 top_n개 목록
- 제외된 옷을 빼고 score 내림차순
- 같은 category가 3개 연속으로 나오지 않게 한다 (연속 최대 2개). 바꿀 후보가 없으면 그대로 둔다
- 상위 top_n 안에서 같은 대표 태그(good_tags 첫 번째)는 최대 3개. 넘는 옷은 상위권에서 빠진다. good_tags가 비면 제한 없음
- 방법: 점수순 후보에서 두 규칙을 지키는 가장 높은 옷을 하나씩 고른다. 둘 다 지키는 옷이 없으면 category 규칙만 포기
- 점수가 같으면 id 오름차순 (결과가 항상 같아야 테스트할 수 있다)

### 4-4. 홈 섹션 `home_feed(body, items, pref=None, season="fall")` (4단계, 완료)
- 섹션 순서: "오늘의 추천" → "상의" → "하의" → "아우터" → "원피스" → "추천 코디"
- "오늘의 추천": rank 상위 10개
- 카테고리별 상위 4개: 제외 빼고 점수순(다양성 규칙 없음)
- "추천 코디": 5단계 outfits 상위 3세트. **5단계 전까지는 빈 목록** — 5단계에서 채우고 test_home_feed_sections의 빈 목록 검사를 바꾼다
- 반환: `{"sections": [{"title": str, "items": [...]}, ...]}`

### 4-5. 코디 조합 `outfits(body, items, ...)` (5단계)
- 제외되지 않은 상의 × 하의 모든 조합. 점수 = (상의 + 하의) / 2 + 보너스
- 보너스 +0.10 (1위 타입 기준, 둘 다 만족할 때):
  - S: 상의 collar 또는 slim_fit + 하의 straight_leg·center_press·h_line 중 하나
  - W: 상의 cropped + 하의 high_waist
  - N: 상의 oversized·boxy·loose_fit 중 하나 + 하의 wide
- 같은 상의는 결과에 최대 1번만

### 4-6. 추천 이유 + 피드백 학습 (6단계)
- `reason(r)`: good_tags를 한국어 문장으로. 예: "칼라가 목선을 세워 주고, 몸에 맞는 핏이 직선 실루엣을 살려 줘요." (태그→문장 표는 rec_config에)
- `update_pref(pref, item, event)`: 아이템 태그마다 click +0.05, like +0.10, purchase +0.20, return −0.20 더하고 −1~1로 자른다
- `need_rediagnosis(history, body)`: 최근 긍정 반응(like·purchase) 20개 중 1위 타입 피해야 함 태그가 붙은 옷이 50% 이상이면 True → "체형을 다시 진단해 볼까요?" 안내

### 4-7. API (7단계)
- `app.py`에 `GET/POST /api/feed` 추가: body·pref·season을 받아 home_feed 결과를 JSON으로
- `POST /api/feed/event`: 반응 기록 → update_pref

## 5. 정답 테스트 (반드시 통과)

`cd recommend && python test_feed.py` — 현재 19개 통과.

| 테스트 | 정답 |
|---|---|
| 스트레이트(S 1.0, 단일형) 칼라 셔츠, 가을 | 체형 0.875, 트렌드 0.9, 최종 **0.785** |
| 스트레이트 단일형 러플 블라우스 | **제외** (avoid_tags = ["ruffle"]) |
| 혼합형(S 0.5/W 0.45/N 0.05) 러플 블라우스, 가을 | 제외 안 됨, 체형 0.51875, 최종 **0.48125** |
| 칼라 셔츠 + pref {"collar": 1.0} | 최종 **0.91** |
| 스트레이트 상위 8개 | 칼라 셔츠·센터프레스 슬랙스·H라인 스커트 포함 |
| rank: 상의 a·b·c + 하의 d | a, b, **d**, c (상의 3연속 방지) |
| rank: collar 대표 태그 5개 + 다른 1개 | collar 3개 + 다른 1개만 |
| 스트레이트(S 1.0) 홈 "상의" 섹션 | t01 0.785, t02 0.77, t03 0.7025, t04 0.63125 |

새 단계를 만들면 그 단계의 정답 테스트를 손으로 계산해 `test_feed.py`에 추가한다. 기존 정답값은 고치지 않는다(사람이 명시적으로 요청한 경우만 예외).

## 6. 코딩 규칙

- 한 번에 한 단계만 만든다. 끝나면 `python test_feed.py` 통과를 확인한다
- 3장 함수 모양(이름·입력·출력 키)은 바꾸지 않는다
- 숫자(비중·보너스·임계값)는 `rec_config.py`에만 둔다
- 외부 라이브러리 없이 파이썬 표준 라이브러리만 쓴다 (Flask는 7단계 API에서만)
- 주석과 출력 메시지는 한국어
- 가상 피팅 코드(app.py의 기존 라우트, models/, services/, blender/)는 건드리지 않는다

## 7. 임시값 (나중에 다시 맞출 것)

치수 구간 기준, 비중 0.60/0.25/0.15, 태그 점수 +2/−3, BODY_SCALE 8, 코디 보너스 0.10, 학습 가중치는 모두 임시값이다.
실제 아바타·사용자 데이터를 모은 뒤 조정한다. 스타일 가이드는 통용 이론 기반이라 전문가 감수가 필요하다.

## 8. 발표 대비 핵심 함수

`final_score`(최종 점수), `rank`(정렬·다양성), `home_feed`(홈 구성) 세 개는 사람이 직접 설명할 수 있어야 한다.

## 9. 진행 체크리스트

- [x] 1단계: 가짜 상품 30개, rec_config.py, fake_matching.py
- [x] 2단계: final_score, score_all + 정답 테스트 9개
- [x] 3단계: rank (정렬 + 다양성) + 테스트 7개
- [x] 4단계: home_feed (홈 섹션, "추천 코디"는 5단계에서 채움) + 테스트 3개
- [ ] 5단계: outfits (코디 조합)
- [ ] 6단계: reason, update_pref, need_rediagnosis
- [ ] 7단계: Flask API (/api/feed)
- [ ] B 파트 match_score로 교체
