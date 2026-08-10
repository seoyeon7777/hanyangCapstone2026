#!/usr/bin/env python3
"""cloth_hoodie.blend 프로브 → ground_truth JSON.

Note: hoodie mesh is currently a top clone (no hood geometry).
This script documents honesty in GT notes — not a trained neural model.
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

PROBE_DIR = os.path.join(ROOT, "outputs", "_probe_hoodie")
BLEND = os.path.join(ROOT, "assets", "clothing", "cloth_hoodie.blend")
# fallback: some trees only have top clone named hoodie
if not os.path.exists(BLEND):
    BLEND = os.path.join(ROOT, "assets", "clothing", "cloth_top.blend")
OUT_JSON = os.path.join(ROOT, "assets", "clothing", "cloth_hoodie_ground_truth.json")
KEYS = ["shoulder", "chest", "sleeve", "length"]


def ensure_probe(force: bool = False):
    basis = os.path.join(PROBE_DIR, "basis.obj")
    if os.path.exists(basis) and not force:
        return
    if not os.path.exists(BLEND):
        raise SystemExit(f"missing blend: {BLEND}")
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
    gtype = "hoodie" if "hoodie" in EXPORT_BASE_MEASUREMENTS else "tshirt"
    names = ["basis"] + [f"{k}_{e}" for k in KEYS for e in ("min", "max")]
    measured = {}
    for n in names:
        path = os.path.join(PROBE_DIR, f"{n}.obj")
        if not os.path.exists(path):
            print("missing", path)
            continue
        measured[n] = measure_garment_obj(path, gtype)
        print(n, measured[n])

    basis = measured.get("basis") or {}
    base_label = dict(EXPORT_BASE_MEASUREMENTS.get("hoodie") or EXPORT_BASE_MEASUREMENTS.get("tshirt") or {})
    gt = {
        "source_blend": os.path.relpath(BLEND, ROOT),
        "source_template": "cloth_top" if "cloth_top" in BLEND or "hoodie" not in BLEND else "cloth_hoodie",
        "base_label_cm": base_label,
        "base_mesh_cm": {k: basis.get(k) for k in KEYS},
        "range_min_label_cm": {},
        "range_max_label_cm": {},
        "label_check_basis": mesh_to_label_cm(basis, gtype) if basis else {},
        "extremes_mesh_cm": measured,
        "notes": "hoodie is top-clone (no hood). rebuilt via scripts/rebuild_hoodie_ground_truth.py",
    }
    for k in KEYS:
        b, mn, mx = basis.get(k), measured.get(f"{k}_min", {}).get(k), measured.get(f"{k}_max", {}).get(k)
        if b is None or mn is None or mx is None or abs(b) < 1e-6 or not base_label.get(k):
            continue
        scale = b / base_label[k]
        rmin = round((b - mn) / scale, 2)
        rmax = round((mx - b) / scale, 2)
        gt["range_min_label_cm"][k] = abs(rmin) if abs(rmin) >= 0.5 else 6.0
        gt["range_max_label_cm"][k] = abs(rmax) if abs(rmax) >= 0.5 else 8.0

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(gt, f, ensure_ascii=False, indent=2)
    print("Wrote", OUT_JSON)


if __name__ == "__main__":
    main()
