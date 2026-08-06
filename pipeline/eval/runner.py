"""정확도 벤치마크 러너.

suites:
  - calibration: Blender export↔재측정 루프 (없으면 plant/skip)
  - measure_consistency: SK=0 export 치수 ≈ base label
  - classification: 합성/픽스처 이미지 분류 정답률
  - silhouette: 마스크→디폼 메트릭 회귀
"""

from __future__ import annotations

import json
from pathlib import Path
import os
import tempfile
import time
import traceback
from typing import Any, Optional

from pipeline.eval.metrics import (
    aggregate_suite,
    pass_tolerance,
    per_key_errors,
    summarize_errors,
)

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load_cases(cases_dir: str) -> list[dict[str, Any]]:
    cases = []
    if not os.path.isdir(cases_dir):
        return cases
    for name in sorted(os.listdir(cases_dir)):
        if not name.endswith(".json"):
            continue
        if name.startswith("_TEMPLATE"):
            continue
        path = os.path.join(cases_dir, name)
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if data.get("disabled"):
            continue
        data.setdefault("id", os.path.splitext(name)[0])
        data["_path"] = path
        cases.append(data)
    return cases


def _blend_for(garment_type: str) -> str:
    from pipeline.adapters.catalog import resolve_template

    match = resolve_template(garment_type)
    blend = match.get("blend_path") or match.get("blend")
    if blend and not os.path.isabs(blend):
        blend = os.path.join(ROOT, blend)
    return blend


def _shape_key_type(garment_type: str) -> str:
    """카탈로그 shape_key_type 우선, 없으면 타입별 기본."""
    from pipeline.adapters.catalog import resolve_template

    g = (garment_type or "tshirt").lower()
    try:
        match = resolve_template(g)
        sk = (match or {}).get("shape_key_type")
        if sk:
            return str(sk)
    except Exception:
        pass
    if g in ("pants", "trousers", "shorts"):
        return "pants"
    if g == "skirt":
        return "skirt"
    if g in ("hoodie", "sweatshirt", "sweater", "jacket", "coat"):
        return "hoodie"
    return "tshirt"


def run_calibration_case(case: dict[str, Any], *, output_root: str, use_blender: bool) -> dict[str, Any]:
    from models.calibrate_shape_keys import calibrate_shape_keys
    from models.fitting_model import calc_export_shape_keys
    from models.garment_measure import measure_garment_obj_label
    from pipeline.adapters.export_adapter import blender_available, export_shaped_cloth

    gid = case["id"]
    gtype = case.get("garment_type") or "tshirt"
    targets = {k: float(v) for k, v in (case.get("target_measurements") or {}).items() if v is not None}
    tol = float(case.get("tolerance_cm", 1.5))
    out_dir = os.path.join(output_root, gid)
    os.makedirs(out_dir, exist_ok=True)

    sk_type = _shape_key_type(gtype)
    initial = calc_export_shape_keys(sk_type, targets)

    result: dict[str, Any] = {
        "id": gid,
        "suite": "calibration",
        "garment_type": gtype,
        "target_measurements": targets,
        "tolerance_cm": tol,
        "initial_shape_keys": initial,
        "soft": bool(case.get("soft")),
        "release_gate": case.get("release_gate", True) is not False,
        "provenance": case.get("provenance"),
        "tags": case.get("tags") or [],
    }

    if not use_blender or not blender_available():
        # plant: perfect measure after one step → tests harness only
        if case.get("allow_plant"):
            measured_store = {"path": None}

            def export_fn(sk, path):
                measured_store["sk"] = dict(sk)
                Path(path).write_text("# plant\n")
                return path

            def measure_fn(path):
                # open-loop plant: report targets exactly when sk near initial solution
                return dict(targets)

            report = calibrate_shape_keys(
                target_measurements=targets,
                initial_shape_keys=initial,
                garment_type=sk_type,
                output_dir=out_dir,
                export_fn=export_fn,
                measure_fn=measure_fn,
                tolerance_cm=tol,
                max_iters=int(case.get("max_iters", 4)),
            )
            errors = report.final_errors_cm
            metrics = summarize_errors(errors)
            result.update({
                "mode": "plant",
                "passed": report.converged and pass_tolerance(errors, tol),
                "converged": report.converged,
                "errors_cm": errors,
                "metrics": metrics,
                "measured": report.final_measured,
                "iterations": len(report.iterations),
            })
            return result

        result.update({
            "mode": "skipped",
            "passed": False,
            "skip_reason": "blender_unavailable",
            "metrics": summarize_errors({}),
        })
        return result

    blend = case.get("blend_path") or _blend_for(gtype)
    if not blend or not os.path.exists(blend):
        result.update({
            "mode": "skipped",
            "passed": False,
            "skip_reason": f"blend_missing:{blend}",
            "metrics": summarize_errors({}),
        })
        return result

    def export_fn(shape_keys, output_obj):
        return export_shaped_cloth(
            blend_path=blend,
            shape_keys=shape_keys,
            output_obj=output_obj,
            timeout=90,
        )

    def measure_fn(obj_path):
        return measure_garment_obj_label(obj_path, sk_type)

    t0 = time.time()
    report = calibrate_shape_keys(
        target_measurements=targets,
        initial_shape_keys=initial,
        garment_type=sk_type,
        output_dir=out_dir,
        export_fn=export_fn,
        measure_fn=measure_fn,
        tolerance_cm=tol,
        max_iters=int(case.get("max_iters", 4)),
        gain=float(case.get("gain", 0.85)),
    )
    elapsed = round(time.time() - t0, 2)
    errors = report.final_errors_cm
    metrics = summarize_errors(errors)
    passed = bool(report.converged) or pass_tolerance(errors, tol)
    result.update({
        "mode": "blender",
        "passed": passed,
        "converged": report.converged,
        "errors_cm": {k: round(v, 3) for k, v in errors.items()},
        "metrics": metrics,
        "measured": report.final_measured,
        "final_shape_keys": report.final_shape_keys,
        "iterations": len(report.iterations),
        "elapsed_sec": elapsed,
        "blend_path": blend,
    })
    return result


