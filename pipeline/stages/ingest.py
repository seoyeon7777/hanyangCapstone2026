"""S0 — 입력 정규화 및 출력 디렉터리 준비."""

from __future__ import annotations

import os
import shutil

from pipeline.stages import StageContext
from pipeline.schemas.manifest import REQUIRED_UPPER_KEYS, REQUIRED_LOWER_KEYS


LOWER_TYPES = {"pants", "skirt", "shorts"}


def run(ctx: StageContext) -> StageContext:
    ctx.progress("입력 검증 중...")
    os.makedirs(ctx.output_dir, exist_ok=True)

    # 업로드 이미지를 job 폴더로 복사 (이미 경로인 경우)
    images = {}
    for view, src in (ctx.manifest.images or {}).items():
        if not src:
            images[view] = None
            continue
        if not os.path.exists(src):
            ctx.result.warnings.append(f"이미지 없음: {view}={src}")
            images[view] = None
            continue
        ext = os.path.splitext(src)[1] or ".jpg"
        dst = ctx.path(f"input_{view}{ext}")
        if os.path.abspath(src) != os.path.abspath(dst):
            shutil.copy2(src, dst)
        images[view] = dst
    ctx.manifest.images = images
    ctx.extras["images"] = images

    gtype = (ctx.manifest.garment_type or "tshirt").lower()
    required = REQUIRED_LOWER_KEYS if gtype in LOWER_TYPES else REQUIRED_UPPER_KEYS
    missing = [k for k in required if ctx.manifest.measurements.get(k) is None]
    if missing:
        ctx.result.warnings.append(f"치수 누락: {', '.join(missing)}")
        ctx.extras["missing_measurements"] = missing

    if not images.get("front") and ctx.manifest.options.bake_texture:
        ctx.result.warnings.append("정면 이미지 없음 — 텍스처 베이크 스킵 예정")

    ctx.result.stage = "ingest"
    return ctx
