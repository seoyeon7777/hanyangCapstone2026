"""S2 — 치수 융합 (user > text/ocr > silhouette_estimate > defaults) + Shape Key 계산."""

from __future__ import annotations

from models.fitting_model import (
    match_avatar,
    calc_export_shape_keys,
    EXPORT_BASE_MEASUREMENTS,
)
from pipeline.stages import StageContext
from pipeline.schemas.manifest import REQUIRED_UPPER_KEYS, REQUIRED_LOWER_KEYS


LOWER_TYPES = {"pants", "skirt", "shorts", "trousers"}

# 소스 우선순위 (낮을수록 우선) — 동일 키에 여러 후보가 있을 때
_SOURCE_RANK = {
    "user": 0,
    "text": 1,
    "ocr": 2,
    "silhouette_estimate": 3,
    "default": 4,
}


def _defaults_for(shape_key_type: str) -> dict[str, float]:
    base = EXPORT_BASE_MEASUREMENTS.get(shape_key_type) or EXPORT_BASE_MEASUREMENTS.get("tshirt", {})
    return dict(base)


def _label_for_source(src: str) -> str:
    return {
        "user": "사용자 입력",
        "text": "사이즈표 텍스트",
        "ocr": "OCR",
        "silhouette_estimate": "실루엣 추정",
        "default": "템플릿 기본값",
    }.get(src, src)


def run(ctx: StageContext) -> StageContext:
    ctx.progress("치수 융합 중...")
    gtype = (ctx.manifest.garment_type or "tshirt").lower()
    match = ctx.extras.get("template_match") or {}
    required = tuple(match.get("measurement_keys") or (
        REQUIRED_LOWER_KEYS if gtype in LOWER_TYPES else REQUIRED_UPPER_KEYS
    ))
    shape_key_type = match.get("shape_key_type") or (
        "tshirt" if gtype not in LOWER_TYPES else gtype
    )

    ocr_meas = ctx.extras.get("ocr_measurements") or {}
    ocr_meta = ctx.extras.get("ocr_meta") or {}
    ocr_sources = ocr_meta.get("sources") or {}
    defaults = _defaults_for(shape_key_type)

    fused: dict[str, float] = {}
    sources: dict[str, str] = {}
    for key in required:
        user_val = ctx.manifest.measurements.get(key)
        if user_val is not None:
            fused[key] = float(user_val)
            sources[key] = "user"
            continue

        if ocr_meas.get(key) is not None:
            fused[key] = float(ocr_meas[key])
            src = ocr_sources.get(key) or "ocr"
            sources[key] = src
            ctx.result.warnings.append(
                f"{key}: {_label_for_source(src)} 사용 ({fused[key]})"
            )
            continue

        if key in defaults:
            fused[key] = float(defaults[key])
            sources[key] = "default"
            ctx.result.warnings.append(f"{key}: 템플릿 기본값 사용 ({fused[key]})")

    for key, val in ctx.manifest.measurements.items():
        if val is not None and key not in fused:
            fused[key] = float(val)
            sources[key] = "user"

    ctx.manifest.measurements = fused
    ctx.extras["measurement_sources"] = sources

    avatar_size = match_avatar(ctx.manifest.body.height, ctx.manifest.body.weight)
    shape_keys = calc_export_shape_keys(shape_key_type, fused)

    ctx.extras["avatar_size"] = avatar_size
    ctx.extras["shape_keys"] = shape_keys
    ctx.extras["shape_key_type"] = shape_key_type
    ctx.result.avatar_size = avatar_size
    ctx.result.shape_keys = shape_keys
    # 결과에 소스 요약 노출
    ctx.result.fit = dict(ctx.result.fit or {})
    ctx.result.fit["measurement_sources"] = sources
    ctx.result.fit["measurements"] = fused
    ctx.result.stage = "measure_fusion"
    return ctx
