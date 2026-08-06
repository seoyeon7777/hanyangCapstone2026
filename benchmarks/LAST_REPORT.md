# Accuracy Benchmark Report

- generated: `2026-08-06T11:31:27`
- blender: `True`
- cases: **41/41** passed (rate=1.0)
- release gate: **36/36** (rate=1.0)

## Suites

- calibration: {'n': 17, 'pass_rate': 1.0, 'mean_mae_cm': 0.217, 'worst_mae_cm': 1.408}
- measure_consistency: {'n': 4, 'pass_rate': 1.0}
- classification: {'n': 7, 'pass_rate': 1.0, 'accuracy': 1.0}
- silhouette: {'n': 8, 'pass_rate': 1.0}
- field_pipeline: {'n': 4, 'pass_rate': 1.0}
- neural_contract: {'n': 1, 'pass_rate': 1.0}

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
| field_pipeline_hoodie_synthetic | field_pipeline | True | None | None | pipeline |
| field_pipeline_pants_synthetic | field_pipeline | True | None | None | pipeline |
| field_pipeline_skirt_synthetic | field_pipeline | True | None | None | pipeline |
| field_pipeline_tee_synthetic | field_pipeline | True | None | None | pipeline |
| field_skirt_tape | calibration | True | 0.0 | 0.0 | blender |
| field_tee_tape | calibration | True | 0.0 | 0.0 | blender |
| hoodie_basis_measure | measure_consistency | True | 0.0 | 0.0 | blender |
| hoodie_calib_base | calibration | True | 0.0 | 0.0 | blender |
| hoodie_calib_large_chest | calibration | True | 1.038 | 1.4 | blender |
| neural_vertex_morph_xz | neural_contract | True | None | None |  |
| pants_basis_measure | measure_consistency | True | 0.0 | 0.0 | blender |
| pants_calib_base | calibration | True | 0.0 | 0.0 | blender |
| pants_calib_narrow | calibration | True | 1.408 | 2.74 | blender |
| pants_calib_wide | calibration | True | 0.17 | 0.43 | blender |
| plant_calib_ok | calibration | True | 0.0 | 0.0 | blender |
| sil_bipodal_pants | silhouette | True | None | None |  |
| sil_front_only | silhouette | True | None | None |  |
| sil_front_side | silhouette | True | None | None |  |
| sil_front_side_rgb_depth_rmse | silhouette | True | None | None |  |
| sil_pants_bipodal_rgb_rmse | silhouette | True | None | None |  |
| sil_rgb_black_bg | silhouette | True | None | None |  |
| sil_skirt_aline | silhouette | True | None | None |  |
| sil_skirt_rgb_waist_guard | silhouette | True | None | None |  |
| skirt_basis_measure | measure_consistency | True | 0.0 | 0.0 | blender |
| skirt_calib_base | calibration | True | 0.0 | 0.0 | blender |
| skirt_calib_narrow | calibration | True | 0.003 | 0.01 | blender |
| skirt_calib_wide_hip | calibration | True | 0.01 | 0.02 | blender |
| top_basis_measure | measure_consistency | True | 0.0 | 0.0 | blender |
| top_calib_base | calibration | True | 0.0 | 0.0 | blender |
| top_calib_large_chest | calibration | True | 0.365 | 0.77 | blender |
| top_calib_long_sleeve | calibration | True | 0.413 | 0.61 | blender |
| top_calib_small | calibration | True | 0.283 | 0.56 | blender |
