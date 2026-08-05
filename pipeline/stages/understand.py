"""S1 — 이미지 이해 (세그멘테이션 / 카테고리).

P0: 휴리스틱 + optional rembg stub.
실제 ML 모델은 vision_adapter 로 교체 가능.
"""

from __future__ import annotations

import os
from typing import Optional

from pipeline.stages import StageContext
from pipeline.adapters.vision_adapter import (
    classify_garment,
    segment_garment,
)


def run(ctx: StageContext) -> StageContext:
    ctx.progress("이미지 분석 중...")
    front = (ctx.manifest.images or {}).get("front")

    if not front or not os.path.exists(front):
        # 이미지 없으면 사용자 garment_type 또는 기본값
        if not ctx.manifest.garment_type:
            ctx.manifest.garment_type = "tshirt"
            ctx.result.warnings.append("이미지 없음 → garment_type=tshirt 기본값")
        ctx.extras["seg_mask"] = None
        ctx.extras["classification"] = {
            "label": ctx.manifest.garment_type,
            "confidence": 0.0,
            "source": "default",
        }
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
    if not seg.get("ok"):
        ctx.result.warnings.append(f"세그멘테이션 fallback: {seg.get('reason', 'unknown')}")

    ctx.result.garment_type = ctx.manifest.garment_type
    ctx.result.stage = "understand"
    return ctx
