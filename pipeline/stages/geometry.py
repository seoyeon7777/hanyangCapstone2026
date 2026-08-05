"""S4/S5/S6/S7 — Blender 기하·시뮬·렌더 (기존 runner 어댑터)."""

from __future__ import annotations

from pipeline.stages import StageContext
from pipeline.adapters.blender_adapter import run_geometry_and_fit
from pipeline.stages.texture import bake_texture_p0


def run_geometry(ctx: StageContext) -> StageContext:
    ctx.progress("의류 형태 적용 중...")
    # 텍스처는 sim 전에 준비 (실패해도 진행)
    if ctx.manifest.options.bake_texture:
        tex = bake_texture_p0(ctx)
        ctx.extras["texture"] = tex
        if tex.get("path"):
            ctx.result.artifacts["texture"] = tex["path"]
        if tex.get("warning"):
            ctx.result.warnings.append(tex["warning"])

    artifacts = run_geometry_and_fit(
        output_dir=ctx.output_dir,
        avatar_size=ctx.extras["avatar_size"],
        garment_file=ctx.extras["garment_file"],
        shape_keys=ctx.extras["shape_keys"],
        fabric=ctx.manifest.fabric,
        run_simulation=ctx.manifest.options.run_simulation,
        run_render=ctx.manifest.options.run_render,
        progress=ctx.progress,
    )
    ctx.extras["blender_artifacts"] = artifacts
    ctx.result.artifacts.update(artifacts.get("files", {}))
    if artifacts.get("fit"):
        ctx.result.fit = artifacts["fit"]
    ctx.result.stage = "geometry_fit"
    return ctx
