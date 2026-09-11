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

    def test_flat_chest_auto_doubled_keeps_slim_fit(self):
        """단면→둘레 후 템플릿 하한만 적용 (ease로 부풀리지 않음, 크롭 기장 유지)."""
        from models.fitting_model import normalize_garment_measurements_for_wear

        # height 160 → avatar M; template chest floor 92
        out, notes = normalize_garment_measurements_for_wear(
            {"shoulder": 37.5, "chest": 43.0, "sleeve": 17.0, "length": 51.0},
            garment_type="tshirt",
            height=160,
            weight=50,
        )
        self.assertAlmostEqual(out["chest"], 92.0, places=1)  # max(86, template 92)
        self.assertAlmostEqual(out["shoulder"], 44.0, places=1)
        self.assertAlmostEqual(out["length"], 51.0, places=1)
        self.assertAlmostEqual(out["sleeve"], 17.0, places=1)
        self.assertTrue(any("단면→둘레" in n for n in notes))
        self.assertTrue(any("템플릿 하한" in n for n in notes))

    def test_flat_chest_soft_floor_only_when_extreme(self):
        from models.fitting_model import normalize_garment_measurements_for_wear

        # avatar S; chart 35→70 still below template 92
        out, notes = normalize_garment_measurements_for_wear(
            {"chest": 35.0, "shoulder": 37.5, "length": 51.0},
            garment_type="tshirt",
            height=155,
            weight=48,
        )
        self.assertAlmostEqual(out["chest"], 92.0, places=1)
        self.assertTrue(any("템플릿 하한" in n for n in notes))

    def test_circumference_chest_not_doubled(self):
        from models.fitting_model import normalize_garment_measurements_for_wear

        out, notes = normalize_garment_measurements_for_wear(
            {"chest": 96.0, "shoulder": 44.0, "sleeve": 20.0, "length": 65.0},
            garment_type="tshirt",
            height=165,
            weight=55,
        )
        self.assertAlmostEqual(out["chest"], 96.0, places=1)
        self.assertFalse(any("단면→둘레" in n for n in notes))

    def test_measure_fusion_exposes_normalize_notes(self):
        m = JobManifest.from_dict({
            "body": {"height": 160, "weight": 50},
            "garment_type": "tshirt",
            "measurements": {
                "shoulder": 37.5,
                "chest": 43.0,
                "sleeve": 17.0,
                "length": 51.0,
            },
            "images": {},
        })
        ctx = StageContext(
            manifest=m,
            result=JobResult(job_id=m.job_id),
            output_dir=os.path.join(ROOT, "outputs", "_test_job_norm"),
        )
        ctx = measure_fusion.run(ctx)
        self.assertAlmostEqual(ctx.manifest.measurements["chest"], 92.0, places=1)
        self.assertAlmostEqual(ctx.manifest.measurements["length"], 51.0, places=1)
        self.assertTrue(ctx.result.fit.get("normalize_notes"))
        self.assertEqual(
            ctx.extras["measurement_sources"].get("chest"),
            "user_normalized",
        )


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