def run_measure_consistency_case(case: dict[str, Any], *, output_root: str, use_blender: bool) -> dict[str, Any]:
    """SK=0 export 치수가 base label에 가까운지."""
    from models.fitting_model import EXPORT_BASE_MEASUREMENTS
    from models.garment_measure import measure_garment_obj_label
    from pipeline.adapters.export_adapter import blender_available, export_shaped_cloth

    gid = case["id"]
    gtype = case.get("garment_type") or "tshirt"
    sk_type = _shape_key_type(gtype)
    base = dict(EXPORT_BASE_MEASUREMENTS.get(sk_type) or {})
    tol = float(case.get("tolerance_cm", 2.5))
    out_dir = os.path.join(output_root, gid)
    os.makedirs(out_dir, exist_ok=True)

    result = {
        "id": gid,
        "suite": "measure_consistency",
        "garment_type": gtype,
        "target_measurements": base,
        "tolerance_cm": tol,
    }
    if not use_blender or not blender_available():
        result.update({"mode": "skipped", "passed": False, "skip_reason": "blender_unavailable",
                       "metrics": summarize_errors({})})
        return result

    blend = case.get("blend_path") or _blend_for(gtype)
    obj = os.path.join(out_dir, "basis.obj")
    t0 = time.time()
    export_shaped_cloth(blend_path=blend, shape_keys={k: 0.0 for k in base}, output_obj=obj, timeout=90)
    measured = measure_garment_obj_label(obj, sk_type)
    errors = per_key_errors(base, measured)
    metrics = summarize_errors(errors)
    result.update({
        "mode": "blender",
        "passed": pass_tolerance(errors, tol),
        "errors_cm": {k: round(v, 3) for k, v in errors.items()},
        "metrics": metrics,
        "measured": measured,
        "elapsed_sec": round(time.time() - t0, 2),
        "blend_path": blend,
    })
    return result


