"""C 파트: 추천 피드.

최종 점수 = 체형 적합도 0.60 + 취향 0.25 + 시즌·인기 0.15
(비중은 rec_config.py에서 관리)

실행: python feed.py  → 스트레이트 사용자 기준 점수표 출력
"""
import json
import os

from rec_config import (
    W_BODY, W_PREF, W_TREND, W_SEASON, W_POPULARITY, PREF_DEFAULT,
    TOP_N, MAX_SAME_CATEGORY_RUN, MAX_SAME_REP_TAG,
    CATEGORY_TOP_N, CATEGORY_TITLES,
    OUTFIT_TOP_N, OUTFIT_BONUS, OUTFIT_RULES,
    REASON_TEXT, REASON_MAX_TAGS, REASON_FALLBACK, REASON_EXCLUDED,
    EVENT_WEIGHTS, POSITIVE_EVENTS, STYLE_TAGS,
    REDIAG_WINDOW, REDIAG_RATIO, REDIAG_MIN_EVENTS,
    SCROLL_PAGE_SIZE,
)
# B 팀원 코드가 오면 이 한 줄만 `from matching import match_score`로 바꾼다
from fake_matching import match_score

DATA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "items.json")


def load_items(path=DATA_PATH):
    with open(path, encoding="utf-8") as f:
        return json.load(f)["items"]


def pref_score(pref, tags):
    """취향 점수 0~1.

    pref: {태그: -1~1} 사용자 반응으로 학습된 태그 선호도. 없으면 콜드 스타트(0.5).
    아이템 태그 중 pref에 있는 것들의 평균을 0~1로 옮긴다.
    """
    if not pref:
        return PREF_DEFAULT
    known = [pref[t] for t in tags if t in pref]
    if not known:
        return PREF_DEFAULT
    avg = sum(known) / len(known)
    return min(1.0, max(0.0, 0.5 + avg / 2))


def trend_score(item, season):
    """시즌·인기 점수 0~1. 지금 계절에 맞으면 1, 아니면 0 + 인기도."""
    season_match = 1.0 if season in item["seasons"] else 0.0
    return W_SEASON * season_match + W_POPULARITY * item["popularity"]


def final_score(body, item, pref=None, season="fall"):
    """옷 하나의 최종 점수.

    body: A 파트 출력 {"ratio": {...}, "kind": "single"|"mixed", "primary": "S"}
    item: items.json의 상품 하나
    pref: {태그: -1~1} 또는 None
    season: "spring" | "summer" | "fall" | "winter"
    반환: {"id", "name", "category", "score", "body", "pref", "trend",
           "excluded", "good_tags", "avoid_tags"}
    제외된 옷은 score가 0.0이고 excluded가 True다.
    """
    match = match_score(body, item)
    b = match["score"]
    p = pref_score(pref, item["tags"])
    t = trend_score(item, season)
    score = 0.0 if match["excluded"] else W_BODY * b + W_PREF * p + W_TREND * t

    return {
        "id": item["id"],
        "name": item["name"],
        "category": item["category"],
        "score": round(score, 4),
        "body": round(b, 4),
        "pref": round(p, 4),
        "trend": round(t, 4),
        "excluded": match["excluded"],
        "good_tags": match["good_tags"],
        "avoid_tags": match["avoid_tags"],
    }


def score_all(body, items, pref=None, season="fall"):
    """모든 옷의 최종 점수 목록 (정렬 안 함 — 정렬은 3단계 rank()에서)."""
    return [final_score(body, item, pref, season) for item in items]


def _by_score(scored):
    """제외된 옷을 빼고 score 내림차순, 점수가 같으면 id 오름차순."""
    kept = [r for r in scored if not r["excluded"]]
    return sorted(kept, key=lambda r: (-r["score"], r["id"]))


def _rep_tag(r):
    """대표 태그 = good_tags 첫 번째. 없으면 None(개수 제한 없음)."""
    return r["good_tags"][0] if r["good_tags"] else None


