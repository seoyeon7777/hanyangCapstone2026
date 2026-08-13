"""Pattern-first 파이프라인 단위/통합 테스트."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from models.garment_spec import GarmentSpec
from models.pattern_draft import draft_pattern
from models.measure_garment import measure_pattern_2d, compare_measurements
from models.panel_mesher import assemble_pattern_mesh
from services.pattern_pipeline import run_pattern_pipeline


class TestPatternDraftAccuracy(unittest.TestCase):
    def test_tshirt_2d_measurements_within_tolerance(self):
        spec = GarmentSpec(
            category="tshirt",
            fit="regular",
            stretch="medium",
            measurements_cm={
                "chest": 88.0,
                "shoulder": 40.0,
                "sleeve": 20.0,
                "length": 65.0,
            },
            fabric={"cotton": 1.0},
        )
        pattern = draft_pattern(spec)
        measured = measure_pattern_2d(pattern)
        targets = spec.target_garment_cm()
        cmp_ = compare_measurements(targets, measured, spec.tolerance_cm)
        self.assertTrue(
            cmp_["pass"],
            msg=json.dumps(cmp_, ensure_ascii=False, indent=2),
        )

    def test_correction_loop_converges(self):
        spec = GarmentSpec(
            category="tshirt",
            fit="slim",
            stretch="high",
            measurements_cm={
                "chest": 92.0,
                "shoulder": 42.0,
                "sleeve": 22.0,
                "length": 70.0,
            },
            fabric={"cotton": 0.8, "spandex": 0.2},
        )
        with tempfile.TemporaryDirectory() as tmp:
            result = run_pattern_pipeline(
                spec,
                job_id="test-job",
                output_root=tmp,
                max_iters=5,
                run_drape=False,
            )
            self.assertTrue(result["compare"]["pass"], msg=json.dumps(result["compare"], indent=2))
            self.assertTrue(os.path.exists(result["artifacts"]["base_obj"]))
            self.assertTrue(os.path.exists(result["artifacts"]["pattern_svg"]))
            self.assertLessEqual(result["iterations"], 5)

    def test_assemble_writes_obj(self):
        spec = GarmentSpec(
            measurements_cm={
                "chest": 88.0,
                "shoulder": 40.0,
                "sleeve": 20.0,
                "length": 65.0,
            }
        )
        pattern = draft_pattern(spec)
        with tempfile.TemporaryDirectory() as tmp:
            obj = os.path.join(tmp, "g.obj")
            lm = os.path.join(tmp, "lm.json")
            info = assemble_pattern_mesh(pattern, obj, lm)
            self.assertTrue(os.path.exists(obj))
            self.assertGreater(info["vertex_count"], 20)
            self.assertAlmostEqual(info["chest_arc_cm"], spec.target_garment_cm()["chest"], places=3)


if __name__ == "__main__":
    unittest.main()
