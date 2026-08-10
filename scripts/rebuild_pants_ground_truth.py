#!/usr/bin/env python3
"""cloth_pants.blend 프로브 → ground_truth JSON + MEASURE/RANGE 상수 출력."""

from __future__ import annotations

import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from blender.config import BLENDER_PATH, SCRIPT_DIR
from models.garment_measure import measure_garment_obj, mesh_to_label_cm, MEASURE_BASE_MESH_CM
from models.fitting_model import EXPORT_BASE_MEASUREMENTS

PROBE_DIR = os.path.join(ROOT, "outputs", "_probe_pants")
BLEND = os.path.join(ROOT, "assets", "clothing", "cloth_pants.blend")
OUT_JSON = os.path.join(ROOT, "assets", "clothing", "cloth_pants_ground_truth.json")


def ensure_probe(force: bool = False):
    basis = os.path.join(PROBE_DIR, "basis.obj")
    if os.path.exists(basis) and not force:
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
    force = "--force" in sys.argv
    ensure_probe(force=force)
    keys = ["waist", "hip", "inseam", "length"]
    names = ["basis"] + [f"{k}_{e}" for k in keys for e in ("min", "max")]
    measured = {}
    for n in names:
        path = os.path.join(PROBE_DIR, f"{n}.obj")
        if not os.path.exists(path):
            print("missing", path)
            continue
        measured[n] = measure_garment_obj(path, "pants")
        print(n, measured[n])

    basis = measured["basis"]
    base_label = dict(EXPORT_BASE_MEASUREMENTS["pants"])

    # MEASURE_BASE 를 basis 로 맞추면 label_check ≈ base_label
    MEASURE_BASE_MESH_CM["pants"] = {
        k: float(basis[k]) for k in keys if basis.get(k) is not None
    }

    gt = {
        "source_blend": "assets/clothing/cloth_pants.blend",
        "base_label_cm": base_label,
        "base_mesh_cm": {k: basis.get(k) for k in keys},
        "range_min_label_cm": {},
        "range_max_label_cm": {},
        "label_check_basis": mesh_to_label_cm(basis, "pants"),
        "extremes_mesh_cm": measured,
    }
    for k in keys:
        b, mn, mx = basis.get(k), measured.get(f"{k}_min", {}).get(k), measured.get(f"{k}_max", {}).get(k)
        if b is None or mn is None or mx is None or abs(b) < 1e-6:
            continue
        scale = b / base_label[k]
        rmin = round((b - mn) / scale, 2)
        rmax = round((mx - b) / scale, 2)
        # hip 등 변화가 너무 작으면 최소 범위 보장
        if abs(rmin) < 0.5 and abs(rmax) < 0.5:
            rmin, rmax = 8.0, 10.0
        gt["range_min_label_cm"][k] = abs(rmin)
        gt["range_max_label_cm"][k] = abs(rmax)

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(gt, f, ensure_ascii=False, indent=2)
    print(json.dumps({
        "base_mesh_cm": gt["base_mesh_cm"],
        "range_min_label_cm": gt["range_min_label_cm"],
        "range_max_label_cm": gt["range_max_label_cm"],
        "label_check_basis": gt["label_check_basis"],
    }, indent=2, ensure_ascii=False))
    print("Wrote", OUT_JSON)


if __name__ == "__main__":
    main()
