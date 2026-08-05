"""Blender 파이프라인 단계 실행기.

단계를 독립 함수로 분리해 선택 실행/재시도가 가능하게 한다.

  export_shaped → simulate → (optional texture glb) → render
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import uuid
from typing import Any, Optional

import numpy as np

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "blender"))
from config import BLENDER_PATH, SCRIPT_DIR, OUTPUT_DIR, BASE_DIR  # noqa: E402

sys.path.append(BASE_DIR)
from models.fitting_model import (  # noqa: E402
    calc_fabric_elasticity,
    calc_fabric_bending,
    calc_pressure_map,
    load_obj,
)


def _emit(q: Optional[queue.Queue], msg: str) -> None:
    if q is not None:
        q.put(msg)


def _run_blender_script(script_name: str, params_path: str, timeout: int) -> subprocess.CompletedProcess:
    cmd = [
        BLENDER_PATH,
        "--background",
        "--python", os.path.join(SCRIPT_DIR, script_name),
        "--",
        params_path,
    ]
    return subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout,
        encoding="utf-8", errors="replace",
    )


def resolve_fabric_params(params: dict) -> tuple[float, float]:
    fabric = params.get("fabric", {}) or {}
    elasticity = calc_fabric_elasticity(fabric)
    bending = calc_fabric_bending(fabric)
    if params.get("fabric_elasticity") is not None:
        elasticity = float(params["fabric_elasticity"])
    if params.get("fabric_bending") is not None:
        bending = float(params["fabric_bending"])
    stretch = params.get("stretch") or ""
    if stretch and params.get("fabric_elasticity") is None:
        from models.fabric import stretch_scale
        elasticity = max(0.01, min(0.99, elasticity * stretch_scale(stretch)))
    return elasticity, bending


def step_export(
    *,
    blend_path: str,
    output_obj: str,
    shape_keys: dict,
    output_dir: str,
    q: Optional[queue.Queue] = None,
) -> str:
    _emit(q, "의류 형태 적용 중...")
    params_path = os.path.join(output_dir, "export_params.json")
    with open(params_path, "w", encoding="utf-8") as f:
        json.dump({
            "blend_path": blend_path,
            "output_obj": output_obj,
            "shape_keys": shape_keys,
        }, f, ensure_ascii=False)

    result = _run_blender_script("export_cloth.py", params_path, timeout=60)
    print(result.stdout)
    if result.returncode != 0:
        raise RuntimeError(f"Shape Key export 오류:\n{result.stderr}\n{result.stdout}")
    if not os.path.exists(output_obj):
        raise RuntimeError(f"OBJ export 실패\n[stdout]\n{result.stdout}\n[stderr]\n{result.stderr}")
    return output_obj


def step_simulate(
    *,
    cloth_obj_path: str,
    avatar_blend_path: str,
    sim_obj_path: str,
    avatar_verts_path: str,
    fabric_elasticity: float,
    fabric_bending: float,
    garment_type: str,
    avatar_size: str,
    output_dir: str,
    preserve_silhouette: bool = False,
    q: Optional[queue.Queue] = None,
) -> dict[str, Any]:
    _emit(q, "물리 시뮬레이션 중...")
    params_path = os.path.join(output_dir, "sim_params.json")
    with open(params_path, "w", encoding="utf-8") as f:
        json.dump({
            "cloth_obj_path": cloth_obj_path,
            "avatar_blend_path": avatar_blend_path,
            "output_obj_path": sim_obj_path,
            "avatar_verts_path": avatar_verts_path,
            "fabric_elasticity": fabric_elasticity,
            "bending_stiffness": fabric_bending,
            "garment_type": garment_type,
            "avatar_size": avatar_size,
            "preserve_silhouette": bool(preserve_silhouette),
            "smooth_iterations": 3 if preserve_silhouette else 12,
            "smooth_factor": 0.35 if preserve_silhouette else 0.8,
        }, f, ensure_ascii=False)

    result = _run_blender_script("simulate_cloth.py", params_path, timeout=300)
    print(result.stdout)
    if result.returncode != 0:
        raise RuntimeError(f"Cloth 시뮬레이션 오류:\n{result.stderr}\n{result.stdout}")
    if not os.path.exists(sim_obj_path):
        raise RuntimeError(f"시뮬레이션 결과 없음\n[stdout]\n{result.stdout}\n[stderr]\n{result.stderr}")

    sim_verts, _ = load_obj(sim_obj_path)
    with open(avatar_verts_path, encoding="utf-8") as f:
        avatar_verts = np.array(json.load(f), dtype=np.float32)
    pressure = calc_pressure_map(sim_verts, avatar_verts, fabric_elasticity)
    print(f"[Runner] 핏 결과: {pressure['fit_result']} (압박도: {pressure['avg_pressure']})")
    # per_vertex는 결과 JSON이 커지므로 요약만 기본 반환
    return {
        "sim_obj_path": sim_obj_path,
        "fit": {
            "fit_result": pressure["fit_result"],
            "avg_pressure": pressure["avg_pressure"],
        },
    }


def step_texture_glb(
    *,
    cloth_obj_path: str,
    output_dir: str,
    texture_path: Optional[str] = None,
    atlas_path: Optional[str] = None,
    atlas_layout: str = "1x2",
    q: Optional[queue.Queue] = None,
) -> Optional[str]:
    if texture_path and not os.path.exists(texture_path):
        texture_path = None
    if atlas_path and not os.path.exists(atlas_path):
        atlas_path = None
    if not texture_path and not atlas_path:
        return None

    _emit(q, "텍스처 GLB 생성 중...")
    glb_path = os.path.join(output_dir, "cloth_textured.glb")
    params_path = os.path.join(output_dir, "texture_params.json")
    with open(params_path, "w", encoding="utf-8") as f:
        json.dump({
            "cloth_obj_path": cloth_obj_path,
            "albedo_path": texture_path,
            "atlas_path": atlas_path,
            "atlas_layout": atlas_layout or "1x2",
            "output_glb": glb_path,
        }, f, ensure_ascii=False)

    try:
        result = _run_blender_script("apply_texture.py", params_path, timeout=90)
        print(result.stdout)
        if result.returncode != 0 or not os.path.exists(glb_path):
            print(f"[Runner] 텍스처 GLB 경고:\n{result.stderr}")
            return None
        return glb_path
    except Exception as e:
        print(f"[Runner] 텍스처 GLB 스킵: {e}")
        return None


def step_render(
    *,
    output_dir: str,
    avatar_blend_path: str,
    sim_obj_path: str,
    texture_path: Optional[str] = None,
    atlas_path: Optional[str] = None,
    atlas_layout: str = "1x2",
    q: Optional[queue.Queue] = None,
) -> list[str]:
    _emit(q, "렌더링 중...")
    params_path = os.path.join(output_dir, "params.json")
    with open(params_path, "w", encoding="utf-8") as f:
        json.dump({
            "output_dir": output_dir,
            "avatar_blend_path": avatar_blend_path,
            "sim_obj_path": sim_obj_path,
            "texture_path": texture_path,
            "atlas_path": atlas_path,
            "atlas_layout": atlas_layout or "1x2",
        }, f, ensure_ascii=False)

    try:
        result = _run_blender_script("script.py", params_path, timeout=120)
        print(result.stdout)
        if result.returncode != 0:
            raise RuntimeError(f"Blender 렌더링 오류:\n{result.stderr}\n{result.stdout}")
    except subprocess.TimeoutExpired:
        raise RuntimeError("Blender 렌더링 시간 초과 (2분)")
    except FileNotFoundError:
        raise RuntimeError(f"Blender를 찾을 수 없습니다: {BLENDER_PATH}")

    expected = [
        "silhouette_front.png", "silhouette_right.png",
        "silhouette_back.png", "silhouette_left.png",
    ]
    missing = [f for f in expected if not os.path.exists(os.path.join(output_dir, f))]
    if missing:
        raise RuntimeError(f"렌더링 실패 — 파일 미생성: {missing}")
    return expected


def run_blender(params: dict, job_id: str = None, q: queue.Queue = None) -> tuple:
    """전체 파이프라인 (하위 호환).

    params 옵션 플래그:
      run_export / run_simulation / run_texture / run_render  (기본 True)
    캘리브레이션에서 이미 shaped OBJ가 있으면:
      cloth_obj_path 를 넘기고 run_export=False 가능
    """
    _emit(q, "체형 분석 중...")

    job_id = job_id or str(uuid.uuid4())
    output_dir = os.path.join(OUTPUT_DIR, job_id)
    os.makedirs(output_dir, exist_ok=True)

    run_export = params.get("run_export", True)
    run_simulation = params.get("run_simulation", True)
    run_texture = params.get("run_texture", True)
    run_render = params.get("run_render", True)

    avatar_size = params["avatar_size"]
    garment_type = params["garment_type"]
    shape_keys = params.get("shape_keys", {})
    fabric_elasticity, fabric_bending = resolve_fabric_params(params)

    blend_path = params.get("blend_path") or os.path.join(
        BASE_DIR, "assets", "clothing", f"cloth_{garment_type}.blend"
    )
    avatar_blend_path = params.get("avatar_blend_path") or os.path.join(
        BASE_DIR, "assets", "avatars", f"body_{avatar_size}.blend"
    )
    cloth_obj_path = params.get("cloth_obj_path") or os.path.join(output_dir, "cloth_shaped.obj")
    sim_obj_path = os.path.join(output_dir, "simulated_cloth.obj")
    avatar_verts_path = os.path.join(output_dir, "avatar_verts.json")

    fit: dict[str, Any] = {}
    glb_path = None

    try:
        if run_export:
            cloth_obj_path = step_export(
                blend_path=blend_path,
                output_obj=cloth_obj_path,
                shape_keys=shape_keys,
                output_dir=output_dir,
                q=q,
            )
        elif not os.path.exists(cloth_obj_path):
            raise FileNotFoundError(f"export 스킵인데 shaped OBJ 없음: {cloth_obj_path}")

        if run_simulation:
            sim_info = step_simulate(
                cloth_obj_path=cloth_obj_path,
                avatar_blend_path=avatar_blend_path,
                sim_obj_path=sim_obj_path,
                avatar_verts_path=avatar_verts_path,
                fabric_elasticity=fabric_elasticity,
                fabric_bending=fabric_bending,
                garment_type=garment_type,
                avatar_size=avatar_size,
                output_dir=output_dir,
                preserve_silhouette=bool(params.get("preserve_silhouette")),
                q=q,
            )
            fit = sim_info.get("fit") or {}
        else:
            # 시뮬 스킵 시 텍스처/렌더는 shaped 메쉬 사용
            sim_obj_path = cloth_obj_path

        texture_path = params.get("texture_path")
        atlas_path = params.get("atlas_path")
        atlas_layout = params.get("atlas_layout") or "1x2"

        if run_texture:
            glb_path = step_texture_glb(
                cloth_obj_path=sim_obj_path,
                output_dir=output_dir,
                texture_path=texture_path,
                atlas_path=atlas_path,
                atlas_layout=atlas_layout,
                q=q,
            )

        if run_render:
            step_render(
                output_dir=output_dir,
                avatar_blend_path=avatar_blend_path,
                sim_obj_path=sim_obj_path,
                texture_path=texture_path,
                atlas_path=atlas_path,
                atlas_layout=atlas_layout,
                q=q,
            )

        # fit 요약을 job 폴더에 저장 (어댑터/파이프라인에서 읽기 쉽게)
        with open(os.path.join(output_dir, "fit_summary.json"), "w", encoding="utf-8") as f:
            json.dump({
                "fit": fit,
                "glb": glb_path,
                "cloth_obj": cloth_obj_path,
                "sim_obj": sim_obj_path if run_simulation else None,
            }, f, ensure_ascii=False, indent=2)

        _emit(q, "done")
        return job_id, output_dir

    except Exception:
        _emit(q, "error")
        raise
