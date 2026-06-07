import os

BLENDER_PATH = r"C:\Program Files\Blender Foundation\Blender 4.4\blender.exe"

BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT_DIR  = os.path.join(BASE_DIR, "blender")
OUTPUT_DIR  = os.path.join(BASE_DIR, "outputs")
