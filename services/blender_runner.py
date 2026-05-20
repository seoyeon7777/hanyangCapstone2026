import subprocess
import json
import uuid
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'blender'))
from config import BLENDER_PATH, SCRIPT_DIR, OUTPUT_DIR, BASE_DIR

# 압박도 계산 함수
sys.path.append(BASE_DIR)
from models.fitting_model import calc_fabric_elasticity, calc_fabric_bending, calc_pressure_map, load_obj


def run_blender(params: dict) -> tuple:
    """
    1. Blender로 shape key 적용 후 cloth OBJ export
    2. Blender Cloth modifier로 물리 시뮬레이션
    3. 시뮬 결과 .obj를 블렌더로 렌더링

    params 예시:
    {
        "avatar_size":   "M",
        "garment_type":  "top",
        "shape_keys":    {"shoulder": -0.03, "chest": 0.13, "sleeve": 0.17},
        "fabric":        {"cotton": 80, "polyester": 20}
    }
    반환: (job_id, output_dir)
    """

    # 1. 고유 작업 ID 및 출력 폴더 생성
    job_id     = str(uuid.uuid4())
    output_dir = os.path.join(OUTPUT_DIR, job_id)
    os.makedirs(output_dir, exist_ok=True)

    avatar_size  = params["avatar_size"]
    garment_type = params["garment_type"]
    shape_keys   = params.get("shape_keys", {})
    fabric       = params.get("fabric", {})

    # 2. 원단 물성 계산
    fabric_elasticity = calc_fabric_elasticity(fabric)
    fabric_bending    = calc_fabric_bending(fabric)

    # 3. 경로 설정
    blend_path      = os.path.join(BASE_DIR, "assets", "clothing", f"cloth_{garment_type}.blend")
    cloth_obj_path  = os.path.join(output_dir, "cloth_shaped.obj")
    avatar_obj_path = os.path.join(BASE_DIR, "assets", "avatars",  f"body_{avatar_size}.obj")
    sim_obj_path    = os.path.join(output_dir, "simulated_cloth.obj")

    # 3-1. Blender로 shape key 적용 후 OBJ export
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
        raise RuntimeError(f"Shape Key export 오류:\n{export_result.stderr}\n{export_result.stdout}")
    if not os.path.exists(cloth_obj_path):
        raise RuntimeError(f"OBJ export 실패\n[stdout]\n{export_result.stdout}\n[stderr]\n{export_result.stderr}")

    # 4. Blender Cloth 시뮬레이션 실행
    sim_params = {
        "cloth_obj_path":    cloth_obj_path,
        "avatar_obj_path":   avatar_obj_path,
        "output_obj_path":   sim_obj_path,
        "fabric_elasticity": fabric_elasticity,
        "bending_stiffness": fabric_bending,
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
    sim_result = subprocess.run(sim_cmd, capture_output=True, text=True, timeout=180, encoding="utf-8", errors="replace")
    print(sim_result.stdout)
    if sim_result.returncode != 0:
        raise RuntimeError(f"Cloth 시뮬레이션 오류:\n{sim_result.stderr}\n{sim_result.stdout}")
    if not os.path.exists(sim_obj_path):
        raise RuntimeError(f"시뮬레이션 결과 없음\n[stdout]\n{sim_result.stdout}\n[stderr]\n{sim_result.stderr}")

    # 5. 압박도 계산 (시뮬 결과 OBJ 기반)
    sim_verts, _    = load_obj(sim_obj_path)
    avatar_verts, _ = load_obj(avatar_obj_path)
    pressure = calc_pressure_map(sim_verts, avatar_verts, fabric_elasticity)
    print(f"[Runner] 핏 결과: {pressure['fit_result']} (압박도: {pressure['avg_pressure']})")

    # 6. 렌더링 파라미터 구성
    render_params = {
        "output_dir":   output_dir,
        "avatar_size":  avatar_size,
        "garment_type": garment_type,
        "sim_obj_path": sim_obj_path,
        "base_dir":     BASE_DIR,
    }
    params_path = os.path.join(output_dir, "params.json")
    with open(params_path, "w", encoding="utf-8") as f:
        json.dump(render_params, f, ensure_ascii=False)

    # 7. 렌더링 실행
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
            raise RuntimeError(f"Blender 렌더링 오류:\n{result.stderr}\n{result.stdout}")

        expected = [
            "silhouette_front.png", "silhouette_right.png",
            "silhouette_back.png",  "silhouette_left.png",
        ]
        missing = [f for f in expected if not os.path.exists(os.path.join(output_dir, f))]
        if missing:
            raise RuntimeError(
                f"렌더링 실패 — 파일 미생성: {missing}\n"
                f"[stdout]\n{result.stdout}\n[stderr]\n{result.stderr}"
            )

        return job_id, output_dir

    except subprocess.TimeoutExpired:
        raise RuntimeError("Blender 렌더링 시간 초과 (2분)")
    except FileNotFoundError:
        raise RuntimeError(f"Blender를 찾을 수 없습니다: {BLENDER_PATH}")
