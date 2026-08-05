# 프로젝트 진행도 (큰 분류)

기준일: 2026-08-05

---

## 한눈에 — 큰 분류

| 대분류 | 진행률 | 한 줄 |
|--------|--------|------|
| **A. P0 제품 경로** | **≈ 99%** | 실사용 가능. 실사진 테이프만 남음 |
| **B. P1 실루엣 형상** | **≈ 91%** | RGB 전경추출·스커트 모드·회귀 케이스 |
| **C. P2 Neural 재구성** | **≈ 15%** | stub+synthetic 계약 / 학습 미착수 |
| **전체 비전 (A+B+C 가중)** | **≈ 81%** | 0.55·A + 0.30·B + 0.15·C |

---

## A. P0 제품 경로 (~99%)

| 중분류 | 상태 |
|--------|------|
| API / 잡 / 워커 / health / ops | 완료 |
| 이해·치수·캘리브·카탈로그 | 완료 (top/hoodie/pants/**skirt**) |
| 텍스처·시뮬·렌더·QA | 완료 |
| 정확도 벤치 | 완료 + **release_gate** / provenance 분리 |
| field 케이스 | **synthetic_template** 명시 (tee/hoodie/pants/skirt) |
| **남음** | 실제 줄자·실사진 (`provenance=field_tape`) |

## B. P1 실루엣 (~91%)

| 중분류 | 상태 |
|--------|------|
| 정면 X + edge-snap / 측면 Z | 완료 |
| bipodal / length_fit(앵커) | 완료 |
| **RGB/알파 전경 추출** | 완료 (`extract_foreground`) |
| **스커트 모드** (bipodal off, waist 보존) | 완료 |
| 벤치 `sil_skirt_aline` 등 | 완료 |
| QA 과도변형 게이트 | 완료 |
| **남음** | 실사진 마스크 회귀·프로필 RMSE 고도화 |

## C. P2 Neural (~15%)

| 중분류 | 상태 |
|--------|------|
| 설계·옵션 계약 | 완료 |
| stub / **synthetic** 백엔드 | 완료 |
| retarget passthrough ≠ 성공 | 완료 |
| QA required/fallback | 완료 |
| 학습·추론 백엔드 | **미착수** |

---

## 정확도

```bash
python scripts/run_accuracy_benchmark.py --blender
```

- 헤드라인: `release_pass_rate` (soft / synthetic field 제외 가능)
- 상세: `benchmarks/LAST_REPORT.md`

## 다음 큰 분류

1. **A** — 실사진+테이프 3벌+
2. **B** — 실사진 실루엣 RMSE
3. **C** — 외부 neural 가중치 1개