def run_classification_case(case: dict[str, Any], *, output_root: str) -> dict[str, Any]:
    from scripts.train_garment_classifier import make_synthetic_sample
    from pipeline.adapters.garment_classifier import classify_image_ml
    import random

    gid = case["id"]
    expected = case.get("expected_label") or case.get("garment_type")
    out_dir = os.path.join(output_root, gid)
    os.makedirs(out_dir, exist_ok=True)
    rng = random.Random(int(case.get("seed", 7)))
    path = case.get("image_path")
    if path and not os.path.isabs(path):
        path = os.path.join(ROOT, path)
    if not path or not os.path.exists(path):
        path = make_synthetic_sample(expected, rng, out_dir)

    pred = classify_image_ml(path)
    label = (pred or {}).get("label")
    conf = (pred or {}).get("confidence")
    # accept near-miss groups
    aliases = case.get("accept_labels") or [expected]
    passed = label in aliases
    return {
        "id": gid,
        "suite": "classification",
        "expected_label": expected,
        "accept_labels": aliases,
        "predicted": label,
        "confidence": conf,
        "passed": passed,
        "soft": bool(case.get("soft")),
        "image_path": path,
        "metrics": {"accuracy": 1.0 if passed else 0.0},
    }


def run_silhouette_case(case: dict[str, Any], *, output_root: str) -> dict[str, Any]:
    try:
        from PIL import Image
        import numpy as np
    except ImportError:
        return {"id": case["id"], "suite": "silhouette", "passed": False, "skip_reason": "pillow"}

    from models.silhouette_deform import (
        deform_obj_by_silhouette,
        mask_width_profile,
        mesh_width_profile,
        mesh_waist_halfwidth,
    )
    from models.fitting_model import load_obj
    from pipeline.eval.metrics import silhouette_profile_rmse

    gid = case["id"]
    out_dir = os.path.join(output_root, gid)
    os.makedirs(out_dir, exist_ok=True)

    obj = os.path.join(out_dir, "box.obj")
    xs = (-1.0, -0.5, 0.0, 0.5, 1.0)
    ys = (0.0, 0.5, 1.0, 1.5, 2.0)
    zs = (-0.3, 0.3)
    with open(obj, "w") as f:
        for x in xs:
            for y in ys:
                for z in zs:
                    f.write(f"v {x} {y} {z}\n")
        f.write("f 1 2 3\n")

    front = os.path.join(out_dir, "front.png")
    fixture = case.get("front_mask")
    if fixture:
        fpath = fixture if os.path.isabs(fixture) else os.path.join(ROOT, fixture)
        if not os.path.exists(fpath):
            return {
                "id": case["id"], "suite": "silhouette", "passed": False,
                "error": f"missing_fixture:{fixture}", "metrics": {},
            }
        Image.open(fpath).convert("RGBA").save(front)
    if not fixture:
        img = Image.new("RGBA", (100, 120), (0, 0, 0, 0))
        px = img.load()
        if case.get("bipodal_mask"):
            for y in range(0, 50):
                for x in range(35, 65):
                    px[x, y] = (255, 0, 0, 255)
            for y in range(50, 120):
                for x in range(28, 42):
                    px[x, y] = (255, 0, 0, 255)
                for x in range(58, 72):
                    px[x, y] = (255, 0, 0, 255)
        else:
            for y in range(120):
                half = int(case.get("front_half", 35))
                if case.get("aline_skirt"):
                    t = y / 119.0
                    half = int(22 + t * 28)
                for x in range(max(0, 50 - half), min(100, 50 + half)):
                    px[x, y] = (255, 0, 0, 255)
        img.save(front)

    side = None
    side_fix = case.get("side_mask")
    side_prof = None
    if side_fix:
        sp = side_fix if os.path.isabs(side_fix) else os.path.join(ROOT, side_fix)
        if not os.path.exists(sp):
            return {
                "id": case["id"], "suite": "silhouette", "passed": False,
                "error": f"missing_side_fixture:{side_fix}", "metrics": {},
            }
        side = os.path.join(out_dir, "side.png")
        Image.open(sp).convert("RGBA").save(side)
    elif case.get("with_side", True) and not case.get("bipodal_mask"):
        side = os.path.join(out_dir, "side.png")
        img2 = Image.new("RGBA", (100, 120), (0, 0, 0, 0))
        px2 = img2.load()
        for y in range(120):
            half = int(case.get("side_half_top", 40)) if y < 60 else int(case.get("side_half_bot", 18))
            for x in range(50 - half, 50 + half):
                px2[x, y] = (0, 255, 0, 255)
        img2.save(side)

    dst = os.path.join(out_dir, "deformed.obj")
    if case.get("bipodal_mask"):
        with open(obj, "w") as f:
            for x in (-0.9, -0.4, 0.4, 0.9):
                for y in (0.0, 0.5, 1.0, 1.5, 2.0):
                    for z in (-0.2, 0.2):
                        f.write(f"v {x} {y} {z}\n")
            f.write("f 1 2 3\n")

    bins = int(case.get("profile_bins", 24))
    mask_prof = mask_width_profile(front, bins=bins)
    v0, _ = load_obj(obj)
    before_prof = mesh_width_profile(v0, bins=bins, axis=0)
    rmse_before = silhouette_profile_rmse(mask_prof["half_widths"], before_prof["half_widths"])
    waist_before = mesh_waist_halfwidth(v0)

    depth_rmse_before = depth_rmse_after = None
    if side:
        side_prof = mask_width_profile(side, bins=bins)
        before_z = mesh_width_profile(v0, bins=bins, axis=2)
        depth_rmse_before = silhouette_profile_rmse(side_prof["half_widths"], before_z["half_widths"])

    report = deform_obj_by_silhouette(
        obj, front, dst,
        strength=float(case.get("strength", 0.8)),
        edge_snap=float(case.get("edge_snap", 0.3)),
        side_mask_path=side,
        depth_strength=float(case.get("depth_strength", 0.8)),
        smooth_iters=0,
        bipodal="force" if case.get("bipodal_mask") else ("off" if case.get("garment_type") == "skirt" else "auto"),
        length_fit=bool(case.get("length_fit", True)),
        garment_type=str(case.get("garment_type") or ""),
        bins=bins,
        fusion_iters=int(case.get("fusion_iters", 2 if side else 1)),
    )
    v1, _ = load_obj(dst)
    after_prof = mesh_width_profile(v1, bins=bins, axis=0)
    rmse_after = silhouette_profile_rmse(mask_prof["half_widths"], after_prof["half_widths"])
    rmse_reduction = rmse_before - rmse_after
    rmse_ratio = (rmse_reduction / rmse_before) if rmse_before > 1e-9 else 0.0
    waist_after = mesh_waist_halfwidth(v1)
    waist_drift_ratio = abs(waist_after - waist_before) / max(waist_before, 1e-6)

    if side and depth_rmse_before is not None and side_prof is not None:
        after_z = mesh_width_profile(v1, bins=bins, axis=2)
        depth_rmse_after = silhouette_profile_rmse(side_prof["half_widths"], after_z["half_widths"])

    dx = float(np.max(np.abs(v1[:, 0] - v0[:, 0])))
    dy = float(np.max(np.abs(v1[:, 1] - v0[:, 1])))
    dz = float(np.max(np.abs(v1[:, 2] - v0[:, 2])))
    min_dx = float(case.get("min_abs_x_delta", 0.01))
    min_dz = float(case.get("min_abs_z_delta", 0.01 if side else 0.0))
    passed = report.get("ok") and dx >= min_dx and (dz >= min_dz if side else True)
    if case.get("bipodal_mask") or case.get("expect_bipodal") is True:
        passed = passed and bool(report.get("bipodal"))
    if case.get("expect_bipodal") is False:
        passed = passed and (not report.get("bipodal"))
    if case.get("require_profile_improve", False) or case.get("aline_skirt"):
        min_red = float(case.get("min_rmse_reduction", 0.0))
        max_after = case.get("max_profile_rmse_after")
        improved = rmse_after < rmse_before - 1e-6 and rmse_reduction >= min_red
        if max_after is not None:
            improved = improved and rmse_after <= float(max_after)
        passed = passed and improved
    if case.get("require_depth_improve"):
        if depth_rmse_before is None or depth_rmse_after is None:
            passed = False
        else:
            depth_red = depth_rmse_before - depth_rmse_after
            depth_ratio = (depth_red / depth_rmse_before) if depth_rmse_before > 1e-9 else 0.0
            min_ratio = float(case.get("min_depth_rmse_reduction_ratio", 0.0))
            passed = passed and (depth_rmse_after < depth_rmse_before - 1e-6)
            if min_ratio > 0:
                passed = passed and depth_ratio >= min_ratio
    if case.get("max_waist_drift_ratio") is not None:
        passed = passed and waist_drift_ratio <= float(case["max_waist_drift_ratio"])

    leg_before = leg_after = None
    if case.get("require_leg_improve") or case.get("bipodal_mask"):
        from models.silhouette_deform import mesh_leg_profiles
        from pipeline.eval.metrics import bipodal_leg_rmse
        legs0 = mesh_leg_profiles(v0, bins=bins)
        legs1 = mesh_leg_profiles(v1, bins=bins)
        leg_before = bipodal_leg_rmse(mask_prof, legs0)
        leg_after = bipodal_leg_rmse(mask_prof, legs1)
        if case.get("require_leg_improve"):
            passed = passed and (
                leg_after["mean_leg_rmse"] < leg_before["mean_leg_rmse"] - 1e-6
            )
        if case.get("forbid_leg_crossover", True) and case.get("bipodal_mask"):
            passed = passed and (not leg_after.get("crossover"))

    return {
        "id": gid,
        "suite": "silhouette",
        "passed": bool(passed),
        "soft": bool(case.get("soft")),
        "release_gate": case.get("release_gate", True) is not False,
        "garment_type": case.get("garment_type"),
        "provenance": case.get("provenance"),
        "tags": case.get("tags") or [],
        "metrics": {
            "max_abs_x_delta": round(dx, 4),
            "max_abs_y_delta": round(dy, 4),
            "max_abs_z_delta": round(dz, 4),
            "mask_quality": report.get("mask_quality"),
            "bipodal": report.get("bipodal"),
            "bipodal_score": report.get("bipodal_score"),
            "length_fit": report.get("length_fit"),
            "fusion_iters": report.get("fusion_iters"),
            "profile_rmse_before": round(rmse_before, 4),
            "profile_rmse_after": round(rmse_after, 4),
            "profile_rmse_reduction": round(rmse_reduction, 4),
            "profile_rmse_reduction_ratio": round(rmse_ratio, 4),
            "depth_rmse_before": None if depth_rmse_before is None else round(depth_rmse_before, 4),
            "depth_rmse_after": None if depth_rmse_after is None else round(depth_rmse_after, 4),
            "depth_rmse_reduction_ratio": (
                None if depth_rmse_before is None or depth_rmse_after is None or depth_rmse_before <= 1e-9
                else round((depth_rmse_before - depth_rmse_after) / depth_rmse_before, 4)
            ),
            "waist_drift_ratio": round(waist_drift_ratio, 4),
            "leg_rmse_before": None if not leg_before else leg_before.get("mean_leg_rmse"),
            "leg_rmse_after": None if not leg_after else leg_after.get("mean_leg_rmse"),
            "leg_crossover": None if not leg_after else leg_after.get("crossover"),
        },
        "report": {
            "depth_ok": bool((report.get("depth") or {}).get("ok")),
            "garment_type": report.get("garment_type"),
        },
    }


