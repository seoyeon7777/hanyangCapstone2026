"""멀티뷰 albedo 준비: front/back(/side) 세그 → 크롭 → atlas."""

from __future__ import annotations

import os
import shutil
from typing import Any, Optional

from pipeline.stages import StageContext


def _alpha_bbox(img):
    alpha = img.split()[-1]
    return alpha.getbbox()


def _prepare_view_patch(src: str, size: int = 512, flip_h: bool = False):
    """세그/원본 이미지 → 정사각 RGBA 패치."""
    from PIL import Image

    img = Image.open(src).convert("RGBA")
    if flip_h:
        img = img.transpose(Image.FLIP_LEFT_RIGHT)

    bbox = _alpha_bbox(img)
    if bbox:
        pad = int(0.02 * max(img.size))
        x0 = max(0, bbox[0] - pad)
        y0 = max(0, bbox[1] - pad)
        x1 = min(img.size[0], bbox[2] + pad)
        y1 = min(img.size[1], bbox[3] + pad)
        img = img.crop((x0, y0, x1, y1))

    canvas = Image.new("RGBA", (size, size), (230, 230, 230, 255))
    # contain fit
    scale = min(size / img.size[0], size / img.size[1])
    nw, nh = max(1, int(img.size[0] * scale)), max(1, int(img.size[1] * scale))
    img = img.resize((nw, nh), Image.Resampling.LANCZOS)
    ox = (size - nw) // 2
    oy = (size - nh) // 2
    canvas.paste(img, (ox, oy), img)
    return canvas


def _resolve_view_source(ctx: StageContext, view: str) -> Optional[str]:
    extras_key = f"seg_rgba_{view}" if view != "front" else "seg_rgba"
    # front 호환: seg_rgba 또는 seg_rgba_front
    candidates = []
    if view == "front":
        candidates.append(ctx.extras.get("seg_rgba"))
        candidates.append(ctx.extras.get("seg_rgba_front"))
    else:
        candidates.append(ctx.extras.get(extras_key))
    candidates.append((ctx.manifest.images or {}).get(view))
    for p in candidates:
        if p and os.path.exists(p):
            return p
    return None


def bake_texture_p0(ctx: StageContext) -> dict[str, Any]:
    """front 필수(있으면), back 선택 → albedo.png(정면) + albedo_atlas.png(앞|뒤)."""
    try:
        from PIL import Image
    except ImportError as e:
        return {"path": None, "mode": "solid", "warning": f"Pillow 없음: {e}"}

    front_src = _resolve_view_source(ctx, "front")
    back_src = _resolve_view_source(ctx, "back")
    side_src = _resolve_view_source(ctx, "side")

    if not front_src and not back_src:
        return {
            "path": None,
            "warning": "텍스처 소스 없음 — solid color fallback",
            "mode": "solid",
        }

    patch_size = 512
    views_used = []
    try:
        if front_src:
            front_patch = _prepare_view_patch(front_src, patch_size, flip_h=False)
            views_used.append("front")
        else:
            # 후면만 있으면 임시로 사용
            front_patch = _prepare_view_patch(back_src, patch_size, flip_h=True)
            views_used.append("back_as_front")

        if back_src:
            back_patch = _prepare_view_patch(back_src, patch_size, flip_h=True)
            views_used.append("back")
        else:
            # 후면 없으면 정면을 어둡게 해서 대체
            back_patch = front_patch.copy()
            # darken
            from PIL import ImageEnhance
            back_patch = ImageEnhance.Brightness(back_patch.convert("RGB")).enhance(0.55)
            back_patch = back_patch.convert("RGBA")
            views_used.append("back_from_front_darkened")

        # 단일 정면 albedo (하위 호환)
        albedo_path = ctx.path("albedo.png")
        front_patch.save(albedo_path)

        # atlas: [front | back]
        atlas = Image.new("RGBA", (patch_size * 2, patch_size), (230, 230, 230, 255))
        atlas.paste(front_patch, (0, 0))
        atlas.paste(back_patch, (patch_size, 0))
        atlas_path = ctx.path("albedo_atlas.png")
        atlas.save(atlas_path)

        back_path = ctx.path("albedo_back.png")
        back_patch.save(back_path)

        side_path = None
        if side_src:
            side_patch = _prepare_view_patch(side_src, patch_size, flip_h=False)
            side_path = ctx.path("albedo_side.png")
            side_patch.save(side_path)
            views_used.append("side")

        mode = "multiview_atlas" if "back" in views_used else "front_cropped_square"
        warning = None
        if "back_from_front_darkened" in views_used:
            warning = "후면 이미지 없음 — 정면 어둡게 복제"

        return {
            "path": albedo_path,
            "atlas_path": atlas_path,
            "back_path": back_path,
            "side_path": side_path,
            "mode": mode,
            "views": views_used,
            "warning": warning,
            "size": patch_size,
            "source": front_src,
        }
    except Exception as e:
        if front_src:
            try:
                out = ctx.path("albedo.png")
                shutil.copy2(front_src, out)
                return {
                    "path": out,
                    "mode": "copy",
                    "warning": f"멀티뷰 처리 실패, 원본 복사: {e}",
                }
            except Exception as e2:
                return {"path": None, "mode": "solid", "warning": f"텍스처 실패: {e2}"}
        return {"path": None, "mode": "solid", "warning": f"텍스처 실패: {e}"}
