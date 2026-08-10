"""S4/S5/S6/S7 — Blender 기하·시뮬·렌더 (기존 runner 어댑터)."""

from __future__ import annotations

import os

from pipeline.stages import StageContext
from pipeline.adapters.blender_adapter import run_geometry_and_fit
from pipeline.stages.texture import bake_texture_p0


def run_geometry(ctx: StageContext) -> StageContext:
    ctx.progress("의류 형태 적용 중...")
    texture_path = None
    atlas_path = None
    atlas_layout = "1x2"
    if ctx.manifest.options.bake_texture:
        tex = bake_texture_p0(ctx)
        ctx.extras["texture"] = tex
        if tex.get("path"):
            texture_path = tex["path"]
            ctx.result.artifacts["texture"] = tex["path"]
        if tex.get("atlas_path"):
            atlas_path = tex["atlas_path"]
            ctx.result.artifacts["albedo_atlas"] = atlas_path
        if tex.get("atlas_layout"):
            atlas_layout = tex["atlas_layout"]
            ctx.result.artifacts["atlas_layout"] = atlas_layout
        if tex.get("back_path"):
            ctx.result.artifacts["albedo_back"] = tex["back_path"]
        if tex.get("side_path"):
            ctx.result.artifacts["albedo_side"] = tex["side_path"]
        if tex.get("warning"):
            ctx.result.warnings.append(tex["warning"])

    fabric_props = ctx.extras.get("fabric_props") or {}

    # 캘리브레이션이 이미 shaped OBJ를 만들었으면 export 재실행 생략
    calibrated_obj = ctx.extras.get("calibrated_obj")
    run_export = True
    cloth_obj_path = None
    if calibrated_obj and os.path.exists(calibrated_obj):
        run_export = False
        cloth_obj_path = calibrated_obj

    artifacts = run_geometry_and_fit(
        output_dir=ctx.output_dir,
        avatar_size=ctx.extras["avatar_size"],
        garment_file=ctx.extras["garment_file"],
        shape_keys=ctx.extras["shape_keys"],
        fabric=ctx.manifest.fabric,
        run_export=run_export,
        run_simulation=ctx.manifest.options.run_simulation,
        run_render=ctx.manifest.options.run_render,
        run_texture=bool(texture_path or atlas_path),
        texture_path=texture_path,
        atlas_path=atlas_path,
        atlas_layout=atlas_layout,
        cloth_obj_path=cloth_obj_path,
        blend_path=ctx.extras.get("blend_path"),
        avatar_blend_path=ctx.extras.get("avatar_blend_path"),
        fabric_elasticity=fabric_props.get("elasticity"),
        fabric_bending=fabric_props.get("bending"),
        stretch=ctx.manifest.stretch,
        preserve_silhouette=bool(ctx.extras.get("preserve_silhouette") or ctx.extras.get("silhouette_deform")),
        progress=ctx.progress,
    )
    ctx.extras["blender_artifacts"] = artifacts
    ctx.result.artifacts.update(artifacts.get("files", {}))
    # Wire texture GLB back into neural export meta when both exist
    try:
        glb = (artifacts.get("files") or {}).get("glb") or ctx.result.artifacts.get("glb")
        export_meta = ctx.result.artifacts.get("cloth_neural_export")
        if glb and os.path.exists(str(glb)) and export_meta and os.path.exists(str(export_meta)):
            import json

            with open(export_meta, encoding="utf-8") as f:
                meta = json.load(f)
            meta["glb"] = str(glb)
            meta["notes"] = (
                "GLB from texture/export stage on post-neural (post-silhouette) mesh; "
                "OBJ remains neural retarget artifact"
            )
            with open(export_meta, "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)
            ctx.result.artifacts["cloth_neural_glb"] = str(glb)
    except Exception:
        pass
    if artifacts.get("fit"):
        # 원단 총평(fit_analysis) 등은 유지하고 시뮬 fit만 병합
        merged = dict(ctx.result.fit or {})
        merged.update(artifacts["fit"])
        ctx.result.fit = merged
    ctx.result.stage = "geometry_fit"
    return ctx
