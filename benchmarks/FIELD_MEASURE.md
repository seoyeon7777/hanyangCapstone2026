# 실측(테이프) 케이스 추가 가이드

실사진 + 줄자 실측 cm 가 있으면 아래 스키마로 `benchmarks/cases/` 에 JSON을 추가한다.

## 템플릿

`benchmarks/cases/_TEMPLATE_field_measurement.json`

필수:
- `suite`: `calibration` (Blender 재측정 루프) 또는 향후 `field_photo`
- `garment_type`
- `target_measurements`: **줄자로 잰 라벨 cm**
- `tolerance_cm`: 보통 상의 1.5 / 하의 2.0

선택:
- `image_path`: 정면 사진 (분류/텍스처 보조; 캘리브 자체는 blend 기반)
- `notes`: 측정 조건 (사이즈, 브랜드, 측정자)

## 실행

```bash
python scripts/run_accuracy_benchmark.py --case my_field_tee --blender
```

온라인 QA(매 잡 ≤1.5cm)와 별개로, 이 케이스는 **릴리즈 회귀**용이다.
