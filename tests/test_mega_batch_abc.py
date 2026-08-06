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

    def test_classifier_holdout_alert(self):
        from services.alerts import evaluate_active_alerts

        a = evaluate_active_alerts(
            blender_ok=True,
            queue_stats={"pending": 0, "running": 0, "failed": 0, "stale_running": 0},
            accuracy_summary={"hard_fails": [], "soft_fails": [], "release_pass_rate": 1.0},
            classifier_meta={"held_out": None},
        )
        codes = {x["code"] for x in a}
        self.assertIn("classifier_holdout_missing", codes)

        b = evaluate_active_alerts(
            blender_ok=True,
            queue_stats={"pending": 0, "running": 0, "failed": 0, "stale_running": 0},
            accuracy_summary={"hard_fails": [], "release_pass_rate": 1.0},
            classifier_meta={"held_out": True, "val_acc": 0.2},
        )
        self.assertIn("classifier_holdout_fail", {x["code"] for x in b})


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

    def test_session_run_path(self):
        from pipeline.adapters.neural_backends.onnx_backend import OnnxNeuralBackend
        from pipeline.adapters.neural_backend import NeuralRequest
        from PIL import Image

        class SessionRunFake:
            def get_inputs(self):
                return [type("I", (), {"name": "images"})()]

            def get_outputs(self):
                return [
                    type("O", (), {"name": "vertices"})(),
                    type("O", (), {"name": "faces"})(),
                ]

            def run(self, out_names, feeds):
                self.assertIn = "images" in feeds
                verts = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float32)
                faces = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int32)
                return [verts, faces]

        with tempfile.TemporaryDirectory() as td:
            front = os.path.join(td, "front.png")
            Image.new("RGB", (32, 32), (200, 40, 40)).save(front)
            b = OnnxNeuralBackend(_session=SessionRunFake(), input_size=32)
            res = b.reconstruct(NeuralRequest(
                images={"front": front}, garment_type="skirt", output_dir=td,
                options={"input_size": 32, "min_views": 1},
            ))
            self.assertTrue(res.ok, res.reason)
            self.assertEqual((res.meta or {}).get("mode"), "session.run")


class TorchBackendTests(unittest.TestCase):
    def test_missing_skips(self):
        from pipeline.adapters.neural_backends.torch_backend import TorchNeuralBackend
        from pipeline.adapters.neural_backend import NeuralRequest

        b = TorchNeuralBackend(model_path="/no/such/model.pt")
        ok, _ = b.available()
        self.assertFalse(ok)
        res = b.reconstruct(NeuralRequest(images={}, garment_type="pants", output_dir=tempfile.mkdtemp()))
        self.assertTrue(res.skipped)

    def test_injected_module(self):
        from pipeline.adapters.neural_backends.torch_backend import TorchNeuralBackend
        from pipeline.adapters.neural_backend import NeuralRequest

        class Mod:
            def run_garment(self, images, gtype):
                return (
                    [[0, 0, 0], [1, 0, 0], [0, 1, 0]],
                    [[0, 1, 2]],
                )

        with tempfile.TemporaryDirectory() as td:
            b = TorchNeuralBackend(_module=Mod())
            res = b.reconstruct(NeuralRequest(images={"front": "x"}, garment_type="top", output_dir=td))
            self.assertTrue(res.ok)
            self.assertTrue(os.path.exists(res.mesh_path))


class LegRmseTests(unittest.TestCase):
    def test_mesh_leg_profiles_and_rmse(self):
        from models.silhouette_deform import mesh_leg_profiles
        from pipeline.eval.metrics import bipodal_leg_rmse

        # two columns of verts (legs)
        verts = []
        for y in np.linspace(0, 1, 10):
            for x in (-0.6, -0.4, 0.4, 0.6):
                verts.append([x, y, 0.0])
        legs = mesh_leg_profiles(np.array(verts), bins=8)
        self.assertEqual(len(legs["left_leg_hw"]), 8)
        self.assertGreater(float(np.mean(legs["left_leg_hw"])), 0)
        mask = {
            "left_leg_hw": legs["left_leg_hw"],
            "right_leg_hw": legs["right_leg_hw"],
            "left_leg_cx": legs["left_leg_cx"],
            "right_leg_cx": legs["right_leg_cx"],
        }
        m = bipodal_leg_rmse(mask, legs)
        self.assertLess(m["mean_leg_rmse"], 0.05)
        self.assertFalse(m["crossover"])


class StratifiedSplitTests(unittest.TestCase):
    def test_holdout_keeps_labels(self):
        from scripts.train_garment_classifier import stratified_split, LABELS

        ds = []
        for lab in LABELS:
            for i in range(10):
                ds.append((lab, [float(i)] * 8))
        train, val = stratified_split(ds, val_ratio=0.2, seed=1)
        self.assertGreater(len(val), 0)
        self.assertEqual(len(train) + len(val), len(ds))
        val_labs = {x[0] for x in val}
        self.assertTrue(val_labs.issubset(set(LABELS)))


