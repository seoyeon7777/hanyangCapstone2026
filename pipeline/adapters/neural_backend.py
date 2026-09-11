"""Neural backend protocol + validation helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol


@dataclass
class NeuralRequest:
    images: dict[str, Optional[str]]
    garment_type: str = "tshirt"
    output_dir: str = ""
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class NeuralResult:
    ok: bool
    backend: str
    mesh_path: Optional[str] = None
    skipped: bool = False
    reason: str = ""
    meta: dict[str, Any] = field(default_factory=dict)


class NeuralBackend(Protocol):
    name: str

    def available(self) -> tuple[bool, str]:
        ...

    def reconstruct(self, req: NeuralRequest) -> NeuralResult:
        ...


def validate_mesh_obj(path: str) -> dict[str, Any]:
    """OBJ 존재·유한 정점·면 최소 검사."""
    from models.fitting_model import load_obj
    import numpy as np

    if not path or not os.path.exists(path):
        return {"ok": False, "reason": "missing"}
    verts, faces = load_obj(path)
    if verts.size == 0:
        return {"ok": False, "reason": "empty"}
    if not np.isfinite(verts).all():
        return {"ok": False, "reason": "non_finite"}
    if len(faces) == 0:
        return {"ok": False, "reason": "no_faces"}
    return {
        "ok": True,
        "n_verts": int(len(verts)),
        "n_faces": int(len(faces)),
    }
