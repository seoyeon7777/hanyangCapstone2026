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

    from models.silhouette_deform import deform_obj_by_silhouette
    from models.fitting_model import load_obj

    gid = case["id"]
    out_dir = os.path.join(output_root, gid)
    os.makedirs(out_dir, exist_ok=True)

    obj = os.path.join(out_dir, "box.obj")
    with open(obj, "w") as f:
        for x in (-1.0, 1.0):
            for y in (0.0, 1.0, 2.0):
                for z in (-0.3, 0.3):
                    f.write(f"v {x} {y} {z}\n")
        f.write("f 1 2 3\n")

    front = os.path.join(out_dir, "front.png")
    img = Image.new("RGBA", (100, 120), (0, 0, 0, 0))
    px = img.load()
    if case.get("bipodal_mask"):
        # torso + two legs
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
            for x in range(50 - half, 50 + half):
                px[x, y] = (255, 0, 0, 255)
    img.save(front)

    side = None
    if case.get("with_side", True) and not case.get("bipodal_mask"):
        side = os.path.join(out_dir, "side.png")
        img2 = Image.new("RGBA", (100, 120), (0, 0, 0, 0))
        px2 = img2.load()
        for y in range(120):
            half = int(case.get("side_half_top", 40)) if y < 60 else int(case.get("side_half_bot", 18))
            for x in range(50 - half, 50 + half):
                px2[x, y] = (0, 255, 0, 255)
        img2.save(side)

    dst = os.path.join(out_dir, "deformed.obj")
    # denser mesh for bipodal
    if case.get("bipodal_mask"):
        with open(obj, "w") as f:
            for x in (-0.9, -0.4, 0.4, 0.9):
                for y in (0.0, 0.5, 1.0, 1.5, 2.0):
                    for z in (-0.2, 0.2):
                        f.write(f"v {x} {y} {z}\n")
            f.write("f 1 2 3\n")

    report = deform_obj_by_silhouette(
        obj, front, dst,
        strength=float(case.get("strength", 0.8)),
        edge_snap=float(case.get("edge_snap", 0.3)),
        side_mask_path=side,
        depth_strength=float(case.get("depth_strength", 0.8)),
        smooth_iters=0,
        bipodal="force" if case.get("bipodal_mask") else "auto",
    )
    v0, _ = load_obj(obj)
    v1, _ = load_obj(dst)
    dx = float(np.max(np.abs(v1[:, 0] - v0[:, 0])))
    dz = float(np.max(np.abs(v1[:, 2] - v0[:, 2])))
    min_dx = float(case.get("min_abs_x_delta", 0.01))
    min_dz = float(case.get("min_abs_z_delta", 0.01 if side else 0.0))
    passed = report.get("ok") and dx >= min_dx and (dz >= min_dz if side else True)
    if case.get("bipodal_mask"):
        passed = passed and bool(report.get("bipodal"))
    return {
        "id": gid,
        "suite": "silhouette",
        "passed": bool(passed),
        "metrics": {
            "max_abs_x_delta": round(dx, 4),
            "max_abs_z_delta": round(dz, 4),
            "mask_quality": report.get("mask_quality"),
            "bipodal": report.get("bipodal"),
            "bipodal_score": report.get("bipodal_score"),
        },
        "report": {
            "depth_ok": bool((report.get("depth") or {}).get("ok")),
        },
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
        "",
        "## Suites",
        "",
        f"- calibration: {s.get('calibration')}",
        f"- measure_consistency: {s.get('measure_consistency')}",
        f"- classification: {s.get('classification')}",
        f"- silhouette: {s.get('silhouette')}",
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
