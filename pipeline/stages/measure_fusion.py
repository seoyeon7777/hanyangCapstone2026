"""S2 — 치수 융합 (user > OCR > defaults) + Shape Key 계산."""

from __future__ import annotations

from models.fitting_model import (
    match_avatar,
    calc_export_shape_keys,
    EXPORT_BASE_MEASUREMENTS,
)
from pipeline.stages import StageContext
from pipeline.schemas.manifest import REQUIRED_UPPER_KEYS, REQUIRED_LOWER_KEYS


LOWER_TYPES = {"pants", "skirt", "shorts", "trousers"}


def _defaults_for(shape_key_type: str) -> dict[str, float]:
    base = EXPORT_BASE_MEASUREMENTS.get(shape_key_type) or EXPORT_BASE_MEASUREMENTS.get("tshirt", {})
    return dict(base)


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
    defaults = _defaults_for(shape_key_type)

    fused: dict[str, float] = {}
    sources: dict[str, str] = {}
    for key in required:
        user_val = ctx.manifest.measurements.get(key)
        if user_val is not None:
            fused[key] = float(user_val)
            sources[key] = "user"
        elif ocr_meas.get(key) is not None:
            fused[key] = float(ocr_meas[key])
            sources[key] = "ocr"
            ctx.result.warnings.append(f"{key}: OCR 추정값 사용 ({fused[key]})")
        elif key in defaults:
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
    ctx.result.stage = "measure_fusion"
    return ctx
