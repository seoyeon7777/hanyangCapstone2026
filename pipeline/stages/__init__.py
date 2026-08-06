"""파이프라인 스테이지 공통 컨텍스트."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional
import os
import queue

from pipeline.schemas.manifest import JobManifest, JobResult
from pipeline.progress import format_progress_event, write_progress


ProgressFn = Callable[[str], None]


@dataclass
class StageContext:
    manifest: JobManifest
    result: JobResult
    output_dir: str
    progress: ProgressFn = field(default=lambda _msg: None)
    extras: dict[str, Any] = field(default_factory=dict)

    def path(self, *parts: str) -> str:
        return os.path.join(self.output_dir, *parts)

    def report(self, percent: int, message: str, stage: Optional[str] = None) -> None:
        """퍼센트+메시지 동시 기록 (파일 + SSE)."""
        st = stage or self.result.stage or "running"
        write_progress(
            self.output_dir,
            percent=percent,
            stage=st,
            message=message,
            status=self.result.status or "running",
        )
        self.progress(format_progress_event(percent, message))


def make_progress_fn(q: Optional[queue.Queue]) -> ProgressFn:
    def _emit(msg: str) -> None:
        if q is not None:
            q.put(msg)
    return _emit
