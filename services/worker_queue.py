"""디스크 기반 로컬 워커 큐.

Redis/RQ가 없어도 Blender 잡을 직렬 실행할 수 있게 한다.
환경변수:
  PIPELINE_QUEUE=disk|thread   (기본 disk)
  PIPELINE_MAX_WORKERS=1       (Blender는 1 권장)
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


def _ensure_dirs():
    for d in (PENDING, RUNNING, DONE, FAILED):
        os.makedirs(d, exist_ok=True)


def enqueue(job_type: str, payload: dict[str, Any], job_id: Optional[str] = None) -> str:
    """잡을 pending에 넣고 job_id 반환."""
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
    """파이프라인 잡 전용 enqueue 헬퍼."""
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
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(item, f, ensure_ascii=False, indent=2)
    try:
        os.remove(src)
    except OSError:
        pass
    return dst


def claim_next() -> Optional[dict]:
    """pending 중 가장 오래된 잡 하나를 running으로 옮김."""
    _ensure_dirs()
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
    with open(path, encoding="utf-8") as f:
        item = json.load(f)
    item["status"] = "running"
    item["started_at"] = time.time()
    run_path = os.path.join(RUNNING, f"{job_id}.json")
    with open(run_path, "w", encoding="utf-8") as f:
        json.dump(item, f, ensure_ascii=False, indent=2)
    try:
        os.remove(path)
    except OSError:
        pass
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


def queue_stats() -> dict[str, Any]:
    _ensure_dirs()

    def count(d):
        return len([n for n in os.listdir(d) if n.endswith(".json")])

    return {
        "pending": count(PENDING),
        "running": count(RUNNING),
        "done": count(DONE),
        "failed": count(FAILED),
        "queue_dir": QUEUE_DIR,
        "mode": "disk" if use_disk_queue() else "thread",
        "workers": int(os.environ.get("PIPELINE_MAX_WORKERS", "1") or 1),
    }


def process_pipeline_job(payload: dict) -> dict:
    """파이프라인 잡 실행 (워커에서 호출)."""
    from pipeline import run_pipeline, JobManifest
    from services.job_store import update_job

    manifest = JobManifest.from_dict(payload)
    job_id = manifest.job_id
    update_job(job_id, status="running")
    # SSE 큐는 웹 프로세스에만 있으므로 파일 progress만 사용
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
    """잡 하나 처리. 없으면 False."""
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

            update_job(job_id, status="error", error=str(e))
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
    """Flask 프로세스 안에서 백그라운드 워커 스레드 기동 (dev 편의)."""
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
