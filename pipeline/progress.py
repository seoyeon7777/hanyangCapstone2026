"""파이프라인 진행률(0–100) 헬퍼."""

from __future__ import annotations

import json
import os
from typing import Optional

# 스테이지별 가중치 (합 ≈ 100). 스테이지 시작 시 cumulative 이전 합 = 퍼센트.
STAGE_WEIGHTS: list[tuple[str, int]] = [
    ("ingest", 4),
    ("understand", 9),
    ("fabric", 4),
    ("template_match", 5),
    ("measure_fusion", 7),
    ("calibrate", 16),
    ("silhouette_deform", 5),
    ("geometry_fit", 41),  # export+sim+texture+render
    ("qa", 9),
]

STAGE_ORDER = [name for name, _ in STAGE_WEIGHTS]
_WEIGHT_MAP = dict(STAGE_WEIGHTS)


def stage_start_percent(stage: str) -> int:
    """해당 스테이지에 진입했을 때의 퍼센트."""
    total = 0
    for name, w in STAGE_WEIGHTS:
        if name == stage:
            return min(99, total)
        total += w
    return min(99, total)


def stage_end_percent(stage: str) -> int:
    total = 0
    for name, w in STAGE_WEIGHTS:
        total += w
        if name == stage:
            return min(100, total)
    return 100


def write_progress(
    output_dir: str,
    *,
    percent: int,
    stage: str,
    message: str,
    status: str = "running",
) -> str:
    """progress.json 기록. SSE와 폴링 모두에서 사용."""
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, "progress.json")
    payload = {
        "percent": max(0, min(100, int(percent))),
        "stage": stage,
        "message": message,
        "status": status,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    return path


def read_progress(output_dir: str) -> Optional[dict]:
    path = os.path.join(output_dir, "progress.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def format_progress_event(percent: int, message: str) -> str:
    """SSE 페이로드: 'PCT:<n>|<message>' (하위호환: plain message도 허용)."""
    pct = max(0, min(100, int(percent)))
    return f"PCT:{pct}|{message}"


def parse_progress_event(data: str) -> tuple[Optional[int], str]:
    if data.startswith("PCT:") and "|" in data:
        try:
            head, msg = data.split("|", 1)
            pct = int(head.split(":", 1)[1])
            return pct, msg
        except (ValueError, IndexError):
            return None, data
    return None, data
