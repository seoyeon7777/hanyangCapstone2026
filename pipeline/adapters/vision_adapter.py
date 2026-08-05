"""Vision 어댑터 — P0 stub / 교체 가능 인터페이스."""

from __future__ import annotations

import os
import shutil
from typing import Any, Optional


GARMENT_LABELS = (
    "tshirt", "hoodie", "jacket", "coat", "pants", "skirt", "shorts", "dress",
)


def classify_garment(image_path: str, hint: Optional[str] = None) -> dict[str, Any]:
    """카테고리 분류.

    P0: hint가 있으면 신뢰도 1.0으로 채택.
    파일명 휴리스틱 → 기본 tshirt.
    추후 torch/onnx 분류기로 교체.
    """
    if hint:
        label = hint.lower()
        if label in GARMENT_LABELS or label in ("top", "shirt"):
            return {"label": "tshirt" if label in ("top", "shirt") else label,
                    "confidence": 1.0, "source": "hint"}

    name = os.path.basename(image_path).lower()
    for label in GARMENT_LABELS:
        if label in name:
            return {"label": label, "confidence": 0.55, "source": "filename"}

    return {"label": "tshirt", "confidence": 0.4, "source": "fallback"}


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

        # 알파를 마스크로 저장
        alpha = img.split()[-1]
        alpha.save(mask_out_path)
        return {"ok": True, "mask_path": mask_out_path, "rgba_path": rgba_path, "engine": "rembg"}
    except Exception as e:
        # fallback: 원본 복사
        try:
            from PIL import Image
            img = Image.open(image_path).convert("RGBA")
            img.save(rgba_path)
            # full-white mask
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