class IterativeIcpTests(unittest.TestCase):
    def test_iterative_icp_reports_rms(self):
        from pipeline.adapters import neural_adapter

        with tempfile.TemporaryDirectory() as td:
            img = Path(td) / "f.png"
            img.write_bytes(b"x")
            recon = neural_adapter.reconstruct(
                images={"front": str(img)}, garment_type="hoodie", output_dir=td, backend="synthetic",
            )
            self.assertEqual(recon.get("style"), "hoodie_bulky")
            tmpl = Path(td) / "t.obj"
            with open(tmpl, "w", encoding="utf-8") as f:
                for x in (-0.4, 0.4):
                    for y in (0.0, 0.5, 1.0):
                        for z in (-0.15, 0.15):
                            f.write(f"v {x + 1.5} {y - 0.8} {z}\n")
                f.write("f 1 2 3\n")
            out = Path(td) / "o.obj"
            ret = neural_adapter.retarget_to_template(
                neural_mesh_path=recon["mesh_path"],
                template_obj_path=str(tmpl),
                output_path=str(out),
                method="icp_morph",
                morph_strength=0.4,
                icp_iters=4,
            )
            self.assertTrue(ret.get("ok"), ret)
            align = ret.get("align") or {}
            self.assertGreaterEqual(int(align.get("iters") or 0), 1)
            self.assertIn("rms_after", align)
            self.assertTrue(align.get("rms_improved"))


class SideGateTests(unittest.TestCase):
    def test_side_gate_rejects_full_frame(self):
        from models.silhouette_deform import should_use_side_mask
        from PIL import Image

        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "full.png")
            Image.new("RGB", (40, 40), (200, 50, 50)).save(path)
            g = should_use_side_mask(path, min_score=0.35)
            self.assertFalse(g.get("use"))


class ResidualSmoothTests(unittest.TestCase):
    def test_smooth_and_residual_fields(self):
        from pipeline.adapters import neural_adapter

        with tempfile.TemporaryDirectory() as td:
            img = Path(td) / "f.png"
            img.write_bytes(b"x")
            recon = neural_adapter.reconstruct(
                images={"front": str(img)}, garment_type="hoodie", output_dir=td, backend="synthetic",
            )
            tmpl = Path(td) / "t.obj"
            with open(tmpl, "w", encoding="utf-8") as f:
                for x in (-0.35, 0.35):
                    for y in (0.0, 0.5, 1.0):
                        for z in (-0.12, 0.12):
                            f.write(f"v {x} {y} {z}\n")
                f.write("f 1 2 3\n")
            out = Path(td) / "o.obj"
            ret = neural_adapter.retarget_to_template(
                neural_mesh_path=recon["mesh_path"],
                template_obj_path=str(tmpl),
                output_path=str(out),
                method="icp_morph",
                morph_strength=0.55,
                smooth_iters=2,
                residual_pass=True,
                residual_threshold=0.01,
            )
            self.assertTrue(ret.get("ok"), ret)
            self.assertIn("morph_residual_rms", ret)
            self.assertEqual(ret.get("smooth_iters"), 2)
            self.assertIn("residual", ret)


class SoftFailAlertTests(unittest.TestCase):
    def test_soft_fail_alert_code(self):
        from services.alerts import evaluate_active_alerts

        a = evaluate_active_alerts(
            blender_ok=True,
            queue_stats={"pending": 0, "running": 0, "failed": 0, "stale_running": 0},
            accuracy_summary={"hard_fails": [], "soft_fails": ["pants_calib_narrow"], "release_pass_rate": 1.0},
        )
        codes = {x["code"] for x in a}
        self.assertIn("soft_fail_cases", codes)


class FusionItersTests(unittest.TestCase):
    def test_fusion_iters_reported(self):
        from models.silhouette_deform import deform_obj_by_silhouette
        from PIL import Image

        with tempfile.TemporaryDirectory() as td:
            obj = os.path.join(td, "b.obj")
            with open(obj, "w") as f:
                for x in (-1, 1):
                    for y in (0, 1, 2):
                        for z in (-0.3, 0.3):
                            f.write(f"v {x} {y} {z}\n")
                f.write("f 1 2 3\n")
            front = os.path.join(td, "f.png")
            side = os.path.join(td, "s.png")
            img = Image.new("RGBA", (80, 100), (0, 0, 0, 0))
            px = img.load()
            for y in range(100):
                for x in range(20, 60):
                    px[x, y] = (255, 0, 0, 255)
            img.save(front)
            img2 = Image.new("RGBA", (80, 100), (0, 0, 0, 0))
            px2 = img2.load()
            for y in range(100):
                half = 30 if y < 50 else 12
                for x in range(40 - half, 40 + half):
                    px2[x, y] = (0, 255, 0, 255)
            img2.save(side)
            dst = os.path.join(td, "o.obj")
            r = deform_obj_by_silhouette(
                obj, front, dst, strength=0.8, side_mask_path=side,
                depth_strength=0.8, smooth_iters=0, fusion_iters=3, bins=12,
            )
            self.assertTrue(r.get("ok"))
            self.assertEqual(r.get("fusion_iters"), 3)
            self.assertGreater(float(r.get("max_abs_z_delta") or 0), 0)


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
