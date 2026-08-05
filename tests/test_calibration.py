"""치수 재측정 + Shape Key 캘리브레이션 단위 테스트 (Blender 불필요)."""

import os
import sys
import tempfile
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from models.garment_measure import (
    measure_garment_verts,
    measurement_errors,
    max_abs_error,
)
from models.calibrate_shape_keys import (
    correct_shape_keys,
    calibrate_shape_keys,
    clip_shape_keys,
)
from models.fitting_model import EXPORT_SHAPE_KEY_RANGE, calc_export_shape_keys
from pipeline.schemas.manifest import JobManifest, JobResult
from pipeline.stages import StageContext
from pipeline.stages import calibrate as calibrate_stage
from pipeline.stages import measure_fusion, template_match


def _make_box_shirt(length_cm=65, shoulder_cm=44, chest_w=30, chest_d=20, sleeve_extra=20):
    """단순 박스 메쉬로 상의 근사 (cm 단위 좌표).

    - Z: 0..length
    - 어깨 밴드(Z≈0.92L): X half-width = shoulder/2
    - 가슴(Z≈0.70L): width=chest_w, depth=chest_d → perimeter 2*(w+d)
    - 소매: 상단에서 X가 shoulder/2 + sleeve_extra 까지 확장
    """
    L = length_cm
    verts = []

    def add_ring(z, hx, hy):
        verts.extend([
            [-hx, -hy, z], [hx, -hy, z], [hx, hy, z], [-hx, hy, z],
        ])

    # hem
    add_ring(0.0, chest_w / 2, chest_d / 2)
    # chest
    add_ring(0.70 * L, chest_w / 2, chest_d / 2)
    # shoulder body
    add_ring(0.92 * L, shoulder_cm / 2, chest_d / 2 * 0.8)
    # collar
    add_ring(L, shoulder_cm / 2 * 0.6, chest_d / 2 * 0.5)
    # sleeve tips at upper band
    tip = shoulder_cm / 2 + sleeve_extra
    z_s = 0.85 * L
    verts.extend([
        [-tip, 0, z_s], [tip, 0, z_s],
        [-tip, 2, 0.80 * L], [tip, 2, 0.80 * L],
    ])
    return np.array(verts, dtype=np.float64)


class MeasureTests(unittest.TestCase):
    def test_box_shirt_dimensions(self):
        verts = _make_box_shirt(
            length_cm=65, shoulder_cm=44, chest_w=30, chest_d=20, sleeve_extra=20
        )
        m = measure_garment_verts(verts, "tshirt")
        self.assertAlmostEqual(m["length"], 65.0, delta=0.5)
        self.assertAlmostEqual(m["shoulder"], 44.0, delta=1.0)
        self.assertAlmostEqual(m["chest"], 2 * (30 + 20), delta=2.0)
        self.assertAlmostEqual(m["sleeve"], 20.0, delta=2.0)

    def test_meter_scale_auto(self):
        verts = _make_box_shirt() / 100.0  # meters
        m = measure_garment_verts(verts, "tshirt")
        self.assertAlmostEqual(m["length"], 65.0, delta=0.5)


class CorrectionTests(unittest.TestCase):
    def test_correct_moves_toward_target(self):
        sk = {"chest": 0.0, "length": 0.0}
        # measured short by 5cm on chest
        errors = {"chest": 5.0}
        updated = correct_shape_keys(sk, errors, gain=1.0)
        expected_delta = 5.0 / EXPORT_SHAPE_KEY_RANGE["chest"]
        self.assertAlmostEqual(updated["chest"], expected_delta, places=5)
        self.assertEqual(updated["length"], 0.0)

    def test_clip(self):
        self.assertEqual(clip_shape_keys({"chest": 2.0})["chest"], 1.0)
        self.assertEqual(clip_shape_keys({"chest": -2.0})["chest"], -1.0)


class CalibrationLoopTests(unittest.TestCase):
    def test_linear_plant_converges(self):
        """가상 plant: measured = base + sk * range  → 1~2 iter면 수렴."""
        base = {"shoulder": 44.0, "chest": 100.0, "sleeve": 20.0, "length": 65.0}
        target = {"shoulder": 46.0, "chest": 105.0, "sleeve": 22.0, "length": 70.0}

        def export_fn(shape_keys, out_obj):
            # OBJ는 안 써도 됨 — measure_fn이 sk를 클로저로 봄
            with open(out_obj, "w") as f:
                f.write("# stub\n")
            export_fn.last_sk = dict(shape_keys)
            return out_obj

        def measure_fn(_path):
            sk = getattr(export_fn, "last_sk", {})
            out = {}
            for k, b in base.items():
                rng = EXPORT_SHAPE_KEY_RANGE[k]
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
        # open-loop 공식과 비슷해야 함
        expected = calc_export_shape_keys("tshirt", target)
        for k in target:
            self.assertAlmostEqual(
                report.final_shape_keys[k], expected[k], delta=0.05
            )


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
            open(out_obj, "w").write("# stub\n")
            export_fn.last_sk = dict(shape_keys)
            return out_obj

        def measure_fn(_path):
            # 일부러 chest를 3cm 작게 보고 → 보정이 chest+ 방향
            sk = getattr(export_fn, "last_sk", {})
            return {
                "shoulder": base["shoulder"] + sk.get("shoulder", 0) * EXPORT_SHAPE_KEY_RANGE["shoulder"],
                "chest": base["chest"] - 3.0 + sk.get("chest", 0) * EXPORT_SHAPE_KEY_RANGE["chest"],
                "sleeve": base["sleeve"] + sk.get("sleeve", 0) * EXPORT_SHAPE_KEY_RANGE["sleeve"],
                "length": base["length"] + sk.get("length", 0) * EXPORT_SHAPE_KEY_RANGE["length"],
            }

        ctx.extras["calibrate_export_fn"] = export_fn
        ctx.extras["calibrate_measure_fn"] = measure_fn
        ctx = calibrate_stage.run(ctx)

        self.assertFalse(ctx.extras["calibration"]["skipped"])
        self.assertIn("chest", ctx.extras["shape_keys"])
        # chest 보정이 + 방향이어야 함
        self.assertGreater(ctx.extras["shape_keys"]["chest"], 0.0)
        self.assertTrue(os.path.exists(ctx.result.artifacts["calibration_report"]))


class ErrorHelperTests(unittest.TestCase):
    def test_errors(self):
        err = measurement_errors({"chest": 100}, {"chest": 97})
        self.assertAlmostEqual(err["chest"], 3.0)


if __name__ == "__main__":
    unittest.main()
