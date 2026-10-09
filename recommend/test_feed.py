"""C 파트 정답 테스트.

실행: python test_feed.py   (pytest가 있으면 pytest test_feed.py 도 가능)
정답값은 모두 손으로 계산한 값이다. 계산 과정은 각 테스트 주석 참고.
AI가 코드를 고친 뒤 이 테스트가 하나라도 깨지면 다음 단계로 넘어가지 않는다.
"""
from rec_config import W_BODY, W_PREF, W_TREND
from fake_matching import classify_kind, match_score
from feed import (load_items, final_score, score_all, rank, home_feed,
                  outfits, reason, update_pref, need_rediagnosis, feed_order)

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
    looks = feed["sections"][-1]["items"]  # 추천 코디 = outfits 상위 3세트
    assert [(c["top"]["id"], c["bottom"]["id"]) for c in looks] == \
        [(c["top"]["id"], c["bottom"]["id"]) for c in outfits(STRAIGHT, list(ITEMS.values()))]


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


# ── 5단계: outfits ──────────────────────────────────────────
WAVE = {"ratio": {"S": 0.0, "W": 1.0, "N": 0.0}, "kind": "single", "primary": "W"}


def pairs(looks):
    return [(c["top"]["id"], c["bottom"]["id"]) for c in looks]


def test_outfits_straight():
    # 스트레이트(S 1.0), 가을 — 손계산
    # 하의 b02 센터프레스 슬랙스 +6 → 체형 0.875, 트렌드 0.875 → 0.525 + 0.125 + 0.13125 = 0.78125 (하의 1위)
    # t01 칼라 셔츠(0.785, collar) + b02(center_press) → 보너스 O
    #     (0.785 + 0.78125) / 2 + 0.10 = 0.883125
    # t02 세로 절개 셔츠(0.77, collar) + b02 → (0.77 + 0.78125) / 2 + 0.10 = 0.875625
    # t03 라운드넥 니트(0.7025, slim_fit) + b02 → (0.7025 + 0.78125) / 2 + 0.10 = 0.841875
    # 같은 상의는 한 번만 → 상위 3세트
    looks = outfits(STRAIGHT, list(ITEMS.values()))
    assert pairs(looks) == [("t01", "b02"), ("t02", "b02"), ("t03", "b02")]
    assert close(looks[0]["score"], 0.883125)
    assert close(looks[1]["score"], 0.875625)
    assert close(looks[2]["score"], 0.841875)
    assert all(c["bonus"] == 0.10 for c in looks)


def test_outfits_wave_cropped_high_waist():
    # 웨이브(W 1.0), 가을 — 크롭 상의 + 하이웨이스트 하의 보너스
    # t04 크롭 니트: cropped +2, soft_fabric +2 → 체형 0.75, 트렌드 0.875 → 0.45 + 0.125 + 0.13125 = 0.70625
    # b04 하이웨이스트 슬림 팬츠: high_waist +2, slim_fit +2 → 체형 0.75, 트렌드 0.85 → 0.7025
    # (0.70625 + 0.7025) / 2 + 0.10 = 0.804375 → 1위
    first = outfits(WAVE, list(ITEMS.values()))[0]
    assert (first["top"]["id"], first["bottom"]["id"]) == ("t04", "b04")
    assert first["bonus"] == 0.10
    assert close(first["score"], 0.804375)


def test_outfits_rules():
    for body in (STRAIGHT, MIXED, WAVE):
        looks = outfits(body, list(ITEMS.values()))
        assert len(looks) == 3
        tops = [c["top"]["id"] for c in looks]
        assert len(set(tops)) == 3  # 같은 상의 한 번만
        for c in looks:
            assert c["top"]["category"] == "top" and c["bottom"]["category"] == "bottom"
            assert not c["top"]["excluded"] and not c["bottom"]["excluded"]


# ── 6단계: reason, update_pref, need_rediagnosis ─────────────
def test_reason_sentence():
    r = final_score(STRAIGHT, ITEMS["t01"])  # good_tags: collar, slim_fit, firm_fabric
    assert reason(r) == "칼라가 목선을 세워 주고, 몸에 맞는 핏이 라인을 정돈해 줘요."


def test_reason_single_tag_and_fallback_and_excluded():
    one = fake("x", 0.5, tag="wide")
    assert reason(one) == "와이드 핏이 다리 라인을 편안하게 감싸요."
    assert reason(fake("y", 0.5)) == "지금 계절과 인기를 반영한 추천이에요."
    assert reason(final_score(STRAIGHT, ITEMS["t06"])) == "체형에 맞지 않는 디자인이 있어 추천에서 뺐어요."


