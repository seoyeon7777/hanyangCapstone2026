#!/usr/bin/env python3
"""Build a tiny deterministic ONNX fixture (NOT a trained model).

Graph: images (float) → ReduceSum→Mul(0)→Add(const verts/faces)
Runtime needs only onnxruntime. Build needs `onnx` package.

Provenance: synthetic_fixture / deterministic_constant_graph
"""

from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

OUT_DIR = os.path.join(ROOT, "assets", "neural")
OUT_ONNX = os.path.join(OUT_DIR, "synthetic_contract.onnx")
OUT_META = os.path.join(OUT_DIR, "synthetic_contract_meta.json")


def main():
    try:
        import numpy as np
        import onnx
        from onnx import helper, TensorProto, numpy_helper
    except ImportError as e:
        raise SystemExit(f"build requires onnx+numpy: {e}")

    # small closed tetrahedron-ish mesh
    verts = np.array(
        [
            [-0.4, 0.0, -0.15],
            [0.4, 0.0, -0.15],
            [0.0, 0.0, 0.2],
            [-0.35, 0.5, -0.12],
            [0.35, 0.5, -0.12],
            [0.0, 0.5, 0.18],
            [-0.3, 1.0, -0.1],
            [0.3, 1.0, -0.1],
            [0.0, 1.0, 0.15],
        ],
        dtype=np.float32,
    )
    faces = np.array(
        [
            [0, 1, 2],
            [3, 4, 5],
            [6, 7, 8],
            [0, 1, 4],
            [0, 4, 3],
            [1, 2, 5],
            [1, 5, 4],
            [2, 0, 3],
            [2, 3, 5],
            [3, 4, 7],
            [3, 7, 6],
            [4, 5, 8],
            [4, 8, 7],
            [5, 3, 6],
            [5, 6, 8],
        ],
        dtype=np.int64,
    )

    # Input: images NCHW float — consumed but ignored (×0)
    images = helper.make_tensor_value_info("images", TensorProto.FLOAT, [1, 6, 64, 64])
    # outputs
    out_v = helper.make_tensor_value_info("vertices", TensorProto.FLOAT, list(verts.shape))
    out_f = helper.make_tensor_value_info("faces", TensorProto.INT64, list(faces.shape))

    verts_init = numpy_helper.from_array(verts, name="const_verts")
    faces_init = numpy_helper.from_array(faces, name="const_faces")
    zero_init = numpy_helper.from_array(np.array(0.0, dtype=np.float32), name="zero")

    # sum images → scalar, *0 → 0, broadcast-add to verts (identity)
    nodes = [
        helper.make_node("ReduceSum", ["images"], ["img_sum"], keepdims=0),
        helper.make_node("Mul", ["img_sum", "zero"], ["img_zero"]),
        helper.make_node("Add", ["const_verts", "img_zero"], ["vertices"]),
        # faces: Identity of const
        helper.make_node("Identity", ["const_faces"], ["faces"]),
    ]

    graph = helper.make_graph(
        nodes,
        "synthetic_contract_garment",
        [images],
        [out_v, out_f],
        [verts_init, faces_init, zero_init],
    )
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)])
    model.ir_version = 8
    onnx.checker.check_model(model)
    os.makedirs(OUT_DIR, exist_ok=True)
    onnx.save(model, OUT_ONNX)

    meta = {
        "path": "assets/neural/synthetic_contract.onnx",
        "provenance": "synthetic_fixture",
        "kind": "deterministic_constant_graph",
        "trained": False,
        "n_verts": int(verts.shape[0]),
        "n_faces": int(faces.shape[0]),
        "input": "images [1,6,64,64] float (front+side RGB stacked)",
        "outputs": ["vertices", "faces"],
        "notes": "NOT a trained garment model — contract fixture for InferenceSession only",
    }
    with open(OUT_META, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print("wrote", OUT_ONNX)
    print("wrote", OUT_META)

    # smoke with ort
    import onnxruntime as ort

    sess = ort.InferenceSession(OUT_ONNX, providers=["CPUExecutionProvider"])
    dummy = np.zeros((1, 6, 64, 64), dtype=np.float32)
    v_out, f_out = sess.run(None, {"images": dummy})
    assert v_out.shape == verts.shape
    assert f_out.shape == faces.shape
    print("ort smoke ok", v_out.shape, f_out.shape)


if __name__ == "__main__":
    main()
