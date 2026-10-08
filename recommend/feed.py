"""C 파트: 추천 피드.

최종 점수 = 체형 적합도 0.60 + 취향 0.25 + 시즌·인기 0.15
(비중은 rec_config.py에서 관리)

실행: python feed.py  → 스트레이트 사용자 기준 점수표 출력
"""
import json
import os

from rec_config import (
    W_BODY, W_PREF, W_TREND, W_SEASON, W_POPULARITY, PREF_DEFAULT,
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
