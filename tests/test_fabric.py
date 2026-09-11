"""원단/소재 정규화 단위 테스트."""

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from models.fabric import normalize_fabric, resolve_fabric_props, stretch_scale
from pipeline.schemas.manifest import JobManifest, JobResult
from pipeline.stages import StageContext
from pipeline.stages import fabric_resolve


class NormalizeTests(unittest.TestCase):
    def test_percent_ui(self):
        f = normalize_fabric({"cotton": 80, "spandex": 20})
        self.assertAlmostEqual(f["cotton"], 0.8, places=3)
        self.assertAlmostEqual(f["spandex"], 0.2, places=3)

    def test_korean_alias(self):
        f = normalize_fabric({"면": 70, "스판": 30})
        self.assertIn("cotton", f)
        self.assertIn("spandex", f)
        self.assertAlmostEqual(f["cotton"], 0.7, places=3)

    def test_json_string(self):
        f = normalize_fabric('{"cotton": 100}')
        self.assertAlmostEqual(f["cotton"], 1.0, places=3)


class ResolveTests(unittest.TestCase):
    def test_denim_stiffer_than_silk(self):
        d = resolve_fabric_props({"denim": 100})
        s = resolve_fabric_props({"silk": 100})
        self.assertGreater(d["bending"], s["bending"])
        self.assertLess(d["elasticity"], s["elasticity"] + 0.5)  # denim low e

    def test_stretch_high_boosts_elasticity(self):
        base = resolve_fabric_props({"cotton": 100}, stretch="보통")
        high = resolve_fabric_props({"cotton": 100}, stretch="높음")
        self.assertGreater(high["elasticity"], base["elasticity"])

    def test_knit_spandex_very_elastic(self):
        p = resolve_fabric_props({"knit": 70, "spandex": 30})
        self.assertGreater(p["elasticity"], 0.5)


class StageTests(unittest.TestCase):
    def test_fabric_stage_writes_result(self):
        m = JobManifest.from_dict({
            "body": {"height": 165, "weight": 55},
            "measurements": {},
            "fabric": {"면": 80, "스판덱스": 20},
            "stretch": "높음",
        })
        ctx = StageContext(
            manifest=m,
            result=JobResult(job_id=m.job_id),
            output_dir="/tmp",
        )
        ctx = fabric_resolve.run(ctx)
        self.assertIn("cotton", ctx.manifest.fabric)
        self.assertIn("spandex", ctx.manifest.fabric)
        self.assertEqual(ctx.result.fabric["summary_ko"].count("%"), 2)
        self.assertGreater(ctx.result.fabric["elasticity"], 0.2)


class StretchScaleTests(unittest.TestCase):
    def test_unknown_defaults_one(self):
        self.assertEqual(stretch_scale("뭔가"), 1.0)
        self.assertEqual(stretch_scale("낮음"), 0.7)


if __name__ == "__main__":
    unittest.main()
