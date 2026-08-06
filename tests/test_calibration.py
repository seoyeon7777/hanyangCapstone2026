"""치수 재측정 + ground-truth 정렬 + 캘리브레이션 테스트."""

import os
import sys
import tempfile
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from models.garment_measure import (
    measure_garment_verts,
    measure_garment_obj_label,
    mesh_to_label_cm,
    measurement_errors,
    max_abs_error,
    MEASURE_BASE_MESH_CM,
)
from models.calibrate_shape_keys import (
    correct_shape_keys,
    calibrate_shape_keys,
    clip_shape_keys,
)
from models.fitting_model import (
    EXPORT_BASE_MEASUREMENTS,
    EXPORT_SHAPE_KEY_RANGE,
    EXPORT_SHAPE_KEY_RANGE_MIN,
    EXPORT_SHAPE_KEY_RANGE_MAX,
    calc_export_shape_keys,
)
from pipeline.schemas.manifest import JobManifest, JobResult
from pipeline.stages import StageContext
from pipeline.stages import calibrate as calibrate_stage


PROBE = os.path.join(ROOT, "outputs", "_probe_cloth_top")


class GroundTruthRangeTests(unittest.TestCase):
    def test_ranges_are_tighter_than_legacy(self):
        # 구버전 과대 RANGE 보다 작아야 shapekey 가 충분히 움직임
        legacy = {"shoulder": 13, "sleeve": 42, "chest": 25, "length": 55}
        for k, old in legacy.items():
            self.assertLess(EXPORT_SHAPE_KEY_RANGE[k], old)
            self.assertGreater(EXPORT_SHAPE_KEY_RANGE_MIN[k], 0)
            self.assertGreater(EXPORT_SHAPE_KEY_RANGE_MAX[k], 0)

    def test_asymmetric_shapekey(self):
        # chest +8cm uses MAX range 7.85 → near 1.0
        sk = calc_export_shape_keys("tshirt", {"chest": 108})
        self.assertGreater(sk["chest"], 0.9)
        # chest -16cm uses MIN range 16.06 → near -1.0
        sk2 = calc_export_shape_keys("tshirt", {"chest": 84})
        self.assertLess(sk2["chest"], -0.9)

    def test_basis_target_is_zero(self):
        base = EXPORT_BASE_MEASUREMENTS["tshirt"]
        sk = calc_export_shape_keys("tshirt", base)
        for k, v in sk.items():
            self.assertAlmostEqual(v, 0.0, places=3)


@unittest.skipUnless(os.path.exists(os.path.join(PROBE, "basis.obj")), "probe OBJ 없음")
class ProbeMeshMeasureTests(unittest.TestCase):
    def test_basis_label_near_export_base(self):
        label = measure_garment_obj_label(os.path.join(PROBE, "basis.obj"), "tshirt")
        base = EXPORT_BASE_MEASUREMENTS["tshirt"]
        for k in ("shoulder", "chest", "sleeve", "length"):
            self.assertIsNotNone(label[k])
            self.assertAlmostEqual(label[k], base[k], delta=2.5)

    def test_sleeve_min_shortens(self):
        b = measure_garment_obj_label(os.path.join(PROBE, "basis.obj"), "tshirt")
        m = measure_garment_obj_label(os.path.join(PROBE, "sleeve_min.obj"), "tshirt")
        self.assertLess(m["sleeve"], b["sleeve"] - 5)

    def test_length_max_lengthens(self):
        b = measure_garment_obj_label(os.path.join(PROBE, "basis.obj"), "tshirt")
        m = measure_garment_obj_label(os.path.join(PROBE, "length_max.obj"), "tshirt")
        self.assertGreater(m["length"], b["length"] + 10)


class MeshToLabelTests(unittest.TestCase):
    def test_identity_at_measure_base(self):
        mesh = MEASURE_BASE_MESH_CM["tshirt"]
        label = mesh_to_label_cm(mesh, "tshirt")
        base = EXPORT_BASE_MEASUREMENTS["tshirt"]
        for k in base:
            self.assertAlmostEqual(label[k], base[k], delta=0.05)


