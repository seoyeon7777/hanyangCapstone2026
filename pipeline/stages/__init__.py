"""파이프라인 스테이지 공통 컨텍스트."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional
import os
import queue

from pipeline.schemas.manifest import JobManifest, JobResult


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


def make_progress_fn(q: Optional[queue.Queue]) -> ProgressFn:
    def _emit(msg: str) -> None:
        if q is not None:
            q.put(msg)
    return _emit
