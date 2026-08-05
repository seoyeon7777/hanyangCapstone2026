# 정확도 검증 (Accuracy Benchmark)

기준일: 2026-08-05

## 언제 검증하나?

| 시점 | 내용 | 합격 기준 |
|------|------|-----------|
| **매 파이프라인 실행** | calibrate → QA `calibration_error` | 기본 ≤ **1.5cm** (키별) |
| **오프라인 벤치마크** (이 문서) | 고정 케이스 세트 반복 측정 | 스위트별 기준 아래 |
| **단위 테스트** | plant/합성 | 로직 회귀 방지 (실측 대체 아님) |

## 실행

```bash
# 기본: Blender 있으면 캘리브+측정 포함
python scripts/run_accuracy_benchmark.py

# CI / CPU만
python scripts/run_accuracy_benchmark.py --no-blender --suite classification --suite silhouette --suite calibration

# 캘리브만
python scripts/run_accuracy_benchmark.py --suite calibration --blender
```

리포트: `outputs/_accuracy/accuracy_report.md` (+ `.json`)

## 스위트

1. **measure_consistency** — Shape Key=0 export 치수 ≈ 템플릿 base label  
2. **calibration** — 목표 cm로 반복 보정 후 오차 ≤ tolerance  
3. **classification** — 합성 실루엣 분류 정답(허용 라벨 포함)  
4. **silhouette** — Δx/Δz + **프로필 RMSE** before/after (A-line 등)  
5. **field_pipeline** — JobManifest 종단 (calibrate±silhouette±neural, sim/render off)

## 최근 리포트 (2026-08-05)

- **35/35** pass, release_gate **30/30**, field_pipeline **2/2**
- calibration mean MAE ≈ **0.22cm**
- 상세: `benchmarks/LAST_REPORT.md`

## 해석

- `passed=false` + `skip_reason=blender_unavailable` → 환경 문제 (정확도 실패 아님)
- calibration `mae_cm` / `max_abs_cm` 가 핵심 품질 지표
- QA UI의 검수 배지는 **온라인** 검증, 이 벤치는 **회귀/릴리즈** 검증
