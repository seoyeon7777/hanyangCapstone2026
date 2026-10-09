"""C 파트 정답 테스트.

실행: python test_feed.py   (pytest가 있으면 pytest test_feed.py 도 가능)
정답값은 모두 손으로 계산한 값이다. 계산 과정은 각 테스트 주석 참고.
AI가 코드를 고친 뒤 이 테스트가 하나라도 깨지면 다음 단계로 넘어가지 않는다.
"""
from rec_config import W_BODY, W_PREF, W_TREND
from fake_matching import classify_kind, match_score
from feed import load_items, final_score, score_all, rank, home_feed

ITEMS = {item["id"]: item for item in load_items()}
STRAIGHT = {"ratio": {"S": 1.0, "W": 0.0, "N": 0.0}, "kind": "single", "primary": "S"}
MIXED = {"ratio": {"S": 0.5, "W": 0.45, "N": 0.05}, "kind": "mixed", "primary": "S"}


def close(a, b, tol=1e-3):
    return abs(a - b) < tol


def test_items_count():
    cats = [i["category"] for i in ITEMS.values()]
    assert len(ITEMS) == 30
    assert (cats.count("top"), cats.count("bottom"),
            cats.count("outer"), cats.count("dress")) == (12, 8, 6, 4)


def test_weights_sum_to_one():
    assert close(W_BODY + W_PREF + W_TREND, 1.0, 1e-9)


def test_classify_kind():
    assert classify_kind({"S": 0.7, "W": 0.2, "N": 0.1}) == ("single", "S")
    assert classify_kind({"S": 0.4, "W": 0.35, "N": 0.25}) == ("mixed", "S")
    # 경계값: 격차가 정확히 10%p면 단일형
    assert classify_kind({"W": 0.45, "S": 0.35, "N": 0.2}) == ("single", "W")


def test_collar_shirt_straight():
    # 태그 collar·slim_fit·firm_fabric 모두 S 어울림 → +6
    # 체형 0.5 + 6/16 = 0.875 / 취향 0.5(콜드 스타트)
    # 트렌드 가을 시즌 1.0*0.5 + 인기 0.8*0.5 = 0.9
    # 최종 0.6*0.875 + 0.25*0.5 + 0.15*0.9 = 0.785
    r = final_score(STRAIGHT, ITEMS["t01"], season="fall")
    assert not r["excluded"]
    assert close(r["body"], 0.875)
    assert close(r["trend"], 0.9)
    assert close(r["score"], 0.785)


def test_ruffle_excluded_for_single_straight():
    # 단일형 스트레이트에게 ruffle은 피해야 할 태그 → 추천에서 제외
    r = final_score(STRAIGHT, ITEMS["t06"])
    assert r["excluded"]
    assert r["score"] == 0.0
    assert r["avoid_tags"] == ["ruffle"]


def test_ruffle_penalized_not_excluded_for_mixed():
    # 혼합형은 빼지 않고 점수만 깎음
    # S: ruffle -3 / W: ruffle +2, soft_fabric +2 = +4 / N: 0
    # 가중합 0.5*(-3) + 0.45*4 = 0.3 → 체형 0.5 + 0.3/16 = 0.51875
    # 트렌드: 봄·여름 상품이라 가을엔 0 + 인기 0.6*0.5 = 0.3
    # 최종 0.6*0.51875 + 0.125 + 0.15*0.3 = 0.48125
    r = final_score(MIXED, ITEMS["t06"], season="fall")
    assert not r["excluded"]
    assert close(r["body"], 0.51875)
    assert close(r["score"], 0.48125)


def test_preference_raises_score():
    # collar 선호 1.0 → 취향 1.0 → 최종 0.525 + 0.25 + 0.135 = 0.91
    r = final_score(STRAIGHT, ITEMS["t01"], pref={"collar": 1.0}, season="fall")
    assert close(r["pref"], 1.0)
    assert close(r["score"], 0.91)


def test_straight_style_guide_order():
    # 스타일 가이드 검증: 스트레이트 상위권에 칼라 셔츠·센터프레스 슬랙스·H라인 스커트
    results = sorted(score_all(STRAIGHT, ITEMS.values()), key=lambda r: r["score"], reverse=True)
    top_ids = [r["id"] for r in results[:8]]
    for must in ("t01", "b02", "b01"):
        assert must in top_ids
    excluded = {r["id"] for r in results if r["excluded"]}
    assert {"t06", "t08", "t09", "t12", "o04", "o06"} <= excluded


def test_body_score_bounds():
    for body in (STRAIGHT, MIXED):
        for item in ITEMS.values():
            s = match_score(body, item)["score"]
            assert 0.0 <= s <= 1.0


# ── 3단계: rank ─────────────────────────────────────────────
def fake(id_, score, category="top", tag=None, excluded=False):
    """rank 테스트용 점수 결과 하나 (final_score 출력 모양)."""
    return {"id": id_, "name": id_, "category": category, "score": score,
            "body": 0, "pref": 0, "trend": 0, "excluded": excluded,
            "good_tags": [tag] if tag else [], "avoid_tags": []}


