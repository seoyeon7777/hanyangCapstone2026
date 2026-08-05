"""정확도 평가 메트릭."""

from __future__ import annotations

from typing import Any, Optional


def per_key_errors(
    target: dict[str, float],
    measured: dict[str, Optional[float]],
) -> dict[str, float]:
    out = {}
    for k, t in target.items():
        if t is None:
            continue
        m = measured.get(k)
        if m is None:
            continue
        out[k] = float(m) - float(t)
    return out


def summarize_errors(errors: dict[str, float]) -> dict[str, Any]:
    if not errors:
        return {
            "n_keys": 0,
            "mae_cm": None,
            "max_abs_cm": None,
            "rmse_cm": None,
            "within_1_5cm": None,
            "within_2_0cm": None,
        }
    abs_errs = [abs(v) for v in errors.values()]
    mae = sum(abs_errs) / len(abs_errs)
    mx = max(abs_errs)
    rmse = (sum(v * v for v in abs_errs) / len(abs_errs)) ** 0.5
    return {
        "n_keys": len(abs_errs),
        "mae_cm": round(mae, 3),
        "max_abs_cm": round(mx, 3),
        "rmse_cm": round(rmse, 3),
        "within_1_5cm": all(a <= 1.5 for a in abs_errs),
        "within_2_0cm": all(a <= 2.0 for a in abs_errs),
        "per_key_abs": {k: round(abs(v), 3) for k, v in errors.items()},
    }


def pass_tolerance(errors: dict[str, float], tolerance_cm: float) -> bool:
    if not errors:
        return False
    return all(abs(v) <= float(tolerance_cm) for v in errors.values())


def silhouette_profile_rmse(
    reference_hw: list[float] | tuple,
    candidate_hw: list[float] | tuple,
) -> float:
    """정규화 half-width 프로파일 RMSE (무차원)."""
    import numpy as np

    from models.silhouette_deform import normalize_halfwidth_profile

    a = normalize_halfwidth_profile(reference_hw)
    b = normalize_halfwidth_profile(candidate_hw)
    n = min(len(a), len(b))
    if n == 0:
        return 999.0
    a, b = a[:n], b[:n]
    return float(np.sqrt(np.mean((a - b) ** 2)))


def aggregate_suite(case_results: list[dict[str, Any]]) -> dict[str, Any]:
    calib = [c for c in case_results if c.get("suite") == "calibration"]
    classify = [c for c in case_results if c.get("suite") == "classification"]
    sil = [c for c in case_results if c.get("suite") == "silhouette"]
    measure = [c for c in case_results if c.get("suite") == "measure_consistency"]
    field_pipe = [c for c in case_results if c.get("suite") == "field_pipeline"]

    def rate(items, key="passed"):
        if not items:
            return None
        return round(sum(1 for x in items if x.get(key)) / len(items), 3)

    def hard_items(items):
        return [
            c for c in items
            if not c.get("soft") and c.get("release_gate", True) is not False
        ]

    maes = [
        (c.get("metrics") or {}).get("mae_cm")
        for c in calib
        if (c.get("metrics") or {}).get("mae_cm") is not None
    ]
    release = hard_items(case_results)
    synthetic_field = [
        c for c in case_results
        if str(c.get("provenance") or "").startswith("synthetic")
        or "synthetic" in [str(t) for t in (c.get("tags") or [])]
    ]
    return {
        "n_cases": len(case_results),
        "n_passed": sum(1 for c in case_results if c.get("passed")),
        "pass_rate": rate(case_results),
        "release_n": len(release),
        "release_passed": sum(1 for c in release if c.get("passed")),
        "release_pass_rate": rate(release),
        "synthetic_field_n": len(synthetic_field),
        "hard_fails": [
            c.get("id") for c in release if not c.get("passed") and not c.get("skip_reason")
        ],
        "soft_fails": [
            c.get("id") for c in case_results
            if (c.get("soft") or c.get("release_gate") is False) and not c.get("passed")
        ],
        "calibration": {
            "n": len(calib),
            "pass_rate": rate(calib),
            "mean_mae_cm": round(sum(maes) / len(maes), 3) if maes else None,
            "worst_mae_cm": round(max(maes), 3) if maes else None,
        },
        "classification": {
            "n": len(classify),
            "pass_rate": rate(classify),
            "accuracy": rate(classify),
        },
        "silhouette": {"n": len(sil), "pass_rate": rate(sil)},
        "measure_consistency": {"n": len(measure), "pass_rate": rate(measure)},
        "field_pipeline": {"n": len(field_pipe), "pass_rate": rate(field_pipe)},
    }