def _pick_in_order(scored, limit, block):
    """rank·feed_order 공통: 다양성 규칙을 지키며 점수 높은 옷부터 하나씩 고른다.

    block: 대표 태그 개수를 세는 묶음 크기. 이 개수만큼 고를 때마다 태그 개수를 다시 0부터 센다.
    limit: 최대 몇 개를 고를지. None이면 끝까지.
    태그 규칙을 지키는 옷이 없을 때: block이 limit 이상(rank)이면 멈추고, 아니면(스크롤) 태그 규칙도 포기.
    """
    candidates = _by_score(scored)
    result = []
    tag_count = {}

    def tag_ok(r):
        tag = _rep_tag(r)
        return tag is None or tag_count.get(tag, 0) < MAX_SAME_REP_TAG

    def category_ok(r):
        recent = result[-MAX_SAME_CATEGORY_RUN:]
        return not (len(recent) == MAX_SAME_CATEGORY_RUN
                    and all(x["category"] == r["category"] for x in recent))

    while candidates and (limit is None or len(result) < limit):
        if result and len(result) % block == 0:
            tag_count = {}  # 새 묶음 시작
        allowed = [r for r in candidates if tag_ok(r)]
        if not allowed:
            if limit is not None and block >= limit:
                break  # rank: 남은 옷이 모두 대표 태그 제한에 걸림
            allowed = candidates  # 스크롤: 뒤로 미룰 곳이 없으면 그냥 보여 줌
        # 두 규칙을 모두 지키는 옷이 없으면 category 규칙만 포기
        pick = next((r for r in allowed if category_ok(r)), allowed[0])
        result.append(pick)
        candidates.remove(pick)
        tag = _rep_tag(pick)
        if tag is not None:
            tag_count[tag] = tag_count.get(tag, 0) + 1

    return result


def rank(scored, top_n=TOP_N):
    """정렬 + 다양성 규칙을 적용한 상위 top_n개.

    scored: score_all() 결과
    규칙 1) 같은 category는 연속 최대 MAX_SAME_CATEGORY_RUN(2)개.
            바꿀 후보가 없으면 규칙을 지키지 않고 그대로 둔다.
    규칙 2) 같은 대표 태그는 최대 MAX_SAME_REP_TAG(3)개. 넘는 옷은 상위권에서 뺀다.
    방법: 점수순 후보 목록에서, 두 규칙을 지키는 가장 높은 점수의 옷을 하나씩 고른다.
    """
    return _pick_in_order(scored, limit=top_n, block=top_n)


def feed_order(scored, page_size=SCROLL_PAGE_SIZE):
    """스크롤 피드용 전체 순서. 제외 안 된 옷이 전부 한 번씩 나온다.

    rank와 같은 규칙을 page_size개 묶음마다 적용한다.
    (같은 category 연속 최대 2개는 전체에 걸쳐, 대표 태그 최대 3개는 묶음마다)
    첫 묶음은 rank(scored, page_size)와 같다 → 홈 첫 화면 = "오늘의 추천".
    태그 제한 때문에 밀린 옷은 버리지 않고 다음 묶음으로 넘어간다.
    """
    return _pick_in_order(scored, limit=None, block=page_size)


def home_feed(body, items, pref=None, season="fall"):
    """홈 화면 섹션.

    순서: "오늘의 추천"(rank 상위 10) → 상의·하의·아우터·원피스(각 상위 4) → "추천 코디"
    "추천 코디"의 items는 옷이 아니라 outfits()의 코디 세트({"top", "bottom", "score", "bonus"})다.
    반환: {"sections": [{"title": str, "items": [...]}, ...]}
    """
    scored = score_all(body, items, pref, season)
    sections = [{"title": "오늘의 추천", "items": rank(scored)}]

    ordered = _by_score(scored)
    for category, title in CATEGORY_TITLES.items():
        picked = [r for r in ordered if r["category"] == category][:CATEGORY_TOP_N]
        sections.append({"title": title, "items": picked})

    sections.append({"title": "추천 코디", "items": outfits(body, items, pref, season)})
    return {"sections": sections}


def outfits(body, items, pref=None, season="fall", top_n=OUTFIT_TOP_N):
    """상의 + 하의 코디 추천 상위 top_n세트.

    점수 = (상의 점수 + 하의 점수) / 2 + 보너스
    보너스: 1위 타입의 궁합 규칙(OUTFIT_RULES)을 상의·하의가 둘 다 만족하면 +0.10
            예) 웨이브: 크롭 상의 + 하이웨이스트 하의
    같은 상의는 결과에 한 번만 나온다. 동점이면 (상의 id, 하의 id) 순.
    반환: [{"top": 상의 결과, "bottom": 하의 결과, "score": float, "bonus": float}, ...]
    """
    ordered = _by_score(score_all(body, items, pref, season))
    tops = [r for r in ordered if r["category"] == "top"]
    bottoms = [r for r in ordered if r["category"] == "bottom"]
    top_rule, bottom_rule = OUTFIT_RULES[body["primary"]]

    combos = []
    for t in tops:
        for b in bottoms:
            ok = top_rule & set(t["good_tags"]) and bottom_rule & set(b["good_tags"])
            bonus = OUTFIT_BONUS if ok else 0.0
            score = (t["score"] + b["score"]) / 2 + bonus
            combos.append({"top": t, "bottom": b, "score": round(score, 4), "bonus": bonus})
    combos.sort(key=lambda c: (-c["score"], c["top"]["id"], c["bottom"]["id"]))

    result, used_tops = [], set()
    for c in combos:
        if c["top"]["id"] in used_tops:
            continue
        result.append(c)
        used_tops.add(c["top"]["id"])
        if len(result) == top_n:
            break
    return result


