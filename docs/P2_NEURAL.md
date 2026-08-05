# P2 — Neural Garment Reconstruction (실험 트랙)

상태: **≈ 15%** — 계약·스텁·synthetic 백엔드 / 학습 추론 미착수

## 목표

사진(정면·측면·후면)에서 **신규 실루엣** dense mesh 를 추정한 뒤,
P0 템플릿 토폴로지로 **retarget** 하여 치수 캘리브·Cloth 시뮬과 결합한다.

## 계약

| 함수 | 입력 | 출력 |
|------|------|------|
| `reconstruct` | images{}, garment_type | mesh_path / meta |
| `retarget_to_template` | neural mesh + template OBJ | 템플릿 토폴로지 OBJ |

코드: `pipeline/adapters/neural_adapter.py`  
스테이지: `pipeline/stages/neural_reconstruct.py`

### 옵션 (`PipelineOptions`)

| 키 | 기본 | 설명 |
|----|------|------|
| `phase=P2` / `neural_enabled` | off | 스테이지 활성 |
| `neural_backend` | `stub` | `stub` \| `synthetic` |
| `neural_required` | false | true면 실패 시 needs_review |
| `neural_fallback_to_template` | true | 실패 시 템플릿 유지 |
| `neural_min_views` | 1 | 최소 뷰 수 |
| `neural_timeout_sec` | 120 | 백엔드 타임아웃(예약) |
| `neural_retarget_method` | passthrough | retarget 방식 |
| `neural_options` | {} | 백엔드 전용 dict |

### 백엔드

- **stub**: mesh 없음 → `skipped` (성공 retarget 아님)
- **synthetic**: 계약/테스트용 단순 OBJ 생성 (GPU 불필요)

`retarget` 에서 neural mesh 가 없으면 `ok=false, passthrough=true` — 템플릿 복사를 “neural 성공”으로 치지 않음.

## 파이프라인 위치

```
… → calibrate → [neural_reconstruct] → silhouette_deform → geometry_fit → qa
```

## 다음 구현 후보

1. 외부 모델 가중치 로드
2. 멀티뷰 fusion → watertight mesh
3. Non-rigid ICP retarget
4. 치수 제약(loss)으로 cm 안정화
