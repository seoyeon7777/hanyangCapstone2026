"""헬스/ops 공통 스냅샷 (단일 정책)."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Optional


PROGRESS = {
    "p0_percent": 100,
    "p1_percent": 100,
    "p2_percent": 93,
}

# weighted overall = 0.55A + 0.30B + 0.15C
PROGRESS["vision_percent"] = int(round(
    0.55 * PROGRESS["p0_percent"]
    + 0.30 * PROGRESS["p1_percent"]
    + 0.15 * PROGRESS["p2_percent"]
))


def build_ops_snapshot(*, reclaim: bool = True) -> dict[str, Any]:
    from services.worker_queue import queue_stats, use_disk_queue, reclaim_stale_running
    from services.job_store import list_recent
    from services.alerts import evaluate_active_alerts, maybe_alert_queue
    from blender.config import BLENDER_PATH, BASE_DIR

    reclaimed = reclaim_stale_running() if reclaim else []
    stats = queue_stats()
    maybe_alert_queue(stats)
    blender_ok = os.path.exists(BLENDER_PATH) if BLENDER_PATH else False
    backlog = int(stats.get("pending") or 0) + int(stats.get("running") or 0)
    stale = int(stats.get("stale_running") or 0)
    ok = bool(blender_ok) and stale == 0

    health = {
        "ok": ok,
        "degraded": not ok,
        "blender_path": BLENDER_PATH,
        "blender_ok": blender_ok,
        "queue_mode": "disk" if use_disk_queue() else "thread",
        "queue": stats,
        "reclaimed": reclaimed,
        "backlog": backlog,
        "stale_running": stale,
        "recent_jobs": len(list_recent(5)),
    }

    accuracy: dict[str, Any] = {}
    for cand in (
        os.path.join(BASE_DIR, "benchmarks", "LAST_REPORT.json"),
        os.path.join(BASE_DIR, "outputs", "_accuracy", "accuracy_report.json"),
    ):
        if os.path.exists(cand):
            with open(cand, encoding="utf-8") as f:
                accuracy = json.load(f)
            accuracy["_source"] = cand
            break

    age_hours: Optional[float] = None
    gen = accuracy.get("generated_at")
    if gen:
        try:
            dt = datetime.strptime(gen[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
            age_hours = (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0
        except Exception:
            age_hours = None

    summary = accuracy.get("summary") or {}
    clf_meta = None
    for cand in (
        os.path.join(BASE_DIR, "assets", "clothing", "classifier_weights_meta.json"),
    ):
        if os.path.exists(cand):
            try:
                with open(cand, encoding="utf-8") as f:
                    clf_meta = json.load(f)
            except Exception:
                clf_meta = {"held_out": None}
            break
    alerts = evaluate_active_alerts(
        blender_ok=blender_ok,
        queue_stats=stats,
        accuracy_summary=summary,
        accuracy_age_hours=age_hours,
        stale_running=stale,
        classifier_meta=clf_meta if clf_meta is not None else {"held_out": None},
    )

    jobs = list_recent(10)
    slim_jobs = [
        {
            "job_id": j.get("job_id"),
            "status": j.get("status"),
            "updated_at": j.get("updated_at"),
            "error": j.get("error"),
            "retries": j.get("retries"),
        }
        for j in jobs
    ]
    status_counts: dict[str, int] = {}
    for j in jobs:
        st = j.get("status") or "unknown"
        status_counts[st] = status_counts.get(st, 0) + 1

    return {
        "health": health,
        "alerts": alerts,
        "accuracy": {
            "generated_at": accuracy.get("generated_at"),
            "use_blender": accuracy.get("use_blender"),
            "summary": summary,
            "source": accuracy.get("_source"),
            "age_hours": round(age_hours, 1) if age_hours is not None else None,
            "synthetic_field_n": summary.get("synthetic_field_n"),
            "release_pass_rate": summary.get("release_pass_rate"),
            "suites": {
                k: summary.get(k)
                for k in (
                    "calibration", "classification", "silhouette",
                    "measure_consistency", "field_pipeline", "neural_contract",
                )
                if summary.get(k) is not None
            },
        },
        "progress": dict(PROGRESS),
        "classifier": {
            "held_out": (clf_meta or {}).get("held_out"),
            "val_acc": (clf_meta or {}).get("val_acc"),
            "val_macro_f1": (clf_meta or {}).get("val_macro_f1"),
        },
        "recent_jobs": slim_jobs,
        "status_counts": status_counts,
        "http_status": 200 if ok else 503,
    }
