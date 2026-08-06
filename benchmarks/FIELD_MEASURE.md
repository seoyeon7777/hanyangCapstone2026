# 실측(테이프) 케이스 추가 가이드

실사진 + 줄자 실측 cm 가 있으면 아래 스키마로 `benchmarks/cases/` 에 JSON을 추가한다.

**스캐폴드 완료** — `provenance=field_tape` 케이스는 아직 0건 (ops 알림 `field_tape_missing`).

## 템플릿

`benchmarks/cases/_TEMPLATE_field_measurement.json`

필수:
- `suite`: `calibration`
- `garment_type`
- `target_measurements`: **줄자로 잰 라벨 cm**
- `tolerance_cm`: 보통 상의 1.5 / 하의 2.0
- `provenance`: `field_tape`
- `tape_meta`: measured_at / measurer / views / notes

선택:
- `image_path` 또는 `images.front|side`
- `release_gate`: 실측 검증 후 `true` 검토

## 검증

```bash
python scripts/validate_bench_cases.py
python scripts/run_accuracy_benchmark.py --case my_field_tee --blender
```

## 자리표시자

`field_*_tape.json` 은 **provenance=`synthetic_template`**, `release_gate=false`.  
줄자 실측으로 값을 바꾸고 provenance를 `field_tape` 로 올리면 된다.
