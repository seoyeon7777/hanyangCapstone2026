"""B 파트(체형-옷 매칭) 코드가 오기 전까지 쓰는 임시 구현.

B 팀원 코드가 오면 feed.py의 import 한 줄만 바꾸면 된다.
    from fake_matching import match_score   →   from matching import match_score
함수 이름·입력·출력 모양은 CLAUDE.md "3. 팀 약속"을 따른다. 바꾸지 말 것.
"""
from rec_config import (
    STYLE_TAGS, TAG_GOOD, TAG_AVOID, BODY_SCALE, SINGLE_TYPE_GAP,
)


def classify_kind(ratio):
    """S·W·N 비율로 단일형/혼합형과 1위 타입을 정한다. (A 파트 출력 형식 확인용)

    ratio: {"S": 0.7, "W": 0.2, "N": 0.1}  (합 1.0)
    반환: ("single" 또는 "mixed", 1위 타입)
    """
    ranked = sorted(ratio.items(), key=lambda kv: kv[1], reverse=True)
    primary = ranked[0][0]
    gap = ranked[0][1] - ranked[1][1]
    # 부동소수 오차로 0.1이 0.0999…가 되는 것을 막기 위해 반올림
    kind = "single" if round(gap, 6) >= SINGLE_TYPE_GAP else "mixed"
    return kind, primary


def tag_score(body_type, tags):
    """한 골격 기준 태그 점수 합. 어울림 +2, 피해야 함 -3."""
    rule = STYLE_TAGS[body_type]
    score = 0
    for tag in tags:
        if tag in rule["good"]:
            score += TAG_GOOD
        elif tag in rule["avoid"]:
            score += TAG_AVOID
    return score


def match_score(body, item):
    """체형과 옷 하나의 적합도.

    body: {"ratio": {"S":..,"W":..,"N":..}, "kind": "single"|"mixed", "primary": "S"}
    item: items.json의 상품 하나 (tags 필수)
    반환: {"score": 0~1, "excluded": bool, "good_tags": [...], "avoid_tags": [...]}
    """
    tags = item["tags"]
    weighted = sum(r * tag_score(t, tags) for t, r in body["ratio"].items())
    score = min(1.0, max(0.0, 0.5 + weighted / (2 * BODY_SCALE)))

    rule = STYLE_TAGS[body["primary"]]
    good_tags = [t for t in tags if t in rule["good"]]
    avoid_tags = [t for t in tags if t in rule["avoid"]]

    # 단일형: 1위 타입이 피해야 할 태그가 하나라도 있으면 추천에서 제외
    # 혼합형: 제외하지 않고 위의 가중합에서 이미 점수가 깎임
    excluded = body["kind"] == "single" and len(avoid_tags) > 0

    return {
        "score": round(score, 4),
        "excluded": excluded,
        "good_tags": good_tags,
        "avoid_tags": avoid_tags,
    }