class CorrectionTests(unittest.TestCase):
    def test_correct_uses_max_range_for_positive_error(self):
        sk = {"chest": 0.0}
        updated = correct_shape_keys(sk, {"chest": 7.85}, gain=1.0)
        self.assertAlmostEqual(updated["chest"], 1.0, places=2)

    def test_clip(self):
        self.assertEqual(clip_shape_keys({"chest": 2.0})["chest"], 1.0)


class CalibrationLoopTests(unittest.TestCase):
    def test_linear_plant_converges(self):
        base = dict(EXPORT_BASE_MEASUREMENTS["tshirt"])
        target = {"shoulder": 46.0, "chest": 105.0, "sleeve": 22.0, "length": 70.0}

        def export_fn(shape_keys, out_obj):
            with open(out_obj, "w") as f:
                f.write("# stub\n")
            export_fn.last_sk = dict(shape_keys)
            return out_obj

        def measure_fn(_path):
            sk = getattr(export_fn, "last_sk", {})
            out = {}
            for k, b in base.items():
                if sk.get(k, 0) >= 0:
                    rng = EXPORT_SHAPE_KEY_RANGE_MAX[k]
                else:
                    rng = EXPORT_SHAPE_KEY_RANGE_MIN[k]
                out[k] = b + sk.get(k, 0.0) * rng
            return out

        report = calibrate_shape_keys(
            target_measurements=target,
            initial_shape_keys={k: 0.0 for k in target},
            garment_type="tshirt",
            output_dir=tempfile.mkdtemp(prefix="cal_"),
            export_fn=export_fn,
            measure_fn=measure_fn,
            max_iters=5,
            tolerance_cm=0.5,
            gain=1.0,
        )
        self.assertTrue(report.converged)
        self.assertLessEqual(max_abs_error(report.final_errors_cm), 0.5)
        expected = calc_export_shape_keys("tshirt", target)
        for k in target:
            self.assertAlmostEqual(report.final_shape_keys[k], expected[k], delta=0.08)


class CalibrateStageTests(unittest.TestCase):
    def test_stage_with_injected_fns(self):
        m = JobManifest.from_dict({
            "body": {"height": 165, "weight": 55},
            "garment_type": "tshirt",
            "measurements": {"shoulder": 44, "chest": 100, "sleeve": 20, "length": 65},
            "options": {"calibrate": True, "calibrate_tolerance_cm": 1.0},
        })
        out = tempfile.mkdtemp(prefix="cal_stage_")
        ctx = StageContext(
            manifest=m,
            result=JobResult(job_id=m.job_id),
            output_dir=out,
            extras={
                "avatar_size": "M",
                "shape_keys": calc_export_shape_keys("tshirt", m.measurements),
                "blend_path": "/fake/cloth_top.blend",
                "garment_file": "top",
            },
        )
        base = dict(m.measurements)

        def export_fn(shape_keys, out_obj):
            with open(out_obj, "w") as f:
                f.write("# stub\n")
            export_fn.last_sk = dict(shape_keys)
            return out_obj

        def measure_fn(_path):
            sk = getattr(export_fn, "last_sk", {})
            return {
                "shoulder": base["shoulder"] + sk.get("shoulder", 0) * EXPORT_SHAPE_KEY_RANGE_MAX["shoulder"],
                "chest": base["chest"] - 3.0 + sk.get("chest", 0) * EXPORT_SHAPE_KEY_RANGE_MAX["chest"],
                "sleeve": base["sleeve"] + sk.get("sleeve", 0) * EXPORT_SHAPE_KEY_RANGE_MAX["sleeve"],
                "length": base["length"] + sk.get("length", 0) * EXPORT_SHAPE_KEY_RANGE_MAX["length"],
            }

        ctx.extras["calibrate_export_fn"] = export_fn
        ctx.extras["calibrate_measure_fn"] = measure_fn
        ctx = calibrate_stage.run(ctx)
        self.assertFalse(ctx.extras["calibration"]["skipped"])
        self.assertGreater(ctx.extras["shape_keys"]["chest"], 0.0)


class ErrorHelperTests(unittest.TestCase):
    def test_errors(self):
        err = measurement_errors({"chest": 100}, {"chest": 97})
        self.assertAlmostEqual(err["chest"], 3.0)


if __name__ == "__main__":
    unittest.main()
