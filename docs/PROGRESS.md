# 프로젝트 진행도 (큰 분류)

기준일: 2026-08-06

---

## 한눈에 — 큰 분류

| 대분류 | 진행률 | 한 줄 |
|--------|--------|------|
| **A. P0 제품 경로** | **≈ 99%** | soft tee/pants P2 multiview |
| **B. P1 실루엣 형상** | **≈ 99%** | side gate · texture↔sil |
| **C. P2 Neural 재구성** | **≈ 88%** | side fixtures · mesh QA · torch inject |
| **전체 비전 (A+B+C 가중)** | **≈ 97%** | 0.55·A + 0.30·B + 0.15·C |

---

## A. P0 (~99%)

| 중분류 | 상태 |
|--------|------|
| field_pipeline | + soft tee/pants neural (front+side, release_gate=false) |
| **남김** | 실제 줄자·실사진 (`field_tape`) |

## B. P1 (~99%)

| 중분류 | 상태 |
|--------|------|
| silhouette / texture glue | 완료 |
| **남김** | 실사진 마스크 |

## C. P2 (~88%)

| 중분류 | 상태 |
|--------|------|
| file ONNX fixture | 완료 — 학습 아님 |
| P2 defaults + correspondence | 완료 |
| **field side fixtures** + require_neural_obj | 완료 |
| neural mesh QA (degenerate/volume) | 완료 |
| torch inject contract | 완료 — 학습 가중치 아님 |
| 학습 가중치 | **미착수** |

---

## 정확도

```bash
python scripts/run_accuracy_benchmark.py --blender --strict --publish-last
```

## 다음 큰 분류

1. **A** — 실사진+테이프
2. **B** — 실사진 실루엣
3. **C** — 실모델 학습 가중치
