# P2 — Neural Garment Reconstruction

상태: **≈ 35%** — stub / synthetic / onnx(session.run) / torch / XZ morph

## 백엔드

| 이름 | 역할 |
|------|------|
| `stub` | mesh 없음 → skipped |
| `synthetic` | 결정적 closed mesh (테스트) |
| `onnx` | `InferenceSession.run` + `run_garment` 주입 — 모델 없으면 **성공 위장 금지** |
| `torch` | TorchScript / 주입 모듈 — 없으면 skip |

전처리: `pipeline/adapters/neural_preprocess.py` (멀티뷰 텐서 · verts/faces decode)

코드: `pipeline/adapters/neural_adapter.py`, `neural_backends/{onnx,torch}_backend.py`, `neural_backend.py`

## Retarget

| method | 동작 |
|--------|------|
| `passthrough` | 템플릿 복사 · ok=false |
| `vertex_morph` | **독립 X/Z** envelope 스케일 · faces 유지 |

옵션: `neural_options.morph_strength`, `morph_depth_strength`

## 벤치

`suite=neural_contract` — CPU only topology + Δx/Δz

## 다음

실모델 `.onnx` / `.pt` 가중치 + ICP 정렬
