"""S8 — QA 게이트."""

from __future__ import annotations

from pipeline.stages import StageContext


def run(ctx: StageContext) -> StageContext:
    ctx.progress("품질 검사 중...")
    checks = []
    passed = True

    # Shape Key clamp
    for k, v in (ctx.result.shape_keys or {}).items():
        clamped = abs(v) >= 0.999
        checks.append({"name": f"shapekey_{k}", "ok": not clamped, "value": v})
        if clamped:
            passed = False
            ctx.result.warnings.append(f"Shape Key '{k}'가 한계(±1)에 도달 — 치수/템플릿 확인")

    # 필수 artifact
    files = ctx.result.artifacts or {}
    if ctx.manifest.options.run_simulation:
        ok = bool(files.get("simulated_obj"))
        checks.append({"name": "simulated_obj", "ok": ok})
        if not ok:
            passed = False

    if ctx.manifest.options.run_render:
        sil = files.get("silhouettes") or {}
        ok = all(sil.get(v) for v in ("front", "right", "back", "left"))
        checks.append({"name": "silhouettes", "ok": ok})
        if not ok:
            passed = False

    fit = (ctx.result.fit or {}).get("fit_result")
    if fit in ("too_tight",):
        checks.append({"name": "fit_extreme", "ok": False, "value": fit})
        ctx.result.warnings.append("핏이 극단적으로 타이트 — 검수 권장")
        # hard fail은 아님
    else:
        checks.append({"name": "fit_extreme", "ok": True, "value": fit})

    missing = ctx.extras.get("missing_measurements") or []
    if missing:
        passed = False
        checks.append({"name": "measurements_complete", "ok": False, "missing": missing})
    else:
        checks.append({"name": "measurements_complete", "ok": True})

    # 캘리브레이션 오차
    cal = ctx.extras.get("calibration") or {}
    if cal and not cal.get("skipped"):
        errs = cal.get("final_errors_cm") or {}
        tol = float(cal.get("tolerance_cm", 1.5))
        max_err = max((abs(v) for v in errs.values()), default=0.0)
        ok = bool(cal.get("converged")) or max_err <= tol
        checks.append({
            "name": "calibration_error",
            "ok": ok,
            "max_abs_error_cm": round(max_err, 3),
            "tolerance_cm": tol,
            "errors_cm": errs,
        })
        if not ok:
            passed = False
            ctx.result.warnings.append(
                f"최종 치수 오차 {max_err:.1f}cm > tolerance {tol}cm"
            )
    elif cal.get("skipped"):
        checks.append({
            "name": "calibration_error",
            "ok": True,
            "skipped": True,
            "reason": cal.get("skip_reason"),
        })

    ctx.result.qa = {"passed": passed, "checks": checks}
    if not passed:
        ctx.result.status = "needs_review"
    ctx.result.stage = "qa"
    return ctx
