"""ONNX Runtime neural backend (optional).

표준 InferenceSession.run 계약 + 테스트용 run_garment 주입.
모델/런타임 없으면 skipped — 성공 위장 금지.
"""

from __future__ import annotations

import os
import time
from typing import Any, Optional

import numpy as np

from pipeline.adapters.neural_backend import NeuralRequest, NeuralResult, validate_mesh_obj
from pipeline.adapters.neural_preprocess import (
    decode_faces,
    decode_verts,
    load_views_tensor,
)


class OnnxNeuralBackend:
    name = "onnx"

    def __init__(self, model_path: Optional[str] = None, **opts: Any):
        self.model_path = model_path or opts.get("model_path") or os.environ.get("NEURAL_ONNX_MODEL")
        self.providers = opts.get("providers") or ["CPUExecutionProvider"]
        self.input_name = opts.get("input_name") or "images"
        self.verts_name = opts.get("verts_name") or "vertices"
        self.faces_name = opts.get("faces_name") or "faces"
        self.faces_path = opts.get("faces_path")  # 외부 fixed topology
        self.one_based_faces = bool(opts.get("one_based_faces", False))
        self.input_size = int(opts.get("input_size", 128))
        self.layout = str(opts.get("layout", "nchw"))
        self.min_views = int(opts.get("min_views", 1))
        self._session = opts.get("_session")

    def available(self) -> tuple[bool, str]:
        if self._session is not None:
            return True, "injected_session"
        try:
            import onnxruntime  # noqa: F401
        except ImportError:
            return False, "onnxruntime_not_installed"
        if not self.model_path or not os.path.exists(self.model_path):
            return False, f"model_missing:{self.model_path or '(unset)'}"
        return True, "ok"

    def reconstruct(self, req: NeuralRequest) -> NeuralResult:
        ok, reason = self.available()
        if not ok:
            return NeuralResult(ok=False, backend=self.name, skipped=True, reason=reason)

        out_dir = req.output_dir
        os.makedirs(out_dir, exist_ok=True)
        out_obj = os.path.join(out_dir, "onnx_neural.obj")
        opts = dict(req.options or {})
        min_views = int(opts.get("min_views", self.min_views))

        session = self._session
        if session is None:
            import onnxruntime as ort
            session = ort.InferenceSession(self.model_path, providers=list(self.providers))

        t0 = time.time()
        try:
            if hasattr(session, "run_garment"):
                verts_raw, faces_raw = session.run_garment(req.images, req.garment_type)
                present = [k for k, v in (req.images or {}).items() if v and os.path.exists(v)]
                feed_meta = {"mode": "run_garment"}
            else:
                tensor, present = load_views_tensor(
                    req.images or {},
                    size=int(opts.get("input_size", self.input_size)),
                    layout=str(opts.get("layout", self.layout)),
                    min_views=min_views,
                )
                in_name = self.input_name
                if hasattr(session, "get_inputs"):
                    inputs = session.get_inputs()
                    if inputs:
                        in_name = inputs[0].name
                feeds = {in_name: tensor}
                out_names = None
                if hasattr(session, "get_outputs"):
                    outs = session.get_outputs()
                    if outs:
                        out_names = [o.name for o in outs]
                raw = session.run(out_names, feeds)
                # map by name if possible
                name_to_val = {}
                if out_names:
                    name_to_val = {n: v for n, v in zip(out_names, raw)}
                verts_raw = name_to_val.get(self.verts_name, raw[0] if raw else None)
                faces_raw = name_to_val.get(self.faces_name)
                if faces_raw is None and self.faces_path and os.path.exists(self.faces_path):
                    faces_raw = np.load(self.faces_path)
                elif faces_raw is None and len(raw) > 1:
                    faces_raw = raw[1]
                feed_meta = {
                    "mode": "session.run",
                    "input_name": in_name,
                    "input_shape": list(tensor.shape),
                    "output_names": out_names,
                }
            verts = decode_verts(verts_raw)
            if faces_raw is None:
                raise ValueError("faces output missing")
            faces = decode_faces(faces_raw, one_based=self.one_based_faces)
            if faces.max() >= len(verts):
                raise ValueError("face index out of range")
        except Exception as e:
            return NeuralResult(
                ok=False,
                backend=self.name,
                skipped=False,
                reason=f"onnx_infer_failed:{e}",
                meta={"error": str(e)},
            )

        from pipeline.adapters.neural_adapter import _write_obj

        _write_obj(out_obj, verts, faces)
        val = validate_mesh_obj(out_obj)
        elapsed = round(time.time() - t0, 4)
        meta = {**val, **feed_meta, "views": present, "elapsed_sec": elapsed, "providers": list(self.providers)}
        if not val.get("ok"):
            return NeuralResult(
                ok=False, backend=self.name, skipped=False,
                reason=f"invalid_mesh:{val.get('reason')}", meta=meta,
            )
        return NeuralResult(
            ok=True, backend=self.name, mesh_path=out_obj, skipped=False,
            reason="onnx reconstruct ok", meta=meta,
        )


def make_onnx_backend(**opts: Any) -> OnnxNeuralBackend:
    return OnnxNeuralBackend(**opts)
