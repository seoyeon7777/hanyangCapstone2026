"""ONNX Runtime neural backend (optional).

모델이 없으면 available()=False — 성공으로 위장하지 않음.
계약: 세션 입출력 이름은 neural_options 로 설정.
"""

from __future__ import annotations

import os
from typing import Any, Optional

from pipeline.adapters.neural_backend import NeuralRequest, NeuralResult, validate_mesh_obj


class OnnxNeuralBackend:
    name = "onnx"

    def __init__(self, model_path: Optional[str] = None, **opts: Any):
        self.model_path = model_path or opts.get("model_path") or os.environ.get("NEURAL_ONNX_MODEL")
        self.providers = opts.get("providers") or ["CPUExecutionProvider"]
        self.input_name = opts.get("input_name") or "images"
        self.verts_name = opts.get("verts_name") or "vertices"
        self.faces_name = opts.get("faces_name") or "faces"
        self._session = opts.get("_session")  # 테스트용 주입

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
            return NeuralResult(
                ok=False,
                backend=self.name,
                skipped=True,
                reason=reason,
            )

        out_dir = req.output_dir
        os.makedirs(out_dir, exist_ok=True)
        out_obj = os.path.join(out_dir, "onnx_neural.obj")

        # 테스트/주입 세션: verts/faces 반환 규약
        session = self._session
        if session is None:
            import onnxruntime as ort

            session = ort.InferenceSession(self.model_path, providers=list(self.providers))

        # 실제 추론은 모델 계약에 의존 — 여기서는 인터페이스만 고정
        if hasattr(session, "run_garment"):
            verts, faces = session.run_garment(req.images, req.garment_type)
        else:
            return NeuralResult(
                ok=False,
                backend=self.name,
                skipped=True,
                reason="onnx_session_unsupported_contract (need run_garment or mapped outputs)",
            )

        from pipeline.adapters.neural_adapter import _write_obj
        import numpy as np

        _write_obj(out_obj, np.asarray(verts, dtype=np.float64), np.asarray(faces, dtype=np.int32))
        val = validate_mesh_obj(out_obj)
        if not val.get("ok"):
            return NeuralResult(
                ok=False,
                backend=self.name,
                skipped=False,
                reason=f"invalid_mesh:{val.get('reason')}",
                meta=val,
            )
        return NeuralResult(
            ok=True,
            backend=self.name,
            mesh_path=out_obj,
            skipped=False,
            reason="onnx reconstruct ok",
            meta=val,
        )


def make_onnx_backend(**opts: Any) -> OnnxNeuralBackend:
    return OnnxNeuralBackend(**opts)
