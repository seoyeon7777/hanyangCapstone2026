#!/usr/bin/env python3
"""Validate benchmark case JSON files (schema + required fields)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "benchmarks" / "cases"

ALLOWED_PROVENANCE = {
    "synthetic_template",
    "synthetic_pipeline",
    "synthetic_contract",
    "synthetic_fixture",
    "synthetic_photo_like",
    "field_tape",
    "field_photo",
}

REQUIRED = {
    "calibration": {"id", "suite", "garment_type", "target_measurements"},
    "classification": {"id", "suite", "expected_label"},
    "silhouette": {"id", "suite"},
    "measure_consistency": {"id", "suite", "garment_type"},
    "field_pipeline": {"id", "suite", "garment_type"},
    "neural_contract": {"id", "suite"},
}


def validate_case(path: Path, data: dict) -> list[str]:
    errs: list[str] = []
    if data.get("disabled"):
        return errs
    suite = data.get("suite") or ""
    req = REQUIRED.get(suite)
    if not req:
        errs.append(f"{path.name}: unknown suite '{suite}'")
        return errs
    missing = req - set(data.keys())
    if missing:
        errs.append(f"{path.name}: missing {sorted(missing)}")
    if "id" in data and data["id"] != path.stem and not path.stem.startswith("_TEMPLATE"):
        errs.append(f"{path.name}: id '{data.get('id')}' != filename stem")
    prov = data.get("provenance")
    if prov is not None and prov not in ALLOWED_PROVENANCE:
        errs.append(f"{path.name}: bad provenance '{prov}'")
    if suite == "field_pipeline":
        has_img = bool(data.get("image_path") or (data.get("images") or {}).get("front"))
        if not has_img:
            errs.append(f"{path.name}: field_pipeline needs image_path or images.front")
    if data.get("provenance") == "field_tape":
        tape = data.get("tape_meta") or {}
        if not tape.get("measured_at") and not tape.get("notes"):
            errs.append(f"{path.name}: field_tape should include tape_meta")
    return errs


def main() -> int:
    errs: list[str] = []
    n = 0
    for path in sorted(CASES.glob("*.json")):
        if path.name.startswith("_TEMPLATE"):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            errs.append(f"{path.name}: JSON error {e}")
            continue
        n += 1
        errs.extend(validate_case(path, data))
    # field_tape coverage info (not an error)
    tape_n = 0
    for path in CASES.glob("*.json"):
        if path.name.startswith("_TEMPLATE"):
            continue
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if d.get("provenance") == "field_tape":
            tape_n += 1
    print(f"validated {n} cases; field_tape cases={tape_n}")
    if errs:
        print("ERRORS:")
        for e in errs:
            print(" -", e)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
