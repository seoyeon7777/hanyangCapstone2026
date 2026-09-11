"""S1 — 이미지 이해 (세그멘테이션 / 카테고리 / OCR·치수 추정)."""

from __future__ import annotations

import os

from pipeline.stages import StageContext
from pipeline.adapters.vision_adapter import (
    classify_garment,
    segment_garment,
)
from pipeline.adapters.ocr_adapter import extract_measurements


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
        _segment_extra_views(ctx, images)
        _run_ocr(ctx, image_path=None, mask_path=None)
        ctx.result.stage = "understand"
        return ctx

    classification = classify_garment(front, hint=ctx.manifest.garment_type)
    ctx.extras["classification"] = classification
    ctx.result.fit = dict(ctx.result.fit or {})
    ctx.result.fit["classification"] = classification

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
    _run_ocr(ctx, image_path=front, mask_path=ctx.extras.get("seg_mask"))

    ctx.result.garment_type = ctx.manifest.garment_type
    ctx.result.stage = "understand"
    return ctx


def _run_ocr(ctx: StageContext, image_path, mask_path) -> None:
    text = getattr(ctx.manifest, "measurement_text", None) or ""
    # extras에 직접 넣은 경우도 허용
    if not text:
        text = (ctx.extras.get("measurement_text") or "")

    # 사용자 치수가 이미 충분하면 실루엣 추정은 생략
    user_meas = {k: v for k, v in (ctx.manifest.measurements or {}).items() if v is not None}
    allow_est = len(user_meas) < 2

    result = extract_measurements(
        measurement_text=text,
        image_path=image_path,
        mask_path=mask_path,
        garment_type=ctx.manifest.garment_type or "tshirt",
        height_cm=ctx.manifest.body.height,
        allow_silhouette_estimate=allow_est,
    )
    ctx.extras["ocr_measurements"] = result.get("measurements") or {}
    ctx.extras["ocr_meta"] = {
        "sources": result.get("sources") or {},
        "ocr_engine": result.get("ocr_engine"),
        "text_used": result.get("text_used"),
    }
    if result.get("measurements"):
        n = len(result["measurements"])
        ctx.progress(f"치수 후보 {n}개 추출")


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
