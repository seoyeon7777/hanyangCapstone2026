"""멀티뷰 albedo 준비: front/back/side 세그 → 크롭 → atlas (+ 측면 보간)."""

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
    scale = min(size / img.size[0], size / img.size[1])
    nw, nh = max(1, int(img.size[0] * scale)), max(1, int(img.size[1] * scale))
    img = img.resize((nw, nh), Image.Resampling.LANCZOS)
    ox = (size - nw) // 2
    oy = (size - nh) // 2
    canvas.paste(img, (ox, oy), img)
    return canvas


def _edge_blend_side(base, side, edge_frac: float = 0.22, strength: float = 0.7):
    """측면 색을 정면/후면 좌·우 가장자리에 보간해 솔기 단차를 줄인다."""
    from PIL import Image, ImageDraw

    w, h = base.size
    side = side.resize((w, h), Image.Resampling.LANCZOS).convert("RGBA")
    side_f = side.transpose(Image.FLIP_LEFT_RIGHT)
    out = base.convert("RGBA")

    edge = max(1, int(w * edge_frac))
    mask_l = Image.new("L", (w, h), 0)
    mask_r = Image.new("L", (w, h), 0)
    draw_l = ImageDraw.Draw(mask_l)
    draw_r = ImageDraw.Draw(mask_r)
    for x in range(edge):
        t = 1.0 - (x / float(edge))
        a = int(255 * t * strength)
        draw_l.line([(x, 0), (x, h - 1)], fill=a)
        draw_r.line([(w - 1 - x, 0), (w - 1 - x, h - 1)], fill=a)

    out = Image.composite(side, out, mask_l)
    out = Image.composite(side_f, out, mask_r)
    return out


def _resolve_view_source(ctx: StageContext, view: str) -> Optional[str]:
    extras_key = f"seg_rgba_{view}" if view != "front" else "seg_rgba"
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
    """front/back/side → albedo.png + albedo_atlas.png.

    atlas 레이아웃:
      - side 없음: 1×2  [front | back]
      - side 있음: 2×2
            [front | back ]
            [side  | sideF]   (sideF = 좌우 반전, 반대면용)
    """
    try:
        from PIL import Image
        from PIL import ImageEnhance
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
            front_patch = _prepare_view_patch(back_src, patch_size, flip_h=True)
            views_used.append("back_as_front")

        if back_src:
            back_patch = _prepare_view_patch(back_src, patch_size, flip_h=True)
            views_used.append("back")
        else:
            back_patch = front_patch.copy()
            back_patch = ImageEnhance.Brightness(back_patch.convert("RGB")).enhance(0.55)
            back_patch = back_patch.convert("RGBA")
            views_used.append("back_from_front_darkened")

        side_path = None
        side_patch = None
        if side_src:
            side_patch = _prepare_view_patch(side_src, patch_size, flip_h=False)
            side_path = ctx.path("albedo_side.png")
            side_patch.save(side_path)
            views_used.append("side")
            # 정면/후면 가장자리에 측면 색 보간
            front_patch = _edge_blend_side(front_patch, side_patch)
            back_patch = _edge_blend_side(back_patch, side_patch)
            views_used.append("side_edge_blend")

        albedo_path = ctx.path("albedo.png")
        front_patch.save(albedo_path)

        # detail 뷰가 있으면 정면 중앙에 오버레이 패치
        detail_src = _resolve_view_source(ctx, "detail")
        if detail_src:
            try:
                detail_patch = _prepare_view_patch(detail_src, patch_size // 2, flip_h=False)
                # 중앙 배치 + 알파 합성
                dw, dh = detail_patch.size
                ox = (patch_size - dw) // 2
                oy = (patch_size - dh) // 2 + patch_size // 10
                # 가장자리 페더
                from PIL import ImageFilter
                alpha = detail_patch.split()[-1].filter(ImageFilter.GaussianBlur(4))
                detail_rgb = detail_patch.copy()
                detail_rgb.putalpha(alpha)
                front_patch.paste(detail_rgb, (ox, oy), detail_rgb)
                front_patch.save(albedo_path)
                views_used.append("detail_overlay")
            except Exception:
                pass

        back_path = ctx.path("albedo_back.png")
        back_patch.save(back_path)

        if side_patch is not None:
            # 2×2 atlas (PIL y=0 = 이미지 상단 = Blender UV v=1)
            # 상단: front | back   /  하단: side | sideF
            atlas = Image.new("RGBA", (patch_size * 2, patch_size * 2), (230, 230, 230, 255))
            atlas.paste(front_patch, (0, 0))
            atlas.paste(back_patch, (patch_size, 0))
            atlas.paste(side_patch, (0, patch_size))
            side_flipped = side_patch.transpose(Image.FLIP_LEFT_RIGHT)
            atlas.paste(side_flipped, (patch_size, patch_size))
            atlas_layout = "2x2"
            mode = "multiview_atlas_side"
        else:
            atlas = Image.new("RGBA", (patch_size * 2, patch_size), (230, 230, 230, 255))
            atlas.paste(front_patch, (0, 0))
            atlas.paste(back_patch, (patch_size, 0))
            atlas_layout = "1x2"
            mode = "multiview_atlas" if "back" in views_used else "front_cropped_square"

        atlas_path = ctx.path("albedo_atlas.png")
        atlas.save(atlas_path)

        warning = None
        if "back_from_front_darkened" in views_used:
            warning = "후면 이미지 없음 — 정면 어둡게 복제"
        if side_patch is not None and warning:
            warning = warning + "; 측면 보간 적용"
        elif side_patch is not None:
            warning = None

        return {
            "path": albedo_path,
            "atlas_path": atlas_path,
            "atlas_layout": atlas_layout,
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
