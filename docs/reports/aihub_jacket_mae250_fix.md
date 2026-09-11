# AI-Hub jacket field_tape — 2026-09-11 calibration diagnosis

## Symptom
`field_jacket_aihub_316767/807/874` reported **MAE ≈ 250–260 cm** (soft fails).
Other jacket cases were ~5–13 cm.

## Root cause
1. Short jackets push `length` Shape Key to **-1**, so body height (Y) < arm span (X).
2. `detect_up_axis()` treated the longest axis as up → **X-up flip**.
3. Sleeve measure then used the body axis as “arm length” → label sleeve **~900+ cm** after the hoodie/jacket long-sleeve scale (~2.9×).

Example (`316767` iter2 before fix): `size=[1.25, 0.91, 0.64]`, up=X, `sleeve_label≈981`.

## Fixes
- Upper garments prefer **Y-up** when Y ≥ 55% of the longest axis (`models/garment_measure.py`).
- Retune jacket `EXPORT_BASE` toward women’s AI-Hub sizes: 43 / 96 / 55 / 64.
- Calibration early-stop now only stops when Shape Keys **stop changing** (still measures clamp once).
- Hoodie/jacket sleeve RANGE overrides for long-sleeve label scale.

## Result (Blender 4.4.3, this agent)
| case | before MAE | after MAE | pass (tol 2cm) |
|------|------------|-----------|----------------|
| 316767 | ~257 | ~2.2 | soft fail |
| 316807 | ~259 | ~3.8 | soft fail |
| 316874 | ~254 | ~1.2 | soft fail |
| 316881 | ~7 | **0.4** | **PASS** |
| 316909 | ~8 | **1.0** | **PASS** |
| 316964 | ~13 | ~6.2 | soft fail (tiny chest 72 beyond SK) |
| 316969 | ~5 | ~2.3 | soft fail |

Jacket mean MAE: **~132 → ~2.4**. Release hoodie/top calib still PASS (except known `top_calib_small` chest floor on this Blender).

