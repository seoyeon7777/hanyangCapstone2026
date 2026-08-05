"""P1 — 실루엣 기반 메쉬 가로폭·깊이 보정 스테이지."""

from __future__ import annotations

import os
import shutil

from pipeline.stages import StageContext


def run(ctx: StageContext) -> StageContext:
    opts = ctx.manifest.options
    phase = (opts.phase or "P0").upper()
    enabled = bool(getattr(opts, "silhouette_deform", False)) or phase == "P1"
    auto = bool(getattr(opts, "silhouette_auto", False))
    auto_info = None

    mask = (
        ctx.extras.get("seg_rgba")
        or ctx.extras.get("seg_rgba_front")
        or ctx.extras.get("seg_mask")
        or (ctx.manifest.images or {}).get("front")
    )
    side_mask = (
        ctx.extras.get("seg_mask_side")
        or ctx.extras.get("seg_rgba_side")
        or (ctx.manifest.images or {}).get("side")
    )

    if not enabled and auto and mask and os.path.exists(mask):
        try:
            from models.silhouette_deform import should_auto_enable

            auto_info = should_auto_enable(
                mask,
                min_score=float(getattr(opts, "silhouette_auto_min_score", 0.42)),
            )
            enabled = bool(auto_info.get("enable"))
            ctx.extras["silhouette_auto"] = auto_info
            if enabled:
                ctx.result.warnings.append(
                    f"실루엣 디폼 자동 활성 (score={auto_info.get('score')})"
                )
            else:
                ctx.result.warnings.append(
                    f"실루엣 디폼 자동 스킵 (score={auto_info.get('score')}, {auto_info.get('reason')})"
                )
        except Exception as e:
            ctx.result.warnings.append(f"실루엣 자동판정 실패: {e}")

    if not enabled:
        ctx.result.stage = "silhouette_deform"
        return ctx

    src_obj = ctx.extras.get("calibrated_obj")
    if not src_obj or not os.path.exists(src_obj):
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
        edge_snap = float(getattr(opts, "silhouette_edge_snap", 0.35))
        depth_strength = float(getattr(opts, "silhouette_depth_strength", strength * 0.75))
        # 하의면 bipodal 자동/강제
        gtype = (ctx.manifest.garment_type or "").lower()
        bipodal_opt = getattr(opts, "silhouette_bipodal", "auto")
        if bipodal_opt == "auto" and gtype in ("pants", "shorts", "trousers"):
            bipodal_opt = "auto"
        report = deform_obj_by_silhouette(
            src_obj,
            mask,
            out_path,
            strength=strength,
            edge_snap=edge_snap,
            side_mask_path=side_mask if side_mask and os.path.exists(side_mask) else None,
            depth_strength=depth_strength,
            smooth_iters=int(getattr(opts, "silhouette_smooth_iters", 1)),
            bipodal=bipodal_opt,
        )
        if auto_info:
            report["auto"] = auto_info
        ctx.extras["calibrated_obj"] = out_path
        ctx.extras["silhouette_deform"] = report
        ctx.extras["preserve_silhouette"] = True
        ctx.result.artifacts["cloth_silhouette_obj"] = out_path
        znote = ""
        if report.get("depth") and report["depth"].get("ok"):
            znote = f", Δz≤{report.get('max_abs_z_delta')}"
        ctx.result.warnings.append(
            f"P1 실루엣 디폼 적용 (strength={strength}, edge={edge_snap}"
            f"{znote}, Δx≤{report['max_abs_x_delta']})"
        )
    except Exception as e:
        ctx.result.warnings.append(f"실루엣 디폼 실패 — 원본 유지: {e}")
        if os.path.exists(src_obj) and not os.path.exists(out_path):
            shutil.copy2(src_obj, out_path)

    ctx.result.stage = "silhouette_deform"
    return ctx
