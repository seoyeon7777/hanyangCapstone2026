# 프로젝트 진행도 (큰 분류)

기준일: 2026-08-06

---

## 한눈에 — 큰 분류

| 대분류 | 진행률 | 한 줄 |
|--------|--------|------|
| **A. P0 제품 경로** | **≈ 99%** | `--strict` release · soft-fail alerts |
| **B. P1 실루엣 형상** | **≈ 99%** | XZ fusion · pants side depth |
| **C. P2 Neural 재구성** | **≈ 48%** | `icp_morph` + neural_contract 확장 |
| **전체 비전 (A+B+C 가중)** | **≈ 91%** | 0.55·A + 0.30·B + 0.15·C |

---

## A. P0 (~99%)

| 중분류 | 상태 |
|--------|------|
| field_pipeline | tee / skirt / pants / hoodie (+ pants/skirt neural) |
| ops / health | `ops_snapshot` · soft-fail alerts · `--strict` |
| 분류기 | held-out stratified |
| **남김** | 실제 줄자·실사진 (`field_tape`) |

## B. P1 (~99%)

| 중분류 | 상태 |
|--------|------|
| XZ **fusion_iters** 잔차 반복 | 완료 |
| leg RMSE / depth RMSE / waist | 완료 |
| pants front+**side** photo-like | 완료 |
| **남김** | 실사진 마스크 |

## C. P2 (~48%)

| 중분류 | 상태 |
|--------|------|
| stub / synthetic / onnx / torch | 완료 |
| **icp_morph** (similarity + XZ morph) | 완료 |
| neural_contract (morph + ICP × garments) | 완료 |
| 학습 가중치 | **미착수** |

---

## 정확도

```bash
python scripts/run_accuracy_benchmark.py --blender --strict --publish-last
```

최근: **44/44**, release **39/39**, silhouette **9/9**, neural_contract **3/3**

## 다음 큰 분류

1. **A** — 실사진+테이프
2. **B** — 실사진 실루엣
3. **C** — 실모델 가중치
