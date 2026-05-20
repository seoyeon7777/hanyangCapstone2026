import os

# Blender 설치 경로
BLENDER_PATH = r"C:\Program Files\Blender Foundation\Blender 4.4\blender.exe"

# 프로젝트 경로
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR)  # blender 폴더의 상위 폴더
SCRIPT_DIR  = os.path.join(BASE_DIR, "blender")
OUTPUT_DIR  = os.path.join(PROJECT_DIR, "outputs")
ASSET_DIR   = os.path.join(BASE_DIR, "assets")

# 아바타 블렌드 파일 경로
AVATAR_BLEND = {
    "S": os.path.join(BASE_DIR, "avatar_s.blend"),
    "M": os.path.join(BASE_DIR, "avatar_m.blend"),
    "L": os.path.join(BASE_DIR, "avatar_l.blend"),
}