import subprocess
import sys
import os
import json

# config.py 경로 추가
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'blender'))
from config import BLENDER_PATH, AVATAR_BLEND, OUTPUT_DIR

def run_blender(avatar_size, shape_keys, job_id="test"):
    """
    Blender를 백그라운드로 실행해서 렌더링
    """
    # 아바타 사이즈에 맞는 블렌드 파일 선택
    blend_file = AVATAR_BLEND.get(avatar_size)
    if not blend_file or not os.path.exists(blend_file):
        raise FileNotFoundError(f"블렌드 파일 없음: {blend_file}")

    # 출력 폴더 설정
    output_dir = os.path.join(OUTPUT_DIR, job_id)
    os.makedirs(output_dir, exist_ok=True)

    # 스크립트 경로
    script_path = os.path.join(os.path.dirname(__file__), '..', 'blender', 'script.py')

    # Blender 실행 명령어
    cmd = [
        BLENDER_PATH,
        "--background",         # UI 없이 실행
        blend_file,             # 블렌드 파일
        "--python", script_path, # 실행할 스크립트
        "--",                   # 이후는 스크립트 인자
        avatar_size,
        json.dumps(shape_keys),
        output_dir
    ]

    print(f"Blender 실행 중... (사이즈: {avatar_size})")
    print(f"출력 폴더: {output_dir}")

    result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore')

    if result.returncode != 0:
        print("Blender 오류:")
        print(result.stderr)
        print("Blender 출력:")
        print(result.stdout)
        raise RuntimeError("Blender 렌더링 실패")