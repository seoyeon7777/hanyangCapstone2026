import os
import shutil

# Windows 기본 설치 경로 + Linux/macOS PATH·환경변수 지원
_DEFAULT_WIN = r"C:\Program Files\Blender Foundation\Blender 4.4\blender.exe"


def _resolve_blender() -> str:
    env = os.environ.get("BLENDER_PATH")
    if env and os.path.isfile(env):
        return env
    which = shutil.which("blender")
    if which:
        return which
    for cand in (
        "/tmp/blender-4.4.3-linux-x64/blender",
        "/usr/bin/blender",
        _DEFAULT_WIN,
    ):
        if cand and os.path.isfile(cand):
            return cand
    return env or _DEFAULT_WIN


BLENDER_PATH = _resolve_blender()

BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT_DIR  = os.path.join(BASE_DIR, "blender")
OUTPUT_DIR  = os.path.join(BASE_DIR, "outputs")
