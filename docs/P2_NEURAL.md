# P2 — Neural Garment Reconstruction

상태: **≈ 62%** — stub / synthetic(의류별) / onnx / torch / vertex_morph / **iterative icp_morph**

## 백엔드

| 이름 | 역할 |
|------|------|
| `stub` | mesh 없음 → skipped |
| `synthetic` | 의류별 closed mesh (`pants_bipodal` / `skirt_aline` / `hoodie_bulky` / `top_taper`) |
| `onnx` / `torch` | 실런타임 — 가중치 없으면 **성공 위장 금지** |

## Retarget

| method | 동작 |
|--------|------|
| `passthrough` | 템플릿 복사 · ok=false |
| `vertex_morph` | 독립 X/Z envelope |
| `icp_morph` | **반복** similarity(Y-match+scale+XZ SVD) → morph · RMS 개선만 유지 |

옵션: `neural_options.morph_strength`, `morph_depth_strength`, `icp_iters`

## QA

`neural_retarget_topology` + `neural_retarget_quality` (Δx/Δz·align RMS; soft unless `neural_required`)

## 벤치

`suite=neural_contract` — top/pants/skirt/hoodie ICP + vertex_morph

## 다음

실모델 `.onnx` / `.pt` 가중치