def reason(r):
    """추천 이유 한 문장. r은 final_score() 결과.

    good_tags 앞에서 REASON_MAX_TAGS(2)개를 이어 붙인다.
    예) ["collar", "slim_fit"] → "칼라가 목선을 세워 주고, 몸에 맞는 핏이 라인을 정돈해 줘요."
    """
    if r["excluded"]:
        return REASON_EXCLUDED
    tags = [t for t in r["good_tags"] if t in REASON_TEXT][:REASON_MAX_TAGS]
    if not tags:
        return REASON_FALLBACK
    middle = [REASON_TEXT[t][0] for t in tags[:-1]]
    last = REASON_TEXT[tags[-1]][1]
    return ", ".join(middle + [last]) + "."


def update_pref(pref, item, event):
    """사용자 반응 하나로 태그 선호도를 고친 새 dict를 돌려준다 (원본은 그대로).

    item의 태그마다 click +0.05 / like +0.10 / purchase +0.20 / return -0.20, 결과는 -1~1.
    """
    if event not in EVENT_WEIGHTS:
        raise ValueError(f"알 수 없는 반응: {event} (가능: {', '.join(EVENT_WEIGHTS)})")
    new = dict(pref or {})
    for tag in item["tags"]:
        value = new.get(tag, 0.0) + EVENT_WEIGHTS[event]
        new[tag] = round(min(1.0, max(-1.0, value)), 4)
    return new


def need_rediagnosis(history, body):
    """반응이 진단 결과와 계속 어긋나면 True → 체형 재진단 안내.

    history: [{"item": 상품, "event": "like"}, ...] (오래된 것 → 최근 순)
    최근 긍정 반응(like·purchase) 20개 중 1위 타입이 피해야 할 태그가 붙은 옷이 50% 이상이면 True.
    긍정 반응이 10개 미만이면 판단하지 않고 False.
    """
    positive = [h["item"] for h in history if h["event"] in POSITIVE_EVENTS][-REDIAG_WINDOW:]
    if len(positive) < REDIAG_MIN_EVENTS:
        return False
    avoid = STYLE_TAGS[body["primary"]]["avoid"]
    mismatched = sum(1 for item in positive if avoid & set(item["tags"]))
    return mismatched / len(positive) >= REDIAG_RATIO


if __name__ == "__main__":
    straight = {"ratio": {"S": 0.8, "W": 0.1, "N": 0.1}, "kind": "single", "primary": "S"}
    results = score_all(straight, load_items())
    results.sort(key=lambda r: r["score"], reverse=True)

    print("스트레이트 사용자 (S 0.8 / W 0.1 / N 0.1, 단일형, 가을)")
    print(f"{'상품':<16}{'최종':>7}{'체형':>7}{'취향':>7}{'트렌드':>7}")
    for r in results:
        if r["excluded"]:
            print(f"{r['name']:<16}{'제외':>7}   ← 피해야 함: {', '.join(r['avoid_tags'])}")
        else:
            print(f"{r['name']:<16}{r['score']:>7.3f}{r['body']:>7.3f}{r['pref']:>7.3f}{r['trend']:>7.3f}")

    print("\n── 홈 화면 ──")
    for section in home_feed(straight, load_items())["sections"]:
        if section["title"] == "추천 코디":
            names = " / ".join(f"{c['top']['name']} + {c['bottom']['name']} ({c['score']:.3f})"
                               for c in section["items"])
        else:
            names = ", ".join(r["name"] for r in section["items"])
        print(f"[{section['title']}] {names}")

    print("\n── 추천 이유 ──")
    for r in rank(results)[:3]:
        print(f"{r['name']}: {reason(r)}")
