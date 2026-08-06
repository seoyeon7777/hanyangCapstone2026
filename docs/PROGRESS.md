# 프로젝트 진행도 (큰 분류)

기준일: 2026-08-06

---

## 한눈에 — 큰 분류

| 대분류 | 진행률 | 한 줄 |
|--------|--------|------|
| **A. P0 제품 경로** | **≈ 99%** | CI · `require_qa_passed` (tee/hoodie) |
| **B. P1 실루엣 형상** | **≈ 99%** | skirt side · side quality gate |
| **C. P2 Neural 재구성** | **≈ 62%** | iterative ICP · garment synthetic · QA gates |
| **전체 비전 (A+B+C 가중)** | **≈ 93%** | 0.55·A + 0.30·B + 0.15·C |

---

## A. P0 (~99%)

| 중분류 | 상태 |
|--------|------|
| field_pipeline | tee/hoodie **QA required** · pants/skirt neural |
| CI | `.github/workflows/ci.yml` (unit + CPU strict) |
| **남김** | 실제 줄자·실사진 (`field_tape`) |

## B. P1 (~99%)

| 중분류 | 상태 |
|--------|------|
| skirt front+**side** depth | 완료 |
| **side quality gate** | `should_use_side_mask` |
| XZ fusion / leg RMSE | 완료 |
| **남김** | 실사진 마스크 |

## C. P2 (~62%)

| 중분류 | 상태 |
|--------|------|
| **iterative icp_morph** | RMS 개선 루프 |
| garment synthetic (pants/skirt/hoodie/top) | 완료 |
| neural_contract ×5 + QA quality gate | 완료 |
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