def run_field_pipeline_case(case: dict[str, Any], *, output_root: str, use_blender: bool) -> dict[str, Any]:
    """합성 이미지+치수로 파이프라인 종단 (sim/render/texture off)."""
    from pipeline import run_pipeline
    from pipeline.schemas.manifest import JobManifest
    from pipeline.adapters.export_adapter import blender_available

    gid = case["id"]
    out_dir = os.path.join(output_root, gid)
    os.makedirs(out_dir, exist_ok=True)
    result: dict[str, Any] = {
        "id": gid,
        "suite": "field_pipeline",
        "garment_type": case.get("garment_type"),
        "provenance": case.get("provenance") or "synthetic_pipeline",
        "soft": bool(case.get("soft")),
        "release_gate": case.get("release_gate", True) is not False,
        "tags": case.get("tags") or [],
    }

    need_blender = case.get("require_blender", True)
    if need_blender and (not use_blender or not blender_available()):
        result.update({
            "passed": False,
            "skip_reason": "blender_unavailable",
            "metrics": {},
        })
        return result

    images = {}
    for key in ("front", "side", "back"):
        rel = (case.get("images") or {}).get(key) or case.get(f"{key}_image")
        if key == "front" and not rel:
            rel = case.get("image_path")
        if not rel:
            images[key] = None
            continue
        path = rel if os.path.isabs(rel) else os.path.join(ROOT, rel)
        images[key] = path if os.path.exists(path) else None
        if path and not os.path.exists(path) and key == "front":
            result.update({"passed": False, "error": f"missing_fixture:{rel}", "metrics": {}})
            return result

    opts = dict(case.get("options") or {})
    opts.setdefault("bake_texture", False)
    opts.setdefault("run_simulation", False)
    opts.setdefault("run_render", False)
    opts.setdefault("calibrate", True)
    opts.setdefault("qa_auto_retry", False)

    manifest = JobManifest.from_dict({
        "job_id": f"bench_{gid}",
        "body": case.get("body") or {"height": 165, "weight": 55},
        "garment_type": case.get("garment_type") or "tshirt",
        "measurements": case.get("target_measurements") or case.get("measurements") or {},
        "fabric": case.get("fabric") or {"cotton": 100},
        "images": images,
        "options": opts,
    })

    t0 = time.time()
    job = run_pipeline(manifest, output_root=out_dir)
    elapsed = round(time.time() - t0, 2)

    arts = job.artifacts or {}
    qa = job.qa or {}
    fit = job.fit or {}
    sources = fit.get("measurement_sources") or {}
    expect_template = case.get("expect_template_id")
    template_ok = True
    if expect_template:
        tid = ((arts.get("template") or {}) if isinstance(arts.get("template"), dict) else {}).get("id")
        template_ok = tid == expect_template or expect_template in str(job.garment_type or "")

    cal_ok = True
    for c in qa.get("checks") or []:
        if c.get("name") == "calibration_error" and not c.get("skipped"):
            cal_ok = bool(c.get("ok"))

    shaped = arts.get("cloth_shaped_obj") or arts.get("cloth_silhouette_obj")
    job_dir = os.path.join(out_dir, manifest.job_id)
    fallback_shaped = os.path.join(job_dir, "cloth_shaped.obj")
    fallback_sil = os.path.join(job_dir, "cloth_silhouette.obj")
    if not shaped or not os.path.exists(str(shaped)):
        if os.path.exists(fallback_sil):
            shaped = fallback_sil
        elif os.path.exists(fallback_shaped):
            shaped = fallback_shaped
    has_shaped = bool(shaped and os.path.exists(str(shaped)))
    status_ok = job.status in ("done", "needs_review") and job.status != "error"
    # needs_review only fail if case forbids it
    if job.status == "needs_review" and case.get("allow_needs_review", True) is False:
        status_ok = False
    if job.status == "error":
        status_ok = False

    require_user_src = case.get("require_user_measurements", True)
    src_ok = True
    if require_user_src and case.get("target_measurements"):
        src_ok = any(sources.get(k) == "user" for k in case["target_measurements"])

    sil_ok = True
    if opts.get("silhouette_deform") or (opts.get("phase") or "").upper() == "P1":
        sil_ok = bool(arts.get("cloth_silhouette_obj")) or any(
            "실루엣" in w for w in (job.warnings or [])
        )

    neural_ok = True
    if opts.get("neural_enabled") or (opts.get("phase") or "").upper() == "P2":
        neural_ok = bool(arts.get("neural_meta") and os.path.exists(arts["neural_meta"]))

    passed = bool(status_ok and cal_ok and has_shaped and src_ok and sil_ok and neural_ok and template_ok)
    # QA passed preferred but soft if allow_needs_review
    if case.get("require_qa_passed") and not qa.get("passed"):
        passed = False

    result.update({
        "passed": passed,
        "mode": "pipeline",
        "job_status": job.status,
        "elapsed_sec": elapsed,
        "metrics": {
            "qa_passed": bool(qa.get("passed")),
            "calibration_ok": cal_ok,
            "has_shaped_obj": has_shaped,
            "user_measurement_sources": src_ok,
            "silhouette_ok": sil_ok,
            "neural_meta_ok": neural_ok,
        },
        "measurement_sources": sources,
        "artifacts": {k: arts.get(k) for k in ("cloth_shaped_obj", "cloth_silhouette_obj", "neural_meta", "calibration_report")},
        "warnings": list(job.warnings or [])[:12],
        "error": job.error,
    })
    return result


