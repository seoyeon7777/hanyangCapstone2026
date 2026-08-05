# 프로젝트 진행률

기준일: 2026-08-05  
범위: **Hybrid P0 (production path)** 를 100%로 두고, P1/P2는 별도.

---

## 한눈에

| 범위 | 진행률 | 설명 |
|------|--------|------|
| **P0 (지금 목표)** | **약 97%** | 디스크 워커 큐 + 분류 학습 + health API |
| **전체 비전 (P0+P1+P2)** | **약 66%** | P1 edge-snap / auto 실루엣 |

---

## P0 세부 (가중 평균 ≈ 97%)

| 항목 | 가중 | 완료 | 점수 | 메모 |
|------|------|------|------|------|
| API / Ingest / Manifest | 8 | 99% | 7.9 | health/queue/status/retry |
| 이미지 이해 (seg/분류) | 8 | 96% | 7.7 | feature model + 학습 스크립트 |
| 치수 융합 → Shape Key | 10 | 95% | 9.5 | |
| 템플릿 카탈로그 | 10 | 88% | 8.8 | top/hoodie/pants+GT |
| 치수 캘리브레이션 | 12 | 95% | 11.4 | |
| 원단/신축성 → 시뮬 | 8 | 95% | 7.6 | |
| 멀티뷰 텍스처 | 12 | 85% | 10.2 | |
| Cloth 시뮬 + 핏 | 12 | 95% | 11.4 | 하의 허리핀·XY 스케일 |
| 4뷰 렌더 / GLB | 8 | 90% | 7.2 | |
| QA 게이트 | 6 | 95% | 5.7 | 자동 재시도 + 수동 retry |
| 웹 UI | 6 | 92% | 5.5 | 재시도 버튼 |
| 워커 큐 / 운영 | — | (상단 반영) | — | disk queue in-process |

합계 가중 100 → **≈ 97 / 100**

---

## 아직 남은 P0 (~3%)

1. 별도 프로세스 워커 운영 문서/헬스체크 알람 (~1pt)
2. 실데이터 라벨로 분류기 재학습 (~1pt)
3. 운영 모니터링 대시보드 (~1pt)

## P1 / P2

| Phase | 진행 | 내용 |
|-------|------|------|
| P1 실루엣 형상 보정 | ~55% | 폭+센터+edge-snap+auto |
| P2 Neural 재구성 | 0% | 미착수 |

---

## 워커 큐

- 기본: `PIPELINE_QUEUE=disk` (Flask 내장 백그라운드 워커)
- 스레드 직접 실행: `PIPELINE_QUEUE=thread`
- 별도 워커: `python -m services.worker`
- 상태: `GET /api/health`, `GET /api/pipeline/queue`

실행 중 진행률은 결과 UI와 `progress.json` / `/api/pipeline/status/<id>` 참고.
