# 프로젝트 진행도 (큰 분류)

기준일: 2026-08-06

---

## 한눈에 — 큰 분류

| 대분류 | 진행률 | 한 줄 |
|--------|--------|------|
| **A. P0 제품 경로** | **≈ 99%** | holdout ops · rebuild skirt/hoodie · hoodie neural |
| **B. P1 실루엣 형상** | **≈ 99%** | texture crop↔silhouette glue |
| **C. P2 Neural 재구성** | **≈ 72%** | ONNX tensor contract · min_views=2 · residual/smooth |
| **전체 비전 (A+B+C 가중)** | **≈ 95%** | 0.55·A + 0.30·B + 0.15·C |

---

## A. P0 (~99%)

| 중분류 | 상태 |
|--------|------|
| field_pipeline | tee/pants/skirt/hoodie(+neural) |
| classifier holdout | ops alert + meta `val_acc` |
| rebuild scripts | skirt / hoodie / pants |
| **남김** | 실제 줄자·실사진 (`field_tape`) |

## B. P1 (~99%)

| 중분류 | 상태 |
|--------|------|
| silhouette + side gate / fusion | 완료 |
| texture tight crop when sil applied | 완료 |
| **남김** | 실사진 마스크 |

## C. P2 (~72%)

| 중분류 | 상태 |
|--------|------|
| ONNX **tensor contract** (injected session.run) | 완료 — 학습 가중치 아님 |
| min_views≥2 + fail case | 완료 |
| residual morph + laplacian smooth | 완료 |
| neural_contract 확장 | 완료 |
| 학습 가중치 | **미착수** |

---

## 정확도

```bash
python scripts/run_accuracy_benchmark.py --blender --strict --publish-last
```

## 다음 큰 분류

1. **A** — 실사진+테이프
2. **B** — 실사진 실루엣
3. **C** — 실모델 가중치
