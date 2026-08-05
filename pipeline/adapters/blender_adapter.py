"""기존 blender_runner 를 파이프라인 스테이지용으로 래핑."""

from __future__ import annotations

import os
from typing import Any, Callable, Optional

from services.blender_runner import run_blender


def run_geometry_and_fit(
    *,
    output_dir: str,
    avatar_size: str,
    garment_file: str,
    shape_keys: dict[str, float],
    fabric: dict,
    run_simulation: bool = True,
    run_render: bool = True,
    progress: Optional[Callable[[str], None]] = None,
) -> dict[str, Any]:
    """기존 run_blender 전체 경로를 호출하고 artifact 맵을 반환.

    참고: 현재 runner는 export+sim+render를 한 번에 수행한다.
    run_simulation/run_render=False 는 향후 runner 분리 시 반영.
    """
    job_id = os.path.basename(output_dir.rstrip("/\\"))

    class _Q:
        def put(self, msg):
            if progress:
                progress(msg)

    # runner는 outputs/<job_id> 를 다시 만들므로 OUTPUT_DIR 구조를 맞춤
    params = {
        "avatar_size": avatar_size,
        "garment_type": garment_file,
        "shape_keys": shape_keys,
        "fabric": fabric,
    }

    if not run_simulation and not run_render:
        # 최소 경로: runner 전체 대신 향후 export-only 분리 지점
        if progress:
            progress("시뮬레이션/렌더 스킵 요청 — 현재는 runner 전체 실행")

    jid, out_dir = run_blender(params, job_id=job_id, q=_Q())

    files: dict[str, Any] = {
        "cloth_shaped_obj": os.path.join(out_dir, "cloth_shaped.obj"),
        "simulated_obj": os.path.join(out_dir, "simulated_cloth.obj"),
        "silhouettes": {
            "front": os.path.join(out_dir, "silhouette_front.png"),
            "right": os.path.join(out_dir, "silhouette_right.png"),
            "back": os.path.join(out_dir, "silhouette_back.png"),
            "left": os.path.join(out_dir, "silhouette_left.png"),
        },
    }
    # 존재 여부 정리
    if not os.path.exists(files["cloth_shaped_obj"]):
        files["cloth_shaped_obj"] = None
    if not os.path.exists(files["simulated_obj"]):
        files["simulated_obj"] = None
    files["silhouettes"] = {
        k: (v if os.path.exists(v) else None) for k, v in files["silhouettes"].items()
    }

    return {"job_id": jid, "files": files, "fit": {}}
