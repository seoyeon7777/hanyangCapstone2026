# Accuracy Benchmark Report

- generated: `2026-08-05T15:43:53`
- blender: `True`
- cases: **27/27** passed (rate=1.0)

## Suites

- calibration: {'n': 13, 'pass_rate': 1.0, 'mean_mae_cm': 0.203, 'worst_mae_cm': 1.408}
- measure_consistency: {'n': 4, 'pass_rate': 1.0}
- classification: {'n': 7, 'pass_rate': 1.0, 'accuracy': 1.0}
- silhouette: {'n': 3, 'pass_rate': 1.0}

## Cases

| id | suite | passed | mae_cm | max_abs_cm | notes |
|----|-------|--------|--------|------------|-------|
| clf_dress | classification | True | None | None |  |
| clf_hoodie | classification | True | None | None |  |
| clf_jacket | classification | True | None | None |  |
| clf_pants | classification | True | None | None |  |
| clf_shorts | classification | True | None | None |  |
| clf_skirt | classification | True | None | None |  |
| clf_tshirt | classification | True | None | None |  |
| field_hoodie_tape | calibration | True | 0.0 | 0.0 | blender |
| field_pants_tape | calibration | True | 0.0 | 0.0 | blender |
| field_tee_tape | calibration | True | 0.0 | 0.0 | blender |
| hoodie_basis_measure | measure_consistency | True | 0.0 | 0.0 | blender |
| hoodie_calib_base | calibration | True | 0.0 | 0.0 | blender |
| pants_basis_measure | measure_consistency | True | 0.0 | 0.0 | blender |
| pants_calib_base | calibration | True | 0.0 | 0.0 | blender |
| pants_calib_narrow | calibration | True | 1.408 | 2.74 | blender |
| pants_calib_wide | calibration | True | 0.17 | 0.43 | blender |
| plant_calib_ok | calibration | True | 0.0 | 0.0 | blender |
| sil_bipodal_pants | silhouette | True | None | None |  |
| sil_front_only | silhouette | True | None | None |  |
| sil_front_side | silhouette | True | None | None |  |
| skirt_basis_measure | measure_consistency | True | 0.0 | 0.0 | blender |
| skirt_calib_base | calibration | True | 0.0 | 0.0 | blender |
| top_basis_measure | measure_consistency | True | 0.0 | 0.0 | blender |
| top_calib_base | calibration | True | 0.0 | 0.0 | blender |
| top_calib_large_chest | calibration | True | 0.365 | 0.77 | blender |
| top_calib_long_sleeve | calibration | True | 0.413 | 0.61 | blender |
| top_calib_small | calibration | True | 0.283 | 0.56 | blender |
