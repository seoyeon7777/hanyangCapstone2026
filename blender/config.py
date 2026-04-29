import os

# Blender 설치 경로
BLENDER_PATH = r"D:\Program Files\Blender Foundation\Blender 4.2\blender.exe"

# 프로젝트 경로
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
SCRIPT_DIR = os.path.join(BASE_DIR, "blender")
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")
ASSET_DIR  = os.path.join(BASE_DIR, "assets")