def ids(results):
    return [r["id"] for r in results]


def test_rank_sorts_and_drops_excluded():
    scored = [fake("a", 0.5), fake("b", 0.9, "bottom"), fake("x", 0.99, excluded=True)]
    assert ids(rank(scored)) == ["b", "a"]


def test_rank_tie_breaks_by_id():
    # 점수가 같으면 id 오름차순 → 매번 같은 결과
    scored = [fake("b", 0.7, "bottom"), fake("a", 0.7, "outer")]
    assert ids(rank(scored)) == ["a", "b"]


def test_rank_no_three_same_category_in_a_row():
    # 점수순은 a b c(상의 3개) d(하의) → 상의 3연속이 되므로 c 앞에 d를 끼움
    scored = [fake("a", 0.9), fake("b", 0.8), fake("c", 0.7), fake("d", 0.6, "bottom")]
    assert ids(rank(scored)) == ["a", "b", "d", "c"]


def test_rank_keeps_order_when_no_swap_candidate():
    # 전부 상의라 바꿀 후보가 없음 → 점수순 그대로
    scored = [fake("a", 0.9), fake("b", 0.8), fake("c", 0.7)]
    assert ids(rank(scored)) == ["a", "b", "c"]


def test_rank_rep_tag_max_three():
    # collar 대표 태그 5개(상의·하의 번갈아) + 다른 태그 1개
    # collar는 3개까지만 → c4, c5는 상위권에서 빠지고 z가 들어옴
    cats = ["top", "bottom", "top", "bottom", "top"]
    scored = [fake(f"c{i + 1}", 0.9 - i * 0.1, cats[i], "collar") for i in range(5)]
    scored.append(fake("z", 0.1, "bottom", "wide"))
    assert ids(rank(scored)) == ["c1", "c2", "c3", "z"]


def test_rank_top_n():
    scored = [fake(f"i{n:02d}", 1 - n / 100, ["top", "bottom", "outer"][n % 3]) for n in range(20)]
    assert len(rank(scored)) == 10
    assert len(rank(scored, top_n=5)) == 5


def test_rank_real_items_rules():
    # 실제 상품으로 규칙 확인: 제외 없음, 같은 category 3연속 없음, 대표 태그 3개 이하
    for body in (STRAIGHT, MIXED):
        top = rank(score_all(body, ITEMS.values()))
        assert len(top) == 10
        assert not any(r["excluded"] for r in top)
        cats = [r["category"] for r in top]
        assert not any(cats[i] == cats[i + 1] == cats[i + 2] for i in range(len(cats) - 2))
        reps = [r["good_tags"][0] for r in top if r["good_tags"]]
        assert all(reps.count(t) <= 3 for t in reps)


# ── 4단계: home_feed ────────────────────────────────────────
def test_home_feed_sections():
    feed = home_feed(STRAIGHT, list(ITEMS.values()))
    titles = [s["title"] for s in feed["sections"]]
    assert titles == ["오늘의 추천", "상의", "하의", "아우터", "원피스", "추천 코디"]
    today = feed["sections"][0]["items"]
    assert ids(today) == ids(rank(score_all(STRAIGHT, ITEMS.values())))
    assert feed["sections"][-1]["items"] == []  # 5단계에서 채움


def test_home_feed_category_sections():
    feed = home_feed(MIXED, list(ITEMS.values()))
    for section, cat in zip(feed["sections"][1:5], ("top", "bottom", "outer", "dress")):
        items = section["items"]
        assert len(items) == 4
        assert all(r["category"] == cat and not r["excluded"] for r in items)
        scores = [r["score"] for r in items]
        assert scores == sorted(scores, reverse=True)


def test_home_feed_straight_tops():
    # 스트레이트(S 1.0) 상의, 가을 — 손계산
    # t01 칼라 셔츠      +6 → 체형 0.875, 트렌드 0.9   → 0.525 + 0.125 + 0.135  = 0.785
    # t02 세로 절개 셔츠  +6 → 체형 0.875, 트렌드 0.8   → 0.525 + 0.125 + 0.12   = 0.77
    # t03 라운드넥 니트   +4 → 체형 0.75,  트렌드 0.85  → 0.45  + 0.125 + 0.1275 = 0.7025
    # t04 크롭 니트      +2 → 체형 0.625, 트렌드 0.875 → 0.375 + 0.125 + 0.13125 = 0.63125
    # 나머지 상의는 0점 태그(체형 0.5)거나 제외 → 상위 4개 = t01, t02, t03, t04
    tops = home_feed(STRAIGHT, list(ITEMS.values()))["sections"][1]["items"]
    assert ids(tops) == ["t01", "t02", "t03", "t04"]
    assert close(tops[1]["score"], 0.77)
    assert close(tops[2]["score"], 0.7025)
    assert close(tops[3]["score"], 0.63125)


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError:
            failed += 1
            print(f"  FAIL  {name}")
        except Exception as e:  # 코드 오류도 실패로 세고 다음 테스트를 계속 돌림
            failed += 1
            print(f"  ERROR {name}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} 통과")
    raise SystemExit(1 if failed else 0)
