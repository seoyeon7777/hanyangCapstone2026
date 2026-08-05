"""Vision 어댑터 — 분류/세그 (휴리스틱 + 교체 가능)."""

from __future__ import annotations

import os
import shutil
from typing import Any, Optional


GARMENT_LABELS = (
    "tshirt", "hoodie", "jacket", "coat", "pants", "skirt", "shorts", "dress",
)

# 파일명·힌트 한글/영문 별칭
_LABEL_HINTS = {
    "tshirt": ["tshirt", "t-shirt", "tee", "top", "shirt", "반팔", "티셔츠", "티"],
    "hoodie": ["hoodie", "hood", "sweatshirt", "후드", "후드티", "맨투맨"],
    "jacket": ["jacket", "자켓", "재킷", "점퍼"],
    "coat": ["coat", "코트", "아우터"],
    "pants": ["pants", "trousers", "바지", "슬랙스", "데님바지"],
    "skirt": ["skirt", "스커트", "치마"],
    "shorts": ["shorts", "반바지", "숏팬츠"],
    "dress": ["dress", "원피스", "드레스"],
}


def _match_label_in_text(text: str) -> Optional[str]:
    t = (text or "").lower()
    # 긴 키워드 우선
    scored = []
    for label, aliases in _LABEL_HINTS.items():
        for a in aliases:
            if a.lower() in t:
                scored.append((len(a), label))
    if not scored:
        return None
    scored.sort(reverse=True)
    return scored[0][1]


def _aspect_hint(image_path: str) -> Optional[str]:
    """세그 전 원본 비율로 하의/상의 힌트."""
    try:
        from PIL import Image
        import numpy as np
        img = Image.open(image_path).convert("RGBA")
        arr = np.array(img)
        alpha = arr[:, :, 3] if arr.shape[2] == 4 else None
        if alpha is not None and alpha.max() > 10:
            fg = alpha > 30
        else:
            gray = arr[:, :, :3].mean(axis=2)
            # 배경이 밝다고 가정 — 중앙 crop
            h, w = gray.shape
            crop = gray[h // 10: h - h // 10, w // 10: w - w // 10]
            fg = crop < 240
        if not fg.any():
            return None
        ys, xs = np.where(fg)
        bh = max(1, int(ys.max() - ys.min()))
        bw = max(1, int(xs.max() - xs.min()))
        aspect = bh / float(bw)
        if aspect >= 2.0:
            return "pants"
        if aspect >= 1.55:
            return "hoodie"
        if aspect <= 0.95:
            return "tshirt"
    except Exception:
        return None
    return None


def classify_garment(image_path: str, hint: Optional[str] = None) -> dict[str, Any]:
    """카테고리 분류.

    우선순위: 명시 hint > 파일명/경로 키워드 > 실루엣 비율 > fallback tshirt
    """
    if hint:
        label = hint.lower().strip()
        mapped = _match_label_in_text(label) or (
            label if label in GARMENT_LABELS else None
        )
        if mapped:
            return {"label": mapped, "confidence": 1.0, "source": "hint"}
        if label in ("top", "shirt"):
            return {"label": "tshirt", "confidence": 1.0, "source": "hint"}

    name = os.path.basename(image_path or "").lower()
    parent = os.path.basename(os.path.dirname(image_path or "")).lower()
    from_name = _match_label_in_text(f"{parent} {name}")
    if from_name:
        return {"label": from_name, "confidence": 0.6, "source": "filename"}

    aspect = _aspect_hint(image_path) if image_path and os.path.exists(image_path) else None
    if aspect:
        return {"label": aspect, "confidence": 0.45, "source": "aspect"}

    return {"label": "tshirt", "confidence": 0.35, "source": "fallback"}


def segment_garment(image_path: str, mask_out_path: str) -> dict[str, Any]:
    """배경 제거 / 옷 영역 추출.

    우선 rembg 시도 → 실패 시 원본 복사 fallback.
    """
    rgba_path = os.path.splitext(mask_out_path)[0] + "_rgba.png"
    try:
        from rembg import remove  # type: ignore
        from PIL import Image
        import io

        with open(image_path, "rb") as f:
            raw = f.read()
        out = remove(raw)
        img = Image.open(io.BytesIO(out)).convert("RGBA")
        img.save(rgba_path)

        alpha = img.split()[-1]
        alpha.save(mask_out_path)
        return {"ok": True, "mask_path": mask_out_path, "rgba_path": rgba_path, "engine": "rembg"}
    except Exception as e:
        try:
            from PIL import Image
            img = Image.open(image_path).convert("RGBA")
            img.save(rgba_path)
            mask = Image.new("L", img.size, 255)
            mask.save(mask_out_path)
        except Exception:
            shutil.copy2(image_path, rgba_path)
            mask_out_path = None
        return {
            "ok": False,
            "mask_path": mask_out_path,
            "rgba_path": rgba_path if os.path.exists(rgba_path) else None,
            "engine": "passthrough",
            "reason": str(e),
        }
