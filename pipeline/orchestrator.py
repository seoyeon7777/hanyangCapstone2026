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


def run_pipeline(
    manifest: JobManifest,
    q: Optional[queue.Queue] = None,
) -> JobResult:
    result = JobResult(job_id=manifest.job_id, status="running", garment_type=manifest.garment_type)
    output_dir = os.path.join(OUTPUT_DIR, manifest.job_id)
    os.makedirs(output_dir, exist_ok=True)

    ctx = StageContext(
        manifest=manifest,
        result=result,
        output_dir=output_dir,
        progress=make_progress_fn(q),
    )

    stages = [
        ("ingest", ingest.run),
        ("understand", understand.run),
        ("fabric", fabric_resolve.run),
        ("measure_fusion", measure_fusion.run),
        ("template_match", template_match.run),
        ("calibrate", calibrate.run),
        ("geometry_fit", run_geometry),
        ("qa", qa.run),
    ]

    try:
        for name, fn in stages:
            ctx.result.stage = name
            ctx = fn(ctx)

        if ctx.result.status != "needs_review":
            ctx.result.status = "done"
        if q:
            q.put("done")
        return ctx.result
    except Exception as e:
        traceback.print_exc()
        ctx.result.status = "error"
        ctx.result.error = str(e)
        if q:
            q.put("error")
        return ctx.result
