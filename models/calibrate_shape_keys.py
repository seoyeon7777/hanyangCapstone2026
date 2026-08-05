"""Shape Key 캘리브레이션 루프.

입력 목표 치수(cm)와 export된 메쉬 실측 치수의 오차로 Shape Key를 반복 보정한다.

  shape_key[k] += gain * (target[k] - measured[k]) / RANGE[k]

export_fn / measure_fn 을 주입하면 Blender 없이 단위 테스트 가능.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Optional
import os

from models.fitting_model import (
    EXPORT_SHAPE_KEY_RANGE,
    EXPORT_SHAPE_KEY_RANGE_MIN,
    EXPORT_SHAPE_KEY_RANGE_MAX,
    calc_export_shape_keys,
)
from models.garment_measure import (
    measure_garment_obj_label,
    measurement_errors,
    max_abs_error,
)


ExportFn = Callable[[dict[str, float], str], str]
# (shape_keys, output_obj_path) -> written_obj_path

MeasureFn = Callable[[str], dict[str, Optional[float]]]
# (obj_path) -> measurements cm


@dataclass
class CalibrationIteration:
    iteration: int
    shape_keys: dict[str, float]
    measured: dict[str, Optional[float]]
    errors_cm: dict[str, float]
    obj_path: Optional[str] = None


@dataclass
class CalibrationReport:
    converged: bool
    iterations: list[CalibrationIteration] = field(default_factory=list)
    final_shape_keys: dict[str, float] = field(default_factory=dict)
    final_measured: dict[str, Optional[float]] = field(default_factory=dict)
    final_errors_cm: dict[str, float] = field(default_factory=dict)
    tolerance_cm: float = 1.5
    max_iters: int = 4
    skipped: bool = False
    skip_reason: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


def clip_shape_keys(shape_keys: dict[str, float]) -> dict[str, float]:
    return {k: float(max(-1.0, min(1.0, v))) for k, v in shape_keys.items()}


def correct_shape_keys(
    shape_keys: dict[str, float],
    errors_cm: dict[str, float],
    *,
    gain: float = 0.85,
    keys: Optional[list[str]] = None,
) -> dict[str, float]:
    """오차(라벨 cm)만큼 Shape Key를 보정. 비대칭 RANGE 사용."""
    updated = dict(shape_keys)
    for k, err in errors_cm.items():
        if keys is not None and k not in keys:
            continue
        if err >= 0:
            rng = float(EXPORT_SHAPE_KEY_RANGE_MAX.get(
                k, EXPORT_SHAPE_KEY_RANGE.get(k, 10.0)
            ))
        else:
            rng = float(EXPORT_SHAPE_KEY_RANGE_MIN.get(
                k, EXPORT_SHAPE_KEY_RANGE.get(k, 10.0)
            ))
        if rng <= 1e-6:
            continue
        delta = gain * (err / rng)
        updated[k] = updated.get(k, 0.0) + delta
    return clip_shape_keys(updated)


def calibrate_shape_keys(
    *,
    target_measurements: dict[str, float],
    initial_shape_keys: Optional[dict[str, float]] = None,
    garment_type: str = "tshirt",
    output_dir: str,
    export_fn: ExportFn,
    measure_fn: Optional[MeasureFn] = None,
    keys_to_calibrate: Optional[list[str]] = None,
    max_iters: int = 4,
    tolerance_cm: float = 1.5,
    gain: float = 0.85,
    progress: Optional[Callable[[str], None]] = None,
) -> CalibrationReport:
    """목표 치수에 수렴하도록 Shape Key를 반복 보정."""
    os.makedirs(output_dir, exist_ok=True)

    keys = keys_to_calibrate or [
        k for k in ("shoulder", "chest", "sleeve", "length", "waist", "hip", "inseam")
        if k in target_measurements and target_measurements[k] is not None
    ]

    if initial_shape_keys is None:
        shape_keys = calc_export_shape_keys(garment_type, target_measurements)
    else:
        shape_keys = clip_shape_keys(dict(initial_shape_keys))

    measure = measure_fn or (
        lambda path: measure_garment_obj_label(path, garment_type=garment_type)
    )

    report = CalibrationReport(
        converged=False,
        tolerance_cm=tolerance_cm,
        max_iters=max_iters,
        final_shape_keys=shape_keys,
    )

    if not keys:
        report.skipped = True
        report.skip_reason = "캘리브레이션 대상 치수 없음"
        return report

    for i in range(1, max_iters + 1):
        if progress:
            progress(f"치수 캘리브레이션 {i}/{max_iters}...")

        obj_path = os.path.join(output_dir, f"calibrate_iter_{i}.obj")
        written = export_fn(shape_keys, obj_path)
        measured = measure(written)
        errors = measurement_errors(target_measurements, measured, keys=keys)

        report.iterations.append(CalibrationIteration(
            iteration=i,
            shape_keys=dict(shape_keys),
            measured=measured,
            errors_cm=errors,
            obj_path=written,
        ))
        report.final_shape_keys = dict(shape_keys)
        report.final_measured = measured
        report.final_errors_cm = errors

        if max_abs_error(errors) <= tolerance_cm:
            report.converged = True
            if progress:
                progress(f"캘리브레이션 수렴 (iter={i}, max|err|≤{tolerance_cm}cm)")
            break

        shape_keys = correct_shape_keys(shape_keys, errors, gain=gain, keys=keys)

        # clamp에 막혀 더 이상 못 움직이면 중단
        if all(abs(shape_keys.get(k, 0.0)) >= 0.999 for k in errors if abs(errors[k]) > tolerance_cm):
            if progress:
                progress("Shape Key 한계 도달 — 캘리브레이션 조기 종료")
            break
    else:
        if progress:
            progress(f"캘리브레이션 미수렴 (max_iters={max_iters})")

    # 마지막 보정값을 final로 (수렴 시에는 이미 측정에 쓰인 값)
    if not report.converged and report.iterations:
        report.final_shape_keys = clip_shape_keys(shape_keys)

    return report