def run_neural_contract_case(case: dict[str, Any], *, output_root: str) -> dict[str, Any]:
    """CPU-only P2 reconstruct+retarget 계약 검증."""
    from pipeline.adapters import neural_adapter
    from models.fitting_model import load_obj
    import numpy as np

    gid = case["id"]
    out_dir = os.path.join(output_root, gid)
    os.makedirs(out_dir, exist_ok=True)
    img = os.path.join(out_dir, "front.png")
    Path(img).write_bytes(b"x")

    backend = str(case.get("backend") or "synthetic")
    recon = neural_adapter.reconstruct(
        images={"front": img},
        garment_type=str(case.get("garment_type") or "skirt"),
        output_dir=out_dir,
        backend=backend,
    )
    tmpl = os.path.join(out_dir, "tmpl.obj")
    with open(tmpl, "w", encoding="utf-8") as f:
        for x in (-0.4, -0.1, 0.1, 0.4):
            for y in (0.0, 0.5, 1.0):
                for z in (-0.2, -0.05, 0.05, 0.2):
                    f.write(f"v {x} {y} {z}\n")
        f.write("f 1 2 3\nf 2 4 3\n")

    out = os.path.join(out_dir, "retarget.obj")
    ret = neural_adapter.retarget_to_template(
        neural_mesh_path=recon.get("mesh_path"),
        template_obj_path=tmpl,
        output_path=out,
        backend=backend,
        method=str(case.get("retarget_method") or "vertex_morph"),
        morph_strength=float(case.get("morph_strength", 0.5)),
        morph_depth_strength=case.get("morph_depth_strength"),
    )
    passed = bool(recon.get("ok") and ret.get("ok") and not ret.get("passthrough"))
    if case.get("require_topology", True):
        passed = passed and bool(ret.get("topology_preserved"))
        v0, f0 = load_obj(tmpl)
        v1, f1 = load_obj(out)
        passed = passed and len(v0) == len(v1) and len(f0) == len(f1)
        dx = float(np.max(np.abs(v1[:, 0] - v0[:, 0])))
        dz = float(np.max(np.abs(v1[:, 2] - v0[:, 2])))
    else:
        dx = float(ret.get("max_abs_x_delta") or 0)
        dz = float(ret.get("max_abs_z_delta") or 0)
    passed = passed and dx >= float(case.get("min_abs_x_delta", 0.0))
    passed = passed and dz >= float(case.get("min_abs_z_delta", 0.0))
    align = ret.get("align") or {}
    if case.get("require_align"):
        passed = passed and (align.get("centroid_err") is not None) and float(align["centroid_err"]) < float(
            case.get("max_align_centroid_err", 1e-3)
        )
        passed = passed and ret.get("method") == "icp_morph"
    return {
        "id": gid,
        "suite": "neural_contract",
        "passed": bool(passed),
        "soft": bool(case.get("soft")),
        "release_gate": case.get("release_gate", True) is not False,
        "provenance": case.get("provenance"),
        "tags": case.get("tags") or [],
        "metrics": {
            "max_abs_x_delta": round(dx, 5),
            "max_abs_z_delta": round(dz, 5),
            "topology_preserved": ret.get("topology_preserved"),
            "scale_z_min": ret.get("scale_z_min"),
            "scale_z_max": ret.get("scale_z_max"),
            "align_scale": align.get("scale"),
            "align_centroid_err": align.get("centroid_err"),
            "align_xz_rotation": align.get("xz_rotation"),
        },
        "reconstruct": {"ok": recon.get("ok"), "backend": recon.get("backend")},
        "retarget": {"ok": ret.get("ok"), "method": ret.get("method")},
    }


