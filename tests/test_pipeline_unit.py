"""파이프라인 스키마 / 치수 융합 단위 테스트 (Blender 불필요)."""

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from pipeline.schemas.manifest import JobManifest
from pipeline.stages import StageContext
from pipeline.schemas.manifest import JobResult
from pipeline.stages import measure_fusion, ingest, template_match


class ManifestTests(unittest.TestCase):
    def test_from_dict_nested_body(self):
        m = JobManifest.from_dict({
            "body": {"height": 165, "weight": 55},
            "measurements": {"shoulder": 44, "chest": 100, "sleeve": 20, "length": 65},
            "garment_type": "tshirt",
        })
        self.assertEqual(m.body.height, 165)
        self.assertEqual(m.options.phase, "P0")

    def test_from_dict_legacy_flat(self):
        m = JobManifest.from_dict({
            "height": 170,
            "weight": 60,
            "measurements": {},
        })
        self.assertEqual(m.body.height, 170)


class MeasureFusionTests(unittest.TestCase):
    def test_user_measurements_drive_shapekeys(self):
        m = JobManifest.from_dict({
            "body": {"height": 165, "weight": 55},
            "garment_type": "tshirt",
            "measurements": {"shoulder": 44, "chest": 100, "sleeve": 20, "length": 65},
            "images": {},
        })
        ctx = StageContext(
            manifest=m,
            result=JobResult(job_id=m.job_id),
            output_dir=os.path.join(ROOT, "outputs", "_test_job"),
        )
        ctx = measure_fusion.run(ctx)
        self.assertEqual(ctx.result.avatar_size, "M")
        # basis와 동일 → shape key ~0
        self.assertAlmostEqual(ctx.extras["shape_keys"].get("chest", 0), 0.0, places=2)
        self.assertAlmostEqual(ctx.extras["shape_keys"].get("shoulder", 0), 0.0, places=2)

    def test_defaults_fill_missing(self):
        m = JobManifest.from_dict({
            "body": {"height": 150, "weight": 45},
            "garment_type": "tshirt",
            "measurements": {"chest": 100},
            "images": {},
        })
        ctx = StageContext(
            manifest=m,
            result=JobResult(job_id=m.job_id),
            output_dir=os.path.join(ROOT, "outputs", "_test_job2"),
        )
        ctx = measure_fusion.run(ctx)
        self.assertEqual(ctx.result.avatar_size, "S")
        self.assertIn("shoulder", ctx.manifest.measurements)
        self.assertTrue(any("기본값" in w for w in ctx.result.warnings))


class TemplateMatchTests(unittest.TestCase):
    def test_tshirt_maps_to_top_blend(self):
        m = JobManifest.from_dict({
            "body": {"height": 165, "weight": 55},
            "garment_type": "tshirt",
            "measurements": {"shoulder": 44, "chest": 100, "sleeve": 20, "length": 65},
        })
        ctx = StageContext(
            manifest=m,
            result=JobResult(job_id=m.job_id),
            output_dir=os.path.join(ROOT, "outputs", "_test_job3"),
            extras={"avatar_size": "M", "shape_keys": {}},
        )
        ctx = template_match.run(ctx)
        self.assertEqual(ctx.extras["garment_file"], "top")
        self.assertTrue(os.path.exists(ctx.extras["blend_path"]))


if __name__ == "__main__":
    unittest.main()
