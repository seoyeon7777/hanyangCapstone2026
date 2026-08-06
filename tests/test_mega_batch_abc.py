"""Mega-batch tests: ONNX backend, alerts, QA retry, photo-like FG, XZ morph."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import numpy as np


class AlertEvalTests(unittest.TestCase):
    def test_blender_and_release_alerts(self):
        from services.alerts import evaluate_active_alerts

        a = evaluate_active_alerts(
            blender_ok=False,
            queue_stats={"pending": 0, "running": 0, "failed": 1, "stale_running": 0},
            accuracy_summary={"hard_fails": ["x"], "release_pass_rate": 0.9},
            accuracy_age_hours=100,
        )
        codes = {x["code"] for x in a}
        self.assertIn("blender_unavailable", codes)
        self.assertIn("queue_failed", codes)
        self.assertIn("release_gate_fail", codes)
        self.assertIn("stale_benchmark", codes)


class QaRetryPolicyTests(unittest.TestCase):
    def test_retry_only_on_calibration(self):
        from pipeline.orchestrator import should_retry_qa_result, apply_qa_retry_relaxation
        from pipeline.schemas.manifest import JobResult, PipelineOptions

        r = JobResult(job_id="j", status="needs_review", qa={
            "checks": [{"name": "calibration_error", "ok": False, "skipped": False}]
        })
        self.assertTrue(should_retry_qa_result(r))
        r2 = JobResult(job_id="j", status="needs_review", qa={
            "checks": [{"name": "mesh_integrity", "ok": False}]
        })
        self.assertFalse(should_retry_qa_result(r2))
        opts = PipelineOptions(calibrate_max_iters=4, calibrate_tolerance_cm=1.5, calibrate_gain=0.85)
        snap = apply_qa_retry_relaxation(opts)
        self.assertEqual(snap["after"]["calibrate_max_iters"], 6)


class OnnxBackendTests(unittest.TestCase):
    def test_missing_runtime_skips(self):
        from pipeline.adapters.neural_backends.onnx_backend import OnnxNeuralBackend
        from pipeline.adapters.neural_backend import NeuralRequest

        b = OnnxNeuralBackend(model_path="/no/such/model.onnx")
        ok, reason = b.available()
        self.assertFalse(ok)
        res = b.reconstruct(NeuralRequest(images={}, garment_type="tshirt", output_dir=tempfile.mkdtemp()))
        self.assertTrue(res.skipped)
        self.assertFalse(res.ok)

    def test_injected_session_success(self):
        from pipeline.adapters.neural_backends.onnx_backend import OnnxNeuralBackend
        from pipeline.adapters.neural_backend import NeuralRequest

        class Fake:
            def run_garment(self, images, gtype):
                verts = [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]]
                faces = [[0, 1, 2], [0, 2, 3]]
                return verts, faces

        with tempfile.TemporaryDirectory() as td:
            b = OnnxNeuralBackend(_session=Fake())
            res = b.reconstruct(NeuralRequest(images={"front": "x"}, garment_type="skirt", output_dir=td))
            self.assertTrue(res.ok)
            self.assertTrue(os.path.exists(res.mesh_path))


class PhotoLikeFgTests(unittest.TestCase):
    def test_photo_like_not_full_frame(self):
        from models.silhouette_deform import extract_foreground

        path = "benchmarks/fixtures/silhouette/photo_like_skirt_front.png"
        if not os.path.exists(path):
            self.skipTest("fixture missing")
        fg = extract_foreground(path)
        cov = float(fg.mean())
        self.assertLess(cov, 0.9)
        self.assertGreater(cov, 0.05)


class XzMorphTests(unittest.TestCase):
    def test_independent_z_delta(self):
        from pipeline.adapters import neural_adapter

        with tempfile.TemporaryDirectory() as td:
            img = Path(td) / "f.png"
            img.write_bytes(b"x")
            recon = neural_adapter.reconstruct(
                images={"front": str(img)}, garment_type="skirt", output_dir=td, backend="synthetic",
                neural_options={"flare": 1.35},
            )
            tmpl = Path(td) / "t.obj"
            with open(tmpl, "w", encoding="utf-8") as f:
                for x in (-0.3, 0.3):
                    for y in (0.0, 0.5, 1.0):
                        for z in (-0.1, 0.1):
                            f.write(f"v {x} {y} {z}\n")
                f.write("f 1 2 3\n")
            out = Path(td) / "o.obj"
            ret = neural_adapter.retarget_to_template(
                neural_mesh_path=recon["mesh_path"],
                template_obj_path=str(tmpl),
                output_path=str(out),
                method="vertex_morph",
                morph_strength=0.2,
                morph_depth_strength=0.9,
            )
            self.assertTrue(ret.get("ok"))
            self.assertGreater(float(ret.get("max_abs_z_delta") or 0), 1e-6)


if __name__ == "__main__":
    unittest.main()
