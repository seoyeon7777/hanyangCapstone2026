# P2 — Neural Garment Reconstruction

상태: **≈ 88%** — synthetic / file ONNX / torch inject / mesh QA / multiview field soft

## 백엔드

| 이름 | 역할 |
|------|------|
| `stub` | skipped |
| `synthetic` | 의류별 closed mesh |
| `onnx` | InferenceSession — fixture=`assets/neural/synthetic_contract.onnx` (**NOT trained**) |
| `torch` | inject contract / skip without weights (**NOT trained**) |

빌드: `python scripts/build_synthetic_onnx_fixture.py` (build-time `onnx` pkg)

## Retarget / Defaults / QA

- P2: default `neural_retarget_method=icp_morph`, `neural_min_views=2`
- ICP + residual + smooth + **partial_match_ratio**
- depth morph는 side 이미지 없으면 soft-skip
- field soft: front+side fixtures → `require_neural_obj`
- mesh QA: degenerate faces / volume_proxy / boundary

## 다음

실모델 학습 가중치 (fixture ≠ trained)
