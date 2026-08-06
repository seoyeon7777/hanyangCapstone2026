# P2 — Neural Garment Reconstruction

상태: **≈ 48%** — stub / synthetic / onnx / torch / vertex_morph / **icp_morph**

## 백엔드

| 이름 | 역할 |
|------|------|
| `stub` | mesh 없음 → skipped |
| `synthetic` | 결정적 closed mesh (테스트) |
| `onnx` | `InferenceSession.run` + `run_garment` 주입 — 모델 없으면 **성공 위장 금지** |
| `torch` | TorchScript / 주입 모듈 — 없으면 skip |

전처리: `pipeline/adapters/neural_preprocess.py`

## Retarget

| method | 동작 |
|--------|------|
| `passthrough` | 템플릿 복사 · ok=false |
| `vertex_morph` | 독립 X/Z envelope 스케일 · faces 유지 |
| `icp_morph` | centroid+scale(+XZ SVD) 정렬 후 vertex_morph |

옵션: `neural_options.morph_strength`, `morph_depth_strength`

## 벤치

`suite=neural_contract` — topology + Δx/Δz + align centroid_err

## 다음

실모델 `.onnx` / `.pt` 가중치
