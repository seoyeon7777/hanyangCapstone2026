"""기존 blender_runner 를 파이프라인 스테이지용으로 래핑."""

from __future__ import annotations

import json
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
    run_export: bool = True,
    run_texture: bool = True,
    texture_path: Optional[str] = None,
    atlas_path: Optional[str] = None,
    atlas_layout: str = "1x2",
    cloth_obj_path: Optional[str] = None,
    blend_path: Optional[str] = None,
    avatar_blend_path: Optional[str] = None,
    fabric_elasticity: Optional[float] = None,
    fabric_bending: Optional[float] = None,
    stretch: str = "",
    preserve_silhouette: bool = False,
    progress: Optional[Callable[[str], None]] = None,
) -> dict[str, Any]:
    """단계 플래그를 지원하는 runner 래퍼."""
    job_id = os.path.basename(output_dir.rstrip("/\\"))

    class _Q:
        def put(self, msg):
            if not progress:
                return
            # geometry_fit 구간(대략 51–91) 내부 세분
            mapping = {
                "체형 분석 중...": 52,
                "의류 형태 적용 중...": 55,
                "물리 시뮬레이션 중...": 62,
                "텍스처 GLB 생성 중...": 78,
                "렌더링 중...": 85,
            }
            if isinstance(msg, str) and msg in mapping:
                from pipeline.progress import format_progress_event
                progress(format_progress_event(mapping[msg], msg))
            else:
                progress(msg)

    params = {
        "avatar_size": avatar_size,
        "garment_type": garment_file,
        "shape_keys": shape_keys,
        "fabric": fabric,
        "texture_path": texture_path,
        "atlas_path": atlas_path,
        "atlas_layout": atlas_layout or "1x2",
        "stretch": stretch,
        "fabric_elasticity": fabric_elasticity,
        "fabric_bending": fabric_bending,
        "run_export": run_export,
        "run_simulation": run_simulation,
        "run_render": run_render,
        "run_texture": run_texture and bool(texture_path or atlas_path),
        "cloth_obj_path": cloth_obj_path,
        "blend_path": blend_path,
        "avatar_blend_path": avatar_blend_path,
        "preserve_silhouette": bool(preserve_silhouette),
        "output_dir": output_dir,
    }

    jid, out_dir = run_blender(params, job_id=job_id, q=_Q())

    # 캘리브 shaped OBJ가 벤치 루트에만 있고 runner 산출물에 없으면 보존
    shaped = os.path.join(out_dir, "cloth_shaped.obj")
    if cloth_obj_path and os.path.exists(cloth_obj_path) and not os.path.exists(shaped):
        import shutil
        shutil.copy2(cloth_obj_path, shaped)
    fit = {}
    fit_path = os.path.join(out_dir, "fit_summary.json")
    if os.path.exists(fit_path):
        with open(fit_path, encoding="utf-8") as f:
            summary = json.load(f)
            fit = summary.get("fit") or {}

    files: dict[str, Any] = {
        "cloth_shaped_obj": os.path.join(out_dir, "cloth_shaped.obj"),
        "simulated_obj": os.path.join(out_dir, "simulated_cloth.obj"),
        "glb": os.path.join(out_dir, "cloth_textured.glb"),
        "albedo": texture_path,
        "albedo_atlas": atlas_path,
        "fit_summary": fit_path if os.path.exists(fit_path) else None,
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

    return {"job_id": jid, "files": files, "fit": fit}
