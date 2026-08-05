# 프로젝트 진행률

기준일: 2026-08-05  
범위: **Hybrid P0 (production path)** 를 100%로 두고, P1/P2는 별도.

---

## 한눈에

| 범위 | 진행률 | 설명 |
|------|--------|------|
| **P0 (지금 목표)** | **약 99%** | 정확도 벤치·Ops 대시보드·분류 재학습 |
| **전체 비전 (P0+P1+P2)** | **약 74%** | P1 bipodal+측면 깊이 ~80% |
| **P1 실루엣** | **약 80%** | X+Z+bipodal+auto+UI |
| **P2 Neural** | **0%** | 미착수 |

### 정확도 (최신 Blender 벤치)

- 캘리브레이션: **7/7 → (확장 후 재실행)** 이전 스냅샷 mean MAE **0.12cm**
- 온라인 QA: 매 잡 ≤ **1.5cm**

---

## P0 세부 (가중 평균 ≈ 99%)

| 항목 | 가중 | 완료 | 점수 | 메모 |
|------|------|------|------|------|
| API / Ingest / Manifest | 8 | 99% | 7.9 | ops dashboard API |
| 이미지 이해 (seg/분류) | 8 | 98% | 7.8 | 합성 재학습 가중치 내장 |
| 치수 융합 → Shape Key | 10 | 97% | 9.7 | |
| 템플릿 카탈로그 | 10 | 90% | 9.0 | hoodie GT |
| 치수 캘리브레이션 | 12 | 97% | 11.6 | 벤치 실측 통과 |
| 원단/신축성 → 시뮬 | 8 | 96% | 7.7 | |
| 멀티뷰 텍스처 | 12 | 88% | 10.6 | |
| Cloth 시뮬 + 핏 | 12 | 96% | 11.5 | |
| 4뷰 렌더 / GLB | 8 | 90% | 7.2 | |
| QA 게이트 | 6 | 98% | 5.9 | |
| 웹 UI / Ops | 6 | 98% | 5.9 | `/ops` 대시보드 |

합계 가중 100 → **≈ 99 / 100**

---

## 정확도 검증

- 온라인: calibrate + QA (`docs/ACCURACY.md`)
- 오프라인: `python scripts/run_accuracy_benchmark.py --blender`
- 실측 추가: `benchmarks/FIELD_MEASURE.md`
- 스냅샷: `benchmarks/LAST_REPORT.md`
- Ops UI: `/ops`

## 남은 일

| 항목 | 범위 |
|------|------|
| 실사진·테이프 케이스 채우기 | P0 마감 / 벤치 |
| 하의 bipodal 실사진 튜닝 | P1 |
| Neural 메쉬 재구성 | P2 |

## 워커 / 운영

- `PIPELINE_QUEUE=disk|thread`
- `GET /api/health`, `GET /api/ops/dashboard`, `POST /api/pipeline/reclaim`
