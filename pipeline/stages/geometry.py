"""S4/S5/S6/S7 — Blender 기하·시뮬·렌더 (기존 runner 어댑터)."""

from __future__ import annotations

from pipeline.stages import StageContext
from pipeline.adapters.blender_adapter import run_geometry_and_fit
from pipeline.stages.texture import bake_texture_p0


def run_geometry(ctx: StageContext) -> StageContext:
    ctx.progress("의류 형태 적용 중...")
    texture_path = None
    atlas_path = None
    if ctx.manifest.options.bake_texture:
        tex = bake_texture_p0(ctx)
        ctx.extras["texture"] = tex
        if tex.get("path"):
            texture_path = tex["path"]
            ctx.result.artifacts["texture"] = tex["path"]
        if tex.get("atlas_path"):
            atlas_path = tex["atlas_path"]
            ctx.result.artifacts["albedo_atlas"] = atlas_path
        if tex.get("back_path"):
            ctx.result.artifacts["albedo_back"] = tex["back_path"]
        if tex.get("warning"):
            ctx.result.warnings.append(tex["warning"])

    fabric_props = ctx.extras.get("fabric_props") or {}

    artifacts = run_geometry_and_fit(
        output_dir=ctx.output_dir,
        avatar_size=ctx.extras["avatar_size"],
        garment_file=ctx.extras["garment_file"],
        shape_keys=ctx.extras["shape_keys"],
        fabric=ctx.manifest.fabric,
        run_simulation=ctx.manifest.options.run_simulation,
        run_render=ctx.manifest.options.run_render,
        texture_path=texture_path,
        atlas_path=atlas_path,
        fabric_elasticity=fabric_props.get("elasticity"),
        fabric_bending=fabric_props.get("bending"),
        stretch=ctx.manifest.stretch,
        progress=ctx.progress,
    )
    ctx.extras["blender_artifacts"] = artifacts
    ctx.result.artifacts.update(artifacts.get("files", {}))
    if artifacts.get("fit"):
        ctx.result.fit = artifacts["fit"]
    ctx.result.stage = "geometry_fit"
    return ctx
