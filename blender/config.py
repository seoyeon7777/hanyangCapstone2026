import os
import shutil

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT_DIR = os.path.join(BASE_DIR, "blender")
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")


def _detect_blender() -> str:
    env = os.environ.get("BLENDER_PATH")
    if env and os.path.exists(env):
        return env

    which = shutil.which("blender")
    if which:
        return which

    candidates = [
        r"C:\Program Files\Blender Foundation\Blender 4.4\blender.exe",
        r"C:\Program Files\Blender Foundation\Blender 4.2\blender.exe",
        r"C:\Program Files\Blender Foundation\Blender 4.0\blender.exe",
        "/usr/bin/blender",
        "/usr/local/bin/blender",
        "/Applications/Blender.app/Contents/MacOS/Blender",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return candidates[0]


BLENDER_PATH = _detect_blender()
