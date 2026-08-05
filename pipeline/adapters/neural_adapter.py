"""P2 — Neural garment reconstruction adapter (스텁).

실제 학습/추론 백엔드는 아직 없다.
phase=P2 또는 neural_enabled 시 파이프라인이 이 어댑터를 호출하며,
기본 백엔드 `stub` 은 템플릿 메쉬를 그대로 통과시키고 경고만 남긴다.

계약:
  reconstruct(images, garment_type) -> {mesh_path|None, meta}
  retarget_to_template(neural_mesh, template_obj) -> {mesh_path, meta}
"""

from __future__ import annotations

import os
import shutil
from typing import Any, Optional


class NeuralNotAvailable(RuntimeError):
    pass


def list_backends() -> list[str]:
    return ["stub"]


def reconstruct(
    *,
    images: dict[str, Optional[str]],
    garment_type: str = "tshirt",
    output_dir: str,
    backend: str = "stub",
) -> dict[str, Any]:
    """멀티뷰 이미지 → dense mesh (미구현: stub)."""
    os.makedirs(output_dir, exist_ok=True)
    backend = (backend or "stub").lower()
    if backend != "stub":
        raise NeuralNotAvailable(
            f"neural backend '{backend}' not installed — available: {list_backends()}"
        )
    return {
        "ok": False,
        "backend": "stub",
        "mesh_path": None,
        "skipped": True,
        "reason": "P2 stub — neural reconstruction not implemented; using template path",
        "images": {k: bool(v and os.path.exists(v)) for k, v in (images or {}).items()},
        "garment_type": garment_type,
    }


def retarget_to_template(
    *,
    neural_mesh_path: Optional[str],
    template_obj_path: str,
    output_path: str,
    backend: str = "stub",
) -> dict[str, Any]:
    """Neural mesh → 템플릿 토폴로지 (미구현: 템플릿 복사)."""
    os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)
    if not template_obj_path or not os.path.exists(template_obj_path):
        return {
            "ok": False,
            "backend": backend,
            "mesh_path": None,
            "reason": "template_obj missing",
        }
    shutil.copy2(template_obj_path, output_path)
    return {
        "ok": True,
        "backend": "stub",
        "mesh_path": output_path,
        "passthrough": True,
        "neural_mesh": neural_mesh_path,
        "reason": "stub retarget = copy template topology",
    }
