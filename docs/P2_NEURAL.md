# P2 — Neural Garment Reconstruction (실험 트랙)

상태: **≈ 22%** — stub + synthetic + vertex_morph / 학습 추론 미착수

## 목표

사진 → dense mesh 추정 → 템플릿 토폴로지 retarget → 캘리브·시뮬 결합.

## 계약

| 함수 | 입력 | 출력 |
|------|------|------|
| `reconstruct` | images{}, garment_type | mesh_path / meta |
| `retarget_to_template` | neural + template OBJ | 템플릿 토폴로지 OBJ |

### 옵션

| 키 | 기본 | 설명 |
|----|------|------|
| `neural_backend` | stub | `stub` \| `synthetic` |
| `neural_retarget_method` | passthrough | `passthrough` \| **`vertex_morph`** |
| `neural_options.morph_strength` | 0.35 | envelope 모프 강도 |
| `neural_required` / `fallback_to_template` | false / true | 실패 정책 |

### Retarget

- **passthrough**: 템플릿 복사 — `ok=false`, `skipped` (neural 성공으로 치지 않음)
- **vertex_morph**: neural Y-밴드 X/Z envelope → 템플릿 정점 스케일, **faces 유지**
- topology QA: vert/face count + face index 일치 (`models/mesh_qa.inspect_obj`)

### 백엔드

- **stub**: mesh 없음
- **synthetic**: 결정적 closed mesh (A-line flare 가능)

## 파이프라인

```
… → calibrate → [neural_reconstruct] → silhouette_deform → geometry_fit → qa
```

## 다음

1. 외부 가중치 로드
2. Non-rigid ICP
3. 치수 제약 loss
