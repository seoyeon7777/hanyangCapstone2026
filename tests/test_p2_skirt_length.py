"""P2 neural contract + skirt silhouette / length-fit tests."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from pipeline.adapters import neural_adapter
from pipeline.adapters.catalog import resolve_template
from pipeline.schemas.manifest import JobManifest, JobResult
from pipeline.stages import StageContext
from pipeline.stages import neural_reconstruct as neural_stage
from models.silhouette_deform import (
    deform_obj_by_silhouette,
    extract_foreground,
    mask_width_profile,
)


def _ctx(manifest: JobManifest, td: str) -> StageContext:
    return StageContext(
        manifest=manifest,
        result=JobResult(job_id=manifest.job_id),
        output_dir=td,
    )


class NeuralStubTests(unittest.TestCase):
    def test_reconstruct_stub(self):
        with tempfile.TemporaryDirectory() as td:
            r = neural_adapter.reconstruct(
                images={}, garment_type="tshirt", output_dir=td, backend="stub"
            )
            self.assertTrue(r.get("skipped"))
            self.assertFalse(r.get("ok"))
            self.assertIsNone(r.get("mesh_path"))

    def test_synthetic_backend_makes_mesh(self):
        with tempfile.TemporaryDirectory() as td:
            img = Path(td) / "f.png"
            img.write_bytes(
                b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
                b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00"
                b"\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05"
                b"\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
            )
            # minimal valid-ish; if pillow needed for existence only path check
            img.write_bytes(b"x")
            r = neural_adapter.reconstruct(
                images={"front": str(img)},
                garment_type="skirt",
                output_dir=td,
                backend="synthetic",
            )
            self.assertTrue(r.get("ok"))
            self.assertTrue(os.path.exists(r["mesh_path"]))

    def test_retarget_without_neural_is_passthrough_not_success(self):
        with tempfile.TemporaryDirectory() as td:
            tmpl = Path(td) / "t.obj"
            with open(tmpl, "w", encoding="utf-8") as f:
                f.write("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n")
            out = Path(td) / "o.obj"
            r = neural_adapter.retarget_to_template(
                neural_mesh_path=None,
                template_obj_path=str(tmpl),
                output_path=str(out),
            )
            self.assertTrue(r.get("passthrough"))
            self.assertTrue(r.get("skipped"))
            self.assertFalse(r.get("ok"))

    def test_stage_skips_on_p0(self):
        with tempfile.TemporaryDirectory() as td:
            m = JobManifest.from_dict({
                "body": {"height": 165, "weight": 55},
                "garment_type": "tshirt",
                "measurements": {},
                "options": {"phase": "P0"},
                "job_id": "j1",
            })
            ctx = _ctx(m, td)
            neural_stage.run(ctx)
            self.assertIsNone(ctx.extras.get("neural_reconstruct"))

    def test_stage_runs_stub_on_p2(self):
        with tempfile.TemporaryDirectory() as td:
            m = JobManifest.from_dict({
                "body": {"height": 165, "weight": 55},
                "garment_type": "tshirt",
                "measurements": {},
                "options": {"phase": "P2", "neural_backend": "stub"},
                "job_id": "j2",
            })
            ctx = _ctx(m, td)
            neural_stage.run(ctx)
            r = ctx.extras.get("neural_reconstruct") or {}
            self.assertTrue(r.get("skipped"))

    def test_unknown_backend_soft_fallback(self):
        with tempfile.TemporaryDirectory() as td:
            m = JobManifest.from_dict({
                "body": {"height": 165, "weight": 55},
                "garment_type": "tshirt",
                "measurements": {},
                "options": {
                    "neural_enabled": True,
                    "neural_backend": "does_not_exist",
                    "neural_required": False,
                },
                "job_id": "j3",
            })
            ctx = _ctx(m, td)
            neural_stage.run(ctx)
            r = ctx.extras.get("neural_reconstruct") or {}
            self.assertTrue(r.get("skipped"))


class SkirtCatalogTests(unittest.TestCase):
    def test_skirt_exact(self):
        r = resolve_template("skirt")
        self.assertEqual(r["template_id"], "skirt")


class LengthFitTests(unittest.TestCase):
    def _box_obj(self, path: str):
        with open(path, "w", encoding="utf-8") as f:
            for x in (-1.0, 1.0):
                for y in (0.0, 2.0):
                    for z in (-0.2, 0.2):
                        f.write(f"v {x} {y} {z}\n")
            f.write("f 1 2 3\n")

    def test_length_fit_changes_y(self):
        from PIL import Image

        with tempfile.TemporaryDirectory() as td:
            obj = os.path.join(td, "b.obj")
            self._box_obj(obj)
            mask = os.path.join(td, "m.png")
            img = Image.new("RGBA", (80, 100), (0, 0, 0, 0))
            px = img.load()
            for y in range(10, 90):
                for x in range(25, 55):
                    px[x, y] = (255, 0, 0, 255)
            img.save(mask)
            out = os.path.join(td, "o.obj")
            from models.fitting_model import load_obj

            rep = deform_obj_by_silhouette(
                obj, mask, out, strength=0.9, length_fit=True, garment_type="skirt", bipodal="off"
            )
            v0, _ = load_obj(obj)
            v1, _ = load_obj(out)
            self.assertTrue(rep.get("ok"))
            lf = rep.get("length_fit") or {}
            self.assertTrue(lf.get("ok"))
            self.assertEqual(lf.get("anchor"), "waist_top")
            self.assertGreater(abs(float(v1[:, 1].max() - v1[:, 1].min()) - float(v0[:, 1].max() - v0[:, 1].min())), 1e-6)


class ForegroundExtractTests(unittest.TestCase):
    def test_rgb_black_bg_not_full_frame(self):
        from PIL import Image

        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "rgb.png")
            img = Image.new("RGB", (60, 80), (0, 0, 0))
            px = img.load()
            for y in range(10, 70):
                for x in range(15, 45):
                    px[x, y] = (220, 220, 220)
            img.save(p)
            fg = extract_foreground(p)
            cov = float(fg.mean())
            self.assertLess(cov, 0.9)
            self.assertGreater(cov, 0.05)
            prof = mask_width_profile(p, bins=16)
            self.assertGreater(int(prof["active_bands"]), 4)

    def test_full_rgba_opaque_photo_low_quality_path(self):
        from PIL import Image

        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "full.png")
            Image.new("RGB", (40, 40), (180, 40, 40)).save(p)
            fg = extract_foreground(p)
            # nearly full bright → high coverage; deform should skip length_fit
            self.assertGreater(float(fg.mean()), 0.9)


if __name__ == "__main__":
    unittest.main()