def run_case(case: dict[str, Any], *, output_root: str, use_blender: bool = True) -> dict[str, Any]:
    suite = case.get("suite") or "calibration"
    try:
        if suite == "calibration":
            return run_calibration_case(case, output_root=output_root, use_blender=use_blender)
        if suite == "measure_consistency":
            return run_measure_consistency_case(case, output_root=output_root, use_blender=use_blender)
        if suite == "classification":
            return run_classification_case(case, output_root=output_root)
        if suite == "silhouette":
            return run_silhouette_case(case, output_root=output_root)
        if suite == "field_pipeline":
            return run_field_pipeline_case(case, output_root=output_root, use_blender=use_blender)
        if suite == "neural_contract":
            return run_neural_contract_case(case, output_root=output_root)
        return {"id": case.get("id"), "suite": suite, "passed": False, "error": "unknown_suite"}
    except Exception as e:
        traceback.print_exc()
        return {
            "id": case.get("id"),
            "suite": suite,
            "passed": False,
            "error": str(e),
            "metrics": summarize_errors({}),
        }


def run_benchmark(
    cases_dir: str,
    output_dir: str,
    *,
    use_blender: bool = True,
    suites: Optional[list[str]] = None,
    case_ids: Optional[list[str]] = None,
) -> dict[str, Any]:
    os.makedirs(output_dir, exist_ok=True)
    cases = load_cases(cases_dir)
    if suites:
        cases = [c for c in cases if c.get("suite") in suites]
    if case_ids:
        want = set(case_ids)
        cases = [c for c in cases if c.get("id") in want]

    results = []
    for case in cases:
        print(f"[Bench] {case.get('suite')}/{case.get('id')} ...")
        r = run_case(case, output_root=output_dir, use_blender=use_blender)
        results.append(r)
        status = "PASS" if r.get("passed") else ("SKIP" if r.get("skip_reason") else "FAIL")
        mae = (r.get("metrics") or {}).get("mae_cm")
        print(f"  -> {status} mae={mae} err={r.get('error') or r.get('skip_reason') or ''}")

    summary = aggregate_suite(results)
    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "use_blender": use_blender,
        "cases_dir": cases_dir,
        "summary": summary,
        "results": results,
    }
    out_json = os.path.join(output_dir, "accuracy_report.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    out_md = os.path.join(output_dir, "accuracy_report.md")
    with open(out_md, "w", encoding="utf-8") as f:
        f.write(render_markdown(report))
    report["report_json"] = out_json
    report["report_md"] = out_md
    return report


def render_markdown(report: dict[str, Any]) -> str:
    s = report.get("summary") or {}
    lines = [
        "# Accuracy Benchmark Report",
        "",
        f"- generated: `{report.get('generated_at')}`",
        f"- blender: `{report.get('use_blender')}`",
        f"- cases: **{s.get('n_passed')}/{s.get('n_cases')}** passed (rate={s.get('pass_rate')})",
        f"- release gate: **{s.get('release_passed')}/{s.get('release_n')}** (rate={s.get('release_pass_rate')})",
        "",
        "## Suites",
        "",
        f"- calibration: {s.get('calibration')}",
        f"- measure_consistency: {s.get('measure_consistency')}",
        f"- classification: {s.get('classification')}",
        f"- silhouette: {s.get('silhouette')}",
        f"- field_pipeline: {s.get('field_pipeline')}",
        f"- neural_contract: {s.get('neural_contract')}",
        "",
        "## Cases",
        "",
        "| id | suite | passed | mae_cm | max_abs_cm | notes |",
        "|----|-------|--------|--------|------------|-------|",
    ]
    for r in report.get("results") or []:
        m = r.get("metrics") or {}
        note = r.get("skip_reason") or r.get("error") or r.get("mode") or ""
        lines.append(
            f"| {r.get('id')} | {r.get('suite')} | {r.get('passed')} | "
            f"{m.get('mae_cm')} | {m.get('max_abs_cm')} | {note} |"
        )
    lines.append("")
    return "\n".join(lines)
