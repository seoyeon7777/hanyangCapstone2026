"""Neural backend package."""

from pipeline.adapters.neural_backends.onnx_backend import OnnxNeuralBackend, make_onnx_backend

__all__ = ["OnnxNeuralBackend", "make_onnx_backend"]
