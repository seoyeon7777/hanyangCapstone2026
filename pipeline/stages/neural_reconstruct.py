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
            )
            ctx.extras["neural_retarget"] = ret
            if ret.get("ok") and ret.get("mesh_path") and os.path.exists(ret["mesh_path"]):
                # passthrough-only retarget은 calibrated 교체하지 않음 (치수 유지)
                if not ret.get("passthrough"):
                    ctx.extras["calibrated_obj"] = ret["mesh_path"]
                    ctx.result.artifacts["cloth_neural_obj"] = ret["mesh_path"]
                else:
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
