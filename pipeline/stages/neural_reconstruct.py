"""P2 — Neural reconstruction stage (feature-flagged stub)."""

from __future__ import annotations

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

    ctx.progress("P2 neural 재구성 (스텁)...")
    backend = str(getattr(opts, "neural_backend", "stub") or "stub")
    out_dir = ctx.path("neural")
    os.makedirs(out_dir, exist_ok=True)

    try:
        recon = neural_adapter.reconstruct(
            images=ctx.manifest.images or {},
            garment_type=ctx.manifest.garment_type or "tshirt",
            output_dir=out_dir,
            backend=backend,
        )
    except neural_adapter.NeuralNotAvailable as e:
        ctx.result.warnings.append(str(e))
        recon = {"ok": False, "skipped": True, "reason": str(e), "backend": backend}

    ctx.extras["neural_reconstruct"] = recon
    ctx.result.artifacts["neural_meta"] = ctx.path("neural_meta.json")
    try:
        import json
        with open(ctx.result.artifacts["neural_meta"], "w", encoding="utf-8") as f:
            json.dump(recon, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    if recon.get("skipped") or not recon.get("ok"):
        ctx.result.warnings.append(
            f"P2 neural stub: {recon.get('reason') or 'passthrough to template'}"
        )
    else:
        mesh = recon.get("mesh_path")
        if mesh and os.path.exists(mesh):
            # 템플릿 토폴로지로 retarget 시도
            tmpl = ctx.extras.get("calibrated_obj") or ctx.extras.get("shaped_obj")
            if tmpl and os.path.exists(tmpl):
                ret = neural_adapter.retarget_to_template(
                    neural_mesh_path=mesh,
                    template_obj_path=tmpl,
                    output_path=ctx.path("cloth_neural_retarget.obj"),
                    backend=backend,
                )
                ctx.extras["neural_retarget"] = ret
                if ret.get("mesh_path") and os.path.exists(ret["mesh_path"]):
                    ctx.extras["calibrated_obj"] = ret["mesh_path"]
                    ctx.result.artifacts["cloth_neural_obj"] = ret["mesh_path"]

    ctx.result.stage = "neural_reconstruct"
    return ctx
