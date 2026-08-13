"""GarmentSpec — 패턴 파이프라인의 단일 입력 스키마."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


# 핏별 기본 여유분 (cm). knit 티셔츠는 ease가 작거나 음수일 수 있음.
DEFAULT_EASE_CM = {
    "slim": {"chest": 2.0, "shoulder": 0.0, "sleeve": 1.0},
    "regular": {"chest": 8.0, "shoulder": 0.5, "sleeve": 2.0},
    "oversized": {"chest": 16.0, "shoulder": 2.0, "sleeve": 4.0},
}

# 재측정 허용 오차 (cm)
DEFAULT_TOLERANCE_CM = {
    "chest": 1.0,
    "shoulder": 0.8,
    "sleeve": 0.8,
    "length": 0.5,
}


@dataclass
class GarmentSpec:
    category: str = "tshirt"
    fit: str = "regular"  # slim | regular | oversized
    measurements_cm: dict[str, float] = field(default_factory=dict)
    ease_cm: dict[str, float] = field(default_factory=dict)
    fabric: dict[str, float] = field(default_factory=dict)
    stretch: str = "medium"  # none | low | medium | high
    construction: dict[str, str] = field(
        default_factory=lambda: {
            "neckline": "crew",
            "sleeve_type": "short",
            "hem": "straight",
        }
    )
    photo_hints: dict[str, Any] = field(default_factory=dict)
    tolerance_cm: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.ease_cm:
            base = dict(DEFAULT_EASE_CM.get(self.fit, DEFAULT_EASE_CM["regular"]))
            # 신축성이 높으면 여유분을 줄임
            stretch_scale = {
                "none": 1.15,
                "low": 1.05,
                "medium": 1.0,
                "high": 0.55,
                "없음": 1.15,
                "낮음": 1.05,
                "높음": 0.55,
            }.get(self.stretch, 1.0)
            self.ease_cm = {k: round(v * stretch_scale, 2) for k, v in base.items()}
        if not self.tolerance_cm:
            self.tolerance_cm = dict(DEFAULT_TOLERANCE_CM)

    def required_measurements(self) -> list[str]:
        if self.category in ("tshirt", "top", "shirt"):
            return ["shoulder", "chest", "sleeve", "length"]
        return ["shoulder", "chest", "sleeve", "length"]

    def validate(self) -> list[str]:
        missing = [k for k in self.required_measurements() if k not in self.measurements_cm]
        return [f"missing measurement: {k}" for k in missing]

    def target_garment_cm(self) -> dict[str, float]:
        """신체 치수 + ease = 의류 목표 치수."""
        m = self.measurements_cm
        e = self.ease_cm
        return {
            "chest": m["chest"] + e.get("chest", 0.0),
            "shoulder": m["shoulder"] + e.get("shoulder", 0.0),
            "sleeve": m["sleeve"] + e.get("sleeve", 0.0),
            "length": m["length"],
        }

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GarmentSpec":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})
