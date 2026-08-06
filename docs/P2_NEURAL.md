# P2 — Neural Garment Reconstruction

상태: **≈ 72%** — synthetic / onnx·torch **계약** / iterative icp_morph / residual+smooth

## 백엔드

| 이름 | 역할 |
|------|------|
| `stub` | skipped |
| `synthetic` | 의류별 closed mesh |
| `onnx` / `torch` | 실런타임 — 가중치 없으면 skip. 벤치의 inject session은 **synthetic_contract** |

## Retarget

| method | 동작 |
|--------|------|
| `passthrough` | ok=false |
| `vertex_morph` | X/Z envelope |
| `icp_morph` | 반복 ICP-lite → morph → **residual pass** → **laplacian smooth** |

옵션: `morph_strength`, `morph_depth_strength`, `icp_iters`, `smooth_iters`, `residual_pass`, `residual_threshold`

## 벤치

- ONNX tensor contract (`inject_contract_session`)
- `min_views=2` pass/fail
- residual+smooth hoodie case

## 다음

실모델 `.onnx` / `.pt` 학습 가중치 (계약 ≠ 학습 성공)
