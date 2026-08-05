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
    texture_path: Optional[str] = None,
    progress: Optional[Callable[[str], None]] = None,
) -> dict[str, Any]:
    """기존 run_blender 전체 경로를 호출하고 artifact 맵을 반환."""
    job_id = os.path.basename(output_dir.rstrip("/\\"))

    class _Q:
        def put(self, msg):
            if progress:
                progress(msg)

    params = {
        "avatar_size": avatar_size,
        "garment_type": garment_file,
        "shape_keys": shape_keys,
        "fabric": fabric,
        "texture_path": texture_path,
    }

    if not run_simulation and not run_render:
        if progress:
            progress("시뮬레이션/렌더 스킵 요청 — 현재는 runner 전체 실행")

    jid, out_dir = run_blender(params, job_id=job_id, q=_Q())

    files: dict[str, Any] = {
        "cloth_shaped_obj": os.path.join(out_dir, "cloth_shaped.obj"),
        "simulated_obj": os.path.join(out_dir, "simulated_cloth.obj"),
        "glb": os.path.join(out_dir, "cloth_textured.glb"),
        "albedo": texture_path,
        "silhouettes": {
            "front": os.path.join(out_dir, "silhouette_front.png"),
            "right": os.path.join(out_dir, "silhouette_right.png"),
            "back": os.path.join(out_dir, "silhouette_back.png"),
            "left": os.path.join(out_dir, "silhouette_left.png"),
        },
    }
    if not os.path.exists(files["cloth_shaped_obj"]):
        files["cloth_shaped_obj"] = None
    if not os.path.exists(files["simulated_obj"]):
        files["simulated_obj"] = None
    if not files["glb"] or not os.path.exists(files["glb"]):
        files["glb"] = None
    files["silhouettes"] = {
        k: (v if os.path.exists(v) else None) for k, v in files["silhouettes"].items()
    }

    return {"job_id": jid, "files": files, "fit": {}}
