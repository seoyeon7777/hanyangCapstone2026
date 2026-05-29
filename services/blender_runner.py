import subprocess
import json
import uuid
import os
import sys
import queue
import numpy as np

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'blender'))
from config import BLENDER_PATH, SCRIPT_DIR, OUTPUT_DIR, BASE_DIR

sys.path.append(BASE_DIR)
from models.fitting_model import calc_fabric_elasticity, calc_fabric_bending, calc_pressure_map, load_obj


def run_blender(params: dict, job_id: str = None, q: queue.Queue = None) -> tuple:

    if q: q.put("체형 분석 중...")

    job_id     = job_id or str(uuid.uuid4())
    output_dir = os.path.join(OUTPUT_DIR, job_id)
    os.makedirs(output_dir, exist_ok=True)

    avatar_size  = params["avatar_size"]
    garment_type = params["garment_type"]
    shape_keys   = params.get("shape_keys", {})
    fabric       = params.get("fabric", {})

    fabric_elasticity = calc_fabric_elasticity(fabric)
    fabric_bending    = calc_fabric_bending(fabric)

    blend_path        = os.path.join(BASE_DIR, "assets", "clothing", f"cloth_{garment_type}.blend")
    avatar_blend_path = os.path.join(BASE_DIR, "assets", "avatars",  f"body_{avatar_size}.blend")
    cloth_obj_path    = os.path.join(output_dir, "cloth_shaped.obj")
    sim_obj_path      = os.path.join(output_dir, "simulated_cloth.obj")
    avatar_verts_path = os.path.join(output_dir, "avatar_verts.json")

    if q: q.put("의류 형태 적용 중...")

    # ── 1단계: Shape Key 적용 후 OBJ export ──────────────────
    export_params = {
        "blend_path": blend_path,
        "output_obj": cloth_obj_path,
        "shape_keys": shape_keys,
    }
    export_params_path = os.path.join(output_dir, "export_params.json")
    with open(export_params_path, "w", encoding="utf-8") as f:
        json.dump(export_params, f, ensure_ascii=False)

    export_cmd = [
        BLENDER_PATH,
        "--background",
        "--python", os.path.join(SCRIPT_DIR, "export_cloth.py"),
        "--",
        export_params_path,
    ]
    export_result = subprocess.run(export_cmd, capture_output=True, text=True, timeout=60, encoding="utf-8", errors="replace")
    print(export_result.stdout)
    if export_result.returncode != 0:
        if q: q.put("error")
        raise RuntimeError(f"Shape Key export 오류:\n{export_result.stderr}\n{export_result.stdout}")
    if not os.path.exists(cloth_obj_path):
        if q: q.put("error")
        raise RuntimeError(f"OBJ export 실패\n[stdout]\n{export_result.stdout}\n[stderr]\n{export_result.stderr}")

    if q: q.put("물리 시뮬레이션 중...")

    # ── 2단계: Cloth 시뮬레이션 (아바타는 blend에서 로드) ────
    sim_params = {
        "cloth_obj_path":    cloth_obj_path,
        "avatar_blend_path": avatar_blend_path,
        "output_obj_path":   sim_obj_path,
        "avatar_verts_path": avatar_verts_path,
        "fabric_elasticity": fabric_elasticity,
        "bending_stiffness": fabric_bending,
        "garment_type":      garment_type,
        "avatar_size":       avatar_size,
    }
    sim_params_path = os.path.join(output_dir, "sim_params.json")
    with open(sim_params_path, "w", encoding="utf-8") as f:
        json.dump(sim_params, f, ensure_ascii=False)

    sim_cmd = [
        BLENDER_PATH,
        "--background",
        "--python", os.path.join(SCRIPT_DIR, "simulate_cloth.py"),
        "--",
        sim_params_path,
    ]
    sim_result = subprocess.run(sim_cmd, capture_output=True, text=True, timeout=300, encoding="utf-8", errors="replace")
    print(sim_result.stdout)
    if sim_result.returncode != 0:
        if q: q.put("error")
        raise RuntimeError(f"Cloth 시뮬레이션 오류:\n{sim_result.stderr}\n{sim_result.stdout}")
    if not os.path.exists(sim_obj_path):
        if q: q.put("error")
        raise RuntimeError(f"시뮬레이션 결과 없음\n[stdout]\n{sim_result.stdout}\n[stderr]\n{sim_result.stderr}")

    # ── 압박도 계산 ───────────────────────────────────────────
    sim_verts, _ = load_obj(sim_obj_path)

    # 아바타 버텍스: simulate_cloth.py가 저장한 JSON에서 로드 (body_*.obj 불필요)
    with open(avatar_verts_path, encoding="utf-8") as f:
        avatar_verts = np.array(json.load(f), dtype=np.float32)

    pressure = calc_pressure_map(sim_verts, avatar_verts, fabric_elasticity)
    print(f"[Runner] 핏 결과: {pressure['fit_result']} (압박도: {pressure['avg_pressure']})")

    if q: q.put("렌더링 중...")

    # ── 3단계: 렌더링 (아바타는 blend, 의류는 OBJ) ───────────
    render_params = {
        "output_dir":        output_dir,
        "avatar_blend_path": avatar_blend_path,
        "sim_obj_path":      sim_obj_path,
    }
    params_path = os.path.join(output_dir, "params.json")
    with open(params_path, "w", encoding="utf-8") as f:
        json.dump(render_params, f, ensure_ascii=False)

    cmd = [
        BLENDER_PATH,
        "--background",
        "--python", os.path.join(SCRIPT_DIR, "script.py"),
        "--",
        params_path,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120, encoding="utf-8", errors="replace")
        print(result.stdout)

        if result.returncode != 0:
            if q: q.put("error")
            raise RuntimeError(f"Blender 렌더링 오류:\n{result.stderr}\n{result.stdout}")

        expected = [
            "silhouette_front.png", "silhouette_right.png",
            "silhouette_back.png",  "silhouette_left.png",
        ]
        missing = [f for f in expected if not os.path.exists(os.path.join(output_dir, f))]
        if missing:
            if q: q.put("error")
            raise RuntimeError(
                f"렌더링 실패 — 파일 미생성: {missing}\n"
                f"[stdout]\n{result.stdout}\n[stderr]\n{result.stderr}"
            )

        if q: q.put("done")
        return job_id, output_dir

    except subprocess.TimeoutExpired:
        if q: q.put("error")
        raise RuntimeError("Blender 렌더링 시간 초과 (2분)")
    except FileNotFoundError:
        if q: q.put("error")
        raise RuntimeError(f"Blender를 찾을 수 없습니다: {BLENDER_PATH}")
