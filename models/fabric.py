"""원단/소재 입력 정규화 + 물리 파라미터 계산.

입력 예:
  {"cotton": 80, "spandex": 20}          # % (UI)
  {"면": 0.8, "스판": 0.2}               # 한글 별칭 + 비율
  {"cotton": 1.0}                        # 단일 소재

stretch 예: "낮음" | "보통" | "높음" | "없음" | "X"
→ 탄성(elasticity)에 배율 적용.
"""

from __future__ import annotations

from typing import Any, Optional
import json

from models.fitting_model import (
    FABRIC_ELASTICITY,
    FABRIC_BENDING,
    calc_fabric_elasticity,
    calc_fabric_bending,
)


# 한글/별칭 → 내부 키
FABRIC_ALIASES = {
    "cotton": "cotton",
    "면": "cotton",
    "코튼": "cotton",
    "순면": "cotton",
    "polyester": "polyester",
    "폴리": "polyester",
    "폴리에스터": "polyester",
    "폴리에스테르": "polyester",
    "linen": "linen",
    "린넨": "linen",
    "마": "linen",
    "wool": "wool",
    "울": "wool",
    "모": "wool",
    "denim": "denim",
    "데님": "denim",
    "청": "denim",
    "knit": "knit",
    "니트": "knit",
    "silk": "silk",
    "실크": "silk",
    "견": "silk",
    "nylon": "nylon",
    "나일론": "nylon",
    "acrylic": "acrylic",
    "아크릴": "acrylic",
    "rayon": "rayon",
    "레이온": "rayon",
    "인견": "rayon",
    "spandex": "spandex",
    "스판": "spandex",
    "스판덱스": "spandex",
    "폴리우레탄": "spandex",
    "pu": "spandex",
    "cashmere": "cashmere",
    "캐시미어": "cashmere",
    "chiffon": "chiffon",
    "시폰": "chiffon",
}

STRETCH_ELASTICITY_SCALE = {
    "없음": 0.4,
    "신축성 없음": 0.4,
    "x": 0.4,
    "낮음": 0.7,
    "보통": 1.0,
    "중간": 1.0,
    "높음": 1.35,
    "좋음": 1.35,
    "우수": 1.5,
}

FABRIC_DISPLAY_KO = {
    "cotton": "면",
    "polyester": "폴리에스터",
    "linen": "린넨",
    "wool": "울",
    "denim": "데님",
    "knit": "니트",
    "silk": "실크",
    "nylon": "나일론",
    "acrylic": "아크릴",
    "rayon": "레이온",
    "spandex": "스판덱스",
    "cashmere": "캐시미어",
    "chiffon": "시폰",
}


def parse_fabric_input(fabric: Any) -> dict[str, float]:
    """문자열 JSON / dict / 빈 값 → raw dict."""
    if fabric is None or fabric == "":
        return {}
    if isinstance(fabric, str):
        try:
            fabric = json.loads(fabric)
        except json.JSONDecodeError:
            # "cotton 80%, spandex 20%" 같은 자유 텍스트는 키워드만 추출
            found = {}
            lower = fabric.lower()
            for alias, key in FABRIC_ALIASES.items():
                if alias.lower() in lower or alias in fabric:
                    found[key] = found.get(key, 0.0) + 1.0
            if found:
                n = sum(found.values())
                return {k: v / n for k, v in found.items()}
            return {}
    if not isinstance(fabric, dict):
        return {}
    out = {}
    for k, v in fabric.items():
        try:
            out[str(k)] = float(v)
        except (TypeError, ValueError):
            continue
    return out


def normalize_fabric(fabric: Any) -> dict[str, float]:
    """별칭 통일 + 비율 합=1.0 로 정규화. 값이 전부 >1 이면 %로 간주."""
    raw = parse_fabric_input(fabric)
    merged: dict[str, float] = {}
    for k, v in raw.items():
        if v is None or v <= 0:
            continue
        key = FABRIC_ALIASES.get(k.lower(), FABRIC_ALIASES.get(k, k.lower()))
        # 미등록 키도 보존 (elasticity 기본 0.1)
        merged[key] = merged.get(key, 0.0) + float(v)

    if not merged:
        return {}

    # % → 비율
    total = sum(merged.values())
    if total <= 0:
        return {}
    if total > 1.5:  # 합이 대략 100% 스케일
        merged = {k: v / total for k, v in merged.items()}
    else:
        # 이미 0~1 근처면 합으로 재정규화
        merged = {k: v / total for k, v in merged.items()}

    return {k: round(v, 4) for k, v in merged.items()}


def stretch_scale(stretch: str) -> float:
    if not stretch:
        return 1.0
    return STRETCH_ELASTICITY_SCALE.get(str(stretch).strip().lower(), 1.0)


def resolve_fabric_props(fabric: Any, stretch: str = "") -> dict[str, Any]:
    """파이프라인/시뮬용 원단 물성 요약."""
    normalized = normalize_fabric(fabric)
    base_e = calc_fabric_elasticity(normalized) if normalized else 0.15
    base_b = calc_fabric_bending(normalized) if normalized else 25.0
    scale = stretch_scale(stretch)
    elasticity = max(0.01, min(0.99, base_e * scale))

    composition = [
        {
            "key": k,
            "name_ko": FABRIC_DISPLAY_KO.get(k, k),
            "ratio": v,
            "percent": round(v * 100, 1),
            "elasticity": FABRIC_ELASTICITY.get(k, 0.1),
            "bending": FABRIC_BENDING.get(k, 25.0),
        }
        for k, v in sorted(normalized.items(), key=lambda x: -x[1])
    ]

    return {
        "fabric": normalized,
        "stretch": stretch or "",
        "stretch_scale": scale,
        "elasticity": round(elasticity, 4),
        "bending": round(base_b, 3),
        "composition": composition,
        "summary_ko": ", ".join(
            f"{c['name_ko']} {c['percent']:.0f}%" for c in composition
        ) if composition else "미지정(면 기본)",
    }
