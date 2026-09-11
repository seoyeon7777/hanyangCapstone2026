"""TorchScript neural backend (optional).

torch 미설치/모델 없으면 skipped. 성공 위장 금지.
"""

from __future__ import annotations

import os
import time
from typing import Any, Optional

import numpy as np

from pipeline.adapters.neural_backend import NeuralRequest, NeuralResult, validate_mesh_obj
from pipeline.adapters.neural_preprocess import decode_faces, decode_verts, load_views_tensor


class TorchNeuralBackend:
    name = "torch"

    def __init__(self, model_path: Optional[str] = None, **opts: Any):
        self.model_path = model_path or opts.get("model_path") or os.environ.get("NEURAL_TORCH_MODEL")
        self.device = opts.get("device") or "cpu"
        self.input_size = int(opts.get("input_size", 128))
        self.layout = str(opts.get("layout", "nchw"))
        self.min_views = int(opts.get("min_views", 1))
        self.one_based_faces = bool(opts.get("one_based_faces", False))
        self.faces_path = opts.get("faces_path")
        self._module = opts.get("_module")  # 테스트 주입

    def available(self) -> tuple[bool, str]:
        if self._module is not None:
            return True, "injected_module"
        try:
            import torch  # noqa: F401
        except ImportError:
            return False, "torch_not_installed"
        if not self.model_path or not os.path.exists(self.model_path):
            return False, f"model_missing:{self.model_path or '(unset)'}"
        return True, "ok"

    def reconstruct(self, req: NeuralRequest) -> NeuralResult:
        ok, reason = self.available()
        if not ok:
            return NeuralResult(ok=False, backend=self.name, skipped=True, reason=reason)

        out_dir = req.output_dir
        os.makedirs(out_dir, exist_ok=True)
        out_obj = os.path.join(out_dir, "torch_neural.obj")
        opts = dict(req.options or {})
        min_views = int(opts.get("min_views", self.min_views))
        t0 = time.time()

        try:
            module = self._module
            if module is None:
                import torch
                module = torch.jit.load(self.model_path, map_location=self.device)
                module.eval()

            if hasattr(module, "run_garment"):
                verts_raw, faces_raw = module.run_garment(req.images, req.garment_type)
                present = [k for k, v in (req.images or {}).items() if v and os.path.exists(v)]
                mode = "run_garment"
            else:
                import torch
                tensor, present = load_views_tensor(
                    req.images or {},
                    size=int(opts.get("input_size", self.input_size)),
                    layout=str(opts.get("layout", self.layout)),
                    min_views=min_views,
                )
                with torch.no_grad():
                    t = torch.from_numpy(tensor)
                    out = module(t)
                if isinstance(out, (tuple, list)) and len(out) >= 2:
                    verts_raw, faces_raw = out[0], out[1]
                elif isinstance(out, dict):
                    verts_raw = out.get("vertices")
                    faces_raw = out.get("faces")
                else:
                    raise ValueError("torch module must return (verts, faces) or dict")
                if hasattr(verts_raw, "detach"):
                    verts_raw = verts_raw.detach().cpu().numpy()
                if hasattr(faces_raw, "detach"):
                    faces_raw = faces_raw.detach().cpu().numpy()
                mode = "forward"

            if faces_raw is None and self.faces_path and os.path.exists(self.faces_path):
                faces_raw = np.load(self.faces_path)
            verts = decode_verts(verts_raw)
            faces = decode_faces(faces_raw, one_based=self.one_based_faces)
            if faces.max() >= len(verts):
                raise ValueError("face index out of range")
        except Exception as e:
            return NeuralResult(
                ok=False, backend=self.name, skipped=False,
                reason=f"torch_infer_failed:{e}", meta={"error": str(e)},
            )

        from pipeline.adapters.neural_adapter import _write_obj

        _write_obj(out_obj, verts, faces)
        val = validate_mesh_obj(out_obj)
        meta = {
            **val,
            "mode": mode,
            "views": present,
            "elapsed_sec": round(time.time() - t0, 4),
            "device": self.device,
        }
        if not val.get("ok"):
            return NeuralResult(
                ok=False, backend=self.name, skipped=False,
                reason=f"invalid_mesh:{val.get('reason')}", meta=meta,
            )
        return NeuralResult(
            ok=True, backend=self.name, mesh_path=out_obj, skipped=False,
            reason="torch reconstruct ok", meta=meta,
        )


def make_torch_backend(**opts: Any) -> TorchNeuralBackend:
    return TorchNeuralBackend(**opts)
