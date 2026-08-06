"""선택적 운영 알림 (웹훅).

환경변수:
  PIPELINE_ALERT_WEBHOOK=https://hooks.example/xxx
  PIPELINE_ALERT_QUEUE_DEPTH=5
  PIPELINE_ALERT_ON_FAIL=1
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
from typing import Any, Optional

_last_sent: dict[str, float] = {}


def _webhook() -> Optional[str]:
    return (os.environ.get("PIPELINE_ALERT_WEBHOOK") or "").strip() or None


def _cooldown_ok(key: str, seconds: float = 120.0) -> bool:
    now = time.time()
    last = _last_sent.get(key, 0.0)
    if now - last < seconds:
        return False
    _last_sent[key] = now
    return True


def send_alert(title: str, detail: dict[str, Any] | None = None, *, key: str = "default") -> bool:
    url = _webhook()
    if not url:
        return False
    if not _cooldown_ok(key):
        return False
    payload = {
        "text": title,
        "title": title,
        "detail": detail or {},
        "ts": time.time(),
    }
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            resp.read()
        return True
    except Exception as e:
        print(f"[Alert] webhook failed: {e}")
        return False


def maybe_alert_queue(stats: dict[str, Any]) -> None:
    depth = int(stats.get("pending") or 0) + int(stats.get("running") or 0)
    threshold = int(os.environ.get("PIPELINE_ALERT_QUEUE_DEPTH", "5") or 5)
    if depth >= threshold:
        send_alert(
            f"pipeline queue depth high: {depth}",
            stats,
            key="queue_depth",
        )


def maybe_alert_failure(job_id: str, error: str) -> None:
    if (os.environ.get("PIPELINE_ALERT_ON_FAIL") or "1").strip() in {"0", "false", "no"}:
        return
    send_alert(
        f"pipeline job failed: {job_id}",
        {"job_id": job_id, "error": error},
        key=f"fail:{job_id}",
    )


def evaluate_active_alerts(
    *,
    blender_ok: bool,
    queue_stats: dict[str, Any] | None = None,
    accuracy_summary: dict[str, Any] | None = None,
    accuracy_age_hours: float | None = None,
    stale_running: int = 0,
    classifier_meta: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """웹훅과 무관한 순수 활성 알림 목록 (ops 대시보드용)."""
    alerts: list[dict[str, Any]] = []
    qs = queue_stats or {}
    depth = int(qs.get("pending") or 0) + int(qs.get("running") or 0)
    threshold = int(os.environ.get("PIPELINE_ALERT_QUEUE_DEPTH", "5") or 5)
    if not blender_ok:
        alerts.append({"level": "error", "code": "blender_unavailable", "message": "Blender missing"})
    if stale_running or int(qs.get("stale_running") or 0) > 0:
        alerts.append({
            "level": "warn",
            "code": "stale_running",
            "message": f"stale running jobs: {stale_running or qs.get('stale_running')}",
        })
    if int(qs.get("failed") or 0) > 0:
        alerts.append({
            "level": "warn",
            "code": "queue_failed",
            "message": f"failed queue jobs: {qs.get('failed')}",
        })
    if depth >= threshold:
        alerts.append({
            "level": "warn",
            "code": "queue_depth",
            "message": f"queue depth high: {depth}",
        })
    if accuracy_age_hours is not None and accuracy_age_hours > 72:
        alerts.append({
            "level": "info",
            "code": "stale_benchmark",
            "message": f"LAST_REPORT age {accuracy_age_hours:.0f}h",
        })
    summ = accuracy_summary or {}
    hard = summ.get("hard_fails") or []
    if hard:
        alerts.append({
            "level": "error",
            "code": "release_gate_fail",
            "message": f"hard fails: {', '.join(map(str, hard[:5]))}",
        })
    elif summ.get("release_pass_rate") is not None and float(summ["release_pass_rate"]) < 1.0:
        alerts.append({
            "level": "warn",
            "code": "release_pass_rate",
            "message": f"release_pass_rate={summ['release_pass_rate']}",
        })
    soft = summ.get("soft_fails") or []
    if soft:
        alerts.append({
            "level": "info",
            "code": "soft_fail_cases",
            "message": f"soft/diagnostic fails: {', '.join(map(str, soft[:5]))}",
        })
    if classifier_meta is not None:
        held = classifier_meta.get("held_out")
        val_acc = classifier_meta.get("val_acc")
        if held is False or (held is None and "val_acc" not in classifier_meta):
            alerts.append({
                "level": "warn",
                "code": "classifier_holdout_missing",
                "message": "classifier meta missing held-out val metrics",
            })
        elif val_acc is not None and float(val_acc) < float(
            os.environ.get("PIPELINE_CLASSIFIER_MIN_VAL_ACC", "0.7") or 0.7
        ):
            alerts.append({
                "level": "warn",
                "code": "classifier_holdout_fail",
                "message": f"classifier val_acc={val_acc}",
            })
    # Engineering scaffold complete; real tape data still external
    try:
        import glob
        from blender.config import BASE_DIR

        tape_n = 0
        for p in glob.glob(os.path.join(BASE_DIR, "benchmarks", "cases", "*.json")):
            try:
                with open(p, encoding="utf-8") as f:
                    d = json.load(f)
                if d.get("disabled"):
                    continue
                if d.get("provenance") == "field_tape":
                    tape_n += 1
            except Exception:
                continue
        if tape_n == 0:
            alerts.append({
                "level": "info",
                "code": "field_tape_missing",
                "message": "no provenance=field_tape cases yet (scaffold ready)",
            })
    except Exception:
        pass
    return alerts

