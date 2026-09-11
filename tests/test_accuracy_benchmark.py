"""정확도 벤치 메트릭/러너 단위 테스트 (Blender 불필요)."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


class MetricsTests(unittest.TestCase):
    def test_summarize_and_pass(self):
        from pipeline.eval.metrics import summarize_errors, pass_tolerance, aggregate_suite

        errs = {"chest": 0.8, "length": -1.2}
        m = summarize_errors(errs)
        self.assertTrue(m["within_1_5cm"])
        self.assertTrue(pass_tolerance(errs, 1.5))
        self.assertFalse(pass_tolerance({"chest": 2.0}, 1.5))
        agg = aggregate_suite([
            {"suite": "calibration", "passed": True, "metrics": {"mae_cm": 0.5}},
            {"suite": "calibration", "passed": False, "metrics": {"mae_cm": 2.0}},
            {"suite": "classification", "passed": True},
        ])
        self.assertEqual(agg["calibration"]["n"], 2)
        self.assertEqual(agg["calibration"]["pass_rate"], 0.5)


class RunnerPlantTests(unittest.TestCase):
    def test_plant_and_cpu_suites(self):
        from pipeline.eval.runner import run_benchmark

        cases_dir = tempfile.mkdtemp(prefix="bcases_")
        out = tempfile.mkdtemp(prefix="bout_")
        cases = [
            {
                "id": "plant1",
                "suite": "calibration",
                "garment_type": "tshirt",
                "target_measurements": {"shoulder": 44, "chest": 100, "sleeve": 20, "length": 65},
                "allow_plant": True,
                "tolerance_cm": 1.5,
            },
            {
                "id": "clf1",
                "suite": "classification",
                "expected_label": "pants",
                "accept_labels": ["pants", "shorts"],
                "seed": 9,
            },
            {
                "id": "sil1",
                "suite": "silhouette",
                "with_side": True,
                "min_abs_x_delta": 0.01,
                "min_abs_z_delta": 0.01,
            },
        ]
        for c in cases:
            with open(os.path.join(cases_dir, f"{c['id']}.json"), "w") as f:
                json.dump(c, f)

        report = run_benchmark(cases_dir, out, use_blender=False)
        self.assertEqual(len(report["results"]), 3)
        by_id = {r["id"]: r for r in report["results"]}
        self.assertTrue(by_id["plant1"]["passed"])
        self.assertTrue(by_id["sil1"]["passed"])
        self.assertTrue(os.path.exists(report["report_md"]))


class CasesOnDiskTests(unittest.TestCase):
    def test_repo_cases_load(self):
        from pipeline.eval.runner import load_cases

        cases = load_cases(os.path.join(ROOT, "benchmarks", "cases"))
        self.assertGreaterEqual(len(cases), 10)
        suites = {c.get("suite") for c in cases}
        self.assertIn("calibration", suites)
        self.assertIn("classification", suites)
        self.assertIn("field_pipeline", suites)


class ProfileRmseTests(unittest.TestCase):
    def test_matching_profile_low_rmse(self):
        from pipeline.eval.metrics import silhouette_profile_rmse

        ref = [0.2, 0.3, 0.4, 0.5]
        self.assertLess(silhouette_profile_rmse(ref, ref), 1e-6)
        worse = [0.5, 0.5, 0.5, 0.5]
        self.assertGreater(silhouette_profile_rmse(ref, worse), 0.05)

    def test_field_pipeline_skips_without_blender(self):
        from pipeline.eval.runner import run_field_pipeline_case

        r = run_field_pipeline_case(
            {
                "id": "fp_skip",
                "garment_type": "tshirt",
                "require_blender": True,
                "target_measurements": {"chest": 100},
            },
            output_root=tempfile.mkdtemp(),
            use_blender=False,
        )
        self.assertEqual(r.get("skip_reason"), "blender_unavailable")
        self.assertFalse(r.get("passed"))


if __name__ == "__main__":
    unittest.main()
