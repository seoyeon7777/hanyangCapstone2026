"""이미지+치수 → 3D 의류 파이프라인 오케스트레이터."""

from __future__ import annotations

import os
import traceback
from typing import Optional
import queue

from blender.config import OUTPUT_DIR
from pipeline.schemas.manifest import JobManifest, JobResult
from pipeline.stages import StageContext, make_progress_fn
from pipeline.stages import ingest, understand, fabric_resolve, measure_fusion, template_match, calibrate, qa
from pipeline.stages.geometry import run_geometry
from pipeline.stages import silhouette_deform
from pipeline.progress import (
    stage_start_percent,
    stage_end_percent,
    write_progress,
    format_progress_event,
)


def _run_stages(ctx: StageContext, stages: list) -> StageContext:
    for name, fn in stages:
        ctx.result.stage = name
        start_pct = stage_start_percent(name)
        ctx.report(start_pct, f"{name} 시작", stage=name)
        ctx = fn(ctx)
        end_pct = stage_end_percent(name)
        ctx.report(end_pct, f"{name} 완료", stage=name)
    return ctx


def _should_retry_qa(ctx: StageContext) -> bool:
    if ctx.result.status != "needs_review":
        return False
    qa = ctx.result.qa or {}
    checks = {c.get("name"): c for c in (qa.get("checks") or []) if isinstance(c, dict)}
    cal = checks.get("calibration_error") or {}
    if cal and not cal.get("ok") and not cal.get("skipped"):
        return True
    return False


def run_pipeline(
    manifest: JobManifest,
    q: Optional[queue.Queue] = None,
) -> JobResult:
    result = JobResult(job_id=manifest.job_id, status="running", garment_type=manifest.garment_type)
    output_dir = os.path.join(OUTPUT_DIR, manifest.job_id)
    os.makedirs(output_dir, exist_ok=True)

    base_progress = make_progress_fn(q)

    def progress_with_file(msg: str) -> None:
        from pipeline.progress import parse_progress_event, write_progress as _wp
        pct, text = parse_progress_event(msg)
        if pct is not None:
            _wp(
                output_dir,
                percent=pct,
                stage=result.stage or "running",
                message=text,
                status=result.status or "running",
            )
            base_progress(msg)
        else:
            base_progress(msg)

    ctx = StageContext(
        manifest=manifest,
        result=result,
        output_dir=output_dir,
        progress=progress_with_file,
    )

    write_progress(output_dir, percent=0, stage="start", message="파이프라인 시작", status="running")
    if q:
        q.put(format_progress_event(0, "파이프라인 시작"))

    early = [
        ("ingest", ingest.run),
        ("understand", understand.run),
        ("fabric", fabric_resolve.run),
        ("template_match", template_match.run),
        ("measure_fusion", measure_fusion.run),
    ]
    late = [
        ("calibrate", calibrate.run),
        ("silhouette_deform", silhouette_deform.run),
        ("geometry_fit", run_geometry),
        ("qa", qa.run),
    ]

    try:
        ctx = _run_stages(ctx, early)
        ctx = _run_stages(ctx, late)

        retries = 0
        max_retries = int(getattr(manifest.options, "qa_max_retries", 1) or 0)
        if getattr(manifest.options, "qa_auto_retry", True):
            while _should_retry_qa(ctx) and retries < max_retries:
                retries += 1
                ctx.result.warnings.append(
                    f"QA 자동 재시도 {retries}/{max_retries} — 캘리브 이터·허용오차 완화"
                )
                ctx.report(88, f"QA 재시도 {retries}", stage="qa_retry")
                # 완화: 이터↑, tolerance↑, gain 약간↓
                opts = ctx.manifest.options
                opts.calibrate_max_iters = int(opts.calibrate_max_iters) + 2
                opts.calibrate_tolerance_cm = float(opts.calibrate_tolerance_cm) + 0.5
                opts.calibrate_gain = max(0.5, float(opts.calibrate_gain) * 0.9)
                ctx.result.status = "running"
                # 캘리브부터 다시 (shaped obj 갱신)
                ctx.extras.pop("calibrated_obj", None)
                ctx = _run_stages(ctx, late)

        if ctx.result.status != "needs_review":
            ctx.result.status = "done"
        write_progress(
            output_dir,
            percent=100,
            stage="done",
            message="완료",
            status=ctx.result.status,
        )
        if q:
            q.put(format_progress_event(100, "완료"))
            q.put("done")
        return ctx.result
    except Exception as e:
        traceback.print_exc()
        ctx.result.status = "error"
        ctx.result.error = str(e)
        write_progress(
            output_dir,
            percent=stage_start_percent(ctx.result.stage or "ingest"),
            stage=ctx.result.stage or "error",
            message=f"오류: {e}",
            status="error",
        )
        if q:
            q.put("error")
        return ctx.result
