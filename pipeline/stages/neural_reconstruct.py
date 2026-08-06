"""P2 — Neural reconstruction stage (feature-flagged)."""

from __future__ import annotations

import json
import os

from pipeline.stages import StageContext
from pipeline.adapters import neural_adapter


def run(ctx: StageContext) -> StageContext:
    opts = ctx.manifest.options
    phase = (getattr(opts, "phase", "P0") or "P0").upper()
    enabled = bool(getattr(opts, "neural_enabled", False)) or phase == "P2"
    if not enabled:
        ctx.result.stage = "neural_reconstruct"
        return ctx

    ctx.progress("P2 neural 재구성...")
    backend = str(getattr(opts, "neural_backend", "stub") or "stub")
    required = bool(getattr(opts, "neural_required", False))
    fallback = bool(getattr(opts, "neural_fallback_to_template", True))
    min_views = int(getattr(opts, "neural_min_views", 1))
    timeout_sec = float(getattr(opts, "neural_timeout_sec", 120.0))
    neural_opts = dict(getattr(opts, "neural_options", None) or {})
    retarget_method = str(getattr(opts, "neural_retarget_method", "passthrough") or "passthrough")
    morph_strength = float(neural_opts.get("morph_strength", 0.35))
    morph_depth_strength = neural_opts.get("morph_depth_strength")
    if morph_depth_strength is not None:
        morph_depth_strength = float(morph_depth_strength)
    icp_iters = int(neural_opts.get("icp_iters", 4))
    smooth_iters = int(neural_opts.get("smooth_iters", 0))
    residual_pass = bool(neural_opts.get("residual_pass", True))
    residual_threshold = float(neural_opts.get("residual_threshold", 0.08))

    out_dir = ctx.path("neural")
    os.makedirs(out_dir, exist_ok=True)

    recon: dict = {}
    try:
        recon = neural_adapter.reconstruct(
            images=ctx.manifest.images or {},
            garment_type=ctx.manifest.garment_type or "tshirt",
            output_dir=out_dir,
            backend=backend,
            min_views=min_views,
            timeout_sec=timeout_sec,
            neural_options=neural_opts,
        )
    except neural_adapter.NeuralNotAvailable as e:
        ctx.result.warnings.append(str(e))
        recon = {"ok": False, "skipped": True, "reason": str(e), "backend": backend}
    except neural_adapter.NeuralError as e:
        ctx.result.warnings.append(f"P2 neural error: {e}")
        recon = {"ok": False, "skipped": False, "reason": str(e), "backend": backend, "error": True}
    except Exception as e:
        ctx.result.warnings.append(f"P2 neural unexpected: {e}")
        recon = {"ok": False, "skipped": False, "reason": str(e), "backend": backend, "error": True}

    recon["required"] = required
    recon["fallback_to_template"] = fallback
    ctx.extras["neural_reconstruct"] = recon
    meta_path = ctx.path("neural_meta.json")
    ctx.result.artifacts["neural_meta"] = meta_path

    failed = (not recon.get("ok")) and (not recon.get("skipped"))
    if recon.get("skipped") or not recon.get("ok"):
        ctx.result.warnings.append(
            f"P2 neural: {recon.get('reason') or 'template path retained'}"
        )
        if failed and required and not fallback:
            ctx.result.status = "needs_review"
            ctx.result.error = recon.get("reason") or "neural_required_failed"
            ctx.result.stage = "neural_reconstruct"
            try:
                with open(meta_path, "w", encoding="utf-8") as f:
                    json.dump({"reconstruct": recon}, f, ensure_ascii=False, indent=2)
            except Exception:
                pass
            return ctx

    ret: dict | None = None
    mesh = recon.get("mesh_path")
    if mesh and os.path.exists(mesh) and recon.get("ok"):
        tmpl = ctx.extras.get("calibrated_obj") or ctx.extras.get("shaped_obj")
        if tmpl and os.path.exists(tmpl):
            ret = neural_adapter.retarget_to_template(
                neural_mesh_path=mesh,
                template_obj_path=tmpl,
                output_path=ctx.path("cloth_neural_retarget.obj"),
                backend=backend,
                method=retarget_method,
                morph_strength=morph_strength,
                morph_depth_strength=morph_depth_strength,
                icp_iters=icp_iters,
                smooth_iters=smooth_iters,
                residual_pass=residual_pass,
                residual_threshold=residual_threshold,
            )
            ctx.extras["neural_retarget"] = ret
            if ret.get("ok") and ret.get("mesh_path") and os.path.exists(ret["mesh_path"]) and not ret.get("passthrough"):
                # topology QA vs template
                try:
                    from models.mesh_qa import inspect_obj

                    qa_rep = inspect_obj(ret["mesh_path"], ref_path=tmpl)
                    ret["topology_qa"] = {
                        k: qa_rep.get(k)
                        for k in (
                            "ok", "topology_match", "same_vert_count", "same_face_count",
                            "issues", "max_abs_x_delta",
                        )
                        if k in qa_rep or k == "ok"
                    }
                    ret["topology_qa"]["ok"] = bool(qa_rep.get("ok") and qa_rep.get("topology_match", True))
                    ret["topology_qa"]["issues"] = qa_rep.get("issues")
                    if ret["topology_qa"]["ok"]:
                        ctx.extras["calibrated_obj"] = ret["mesh_path"]
                        ctx.result.artifacts["cloth_neural_obj"] = ret["mesh_path"]
                        ctx.result.warnings.append(
                            f"P2 {ret.get('method') or 'retarget'} 적용 "
                            f"(Δx≤{ret.get('max_abs_x_delta')}, Δz≤{ret.get('max_abs_z_delta')})"
                        )
                    else:
                        ctx.result.warnings.append(
                            f"P2 retarget 토폴로지 QA 실패 — 템플릿 유지: {qa_rep.get('issues')}"
                        )
                        if required and not fallback:
                            ctx.result.status = "needs_review"
                except Exception as e:
                    ctx.result.warnings.append(f"P2 topology QA 스킵: {e}")
                    ctx.extras["calibrated_obj"] = ret["mesh_path"]
                    ctx.result.artifacts["cloth_neural_obj"] = ret["mesh_path"]
            elif ret.get("passthrough") or ret.get("skipped"):
                ctx.result.warnings.append(
                    "P2 retarget passthrough — calibrated template 유지"
                )
            elif required and not fallback:
                ctx.result.status = "needs_review"
                ctx.result.warnings.append("P2 retarget 실패 (required)")

    try:
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(
                {"reconstruct": recon, "retarget": ret},
                f,
                ensure_ascii=False,
                indent=2,
            )
    except Exception:
        pass

    ctx.result.stage = "neural_reconstruct"
    return ctx
