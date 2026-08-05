"""P2 neural stub / P0-P1 large-category tests."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


class NeuralStubTests(unittest.TestCase):
    def test_reconstruct_stub(self):
        from pipeline.adapters.neural_adapter import reconstruct, retarget_to_template

        out = tempfile.mkdtemp(prefix="neu_")
        r = reconstruct(images={"front": None}, garment_type="tshirt", output_dir=out, backend="stub")
        self.assertTrue(r.get("skipped"))
        tmpl = os.path.join(out, "t.obj")
        with open(tmpl, "w", encoding="utf-8") as f:
            f.write("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n")
        ret = retarget_to_template(
            neural_mesh_path=None,
            template_obj_path=tmpl,
            output_path=os.path.join(out, "o.obj"),
        )
        self.assertTrue(ret.get("ok"))
        self.assertTrue(os.path.exists(ret["mesh_path"]))

    def test_stage_skips_on_p0(self):
        from pipeline.schemas.manifest import JobManifest, JobResult
        from pipeline.stages import StageContext
        from pipeline.stages.neural_reconstruct import run

        m = JobManifest.from_dict({"body": {"height": 170, "weight": 60}, "options": {"phase": "P0"}})
        ctx = StageContext(manifest=m, result=JobResult(job_id=m.job_id), output_dir=tempfile.mkdtemp())
        ctx = run(ctx)
        self.assertNotIn("neural_reconstruct", ctx.extras)

    def test_stage_runs_stub_on_p2(self):
        from pipeline.schemas.manifest import JobManifest, JobResult
        from pipeline.stages import StageContext
        from pipeline.stages.neural_reconstruct import run

        m = JobManifest.from_dict({
            "body": {"height": 170, "weight": 60},
            "options": {"phase": "P2", "neural_enabled": True},
        })
        ctx = StageContext(manifest=m, result=JobResult(job_id=m.job_id), output_dir=tempfile.mkdtemp())
        ctx = run(ctx)
        self.assertIn("neural_reconstruct", ctx.extras)
        self.assertTrue(any("P2" in w or "neural" in w.lower() for w in ctx.result.warnings))


class SkirtCatalogTests(unittest.TestCase):
    def test_skirt_exact(self):
        from pipeline.adapters.catalog import resolve_template
        import os

        r = resolve_template("skirt")
        self.assertEqual(r["template_id"], "skirt")
        self.assertTrue(r["exact_match"])
        self.assertTrue(os.path.exists(r["blend_path"]))
        self.assertIn("waist", r["measurement_keys"])
        self.assertNotIn("inseam", r["measurement_keys"])


class LengthFitTests(unittest.TestCase):
    def test_length_fit_changes_y(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("no pillow")
        from models.silhouette_deform import deform_obj_by_silhouette
        from models.fitting_model import load_obj

        out = tempfile.mkdtemp(prefix="len_")
        obj = os.path.join(out, "b.obj")
        with open(obj, "w") as f:
            for x in (-1.0, 1.0):
                for y in (0.0, 2.0):
                    f.write(f"v {x} {y} 0\n")
            f.write("f 1 2 3\n")
        mask = os.path.join(out, "m.png")
        img = Image.new("RGBA", (80, 200), (0, 0, 0, 0))
        px = img.load()
        for y in range(10, 190):
            for x in range(25, 55):
                px[x, y] = (255, 0, 0, 255)
        img.save(mask)
        dst = os.path.join(out, "o.obj")
        rep = deform_obj_by_silhouette(obj, mask, dst, strength=1.0, length_fit=True, smooth_iters=0, bipodal="off")
        self.assertTrue((rep.get("length_fit") or {}).get("ok"))
        self.assertGreater(rep.get("max_abs_y_delta", 0), 0.0)


if __name__ == "__main__":
    unittest.main()
