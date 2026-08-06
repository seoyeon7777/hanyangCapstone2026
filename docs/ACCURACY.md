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

1. **measure_consistency** — SK=0 ≈ base label  
2. **calibration** — 목표 cm 보정  
3. **classification** — 합성 분류  
4. **silhouette** — Δx/Δz + RMSE + waist + leg + **XZ fusion**  
5. **field_pipeline** — 종단 (tee/skirt/pants/hoodie)  
6. **neural_contract** — P2 morph + **icp_morph** (CPU)

## 최근 리포트 (2026-08-06)

- **47/47** pass, release **42/42**
- field_pipeline **4/4**, silhouette **10/10**, neural_contract **5/5**
- CI: `.github/workflows/ci.yml` (unit + CPU strict)
- 상세: `benchmarks/LAST_REPORT.md`
## 해석

- `passed=false` + `skip_reason=blender_unavailable` → 환경 문제 (정확도 실패 아님)
- calibration `mae_cm` / `max_abs_cm` 가 핵심 품질 지표
- QA UI의 검수 배지는 **온라인** 검증, 이 벤치는 **회귀/릴리즈** 검증
