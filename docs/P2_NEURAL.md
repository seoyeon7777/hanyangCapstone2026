# P2 — Neural Garment Reconstruction

상태: **≈ 93%** (엔지니어링) — synthetic / file ONNX / torch inject / mesh QA / multiview / GLB meta

## 백엔드

| 이름 | 역할 |
|------|------|
| `stub` | skipped |
| `synthetic` | 의류별 closed mesh (jacket→`jacket_bulky`) |
| `onnx` | InferenceSession — `assets/neural/synthetic_contract.onnx` (**NOT trained**) |
| `torch` | inject contract / skip without weights (**NOT trained**) |

## Retarget / QA / Export

- P2 defaults: `icp_morph`, `min_views=2`
- correspondence `partial_match_ratio` + mesh QA (degenerate/volume)
- depth morph: side 없으면 soft-skip
- soft field: tee/pants/skirt/hoodie/jacket front+side → `require_neural_obj`
- texture 단계 후 `cloth_neural_export.json`에 GLB 경로 기입 (`cloth_neural_glb`)

## 외부 블로커

실모델 학습 가중치 (fixture/inject ≠ trained reconstruction model)
