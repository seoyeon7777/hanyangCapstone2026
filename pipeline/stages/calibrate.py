"""S3.5 — 치수 캘리브레이션 (export → 재측정 → Shape Key 보정)."""

from __future__ import annotations

import json
import os
import shutil

from models.calibrate_shape_keys import calibrate_shape_keys
from models.garment_measure import measure_garment_obj
from pipeline.adapters.export_adapter import export_shaped_cloth, blender_available
from pipeline.stages import StageContext


def run(ctx: StageContext) -> StageContext:
    opts = ctx.manifest.options
    if not getattr(opts, "calibrate", True):
        ctx.result.warnings.append("캘리브레이션 스킵 (options.calibrate=false)")
        ctx.result.stage = "calibrate"
        return ctx

    ctx.progress("치수 캘리브레이션 준비...")
    blend_path = ctx.extras.get("blend_path")
    shape_keys = dict(ctx.extras.get("shape_keys") or {})
    targets = {
        k: float(v)
        for k, v in (ctx.manifest.measurements or {}).items()
        if v is not None
    }
    gtype = ctx.manifest.garment_type or "tshirt"
    lower = gtype.lower() in {"pants", "skirt", "shorts"}
    sk_type = gtype if lower else "tshirt"

    cal_dir = ctx.path("calibration")
    os.makedirs(cal_dir, exist_ok=True)

    export_fn = ctx.extras.get("calibrate_export_fn")
    measure_fn = ctx.extras.get("calibrate_measure_fn")

    if export_fn is None:
        if ctx.extras.get("skip_calibration") or not blender_available():
            reason = "skip_calibration" if ctx.extras.get("skip_calibration") else "Blender 없음"
            ctx.result.warnings.append(
                f"캘리브레이션 스킵 — {reason} (open-loop Shape Key 사용)"
            )
            ctx.extras["calibration"] = {
                "skipped": True,
                "skip_reason": reason,
                "converged": False,
                "final_shape_keys": shape_keys,
                "final_errors_cm": {},
                "tolerance_cm": float(getattr(opts, "calibrate_tolerance_cm", 1.5)),
            }
            ctx.result.stage = "calibrate"
            return ctx

        def export_fn(sk, out_obj):
            return export_shaped_cloth(
                blend_path=blend_path,
                shape_keys=sk,
                output_obj=out_obj,
            )

    if measure_fn is None:
        def measure_fn(path):
            return measure_garment_obj(path, garment_type=gtype)

    report = calibrate_shape_keys(
        target_measurements=targets,
        initial_shape_keys=shape_keys,
        garment_type=sk_type,
        output_dir=cal_dir,
        export_fn=export_fn,
        measure_fn=measure_fn,
        max_iters=int(getattr(opts, "calibrate_max_iters", 4)),
        tolerance_cm=float(getattr(opts, "calibrate_tolerance_cm", 1.5)),
        gain=float(getattr(opts, "calibrate_gain", 0.85)),
        progress=ctx.progress,
    )

    ctx.extras["shape_keys"] = report.final_shape_keys
    ctx.extras["calibration"] = report.to_dict()
    ctx.result.shape_keys = report.final_shape_keys

    report_path = ctx.path("calibration_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)
    ctx.result.artifacts["calibration_report"] = report_path

    if report.skipped:
        ctx.result.warnings.append(f"캘리브레이션 스킵: {report.skip_reason}")
    elif not report.converged:
        max_err = max((abs(v) for v in report.final_errors_cm.values()), default=0.0)
        ctx.result.warnings.append(
            f"캘리브레이션 미수렴 — max|err|≈{max_err:.1f}cm "
            f"(tolerance={report.tolerance_cm}cm)"
        )

    if report.iterations:
        last_obj = report.iterations[-1].obj_path
        if last_obj and os.path.exists(last_obj):
            dst = ctx.path("cloth_shaped.obj")
            shutil.copy2(last_obj, dst)
            ctx.extras["calibrated_obj"] = dst
            ctx.result.artifacts["cloth_shaped_obj"] = dst

    ctx.result.stage = "calibrate"
    return ctx
