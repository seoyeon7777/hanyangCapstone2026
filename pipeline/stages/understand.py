"""S1 — 이미지 이해 (세그멘테이션 / 카테고리). front/back/side 지원."""

from __future__ import annotations

import os

from pipeline.stages import StageContext
from pipeline.adapters.vision_adapter import (
    classify_garment,
    segment_garment,
)


def run(ctx: StageContext) -> StageContext:
    ctx.progress("이미지 분석 중...")
    images = ctx.manifest.images or {}
    front = images.get("front")

    if not front or not os.path.exists(front):
        if not ctx.manifest.garment_type:
            ctx.manifest.garment_type = "tshirt"
            ctx.result.warnings.append("이미지 없음 → garment_type=tshirt 기본값")
        ctx.extras["seg_mask"] = None
        ctx.extras["seg_rgba"] = None
        ctx.extras["classification"] = {
            "label": ctx.manifest.garment_type,
            "confidence": 0.0,
            "source": "default",
        }
        # 후면만 있는 경우도 세그
        _segment_extra_views(ctx, images)
        ctx.result.stage = "understand"
        return ctx

    classification = classify_garment(front, hint=ctx.manifest.garment_type)
    ctx.extras["classification"] = classification

    if not ctx.manifest.garment_type:
        ctx.manifest.garment_type = classification["label"]
    elif classification["confidence"] >= 0.7 and classification["label"] != ctx.manifest.garment_type:
        ctx.result.warnings.append(
            f"분류 결과({classification['label']})와 입력({ctx.manifest.garment_type}) 불일치"
        )

    if classification["confidence"] < 0.7 and classification["source"] != "hint":
        ctx.result.warnings.append(
            f"카테고리 신뢰도 낮음({classification['confidence']:.2f}) — 검수 권장"
        )

    mask_path = ctx.path("seg_front.png")
    seg = segment_garment(front, mask_path)
    ctx.extras["seg_mask"] = seg.get("mask_path")
    ctx.extras["seg_rgba"] = seg.get("rgba_path")
    ctx.extras["seg_rgba_front"] = seg.get("rgba_path")
    if not seg.get("ok"):
        ctx.result.warnings.append(f"세그멘테이션 fallback(front): {seg.get('reason', 'unknown')}")

    _segment_extra_views(ctx, images)

    ctx.result.garment_type = ctx.manifest.garment_type
    ctx.result.stage = "understand"
    return ctx


def _segment_extra_views(ctx: StageContext, images: dict) -> None:
    for view in ("back", "side", "detail"):
        src = images.get(view)
        if not src or not os.path.exists(src):
            continue
        mask_path = ctx.path(f"seg_{view}.png")
        seg = segment_garment(src, mask_path)
        ctx.extras[f"seg_mask_{view}"] = seg.get("mask_path")
        ctx.extras[f"seg_rgba_{view}"] = seg.get("rgba_path")
        if not seg.get("ok"):
            ctx.result.warnings.append(
                f"세그멘테이션 fallback({view}): {seg.get('reason', 'unknown')}"
            )
        else:
            ctx.progress(f"{view} 이미지 세그 완료")
