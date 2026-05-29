import os

# Blender 설치 경로
BLENDER_PATH = r"C:\Program Files\Blender Foundation\Blender 4.4\blender.exe"

# config.py는 blender/ 폴더 안에 있음
BLENDER_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR    = os.path.dirname(BLENDER_DIR)   # 프로젝트 루트
SCRIPT_DIR  = BLENDER_DIR
OUTPUT_DIR  = os.path.join(BASE_DIR, "outputs")
ASSET_DIR   = os.path.join(BASE_DIR, "assets")

# 아바타 블렌드 파일 경로 (의류 포함)
AVATAR_BLEND = {
    "S": os.path.join(BLENDER_DIR, "avatar_s.blend"),
    "M": os.path.join(BLENDER_DIR, "avatar_m.blend"),
    "L": os.path.join(BLENDER_DIR, "avatar_l.blend"),
}
