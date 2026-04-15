import os

# 경로 모음 파일

# Blender 설치 경로 - 각자 블렌더 설치된 위치 넣으면 됨
BLENDER_PATH = r""

# 프로젝트 경로
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
SCRIPT_DIR = os.path.join(BASE_DIR, "blender")
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")
ASSET_DIR  = os.path.join(BASE_DIR, "assets")