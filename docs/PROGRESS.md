# 프로젝트 진행도 (큰 분류)

기준일: 2026-08-05

---

## 한눈에 — 큰 분류

| 대분류 | 진행률 | 한 줄 |
|--------|--------|------|
| **A. P0 제품 경로** | **≈ 99%** | 종단 `field_pipeline` 합성 검증까지 |
| **B. P1 실루엣 형상** | **≈ 93%** | 프로필 RMSE before/after 게이트 |
| **C. P2 Neural 재구성** | **≈ 22%** | synthetic + **vertex_morph** retarget |
| **전체 비전 (A+B+C 가중)** | **≈ 83%** | 0.55·A + 0.30·B + 0.15·C |

---

## A. P0 제품 경로 (~99%)

| 중분류 | 상태 |
|--------|------|
| API / 잡 / 워커 / ops / 카탈로그 | 완료 |
| 정확도 벤치 + release_gate | 완료 |
| **field_pipeline** 종단 스위트 | 완료 (tee/skirt 합성) |
| blender `output_dir` 벤치 루트 | 완료 |
| **남김** | 실제 줄자·실사진 (`provenance=field_tape`) |

## B. P1 실루엣 (~93%)

| 중분류 | 상태 |
|--------|------|
| X/Z/Y · bipodal · 스커트 모드 · RGB 전경 | 완료 |
| **프로필 RMSE** before/after | 완료 |
| `sil_skirt_aline` 정량 게이트 | 완료 |
| **남김** | 실사진 마스크 RMSE |

## C. P2 Neural (~22%)

| 중분류 | 상태 |
|--------|------|
| stub / synthetic closed mesh | 완료 |
| **vertex_morph** retarget + topology QA | 완료 |
| passthrough ≠ 성공 | 완료 |
| 학습·추론 가중치 | **미착수** |

---

## 정확도

```bash
python scripts/run_accuracy_benchmark.py --blender
```

최근: **35/35**, release **30/30**, field_pipeline **2/2**

## 다음 큰 분류

1. **A** — 실사진+테이프
2. **B** — 실사진 실루엣 RMSE
3. **C** — 외부 neural 가중치
