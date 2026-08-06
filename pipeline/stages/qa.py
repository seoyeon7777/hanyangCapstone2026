"""S8 — QA 게이트."""

from __future__ import annotations

import os

from pipeline.stages import StageContext


def run(ctx: StageContext) -> StageContext:
    ctx.progress("품질 검사 중...")
    checks = []
    passed = True

    for k, v in (ctx.result.shape_keys or {}).items():
        clamped = abs(v) >= 0.999
        checks.append({"name": f"shapekey_{k}", "ok": not clamped, "value": v})
        if clamped:
            passed = False
            ctx.result.warnings.append(f"Shape Key '{k}'가 한계(±1)에 도달 — 치수/템플릿 확인")

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

    if ctx.manifest.options.bake_texture:
        glb = files.get("glb")
        glb_ok = bool(glb and os.path.exists(str(glb)))
        checks.append({"name": "textured_glb", "ok": glb_ok, "path": glb})
        if not glb_ok:
            # hard fail보다는 검수 — 렌더는 됐을 수 있음
            ctx.result.warnings.append("텍스처 GLB 없음 — 시뮬/렌더만 확인하세요")
            checks[-1]["ok"] = True
            checks[-1]["soft"] = True

    fit = (ctx.result.fit or {}).get("fit_result")
    if fit in ("too_tight",):
        checks.append({"name": "fit_extreme", "ok": False, "value": fit})
        ctx.result.warnings.append("핏이 극단적으로 타이트 — 검수 권장")
    else:
        checks.append({"name": "fit_extreme", "ok": True, "value": fit})

    missing = ctx.extras.get("missing_measurements") or []
    if missing:
        passed = False
        checks.append({"name": "measurements_complete", "ok": False, "missing": missing})
    else:
        checks.append({"name": "measurements_complete", "ok": True})

    sources = ctx.extras.get("measurement_sources") or {}
    if sources:
        soft_ratio = sum(
            1 for s in sources.values() if s in ("ocr", "text", "silhouette_estimate")
        ) / max(len(sources), 1)
        est_ratio = sum(1 for s in sources.values() if s == "silhouette_estimate") / max(len(sources), 1)
        checks.append({
            "name": "measurement_sources",
            "ok": True,
            "sources": sources,
            "ocr_ratio": round(soft_ratio, 2),
            "silhouette_estimate_ratio": round(est_ratio, 2),
        })

    match = ctx.extras.get("template_match") or {}
    classification = ctx.extras.get("classification") or {}
    if match.get("nearest"):
        conf = float(classification.get("confidence") or 0.0)
        checks.append({
            "name": "template_exact",
            "ok": conf >= 0.35,
            "nearest": True,
            "template_id": match.get("template_id"),
            "classify_confidence": conf,
        })
        ctx.result.warnings.append(
            "권장: 전용 템플릿이 아닌 nearest 매칭 — 실측과 다를 수 있음"
        )
        if conf < 0.35:
            passed = False
            ctx.result.warnings.append("nearest 템플릿 + 낮은 분류 신뢰도 — 검수 필요")

    if classification:
        checks.append({
            "name": "classification",
            "ok": True,
            "label": classification.get("label"),
            "confidence": classification.get("confidence"),
            "source": classification.get("source"),
        })
        ctx.result.fit = dict(ctx.result.fit or {})
        ctx.result.fit["classification"] = classification

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
                f"최종 치수 오차 {max_err:.1f}cm > tolerance {tol}cm — 치수/템플릿 확인"
            )
    elif cal.get("skipped"):
        checks.append({
            "name": "calibration_error",
            "ok": True,
            "skipped": True,
            "reason": cal.get("skip_reason"),
        })

    # 메쉬 휴리스틱
    try:
        from models.mesh_qa import inspect_obj

        sim = files.get("simulated_obj")
        shaped = files.get("cloth_shaped_obj") or ctx.extras.get("calibrated_obj")
        if sim:
            mesh_rep = inspect_obj(sim, ref_path=shaped)
            checks.append({
                "name": "mesh_integrity",
                "ok": bool(mesh_rep.get("ok")),
                **{k: mesh_rep[k] for k in ("issues", "extents", "extent_ratio_vs_ref", "center_drift") if k in mesh_rep},
            })
            if not mesh_rep.get("ok"):
                passed = False
                ctx.result.warnings.append(
                    f"시뮬 메쉬 이상: {', '.join(mesh_rep.get('issues') or [])}"
                )
    except Exception as e:
        checks.append({"name": "mesh_integrity", "ok": True, "skipped": True, "error": str(e)})

    sil_rep = ctx.extras.get("silhouette_deform")
    if sil_rep:
        sil_ok = True
        sil_check = {
            "name": "silhouette_deform",
            "ok": True,
            "max_abs_x_delta": sil_rep.get("max_abs_x_delta"),
            "max_abs_y_delta": sil_rep.get("max_abs_y_delta"),
            "max_abs_z_delta": sil_rep.get("max_abs_z_delta"),
            "mask_quality": sil_rep.get("mask_quality"),
            "bipodal": sil_rep.get("bipodal"),
            "depth": bool((sil_rep.get("depth") or {}).get("ok")),
            "length_fit": sil_rep.get("length_fit"),
            "garment_type": sil_rep.get("garment_type"),
        }
        q = sil_rep.get("mask_quality")
        if q is not None and float(q) < 0.25:
            sil_ok = False
            ctx.result.warnings.append(f"실루엣 마스크 품질 낮음 ({q})")
        # 과도 변형 게이트 (캘리브 붕괴 방지)
        try:
            if float(sil_rep.get("max_abs_x_delta") or 0) > 0.55:
                sil_ok = False
                ctx.result.warnings.append("실루엣 X 변형 과다")
            if float(sil_rep.get("max_abs_y_delta") or 0) > 0.45:
                sil_ok = False
                ctx.result.warnings.append("실루엣 Y 변형 과다")
        except (TypeError, ValueError):
            pass
        lf = sil_rep.get("length_fit") or {}
        if lf.get("skipped") and lf.get("reason") == "full_frame_or_empty":
            sil_check["length_fit_skipped"] = True
        sil_check["ok"] = sil_ok
        checks.append(sil_check)
        if not sil_ok:
            passed = False

    neural = ctx.extras.get("neural_reconstruct")
    if neural:
        soft = not bool(neural.get("required"))
        n_ok = True
        if neural.get("error") or (not neural.get("skipped") and not neural.get("ok")):
            n_ok = False if neural.get("required") else True
            if not neural.get("skipped"):
                ctx.result.warnings.append("P2 neural 실패 — 템플릿 경로 유지")
        ret = ctx.extras.get("neural_retarget") or {}
        checks.append({
            "name": "neural_reconstruct",
            "ok": n_ok if neural.get("required") else True,
            "soft": soft,
            "backend": neural.get("backend"),
            "skipped": neural.get("skipped", True),
            "reason": neural.get("reason"),
            "retarget_ok": ret.get("ok"),
            "retarget_passthrough": ret.get("passthrough"),
            "retarget_method": ret.get("method"),
            "max_abs_x_delta": ret.get("max_abs_x_delta"),
            "max_abs_z_delta": ret.get("max_abs_z_delta"),
            "align_rms_after": (ret.get("align") or {}).get("rms_after"),
            "align_iters": (ret.get("align") or {}).get("iters"),
        })
        if neural.get("required") and not n_ok:
            passed = False
            ctx.result.warnings.append("P2 neural_required 실패")
        topo = (ret.get("topology_qa") or {}) if ret else {}
        if ret and ret.get("ok") and not ret.get("passthrough"):
            topo_ok = bool(topo.get("ok", True))
            checks.append({
                "name": "neural_retarget_topology",
                "ok": topo_ok,
                "soft": soft,
                "issues": topo.get("issues"),
                "topology_match": topo.get("topology_match"),
            })
            if not topo_ok and neural.get("required"):
                passed = False
            # morph magnitude / align quality gates (soft unless required)
            opts = ctx.manifest.options
            max_dx_gate = float(getattr(opts, "neural_max_abs_x_delta", 0.55) or 0.55)
            max_dz_gate = float(getattr(opts, "neural_max_abs_z_delta", 0.55) or 0.55)
            dx = float(ret.get("max_abs_x_delta") or 0)
            dz = float(ret.get("max_abs_z_delta") or 0)
            mag_ok = dx <= max_dx_gate and dz <= max_dz_gate
            align = ret.get("align") or {}
            align_ok = True
            if ret.get("method") == "icp_morph":
                align_ok = bool(align.get("rms_improved", True)) and float(
                    align.get("centroid_err") or 0
                ) < 0.05
            checks.append({
                "name": "neural_retarget_quality",
                "ok": bool(mag_ok and align_ok),
                "soft": soft,
                "max_abs_x_delta": dx,
                "max_abs_z_delta": dz,
                "morph_residual_rms": ret.get("morph_residual_rms"),
                "residual_pass": (ret.get("residual") or {}).get("applied"),
                "smooth_iters": ret.get("smooth_iters"),
                "partial_match_ratio": align.get("partial_match_ratio"),
                "align": {
                    "iters": align.get("iters"),
                    "rms_before": align.get("rms_before"),
                    "rms_after": align.get("rms_after"),
                    "centroid_err": align.get("centroid_err"),
                    "partial_match_ratio": align.get("partial_match_ratio"),
                },
            })
            if neural.get("required") and not (mag_ok and align_ok):
                passed = False
                ctx.result.warnings.append("P2 neural retarget quality gate 실패")
            # residual soft warning
            res_rms = float(ret.get("morph_residual_rms") or 0)
            if res_rms > 0.15:
                ctx.result.warnings.append(f"P2 morph residual RMS high: {res_rms}")
            # correspondence soft gate
            pmr = float(align.get("partial_match_ratio") or 0)
            if ret.get("method") == "icp_morph" and pmr < 0.35:
                ctx.result.warnings.append(f"P2 partial match low: {pmr}")
            checks.append({
                "name": "neural_export_artifact",
                "ok": bool(ctx.result.artifacts.get("cloth_neural_obj") or ctx.result.artifacts.get("cloth_neural_export")),
                "soft": True,
                "obj": ctx.result.artifacts.get("cloth_neural_obj"),
                "export_meta": ctx.result.artifacts.get("cloth_neural_export"),
            })

    hints = []
    if not passed:
        hints.append("needs_review: 결과 카드의 경고를 확인하세요")
    if any(s == "silhouette_estimate" for s in sources.values()):
        hints.append("치수 일부가 실루엣 추정입니다 — 수동 입력 권장")
    if any(s == "default" for s in sources.values()):
        hints.append("기본 치수가 포함되어 있습니다 — 사이즈표 입력 시 정확도↑")

    ctx.result.qa = {"passed": passed, "checks": checks, "hints": hints}
    if not passed:
        ctx.result.status = "needs_review"
    ctx.result.stage = "qa"
    return ctx
