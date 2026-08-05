"""S5 — P0 텍스처 베이크 (단순 정면 복사 / solid fallback).

본격 UV 프로젝션은 Blender 스크립트로 확장 예정.
P0에서는 세그먼트 RGBA 또는 원본 front를 albedo 후보로 저장한다.
"""

from __future__ import annotations

import os
import shutil
from typing import Any

from pipeline.stages import StageContext


def bake_texture_p0(ctx: StageContext) -> dict[str, Any]:
    out = ctx.path("albedo.png")
    rgba = ctx.extras.get("seg_rgba")
    front = (ctx.manifest.images or {}).get("front")

    src = None
    if rgba and os.path.exists(rgba):
        src = rgba
    elif front and os.path.exists(front):
        src = front

    if not src:
        return {
            "path": None,
            "warning": "텍스처 소스 없음 — solid color fallback",
            "mode": "solid",
        }

    # 이미지 변환이 가능하면 PNG로, 아니면 그대로 복사
    try:
        from PIL import Image
        img = Image.open(src).convert("RGBA")
        # 정사각 패치로 정규화 (UV 임시용)
        size = max(img.size)
        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        ox = (size - img.size[0]) // 2
        oy = (size - img.size[1]) // 2
        canvas.paste(img, (ox, oy))
        canvas.save(out)
        return {"path": out, "mode": "front_projection_proxy", "warning": None}
    except Exception as e:
        shutil.copy2(src, out)
        return {
            "path": out,
            "mode": "copy",
            "warning": f"PIL 처리 실패, 원본 복사: {e}",
        }