def test_update_pref():
    shirt = ITEMS["t01"]  # collar, slim_fit, firm_fabric
    p = update_pref({}, shirt, "like")
    assert p == {"collar": 0.1, "slim_fit": 0.1, "firm_fabric": 0.1}
    p = update_pref(p, shirt, "purchase")          # 0.1 + 0.2 = 0.3
    p = update_pref(p, shirt, "return")            # 0.3 - 0.2 = 0.1
    p = update_pref(p, shirt, "click")             # 0.1 + 0.05 = 0.15
    assert close(p["collar"], 0.15)


def test_update_pref_clips_and_keeps_original():
    original = {"collar": 0.95}
    p = update_pref(original, ITEMS["t01"], "purchase")
    assert p["collar"] == 1.0               # 1.15 → 1.0으로 자름
    assert original == {"collar": 0.95}     # 원본은 그대로
    p = update_pref({"collar": -0.9}, ITEMS["t01"], "return")
    assert p["collar"] == -1.0
    try:
        update_pref({}, ITEMS["t01"], "share")
        assert False, "알 수 없는 반응은 오류여야 함"
    except ValueError:
        pass


def test_learning_changes_ranking():
    # 피드백이 실제 추천 점수에 반영되는지: 크롭 니트를 5번 구매 → 취향 점수 상승
    before = final_score(STRAIGHT, ITEMS["t04"])["score"]
    pref = {}
    for _ in range(5):
        pref = update_pref(pref, ITEMS["t04"], "purchase")
    # cropped, soft_fabric 각각 0.2 * 5 = 1.0 → 취향 1.0 → 최종 +0.25 * 0.5 = +0.125
    after = final_score(STRAIGHT, ITEMS["t04"], pref=pref)["score"]
    assert close(after - before, 0.125)


def test_need_rediagnosis():
    ruffle, shirt = ITEMS["t06"], ITEMS["t01"]  # 러플은 스트레이트가 피해야 할 옷
    likes = lambda item, n: [{"item": item, "event": "like"}] * n
    # 긍정 반응이 10개 미만이면 판단 안 함
    assert need_rediagnosis(likes(ruffle, 9), STRAIGHT) is False
    # 20개 중 10개(50%)가 피해야 할 옷 → 재진단
    assert need_rediagnosis(likes(shirt, 10) + likes(ruffle, 10), STRAIGHT) is True
    # 20개 중 9개(45%) → 아님
    assert need_rediagnosis(likes(shirt, 11) + likes(ruffle, 9), STRAIGHT) is False
    # 클릭·반품은 긍정 반응이 아님 → 세지 않음
    clicks = [{"item": ruffle, "event": "click"}] * 30
    assert need_rediagnosis(clicks + likes(shirt, 10), STRAIGHT) is False
    # 최근 20개만 봄: 오래된 러플 찜 20개 뒤에 셔츠 찜 20개 → 아님
    assert need_rediagnosis(likes(ruffle, 20) + likes(shirt, 20), STRAIGHT) is False


# ── 8단계: 스크롤 피드 feed_order ───────────────────────────
def test_feed_order_first_page_equals_rank():
    # 홈 첫 화면(스크롤 첫 묶음) = 오늘의 추천
    for body in (STRAIGHT, MIXED, WAVE):
        scored = score_all(body, ITEMS.values())
        assert ids(feed_order(scored)[:10]) == ids(rank(scored))


def test_feed_order_shows_every_item_once():
    # 제외 안 된 옷은 스크롤 끝까지 내리면 전부 정확히 한 번씩 나옴 (태그 제한으로 버려지지 않음)
    for body in (STRAIGHT, MIXED, WAVE):
        scored = score_all(body, ITEMS.values())
        expected = sorted(r["id"] for r in scored if not r["excluded"])
        assert sorted(ids(feed_order(scored))) == expected


def test_feed_order_pushes_capped_tag_to_next_page():
    # collar 5개(상의·하의 번갈아) + 다른 태그 1개, 묶음 크기 4
    # 1묶음: c1 c2 c3(collar 3개 한도) + z  → 2묶음: c4 c5 (태그 수 다시 0부터)
    cats = ["top", "bottom", "top", "bottom", "top"]
    scored = [fake(f"c{i + 1}", 0.9 - i * 0.1, cats[i], "collar") for i in range(5)]
    scored.append(fake("z", 0.1, "bottom", "wide"))
    assert ids(feed_order(scored, page_size=4)) == ["c1", "c2", "c3", "z", "c4", "c5"]


def test_feed_order_rules_per_page():
    scored = score_all(MIXED, ITEMS.values())
    order = feed_order(scored)
    for start in range(0, len(order), 10):
        reps = [r["good_tags"][0] for r in order[start:start + 10] if r["good_tags"]]
        assert all(reps.count(t) <= 3 for t in reps)


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
