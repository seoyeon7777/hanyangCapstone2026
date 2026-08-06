# 프로젝트 진행도 (큰 분류)

기준일: 2026-08-06

---

## 한눈에 — 큰 분류

| 대분류 | 진행률 | 한 줄 |
|--------|--------|------|
| **A. P0 제품 경로** | **≈ 99%** | field_pipeline 4종 + ops/health 단일 스냅샷 |
| **B. P1 실루엣 형상** | **≈ 97%** | leg RMSE · bipodal crossover 게이트 |
| **C. P2 Neural 재구성** | **≈ 35%** | ONNX session.run + Torch 백엔드 |
| **전체 비전 (A+B+C 가중)** | **≈ 89%** | 0.55·A + 0.30·B + 0.15·C |

---

## A. P0 (~99%)

| 중분류 | 상태 |
|--------|------|
| field_pipeline | tee / skirt / **pants** / **hoodie** |
| ops / health | **단일 `ops_snapshot`** · alerts · suite 요약 |
| 분류기 | **held-out stratified** val macro-F1 |
| QA retry 정책 | 순수 함수 + 로그 아티팩트 |
| **남김** | 실제 줄자·실사진 (`field_tape`) |

## B. P1 (~97%)

| 중분류 | 상태 |
|--------|------|
| 프로필 RMSE / **depth RMSE** / **waist drift** | 완료 |
| **leg-local RMSE** / crossover | 완료 (`bipodal_leg_rmse`) |
| photo-like 합성 픽스처 | 완료 |
| RGB 테두리 전경 추출 | 완료 |
| **남김** | 실사진 마스크 |

## C. P2 (~35%)

| 중분류 | 상태 |
|--------|------|
| stub / synthetic / **onnx** / **torch** | 실런타임 계약 (가중치 없으면 skip) |
| ONNX `session.run` + 주입 | 완료 |
| **독립 X/Z vertex_morph** | 완료 |
| neural_contract 벤치 | 완료 |
| 학습 가중치 | **미착수** |

---

## 정확도

```bash
python scripts/run_accuracy_benchmark.py --blender
```

최근: **41/41**, release **36/36**, field_pipeline **4/4**, silhouette **8/8** (leg RMSE 포함), neural_contract **1/1**

## 다음 큰 분류

1. **A** — 실사진+테이프
2. **B** — 실사진 실루엣
3. **C** — ONNX/토치 실모델 가중치
