"""의류 템플릿 카탈로그 로더."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any

from blender.config import BASE_DIR

CATALOG_PATH = os.path.join(BASE_DIR, "assets", "clothing", "garment_catalog.json")

# 하의로 취급 (측정 키/시뮬 pin 분기)
LOWER_BODY = {"pants", "trousers", "skirt", "shorts"}


@lru_cache(maxsize=1)
def load_catalog() -> dict[str, Any]:
    if not os.path.exists(CATALOG_PATH):
        return {"templates": {}, "aliases": {"tshirt": "top", "top": "top"}, "nearest_notes": {}}
    with open(CATALOG_PATH, encoding="utf-8") as f:
        return json.load(f)


def resolve_template(garment_type: str | None) -> dict[str, Any]:
    """garment_type → 템플릿 매칭 결과."""
    catalog = load_catalog()
    gtype = (garment_type or "tshirt").lower().strip()
    aliases = catalog.get("aliases") or {}
    templates = catalog.get("templates") or {}
    notes = catalog.get("nearest_notes") or {}

    template_id = aliases.get(gtype)
    exact = template_id == gtype or gtype in ("tshirt", "top", "shirt", "tee")
    if template_id is None:
        template_id = "top"
        exact = False
        note = f"미등록 카테고리 '{gtype}' → top 템플릿"
    else:
        note = None if exact or gtype in ("tshirt", "top", "shirt", "tee") else notes.get(gtype)

    tmpl = templates.get(template_id) or {
        "blend": f"assets/clothing/cloth_{template_id}.blend",
        "garment_file": template_id,
        "category": "upper",
        "measurement_keys": ["shoulder", "chest", "sleeve", "length"],
        "shape_key_type": "tshirt",
    }

    blend_rel = tmpl.get("blend") or f"assets/clothing/cloth_{template_id}.blend"
    blend_path = blend_rel if os.path.isabs(blend_rel) else os.path.join(BASE_DIR, blend_rel)

    return {
        "garment_type": gtype,
        "template_id": template_id,
        "garment_file": tmpl.get("garment_file", template_id),
        "blend_path": blend_path,
        "category": tmpl.get("category", "lower" if gtype in LOWER_BODY else "upper"),
        "measurement_keys": tmpl.get("measurement_keys") or ["shoulder", "chest", "sleeve", "length"],
        "shape_key_type": tmpl.get("shape_key_type", "tshirt"),
        "exact_match": bool(exact and os.path.exists(blend_path) and template_id == "top" and gtype in ("tshirt", "top", "shirt", "tee")),
        "nearest": not (gtype in ("tshirt", "top", "shirt", "tee")),
        "warning": note,
        "planned": catalog.get("planned_templates") or [],
        "is_lower": gtype in LOWER_BODY,
    }
