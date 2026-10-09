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


def rank(scored, top_n=TOP_N):
    """정렬 + 다양성 규칙을 적용한 상위 top_n개.

    scored: score_all() 결과
    규칙 1) 같은 category는 연속 최대 MAX_SAME_CATEGORY_RUN(2)개.
            바꿀 후보가 없으면 규칙을 지키지 않고 그대로 둔다.
    규칙 2) 같은 대표 태그는 최대 MAX_SAME_REP_TAG(3)개. 넘는 옷은 상위권에서 뺀다.
    방법: 점수순 후보 목록에서, 두 규칙을 지키는 가장 높은 점수의 옷을 하나씩 고른다.
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

    while candidates and len(result) < top_n:
        allowed = [r for r in candidates if tag_ok(r)]
        if not allowed:
            break  # 남은 옷이 모두 대표 태그 제한에 걸림
        # 두 규칙을 모두 지키는 옷이 없으면 category 규칙만 포기
        pick = next((r for r in allowed if category_ok(r)), allowed[0])
        result.append(pick)
        candidates.remove(pick)
        tag = _rep_tag(pick)
        if tag is not None:
            tag_count[tag] = tag_count.get(tag, 0) + 1

    return result


def home_feed(body, items, pref=None, season="fall"):
    """홈 화면 섹션.

    순서: "오늘의 추천"(rank 상위 10) → 상의·하의·아우터·원피스(각 상위 4) → "추천 코디"
    "추천 코디"는 5단계 outfits()가 생기면 채운다. 지금은 빈 목록.
    반환: {"sections": [{"title": str, "items": [...]}, ...]}
    """
    scored = score_all(body, items, pref, season)
    sections = [{"title": "오늘의 추천", "items": rank(scored)}]

    ordered = _by_score(scored)
    for category, title in CATEGORY_TITLES.items():
        picked = [r for r in ordered if r["category"] == category][:CATEGORY_TOP_N]
        sections.append({"title": title, "items": picked})

    sections.append({"title": "추천 코디", "items": []})
    return {"sections": sections}


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
        names = ", ".join(r["name"] for r in section["items"]) or "(5단계에서 채움)"
        print(f"[{section['title']}] {names}")
