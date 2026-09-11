"""템플릿 카탈로그 + runner 단계 분리 테스트."""

import os
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from pipeline.adapters.catalog import resolve_template, load_catalog, LOWER_BODY
from pipeline.schemas.manifest import JobManifest, JobResult
from pipeline.stages import StageContext
from pipeline.stages import template_match


class CatalogTests(unittest.TestCase):
    def test_catalog_loads(self):
        cat = load_catalog()
        self.assertIn("top", cat["templates"])
        self.assertIn("hoodie", cat["templates"])
        self.assertIn("pants", cat["templates"])
        self.assertEqual(cat["aliases"]["tshirt"], "top")

    def test_hoodie_exact_template(self):
        m = resolve_template("hoodie")
        self.assertEqual(m["template_id"], "hoodie")
        self.assertFalse(m["nearest"])
        self.assertTrue(os.path.exists(m["blend_path"]))
        self.assertEqual(m["shape_key_type"], "hoodie")

    def test_pants_exact_lower(self):
        m = resolve_template("pants")
        self.assertTrue(m["is_lower"])
        self.assertEqual(m["garment_file"], "pants")
        self.assertEqual(m["template_id"], "pants")
        self.assertTrue(os.path.exists(m["blend_path"]))
        self.assertEqual(m["measurement_keys"][0], "waist")

    def test_jacket_exact_nearest_clone(self):
        m = resolve_template("jacket")
        self.assertEqual(m["template_id"], "jacket")
        self.assertFalse(m["nearest"])
        self.assertTrue(m["exact_match"])
        self.assertTrue(os.path.exists(m["blend_path"]))
        self.assertEqual(m["shape_key_type"], "jacket")

    def test_tshirt_exact(self):
        m = resolve_template("tshirt")
        self.assertFalse(m["nearest"])
        self.assertTrue(os.path.exists(m["blend_path"]))


class TemplateStageTests(unittest.TestCase):
    def test_stage_sets_blend(self):
        man = JobManifest.from_dict({
            "body": {"height": 165, "weight": 55},
            "garment_type": "jacket",
            "measurements": {},
        })
        ctx = StageContext(
            manifest=man,
            result=JobResult(job_id=man.job_id),
            output_dir="/tmp",
        )
        ctx = template_match.run(ctx)
        self.assertEqual(ctx.extras["garment_file"], "jacket")
        self.assertTrue(os.path.exists(ctx.extras["blend_path"]))
        self.assertEqual(ctx.extras["avatar_size"], "M")
        self.assertEqual(ctx.extras["shape_key_type"], "jacket")


class RunnerStepsTests(unittest.TestCase):
    def test_resolve_fabric_params_respects_override(self):
        from services.blender_runner import resolve_fabric_params
        e, b = resolve_fabric_params({
            "fabric": {"cotton": 100},
            "fabric_elasticity": 0.55,
            "fabric_bending": 12.0,
        })
        self.assertAlmostEqual(e, 0.55)
        self.assertAlmostEqual(b, 12.0)

    def test_run_blender_honors_skip_flags(self):
        from services import blender_runner as br

        calls = []

        def fake_step_export(**kwargs):
            calls.append("export")
            return kwargs["output_obj"]

        def fake_step_simulate(**kwargs):
            calls.append("simulate")
            return {"sim_obj_path": kwargs["sim_obj_path"], "fit": {"fit_result": "good", "avg_pressure": 0.2}}

        def fake_step_texture(**kwargs):
            calls.append("texture")
            return None

        def fake_step_render(**kwargs):
            calls.append("render")
            return []

        with mock.patch.object(br, "step_export", side_effect=fake_step_export), \
             mock.patch.object(br, "step_simulate", side_effect=fake_step_simulate), \
             mock.patch.object(br, "step_texture_glb", side_effect=fake_step_texture), \
             mock.patch.object(br, "step_render", side_effect=fake_step_render):
            # only simulate+render, skip export using existing obj path
            import tempfile
            out = tempfile.mkdtemp(prefix="runner_")
            shaped = os.path.join(out, "cloth_shaped.obj")
            with open(shaped, "w") as f:
                f.write("# stub\n")
            job = os.path.basename(out)
            # OUTPUT_DIR is services path - patch by using job_id under real outputs
            from blender.config import OUTPUT_DIR
            real_job = "test_runner_flags"
            real_out = os.path.join(OUTPUT_DIR, real_job)
            os.makedirs(real_out, exist_ok=True)
            shaped2 = os.path.join(real_out, "pre.obj")
            with open(shaped2, "w") as f:
                f.write("# stub\n")

            jid, odir = br.run_blender({
                "avatar_size": "M",
                "garment_type": "top",
                "shape_keys": {},
                "fabric": {},
                "run_export": False,
                "run_simulation": True,
                "run_texture": False,
                "run_render": True,
                "cloth_obj_path": shaped2,
            }, job_id=real_job)

            self.assertEqual(jid, real_job)
            self.assertEqual(calls, ["simulate", "render"])
            self.assertTrue(os.path.exists(os.path.join(odir, "fit_summary.json")))


if __name__ == "__main__":
    unittest.main()
