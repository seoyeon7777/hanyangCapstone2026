"""치수 OCR / 텍스트·이미지 추정 어댑터.

우선순위 소스:
  1) manifest.measurement_text (사용자가 붙여넣은 사이즈표 텍스트)
  2) pytesseract (설치·tesseract 있을 때 이미지 OCR)
  3) 실루엣 비율 휴리스틱 (대략치, 신뢰도 낮음)
"""

from __future__ import annotations

import os
import re
from typing import Any, Optional


# 한글/영문 키 매핑
_KEY_ALIASES = {
    "shoulder": ["shoulder", "어깨", "어깨너비", "어깨폭"],
    "chest": ["chest", "bust", "가슴", "가슴둘레", "가슴폭", "흉위"],
    "sleeve": ["sleeve", "소매", "소매길이", "소매기장"],
    "length": ["length", "총장", "총기장", "기장", "옷기장", "전체기장"],
    "waist": ["waist", "허리", "허리둘레", "웨이스트"],
    "hip": ["hip", "hips", "엉덩이", "엉덩이둘레", "힙"],
    "inseam": ["inseam", "밑위", "인심", "안쪽기장", "밑단기장"],
}


def _compile_patterns() -> list[tuple[str, re.Pattern]]:
    patterns = []
    for key, aliases in _KEY_ALIASES.items():
        alt = "|".join(re.escape(a) for a in aliases)
        # "어깨 44", "어깨:44cm", "shoulder=44.5"
        patterns.append((
            key,
            re.compile(
                rf"(?:{alt})\s*[:：=\-]?\s*(\d{{2,3}}(?:\.\d+)?)\s*(?:cm|CM)?",
                re.IGNORECASE,
            ),
        ))
        # "44cm 어깨" 역순
        patterns.append((
            key,
            re.compile(
                rf"(\d{{2,3}}(?:\.\d+)?)\s*(?:cm|CM)?\s*(?:{alt})",
                re.IGNORECASE,
            ),
        ))
    return patterns


_PATTERNS = _compile_patterns()


def parse_measurement_text(text: str) -> dict[str, float]:
    """사이즈표/라벨 텍스트에서 cm 치수 추출."""
    if not text or not str(text).strip():
        return {}
    found: dict[str, float] = {}
    for key, pat in _PATTERNS:
        if key in found:
            continue
        m = pat.search(text)
        if not m:
            continue
        val = float(m.group(1))
        if 10.0 <= val <= 200.0:
            found[key] = val
    return found


def ocr_image_tesseract(image_path: str) -> tuple[str, str]:
    """pytesseract로 텍스트 추출. 실패 시 ('', reason)."""
    try:
        import pytesseract
        from PIL import Image, ImageOps, ImageFilter, ImageEnhance
    except ImportError:
        return "", "pytesseract/Pillow 없음"

    try:
        img = Image.open(image_path).convert("RGB")
        # 전처리: 대비↑, 샤픈, 그레이스케일
        g = ImageOps.grayscale(img)
        g = ImageEnhance.Contrast(g).enhance(1.8)
        g = g.filter(ImageFilter.SHARPEN)
        # 작은 이미지는 업스케일
        if max(g.size) < 900:
            scale = 900 / max(g.size)
            g = g.resize((int(g.size[0] * scale), int(g.size[1] * scale)))
        config = "--psm 6"
        try:
            text = pytesseract.image_to_string(g, lang="kor+eng", config=config)
        except Exception:
            text = pytesseract.image_to_string(g, lang="eng", config=config)
        return (text or "").strip(), "tesseract"
    except Exception as e:
        return "", f"tesseract 실패: {e}"


def estimate_from_silhouette(
    mask_path: str,
    garment_type: str = "tshirt",
    height_cm: Optional[float] = None,
) -> dict[str, float]:
    """마스크 bbox 비율로 상의 치수 대략 추정 (신뢰도 낮음)."""
    try:
        from PIL import Image
        import numpy as np
    except ImportError:
        return {}

    if not mask_path or not os.path.exists(mask_path):
        return {}

    img = Image.open(mask_path).convert("L")
    arr = np.array(img)
    fg = arr > 30
    if not fg.any():
        return {}

    ys, xs = np.where(fg)
    y0, y1 = int(ys.min()), int(ys.max())
    x0, x1 = int(xs.min()), int(xs.max())
    h = max(1, y1 - y0)
    w = max(1, x1 - x0)
    aspect = h / float(w)  # 세로/가로

    # 참조: 키로 스케일 (없으면 165)
    H = float(height_cm or 165.0)
    # 상의 총기장 ≈ 키의 0.38~0.42
    length = round(H * 0.40 * min(1.15, max(0.85, aspect / 1.3)), 1)
    chest = round(40.0 + w / float(arr.shape[1]) * 90.0, 1)  # 매우 거친 추정
    chest = float(np.clip(chest, 80.0, 130.0))
    shoulder = round(chest * 0.42, 1)
    sleeve = round(length * 0.32, 1)

    g = (garment_type or "tshirt").lower()
    if g in ("pants", "trousers", "shorts", "skirt"):
        waist = round(chest * 0.72, 1)
        hip = round(chest * 0.95, 1)
        inseam = round(H * 0.45, 1)
        plen = round(H * 0.58, 1)
        return {"waist": waist, "hip": hip, "inseam": inseam, "length": plen}

    if g in ("hoodie", "sweatshirt"):
        return {
            "shoulder": shoulder,
            "chest": round(chest * 1.05, 1),
            "sleeve": round(sleeve * 2.4, 1),
            "length": round(length * 1.05, 1),
        }

    return {
        "shoulder": shoulder,
        "chest": chest,
        "sleeve": sleeve,
        "length": length,
    }


def extract_measurements(
    *,
    measurement_text: Optional[str] = None,
    image_path: Optional[str] = None,
    mask_path: Optional[str] = None,
    garment_type: str = "tshirt",
    height_cm: Optional[float] = None,
    allow_silhouette_estimate: bool = True,
) -> dict[str, Any]:
    """통합 추출. measurements + meta."""
    sources: dict[str, str] = {}
    measurements: dict[str, float] = {}

    text_meas = parse_measurement_text(measurement_text or "")
    for k, v in text_meas.items():
        measurements[k] = v
        sources[k] = "text"

    ocr_engine = None
    if image_path and os.path.exists(image_path):
        raw, engine = ocr_image_tesseract(image_path)
        if raw.strip():
            ocr_engine = engine
            for k, v in parse_measurement_text(raw).items():
                if k not in measurements:
                    measurements[k] = v
                    sources[k] = "ocr"

    if allow_silhouette_estimate and mask_path and os.path.exists(mask_path):
        est = estimate_from_silhouette(mask_path, garment_type, height_cm)
        for k, v in est.items():
            if k not in measurements:
                measurements[k] = v
                sources[k] = "silhouette_estimate"

    return {
        "measurements": measurements,
        "sources": sources,
        "ocr_engine": ocr_engine,
        "text_used": bool(text_meas),
    }
