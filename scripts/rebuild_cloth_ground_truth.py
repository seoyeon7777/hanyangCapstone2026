#!/usr/bin/env python3
"""cloth_top.blend 프로브 → ground_truth JSON / MEASURE 상수 검증.

사용:
  BLENDER_PATH=... python3 scripts/rebuild_cloth_ground_truth.py
  # 또는 probe OBJ 가 outputs/_probe_cloth_top 에 있으면 Blender 없이 측정만
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from blender.config import BLENDER_PATH, SCRIPT_DIR
from models.garment_measure import measure_garment_obj, mesh_to_label_cm
from models.fitting_model import EXPORT_BASE_MEASUREMENTS


PROBE_DIR = os.path.join(ROOT, "outputs", "_probe_cloth_top")
BLEND = os.path.join(ROOT, "assets", "clothing", "cloth_top.blend")
OUT_JSON = os.path.join(ROOT, "assets", "clothing", "cloth_top_ground_truth.json")


def ensure_probe():
    basis = os.path.join(PROBE_DIR, "basis.obj")
    if os.path.exists(basis):
        return
    os.makedirs(PROBE_DIR, exist_ok=True)
    cmd = [
        BLENDER_PATH, "--background",
        "--python", os.path.join(SCRIPT_DIR, "probe_cloth_shapekeys.py"),
        "--", BLEND, PROBE_DIR,
    ]
    print("Running:", " ".join(cmd))
    subprocess.check_call(cmd)


def main():
    ensure_probe()
    names = [
        "basis", "sleeve_min", "sleeve_max", "length_min", "length_max",
        "chest_min", "chest_max", "shoulder_min", "shoulder_max",
    ]
    measured = {n: measure_garment_obj(os.path.join(PROBE_DIR, f"{n}.obj"), "tshirt") for n in names}
    basis = measured["basis"]
    base_label = EXPORT_BASE_MEASUREMENTS["tshirt"]

    gt = {
        "source_blend": "assets/clothing/cloth_top.blend",
        "base_label_cm": base_label,
        "base_mesh_cm": basis,
        "range_min_label_cm": {},
        "range_max_label_cm": {},
        "label_check_basis": mesh_to_label_cm(basis, "tshirt"),
        "extremes_mesh_cm": measured,
    }
    for k in base_label:
        b, mn, mx = basis[k], measured[f"{k}_min"][k], measured[f"{k}_max"][k]
        scale = b / base_label[k]
        gt["range_min_label_cm"][k] = round((b - mn) / scale, 2)
        gt["range_max_label_cm"][k] = round((mx - b) / scale, 2)

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(gt, f, ensure_ascii=False, indent=2)
    print(json.dumps(gt, indent=2, ensure_ascii=False))
    print("Wrote", OUT_JSON)


if __name__ == "__main__":
    main()
