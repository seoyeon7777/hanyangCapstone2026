"""디스크 기반 잡 상태 스토어 (경량 — Celery 없이 재시도/조회)."""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Any, Optional

from blender.config import OUTPUT_DIR, BASE_DIR

_LOCK = threading.Lock()
STORE_DIR = os.path.join(BASE_DIR, "outputs", "_jobs")


def _path(job_id: str) -> str:
    os.makedirs(STORE_DIR, exist_ok=True)
    return os.path.join(STORE_DIR, f"{job_id}.json")


def save_job(job_id: str, payload: dict[str, Any]) -> str:
    data = dict(payload)
    data["job_id"] = job_id
    data["updated_at"] = time.time()
    if "created_at" not in data:
        data["created_at"] = data["updated_at"]
    path = _path(job_id)
    with _LOCK:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    return path


def update_job(job_id: str, **fields) -> Optional[dict]:
    cur = load_job(job_id) or {"job_id": job_id}
    cur.update(fields)
    save_job(job_id, cur)
    return cur


def load_job(job_id: str) -> Optional[dict]:
    path = _path(job_id)
    if not os.path.exists(path):
        # fallback: progress.json / job_result.json
        out = os.path.join(OUTPUT_DIR, job_id)
        prog = os.path.join(out, "progress.json")
        result = os.path.join(out, "job_result.json")
        if os.path.exists(result):
            with open(result, encoding="utf-8") as f:
                data = json.load(f)
            return {
                "job_id": job_id,
                "status": data.get("status", "done"),
                "result_path": result,
                "manifest": None,
            }
        if os.path.exists(prog):
            with open(prog, encoding="utf-8") as f:
                p = json.load(f)
            return {
                "job_id": job_id,
                "status": p.get("status", "running"),
                "progress": p,
            }
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def list_recent(limit: int = 20) -> list[dict]:
    os.makedirs(STORE_DIR, exist_ok=True)
    files = [
        os.path.join(STORE_DIR, n)
        for n in os.listdir(STORE_DIR)
        if n.endswith(".json")
    ]
    files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    out = []
    for p in files[:limit]:
        try:
            with open(p, encoding="utf-8") as f:
                out.append(json.load(f))
        except Exception:
            continue
    return out


def mark_retry(job_id: str) -> dict:
    cur = load_job(job_id) or {"job_id": job_id}
    retries = int(cur.get("retries") or 0) + 1
    cur["retries"] = retries
    cur["status"] = "queued_retry"
    cur["last_error"] = cur.get("error")
    save_job(job_id, cur)
    return cur
