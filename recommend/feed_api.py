"""7단계: 추천 피드 API (Flask Blueprint).

app.py에서 등록:  app.register_blueprint(feed_bp)

GET  /api/feed?user_id=u1&S=0.6&W=0.3&N=0.1&season=fall
POST /api/feed        {"user_id": "u1", "body": {"ratio": {"S":0.6,"W":0.3,"N":0.1}}, "season": "fall"}
POST /api/feed/event  {"user_id": "u1", "item_id": "t01", "event": "like"}

사용자 취향(pref)과 반응 기록(history)은 서버 메모리에 저장한다(서버를 끄면 사라짐 — 시연용).
"""
from datetime import date

from flask import Blueprint, jsonify, request

from rec_config import SEASONS, SEASON_BY_MONTH, REDIAG_MESSAGE
from fake_matching import classify_kind
from feed import load_items, home_feed, reason, update_pref, need_rediagnosis

feed_bp = Blueprint("feed", __name__)

ITEMS = load_items()
ITEMS_BY_ID = {item["id"]: item for item in ITEMS}

# user_id → {"body": {...}, "pref": {...}, "history": [...]}
USERS = {}


class BadRequest(Exception):
    pass


def current_season():
    return SEASON_BY_MONTH[date.today().month]


def make_body(ratio):
    """S·W·N 비율 → body. 합이 1이 아니면 1이 되게 맞춘다."""
    try:
        ratio = {t: float(ratio.get(t, 0)) for t in ("S", "W", "N")}
    except (TypeError, ValueError, AttributeError):
        raise BadRequest("ratio는 S, W, N 숫자여야 해요")
    total = sum(ratio.values())
    if total <= 0 or any(v < 0 for v in ratio.values()):
        raise BadRequest("ratio는 0 이상이고 합이 0보다 커야 해요")
    ratio = {t: v / total for t, v in ratio.items()}
    kind, primary = classify_kind(ratio)
    return {"ratio": ratio, "kind": kind, "primary": primary}


def with_reasons(feed):
    """화면에 바로 쓰도록 각 옷에 추천 이유(reason)를 붙인다."""
    for section in feed["sections"]:
        for entry in section["items"]:
            if "top" in entry:  # 추천 코디
                for part in ("top", "bottom"):
                    entry[part] = {**entry[part], "reason": reason(entry[part])}
            else:
                entry["reason"] = reason(entry)
    return feed


@feed_bp.errorhandler(BadRequest)
def bad_request(e):
    return jsonify({"error": str(e)}), 400


@feed_bp.route("/api/feed", methods=["GET", "POST"])
def get_feed():
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        ratio = (data.get("body") or {}).get("ratio")
    else:
        data = request.args
        ratio = {t: data.get(t) for t in ("S", "W", "N")} if any(t in data for t in "SWN") else None

    user_id = data.get("user_id")
    user = USERS.get(user_id) if user_id else None

    if ratio is not None:
        body = make_body(ratio)
    elif user:
        body = user["body"]  # 이전에 보낸 체형 재사용
    else:
        raise BadRequest("체형 비율(S, W, N)이 필요해요")

    season = data.get("season") or current_season()
    if season not in SEASONS:
        raise BadRequest(f"season은 {', '.join(SEASONS)} 중 하나여야 해요")

    if user_id:
        user = USERS.setdefault(user_id, {"pref": {}, "history": []})
        user["body"] = body
    pref = user["pref"] if user else None

    feed = with_reasons(home_feed(body, ITEMS, pref, season))
    return jsonify({"body": body, "season": season, **feed})


@feed_bp.route("/api/feed/event", methods=["POST"])
def post_event():
    data = request.get_json(silent=True) or {}
    user = USERS.get(data.get("user_id"))
    if not user:
        raise BadRequest("먼저 /api/feed로 체형을 보내 주세요 (user_id 필요)")
    item = ITEMS_BY_ID.get(data.get("item_id"))
    if not item:
        raise BadRequest("없는 상품이에요")
    try:
        user["pref"] = update_pref(user["pref"], item, data.get("event"))
    except ValueError as e:
        raise BadRequest(str(e))
    user["history"].append({"item": item, "event": data["event"]})

    rediag = need_rediagnosis(user["history"], user["body"])
    return jsonify({
        "pref": user["pref"],
        "need_rediagnosis": rediag,
        "message": REDIAG_MESSAGE if rediag else "",
    })
