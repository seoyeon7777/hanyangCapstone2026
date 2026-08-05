"""S3 — 템플릿 매칭 (blend 카탈로그)."""

from __future__ import annotations

import os

from blender.config import BASE_DIR
from pipeline.stages import StageContext


# API garment_type → blend 파일 stem / runner garment_file
GARMENT_FILE_MAP = {
    "tshirt": "top",
    "top": "top",
    "shirt": "top",
    "hoodie": "top",   # P0: nearest template
    "jacket": "top",
    "coat": "top",
}


def run(ctx: StageContext) -> StageContext:
    ctx.progress("템플릿 매칭 중...")
    gtype = (ctx.manifest.garment_type or "tshirt").lower()
    garment_file = GARMENT_FILE_MAP.get(gtype, "top")

    if gtype not in GARMENT_FILE_MAP:
        ctx.result.warnings.append(f"미등록 카테고리 '{gtype}' → top 템플릿 사용")
    elif gtype not in ("tshirt", "top", "shirt"):
        ctx.result.warnings.append(f"'{gtype}'는 nearest template(top) 매핑 (P0)")

    blend_path = os.path.join(BASE_DIR, "assets", "clothing", f"cloth_{garment_file}.blend")
    if not os.path.exists(blend_path):
        raise FileNotFoundError(f"의류 템플릿 없음: {blend_path}")

    avatar_size = ctx.extras["avatar_size"]
    avatar_blend = os.path.join(BASE_DIR, "assets", "avatars", f"body_{avatar_size}.blend")
    if not os.path.exists(avatar_blend):
        raise FileNotFoundError(f"아바타 없음: {avatar_blend}")

    ctx.extras["garment_file"] = garment_file
    ctx.extras["blend_path"] = blend_path
    ctx.extras["avatar_blend_path"] = avatar_blend
    ctx.result.garment_type = gtype
    ctx.result.stage = "template_match"
    return ctx
