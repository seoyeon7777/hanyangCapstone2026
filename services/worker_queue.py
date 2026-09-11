"""디스크 기반 로컬 워커 큐.

Redis/RQ가 없어도 Blender 잡을 직렬 실행할 수 있게 한다.
환경변수:
  PIPELINE_QUEUE=disk|thread   (기본 disk)
  PIPELINE_MAX_WORKERS=1       (Blender는 1 권장)
  PIPELINE_STALE_RUNNING_SEC=900  (stuck running 회수)
"""

from __future__ import annotations

import json
import os
import threading
import time
import traceback
import uuid
from typing import Any, Callable, Optional

from blender.config import BASE_DIR, OUTPUT_DIR

QUEUE_DIR = os.path.join(BASE_DIR, "outputs", "_queue")
PENDING = os.path.join(QUEUE_DIR, "pending")
RUNNING = os.path.join(QUEUE_DIR, "running")
DONE = os.path.join(QUEUE_DIR, "done")
FAILED = os.path.join(QUEUE_DIR, "failed")

_worker_started = False
_worker_lock = threading.Lock()
_claim_lock = threading.Lock()


def _ensure_dirs():
    for d in (PENDING, RUNNING, DONE, FAILED):
        os.makedirs(d, exist_ok=True)


def enqueue(job_type: str, payload: dict[str, Any], job_id: Optional[str] = None) -> str:
    _ensure_dirs()
    job_id = job_id or str(uuid.uuid4())
    item = {
        "job_id": job_id,
        "type": job_type,
        "payload": payload,
        "enqueued_at": time.time(),
        "status": "pending",
    }
    path = os.path.join(PENDING, f"{job_id}.json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(item, f, ensure_ascii=False)
    os.replace(tmp, path)
    return job_id


def enqueue_pipeline_job(job_id: str, payload: dict[str, Any]) -> str:
    return enqueue("pipeline", payload, job_id=job_id)


def _move(src_dir: str, dst_dir: str, job_id: str, extra: Optional[dict] = None) -> Optional[str]:
    src = os.path.join(src_dir, f"{job_id}.json")
    if not os.path.exists(src):
        return None
    with open(src, encoding="utf-8") as f:
        item = json.load(f)
    if extra:
        item.update(extra)
    dst = os.path.join(dst_dir, f"{job_id}.json")
    tmp = dst + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(item, f, ensure_ascii=False, indent=2)
    os.replace(tmp, dst)
    try:
        os.remove(src)
    except OSError:
        pass
    return dst


def claim_next() -> Optional[dict]:
    """pending 중 가장 오래된 잡 하나를 running으로 원자적으로 옮김."""
    _ensure_dirs()
    with _claim_lock:
        files = [
            os.path.join(PENDING, n)
            for n in os.listdir(PENDING)
            if n.endswith(".json")
        ]
        if not files:
            return None
        files.sort(key=os.path.getmtime)
        path = files[0]
        job_id = os.path.splitext(os.path.basename(path))[0]
        try:
            with open(path, encoding="utf-8") as f:
                item = json.load(f)
        except Exception:
            return None
        item["status"] = "running"
        item["started_at"] = time.time()
        run_path = os.path.join(RUNNING, f"{job_id}.json")
        tmp = run_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(item, f, ensure_ascii=False, indent=2)
        try:
            os.replace(tmp, run_path)
            os.remove(path)
        except OSError:
            # 다른 워커가 가져간 경우
            try:
                os.remove(tmp)
            except OSError:
                pass
            if not os.path.exists(run_path):
                return None
            with open(run_path, encoding="utf-8") as f:
                item = json.load(f)
        try:
            from services.job_store import update_job

            update_job(job_id, status="running")
        except Exception:
            pass
        return item


def complete(job_id: str, ok: bool = True, error: Optional[str] = None) -> None:
    extra = {
        "status": "done" if ok else "failed",
        "finished_at": time.time(),
        "error": error,
    }
    dst = DONE if ok else FAILED
    if not _move(RUNNING, dst, job_id, extra):
        _move(PENDING, dst, job_id, extra)


def reclaim_stale_running(max_age_sec: Optional[float] = None) -> list[str]:
    """오래 running에 남은 잡을 pending으로 되돌림 (워커 크래시 복구)."""
    _ensure_dirs()
    if max_age_sec is None:
        max_age_sec = float(os.environ.get("PIPELINE_STALE_RUNNING_SEC", "900") or 900)
    now = time.time()
    reclaimed = []
    for name in list(os.listdir(RUNNING)):
        if not name.endswith(".json"):
            continue
        path = os.path.join(RUNNING, name)
        try:
            with open(path, encoding="utf-8") as f:
                item = json.load(f)
            started = float(item.get("started_at") or os.path.getmtime(path))
            if now - started < max_age_sec:
                continue
            job_id = item.get("job_id") or os.path.splitext(name)[0]
            item["status"] = "pending"
            item["reclaimed_at"] = now
            item["reclaim_reason"] = f"stale_running>{max_age_sec}s"
            item.pop("started_at", None)
            dst = os.path.join(PENDING, f"{job_id}.json")
            tmp = dst + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(item, f, ensure_ascii=False, indent=2)
            os.replace(tmp, dst)
            os.remove(path)
            reclaimed.append(job_id)
            try:
                from services.job_store import update_job

                update_job(job_id, status="queued", error=item.get("reclaim_reason"))
            except Exception:
                pass
        except Exception:
            traceback.print_exc()
            continue
    return reclaimed


def _oldest_age(dir_path: str) -> Optional[float]:
    files = [os.path.join(dir_path, n) for n in os.listdir(dir_path) if n.endswith(".json")]
    if not files:
        return None
    oldest = min(os.path.getmtime(p) for p in files)
    return round(time.time() - oldest, 1)


def queue_stats() -> dict[str, Any]:
    _ensure_dirs()

    def count(d):
        return len([n for n in os.listdir(d) if n.endswith(".json")])

    stale_threshold = float(os.environ.get("PIPELINE_STALE_RUNNING_SEC", "900") or 900)
    stale_running = 0
    now = time.time()
    for name in os.listdir(RUNNING):
        if not name.endswith(".json"):
            continue
        path = os.path.join(RUNNING, name)
        try:
            with open(path, encoding="utf-8") as f:
                item = json.load(f)
            started = float(item.get("started_at") or os.path.getmtime(path))
            if now - started >= stale_threshold:
                stale_running += 1
        except Exception:
            stale_running += 1

    return {
        "pending": count(PENDING),
        "running": count(RUNNING),
        "done": count(DONE),
        "failed": count(FAILED),
        "stale_running": stale_running,
        "oldest_pending_age_sec": _oldest_age(PENDING),
        "oldest_running_age_sec": _oldest_age(RUNNING),
        "queue_dir": QUEUE_DIR,
        "mode": "disk" if use_disk_queue() else "thread",
        "workers": int(os.environ.get("PIPELINE_MAX_WORKERS", "1") or 1),
        "stale_threshold_sec": stale_threshold,
    }


def process_pipeline_job(payload: dict) -> dict:
    from pipeline import run_pipeline, JobManifest
    from services.job_store import update_job

    manifest = JobManifest.from_dict(payload)
    job_id = manifest.job_id
    update_job(job_id, status="running")
    result = run_pipeline(manifest, q=None)
    out_dir = os.path.join(OUTPUT_DIR, job_id)
    os.makedirs(out_dir, exist_ok=True)
    result_path = os.path.join(out_dir, "job_result.json")
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(result.to_dict(), f, ensure_ascii=False, indent=2)
    update_job(
        job_id,
        status=result.status,
        error=result.error,
        result_path=result_path,
    )
    if result.status == "error":
        raise RuntimeError(result.error or "pipeline error")
    return result.to_dict()


HANDLERS: dict[str, Callable[[dict], Any]] = {
    "pipeline": process_pipeline_job,
}


def run_one() -> bool:
    reclaim_stale_running()
    item = claim_next()
    if not item:
        return False
    job_id = item["job_id"]
    job_type = item.get("type") or "pipeline"
    handler = HANDLERS.get(job_type)
    try:
        if not handler:
            raise RuntimeError(f"unknown job type: {job_type}")
        handler(item.get("payload") or {})
        complete(job_id, ok=True)
    except Exception as e:
        traceback.print_exc()
        complete(job_id, ok=False, error=str(e))
        try:
            from services.job_store import update_job
            from services.alerts import maybe_alert_failure

            update_job(job_id, status="error", error=str(e))
            maybe_alert_failure(job_id, str(e))
        except Exception:
            pass
    return True


def worker_loop(poll_seconds: float = 1.0, once: bool = False) -> None:
    print(f"[Worker] start queue={QUEUE_DIR}")
    while True:
        did = run_one()
        if once:
            break
        if not did:
            time.sleep(poll_seconds)


def ensure_background_worker(max_workers: int = 1) -> None:
    global _worker_started
    with _worker_lock:
        if _worker_started:
            return
        _worker_started = True

        def _loop():
            while True:
                try:
                    if not run_one():
                        time.sleep(0.8)
                except Exception:
                    traceback.print_exc()
                    time.sleep(1.0)

        n = max(1, int(max_workers))
        for i in range(n):
            t = threading.Thread(target=_loop, name=f"pipeline-worker-{i}", daemon=True)
            t.start()
        print(f"[Worker] in-process workers={n}")


def use_disk_queue() -> bool:
    mode = (os.environ.get("PIPELINE_QUEUE") or "disk").strip().lower()
    return mode in {"disk", "queue", "worker", "1", "true"}
