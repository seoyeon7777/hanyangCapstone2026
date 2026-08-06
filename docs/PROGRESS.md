# 프로젝트 진행도 (큰 분류)

기준일: 2026-08-06 — **엔지니어링 마감**

---

## 한눈에 — 큰 분류

| 대분류 | 진행률 | 한 줄 |
|--------|--------|------|
| **A. P0 제품 경로** | **100%** | 종단 파이프라인 · jacket nearest · field_tape 스캐폴드 |
| **B. P1 실루엣 형상** | **100%** | side gate · texture↔sil · photo-like fixtures |
| **C. P2 Neural 재구성** | **≈ 93%** | multiview soft · mesh QA · ONNX/torch contract · GLB 연동 |
| **전체 비전 (A+B+C 가중)** | **≈ 99%** | 0.55·A + 0.30·B + 0.15·C |

---

## A. P0 (엔지니어링 100%)

| 중분류 | 상태 |
|--------|------|
| field_pipeline | tee/pants/skirt/hoodie + soft P2 multiview + jacket soft |
| jacket 템플릿 | `done_nearest` (hoodie clone — 카라/여밈 외부) |
| field_tape 스캐폴드 | 스키마·validator·tape_meta — **실측 데이터만 외부** |

## B. P1 (엔지니어링 100%)

| 중분류 | 상태 |
|--------|------|
| silhouette / texture glue | 완료 |
| **외부** | 실사진 마스크 데이터 |

## C. P2 (≈93%)

| 중분류 | 상태 |
|--------|------|
| synthetic / file ONNX / torch inject | 완료 — **학습 아님** |
| P2 defaults · correspondence · mesh QA | 완료 |
| multiview soft field (4종 + jacket) | 완료 |
| neural OBJ → texture GLB meta 연동 | 완료 |
| **외부 블로커** | 실모델 학습 가중치 |

---

## 정확도

```bash
python scripts/validate_bench_cases.py
python scripts/run_accuracy_benchmark.py --blender --strict --publish-last
```

## 외부 블로커 (코드로 완료 불가)

1. 실사진 + 줄자 cm → `provenance=field_tape`
2. 실사진 실루엣 마스크
3. 학습된 neural 가중치 (fixture ≠ trained)
4. 자켓 카라/여밈 아티스트 blend
