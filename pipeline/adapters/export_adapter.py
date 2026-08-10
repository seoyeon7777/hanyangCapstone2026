"""Blender Shape Key export 전용 (캘리브레이션 반복용)."""

from __future__ import annotations

import json
import os
import subprocess
from typing import Any, Optional

from blender.config import BLENDER_PATH, SCRIPT_DIR


def export_shaped_cloth(
    *,
    blend_path: str,
    shape_keys: dict[str, float],
    output_obj: str,
    params_path: Optional[str] = None,
    timeout: int = 60,
) -> str:
    """export_cloth.py 로 Shape Key 적용 OBJ를 뽑는다. 성공 시 output_obj 경로 반환."""
    os.makedirs(os.path.dirname(os.path.abspath(output_obj)) or ".", exist_ok=True)
    params_path = params_path or (output_obj + ".params.json")
    payload = {
        "blend_path": blend_path,
        "output_obj": output_obj,
        "shape_keys": shape_keys,
    }
    with open(params_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)

    cmd = [
        BLENDER_PATH,
        "--background",
        "--python", os.path.join(SCRIPT_DIR, "export_cloth.py"),
        "--",
        params_path,
    ]
    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout,
        encoding="utf-8", errors="replace",
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Shape Key export 오류:\n{result.stderr}\n{result.stdout}"
        )
    if not os.path.exists(output_obj):
        raise RuntimeError(
            f"OBJ export 실패\n[stdout]\n{result.stdout}\n[stderr]\n{result.stderr}"
        )
    return output_obj


def blender_available() -> bool:
    path = BLENDER_PATH
    if not path:
        return False
    if os.path.isfile(path):
        return True
    # PATH 상의 blender
    from shutil import which
    return which("blender") is not None
