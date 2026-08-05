"""S3 — 템플릿 매칭 (garment_catalog.json)."""

from __future__ import annotations

import os

from blender.config import BASE_DIR
from models.fitting_model import match_avatar
from pipeline.adapters.catalog import resolve_template
from pipeline.stages import StageContext


def run(ctx: StageContext) -> StageContext:
    ctx.progress("템플릿 매칭 중...")
    gtype = ctx.manifest.garment_type or "tshirt"
    match = resolve_template(gtype)

    if match.get("warning"):
        ctx.result.warnings.append(match["warning"])
    if match.get("is_lower"):
        ctx.result.warnings.append(
            f"하의 카테고리 '{gtype}'는 아직 전용 템플릿 없음 — 결과 품질 제한"
        )

    blend_path = match["blend_path"]
    if not os.path.exists(blend_path):
        raise FileNotFoundError(f"의류 템플릿 없음: {blend_path}")

    avatar_size = ctx.extras.get("avatar_size") or match_avatar(
        ctx.manifest.body.height, ctx.manifest.body.weight
    )
    avatar_blend = os.path.join(BASE_DIR, "assets", "avatars", f"body_{avatar_size}.blend")
    if not os.path.exists(avatar_blend):
        raise FileNotFoundError(f"아바타 없음: {avatar_blend}")

    ctx.extras["avatar_size"] = avatar_size
    ctx.extras["garment_file"] = match["garment_file"]
    ctx.extras["blend_path"] = blend_path
    ctx.extras["avatar_blend_path"] = avatar_blend
    ctx.extras["template_match"] = match
    ctx.extras["shape_key_type"] = match["shape_key_type"]
    ctx.result.avatar_size = avatar_size
    ctx.result.garment_type = match["garment_type"]
    ctx.result.artifacts["template"] = {
        "id": match["template_id"],
        "blend": blend_path,
        "nearest": match["nearest"],
    }
    ctx.result.stage = "template_match"
    return ctx
