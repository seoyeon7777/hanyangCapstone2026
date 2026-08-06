# P2 — Neural Garment Reconstruction

상태: **≈ 28%** — stub / synthetic / onnx(골격) / XZ morph

## 백엔드

| 이름 | 역할 |
|------|------|
| `stub` | mesh 없음 → skipped |
| `synthetic` | 결정적 closed mesh (테스트) |
| `onnx` | ONNX Runtime 계약 — 모델 없으면 **성공 위장 금지** |

코드: `pipeline/adapters/neural_adapter.py`, `neural_backends/onnx_backend.py`, `neural_backend.py`

## Retarget

| method | 동작 |
|--------|------|
| `passthrough` | 템플릿 복사 · ok=false |
| `vertex_morph` | **독립 X/Z** envelope 스케일 · faces 유지 |

옵션: `neural_options.morph_strength`, `morph_depth_strength`

## 벤치

`suite=neural_contract` — CPU only topology + Δx/Δz

## 다음

실모델 `.onnx` 경로 + 입출력 텐서 매핑 / ICP
