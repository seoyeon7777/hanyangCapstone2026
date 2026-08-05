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
            # plain 메시지도 SSE로 전달 (레거시 runner)
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

    stages = [
        ("ingest", ingest.run),
        ("understand", understand.run),
        ("fabric", fabric_resolve.run),
        ("template_match", template_match.run),
        ("measure_fusion", measure_fusion.run),
        ("calibrate", calibrate.run),
        ("silhouette_deform", silhouette_deform.run),
        ("geometry_fit", run_geometry),
        ("qa", qa.run),
    ]

    try:
        for name, fn in stages:
            ctx.result.stage = name
            start_pct = stage_start_percent(name)
            ctx.report(start_pct, f"{name} 시작", stage=name)
            ctx = fn(ctx)
            end_pct = stage_end_percent(name)
            ctx.report(end_pct, f"{name} 완료", stage=name)

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
