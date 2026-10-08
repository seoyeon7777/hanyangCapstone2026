"""C 파트 정답 테스트.

실행: python test_feed.py   (pytest가 있으면 pytest test_feed.py 도 가능)
정답값은 모두 손으로 계산한 값이다. 계산 과정은 각 테스트 주석 참고.
AI가 코드를 고친 뒤 이 테스트가 하나라도 깨지면 다음 단계로 넘어가지 않는다.
"""
from rec_config import W_BODY, W_PREF, W_TREND
from fake_matching import classify_kind, match_score
from feed import load_items, final_score, score_all

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
    print(f"\n{len(tests) - failed}/{len(tests)} 통과")
    raise SystemExit(1 if failed else 0)
