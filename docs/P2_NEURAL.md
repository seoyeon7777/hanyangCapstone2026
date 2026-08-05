# P2 — Neural Garment Reconstruction (실험 트랙)

상태: **스텁 / 0% 구현** (인터페이스만)

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
플래그: `options.phase="P2"` 또는 `options.neural_enabled=true`  
백엔드: `options.neural_backend="stub"` (현재 유일)

## 파이프라인 위치

```
… → calibrate → [neural_reconstruct] → silhouette_deform → geometry_fit → qa
```

stub 은 neural mesh 를 만들지 않고 **경고 후 템플릿 경로 유지**.

## 다음 구현 후보 (미착수)

1. 외부 모델 가중치 로드 (예: SMPL/Garment 계열 또는 자체 경량 네트워크)
2. 멀티뷰 fusion → watertight mesh
3. Non-rigid ICP / correspondence 로 템플릿 retarget
4. 치수 제약(loss)으로 cm 안정화

GPU/학습 인프라 없으면 stub 유지가 정상이다.
