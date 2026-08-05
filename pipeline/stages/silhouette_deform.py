"""P1 — 실루엣 기반 메쉬 가로폭 보정 스테이지."""

from __future__ import annotations

import os
import shutil

from pipeline.stages import StageContext


def run(ctx: StageContext) -> StageContext:
    opts = ctx.manifest.options
    phase = (opts.phase or "P0").upper()
    enabled = bool(getattr(opts, "silhouette_deform", False)) or phase == "P1"
    if not enabled:
        ctx.result.stage = "silhouette_deform"
        return ctx

    mask = (
        ctx.extras.get("seg_rgba")
        or ctx.extras.get("seg_rgba_front")
        or ctx.extras.get("seg_mask")
        or (ctx.manifest.images or {}).get("front")
    )
    src_obj = ctx.extras.get("calibrated_obj")
    if not src_obj or not os.path.exists(src_obj):
        # 캘리브레이션 OBJ가 없으면 geometry가 export 하므로 스킵
        ctx.result.warnings.append("실루엣 디폼 스킵 — shaped OBJ 없음")
        ctx.result.stage = "silhouette_deform"
        return ctx

    if not mask or not os.path.exists(mask):
        ctx.result.warnings.append("실루엣 디폼 스킵 — 정면 마스크/이미지 없음")
        ctx.result.stage = "silhouette_deform"
        return ctx

    ctx.progress("실루엣 형상 보정 중...")
    out_path = ctx.path("cloth_silhouette.obj")
    try:
        from models.silhouette_deform import deform_obj_by_silhouette

        strength = float(getattr(opts, "silhouette_strength", 0.45))
        report = deform_obj_by_silhouette(
            src_obj,
            mask,
            out_path,
            strength=strength,
        )
        ctx.extras["calibrated_obj"] = out_path
        ctx.extras["silhouette_deform"] = report
        ctx.result.artifacts["cloth_silhouette_obj"] = out_path
        ctx.result.warnings.append(
            f"P1 실루엣 디폼 적용 (strength={strength}, Δx≤{report['max_abs_x_delta']})"
        )
    except Exception as e:
        ctx.result.warnings.append(f"실루엣 디폼 실패 — 원본 유지: {e}")
        if os.path.exists(src_obj) and not os.path.exists(out_path):
            shutil.copy2(src_obj, out_path)

    ctx.result.stage = "silhouette_deform"
    return ctx
