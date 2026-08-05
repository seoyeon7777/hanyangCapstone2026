# Accuracy Benchmark Report

- generated: `2026-08-05T15:00:57`
- blender: `True`
- cases: **15/17** passed (rate=0.882)

## Suites

- calibration: {'n': 7, 'pass_rate': 1.0, 'mean_mae_cm': 0.117, 'worst_mae_cm': 0.365}
- measure_consistency: {'n': 3, 'pass_rate': 1.0}
- classification: {'n': 5, 'pass_rate': 0.6, 'accuracy': 0.6}
- silhouette: {'n': 2, 'pass_rate': 1.0}

## Cases

| id | suite | passed | mae_cm | max_abs_cm | notes |
|----|-------|--------|--------|------------|-------|
| clf_hoodie | classification | False | None | None |  |
| clf_pants | classification | True | None | None |  |
| clf_shorts | classification | True | None | None |  |
| clf_skirt | classification | False | None | None |  |
| clf_tshirt | classification | True | None | None |  |
| hoodie_basis_measure | measure_consistency | True | 0.0 | 0.0 | blender |
| hoodie_calib_base | calibration | True | 0.0 | 0.0 | blender |
| pants_basis_measure | measure_consistency | True | 0.0 | 0.0 | blender |
| pants_calib_base | calibration | True | 0.0 | 0.0 | blender |
| pants_calib_wide | calibration | True | 0.17 | 0.43 | blender |
| plant_calib_ok | calibration | True | 0.0 | 0.0 | blender |
| sil_front_only | silhouette | True | None | None |  |
| sil_front_side | silhouette | True | None | None |  |
| top_basis_measure | measure_consistency | True | 0.0 | 0.0 | blender |
| top_calib_base | calibration | True | 0.0 | 0.0 | blender |
| top_calib_large_chest | calibration | True | 0.365 | 0.77 | blender |
| top_calib_small | calibration | True | 0.283 | 0.56 | blender |
