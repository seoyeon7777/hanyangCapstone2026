"""의류 OBJ/메쉬에서 cm 치수를 재측정한다.

캘리브레이션 루프의 피드백 센서. Basis와 변형 메쉬에 동일한 공식을 써야
절대 바이어스가 있어도 Shape Key 보정이 수렴한다.
"""

from __future__ import annotations

from typing import Any, Optional
import numpy as np

from models.fitting_model import load_obj


def _auto_to_cm(verts: np.ndarray) -> tuple[np.ndarray, float]:
    """좌표 단위 추정: bbox 대각선 < 5 이면 meter → cm(*100)."""
    mins = verts.min(axis=0)
    maxs = verts.max(axis=0)
    diag = float(np.linalg.norm(maxs - mins))
    if diag < 5.0:
        return verts * 100.0, 100.0
    return verts.copy(), 1.0


def _slice_points(verts_cm: np.ndarray, z: float, half_band: float) -> np.ndarray:
    mask = np.abs(verts_cm[:, 2] - z) <= half_band
    return verts_cm[mask]


def _width_at(verts_cm: np.ndarray, z_ratio: float, z_min: float, z_span: float,
              half_band_ratio: float = 0.03) -> Optional[float]:
    z = z_min + z_ratio * z_span
    band = max(0.5, half_band_ratio * z_span)
    pts = _slice_points(verts_cm, z, band)
    if len(pts) < 4:
        return None
    return float(pts[:, 0].max() - pts[:, 0].min())


def _depth_at(verts_cm: np.ndarray, z_ratio: float, z_min: float, z_span: float,
              half_band_ratio: float = 0.03) -> Optional[float]:
    z = z_min + z_ratio * z_span
    band = max(0.5, half_band_ratio * z_span)
    pts = _slice_points(verts_cm, z, band)
    if len(pts) < 4:
        return None
    return float(pts[:, 1].max() - pts[:, 1].min())


def _perimeter_rect_approx(width: float, depth: float) -> float:
    """얇은 쉘/열린 메쉬용 둘레 근사: 2*(w+d).

    닫힌 단면 convex hull보다 템플릿 옷 메쉬에서 안정적인 경우가 많음.
    """
    return 2.0 * (width + depth)


def _sleeve_length(verts_cm: np.ndarray, z_min: float, z_span: float,
                   shoulder_width: Optional[float]) -> Optional[float]:
    """상의 소매 길이 근사.

    어깨 밴드(Z≈92%)의 반폭과, 소매 영역(Z≈75~90%)의 최외곽 X 차이를 사용.
    T셔츠 A-포즈/드롭숄더 모두에서 1차 근사로 동작.
    """
    if shoulder_width is None or shoulder_width <= 0:
        return None

    z_lo = z_min + 0.75 * z_span
    z_hi = z_min + 0.92 * z_span
    arm_pts = verts_cm[(verts_cm[:, 2] >= z_lo) & (verts_cm[:, 2] <= z_hi)]
    if len(arm_pts) < 4:
        return None

    half_body = shoulder_width * 0.5
    max_abs_x = float(np.abs(arm_pts[:, 0]).max())
    sleeve = max_abs_x - half_body
    # 드롭숄더/넓은 소매에서 음수 방지
    return float(max(0.0, sleeve))


def measure_garment_verts(
    verts: np.ndarray,
    garment_type: str = "tshirt",
) -> dict[str, Optional[float]]:
    """버텍스 배열(N,3) → cm 치수 dict."""
    if verts is None or len(verts) == 0:
        return {}

    verts_cm, _ = _auto_to_cm(np.asarray(verts, dtype=np.float64))
    z_min = float(verts_cm[:, 2].min())
    z_max = float(verts_cm[:, 2].max())
    z_span = max(z_max - z_min, 1e-6)

    length = z_span
    shoulder = _width_at(verts_cm, 0.92, z_min, z_span)
    chest_w = _width_at(verts_cm, 0.70, z_min, z_span)
    chest_d = _depth_at(verts_cm, 0.70, z_min, z_span)
    chest = None
    if chest_w is not None and chest_d is not None:
        chest = _perimeter_rect_approx(chest_w, chest_d)

    g = (garment_type or "tshirt").lower()
    lower = g in {"pants", "skirt", "shorts"}

    if lower:
        waist_w = _width_at(verts_cm, 0.95, z_min, z_span)
        waist_d = _depth_at(verts_cm, 0.95, z_min, z_span)
        hip_w = _width_at(verts_cm, 0.70, z_min, z_span)
        hip_d = _depth_at(verts_cm, 0.70, z_min, z_span)
        waist = _perimeter_rect_approx(waist_w, waist_d) if waist_w and waist_d else None
        hip = _perimeter_rect_approx(hip_w, hip_d) if hip_w and hip_d else None
        return {
            "length": round(length, 2),
            "waist": round(waist, 2) if waist is not None else None,
            "hip": round(hip, 2) if hip is not None else None,
            "inseam": round(length * 0.85, 2),  # 1차 근사 — 템플릿별 보정 예정
        }

    sleeve = _sleeve_length(verts_cm, z_min, z_span, shoulder)
    return {
        "length": round(length, 2),
        "shoulder": round(shoulder, 2) if shoulder is not None else None,
        "chest": round(chest, 2) if chest is not None else None,
        "sleeve": round(sleeve, 2) if sleeve is not None else None,
    }


def measure_garment_obj(obj_path: str, garment_type: str = "tshirt") -> dict[str, Optional[float]]:
    verts, _faces = load_obj(obj_path)
    return measure_garment_verts(verts, garment_type=garment_type)


def measurement_errors(
    target: dict[str, float],
    measured: dict[str, Optional[float]],
    keys: Optional[list[str]] = None,
) -> dict[str, float]:
    """target - measured (cm). measured가 없는 키는 생략."""
    keys = keys or list(target.keys())
    err = {}
    for k in keys:
        if k not in target or target[k] is None:
            continue
        m = measured.get(k)
        if m is None:
            continue
        err[k] = round(float(target[k]) - float(m), 3)
    return err


def max_abs_error(errors: dict[str, float]) -> float:
    if not errors:
        return 0.0
    return float(max(abs(v) for v in errors.values()))
