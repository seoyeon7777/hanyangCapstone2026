"""S5 — 정면 이미지 → albedo 준비 (세그 크롭 + 정사각 패치)."""

from __future__ import annotations

import os
import shutil
from typing import Any

from pipeline.stages import StageContext


def _alpha_bbox(img):
    """RGBA 이미지의 불투명 영역 bbox. 없으면 None."""
    alpha = img.split()[-1]
    bbox = alpha.getbbox()
    return bbox


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

    try:
        from PIL import Image

        img = Image.open(src).convert("RGBA")
        bbox = _alpha_bbox(img)
        if bbox:
            # 약간 패딩
            pad = int(0.02 * max(img.size))
            x0 = max(0, bbox[0] - pad)
            y0 = max(0, bbox[1] - pad)
            x1 = min(img.size[0], bbox[2] + pad)
            y1 = min(img.size[1], bbox[3] + pad)
            img = img.crop((x0, y0, x1, y1))

        # 정사각 캔버스 + 밝은 중립 배경 (투명→연한 회색)
        size = max(img.size)
        size = max(size, 256)
        canvas = Image.new("RGBA", (size, size), (230, 230, 230, 255))
        ox = (size - img.size[0]) // 2
        oy = (size - img.size[1]) // 2
        canvas.paste(img, (ox, oy), img)
        # RGB로도 저장 (일부 glTF 경로 호환)
        canvas.convert("RGBA").save(out)
        return {
            "path": out,
            "mode": "front_cropped_square",
            "warning": None,
            "size": size,
            "source": src,
        }
    except Exception as e:
        try:
            shutil.copy2(src, out)
            return {
                "path": out,
                "mode": "copy",
                "warning": f"PIL 처리 실패, 원본 복사: {e}",
            }
        except Exception as e2:
            return {
                "path": None,
                "mode": "solid",
                "warning": f"텍스처 준비 실패: {e2}",
            }
