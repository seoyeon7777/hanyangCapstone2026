# 프로젝트 진행률

기준일: 2026-08-05  
범위: **Hybrid P0 (production path)** 를 100%로 두고, P1/P2는 별도.

---

## 한눈에

| 범위 | 진행률 | 설명 |
|------|--------|------|
| **P0 (지금 목표)** | **약 98%** | 워커 reclaim·health·SSE 브리지·UI/QA 완비 |
| **전체 비전 (P0+P1+P2)** | **약 70%** | P1 측면 깊이(Z)+auto+UI |

---

## P0 세부 (가중 평균 ≈ 98%)

| 항목 | 가중 | 완료 | 점수 | 메모 |
|------|------|------|------|------|
| API / Ingest / Manifest | 8 | 99% | 7.9 | health/queue/reclaim/retry |
| 이미지 이해 (seg/분류) | 8 | 96% | 7.7 | multi-PSM OCR + feature model |
| 치수 융합 → Shape Key | 10 | 97% | 9.7 | 소스 라벨 분리 |
| 템플릿 카탈로그 | 10 | 88% | 8.8 | |
| 치수 캘리브레이션 | 12 | 95% | 11.4 | |
| 원단/신축성 → 시뮬 | 8 | 96% | 7.7 | UI stretch |
| 멀티뷰 텍스처 | 12 | 88% | 10.6 | detail overlay |
| Cloth 시뮬 + 핏 | 12 | 96% | 11.5 | silhouette-preserving smooth |
| 4뷰 렌더 / GLB | 8 | 90% | 7.2 | |
| QA 게이트 | 6 | 98% | 5.9 | mesh integrity + GLB soft |
| 웹 UI | 6 | 96% | 5.8 | P1옵션·다운로드·QA카드 |
| 워커/운영 | — | (상단) | — | reclaim + webhook alert |
| 정확도 벤치 | — | (신규) | — | `docs/ACCURACY.md` |

합계 가중 100 → **≈ 98 / 100**

---

## 정확도 검증

- 온라인: 매 잡 calibrate + QA (≤1.5cm)
- 오프라인: `python scripts/run_accuracy_benchmark.py` → `outputs/_accuracy/`
- 상세: [`docs/ACCURACY.md`](ACCURACY.md)

---

## 아직 남은 P0 (~2%)

1. 실사진 라벨로 분류기 재학습 (~1pt)
2. 모니터링 대시보드 UI (~1pt)

## P1 / P2

| Phase | 진행 | 내용 |
|-------|------|------|
| P1 실루엣 형상 보정 | ~70% | X+Z depth + edge-snap + auto + UI |
| P2 Neural 재구성 | 0% | 미착수 |

---

## 워커 / 운영

- `PIPELINE_QUEUE=disk|thread`
- `PIPELINE_STALE_RUNNING_SEC=900`
- `PIPELINE_ALERT_WEBHOOK=...` (선택)
- `GET /api/health` — blender/stale 시 503
- `POST /api/pipeline/reclaim` — stuck running 복구
- 디스크 큐도 SSE: `progress.json` 브리지

실행 중 진행률은 결과 UI와 `progress.json` / `/api/pipeline/status/<id>` 참고.
