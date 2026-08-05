"""P2 — Neural garment reconstruction adapter.

실제 학습 가중치는 아직 없다.
백엔드:
  - stub: neural mesh 없음 → skipped (템플릿 유지)
  - synthetic: 테스트용 결정 변형 mesh 생성 (GPU 불필요)

계약:
  reconstruct(images, garment_type) -> {ok, mesh_path|None, skipped, ...}
  retarget_to_template(neural_mesh, template_obj) -> {ok, mesh_path, passthrough?}
"""

from __future__ import annotations

import os
import shutil
from typing import Any, Callable, Optional


class NeuralNotAvailable(RuntimeError):
    pass


class NeuralError(RuntimeError):
    pass


BackendFn = Callable[..., dict[str, Any]]

_BACKENDS: dict[str, BackendFn] = {}


def register_backend(name: str, fn: BackendFn) -> None:
    _BACKENDS[name.lower()] = fn


def list_backends() -> list[str]:
    return sorted(_BACKENDS.keys())


def _backend_stub(
    *,
    images: dict[str, Optional[str]],
    garment_type: str,
    output_dir: str,
    **_kw: Any,
) -> dict[str, Any]:
    return {
        "ok": False,
        "backend": "stub",
        "mesh_path": None,
        "skipped": True,
        "reason": "P2 stub — neural reconstruction not implemented; using template path",
        "images": {k: bool(v and os.path.exists(v)) for k, v in (images or {}).items()},
        "garment_type": garment_type,
    }


def _backend_synthetic(
    *,
    images: dict[str, Optional[str]],
    garment_type: str,
    output_dir: str,
    min_views: int = 1,
    **_kw: Any,
) -> dict[str, Any]:
    """테스트용: 존재하는 이미지 수와 garment_type에 따라 단순 OBJ 생성."""
    os.makedirs(output_dir, exist_ok=True)
    present = [k for k, v in (images or {}).items() if v and os.path.exists(v)]
    if len(present) < int(min_views):
        raise NeuralError(f"synthetic backend needs ≥{min_views} views, got {len(present)}")

    # 간단한 상자 mesh — 토폴로지는 템플릿과 무관 (retarget가 처리)
    path = os.path.join(output_dir, "synthetic_neural.obj")
    scale = 1.05 if "pants" in (garment_type or "").lower() else 1.0
    with open(path, "w", encoding="utf-8") as f:
        for x in (-0.5 * scale, 0.5 * scale):
            for y in (0.0, 1.0 * scale):
                for z in (-0.2, 0.2):
                    f.write(f"v {x:.4f} {y:.4f} {z:.4f}\n")
        # 2 triangles (dummy)
        f.write("f 1 2 3\nf 2 4 3\n")
    return {
        "ok": True,
        "backend": "synthetic",
        "mesh_path": path,
        "skipped": False,
        "views": present,
        "garment_type": garment_type,
        "reason": "synthetic dense mesh for contract tests",
    }


register_backend("stub", _backend_stub)
register_backend("synthetic", _backend_synthetic)


def reconstruct(
    *,
    images: dict[str, Optional[str]],
    garment_type: str = "tshirt",
    output_dir: str,
    backend: str = "stub",
    min_views: int = 1,
    timeout_sec: float = 120.0,
    neural_options: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """멀티뷰 이미지 → dense mesh."""
    os.makedirs(output_dir, exist_ok=True)
    backend = (backend or "stub").lower()
    fn = _BACKENDS.get(backend)
    if fn is None:
        raise NeuralNotAvailable(
            f"neural backend '{backend}' not installed — available: {list_backends()}"
        )
    opts = dict(neural_options or {})
    opts.setdefault("min_views", min_views)
    opts.setdefault("timeout_sec", timeout_sec)
    return fn(
        images=images or {},
        garment_type=garment_type,
        output_dir=output_dir,
        **opts,
    )


def retarget_to_template(
    *,
    neural_mesh_path: Optional[str],
    template_obj_path: str,
    output_path: str,
    backend: str = "stub",
    method: str = "passthrough",
) -> dict[str, Any]:
    """Neural mesh → 템플릿 토폴로지.

    neural mesh 가 없으면 성공이 아니라 skipped/passthrough.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)
    if not template_obj_path or not os.path.exists(template_obj_path):
        return {
            "ok": False,
            "backend": backend,
            "mesh_path": None,
            "skipped": True,
            "reason": "template_obj missing",
        }
    if not neural_mesh_path or not os.path.exists(neural_mesh_path):
        shutil.copy2(template_obj_path, output_path)
        return {
            "ok": False,
            "backend": backend,
            "mesh_path": output_path,
            "skipped": True,
            "passthrough": True,
            "method": method,
            "reason": "no neural mesh — template passthrough (not a neural retarget success)",
        }

    # 실제 non-rigid ICP 미구현: 템플릿 토폴로지 유지 + meta만 기록
    shutil.copy2(template_obj_path, output_path)
    return {
        "ok": True,
        "backend": backend,
        "mesh_path": output_path,
        "skipped": False,
        "passthrough": method == "passthrough",
        "method": method,
        "neural_mesh": neural_mesh_path,
        "reason": "retarget stub — preserve template topology (ICP TODO)",
    }
