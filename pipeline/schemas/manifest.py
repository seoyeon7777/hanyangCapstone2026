"""JobManifest / JobResult 데이터 계약."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional
import uuid


REQUIRED_UPPER_KEYS = ("shoulder", "chest", "sleeve", "length")
REQUIRED_LOWER_KEYS = ("waist", "hip", "inseam", "length")


@dataclass
class BodyInput:
    height: float
    weight: float


@dataclass
class PipelineOptions:
    phase: str = "P0"  # P0 | P1 | P2
    bake_texture: bool = True
    run_simulation: bool = True
    run_render: bool = True
    calibrate: bool = True
    calibrate_max_iters: int = 4
    calibrate_tolerance_cm: float = 1.5
    calibrate_gain: float = 0.85
    silhouette_deform: bool = False
    silhouette_strength: float = 0.45
    silhouette_auto: bool = False
    silhouette_auto_min_score: float = 0.42
    silhouette_edge_snap: float = 0.35
    silhouette_depth_strength: float = 0.35
    silhouette_smooth_iters: int = 1
    qa_auto_retry: bool = True
    qa_max_retries: int = 1

@dataclass
class JobManifest:
    images: dict[str, Optional[str]]
    measurements: dict[str, Optional[float]]
    body: BodyInput
    garment_type: Optional[str] = None
    fabric: dict[str, float] = field(default_factory=dict)
    stretch: str = ""
    measurement_text: str = ""
    options: PipelineOptions = field(default_factory=PipelineOptions)
    job_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "JobManifest":
        body = data.get("body") or {}
        if "height" not in body or "weight" not in body:
            # 레거시 flat 필드 호환
            if "height" in data and "weight" in data:
                body = {"height": data["height"], "weight": data["weight"]}
            else:
                raise KeyError("body.height / body.weight")

        opts = data.get("options") or {}
        return cls(
            job_id=data.get("job_id") or str(uuid.uuid4()),
            images=data.get("images") or {"front": None, "side": None, "back": None},
            measurements=data.get("measurements") or {},
            body=BodyInput(height=float(body["height"]), weight=float(body["weight"])),
            garment_type=data.get("garment_type"),
            fabric=data.get("fabric") or {},
            stretch=data.get("stretch") or "",
            measurement_text=str(data.get("measurement_text") or ""),
            options=PipelineOptions(
                phase=opts.get("phase", "P0"),
                bake_texture=bool(opts.get("bake_texture", True)),
                run_simulation=bool(opts.get("run_simulation", True)),
                run_render=bool(opts.get("run_render", True)),
                calibrate=bool(opts.get("calibrate", True)),
                calibrate_max_iters=int(opts.get("calibrate_max_iters", 4)),
                calibrate_tolerance_cm=float(opts.get("calibrate_tolerance_cm", 1.5)),
                calibrate_gain=float(opts.get("calibrate_gain", 0.85)),
                silhouette_deform=bool(opts.get("silhouette_deform", False)),
                silhouette_strength=float(opts.get("silhouette_strength", 0.45)),
                silhouette_auto=bool(opts.get("silhouette_auto", False)),
                silhouette_auto_min_score=float(opts.get("silhouette_auto_min_score", 0.42)),
                silhouette_edge_snap=float(opts.get("silhouette_edge_snap", 0.35)),
                silhouette_depth_strength=float(opts.get("silhouette_depth_strength", 0.35)),
                silhouette_smooth_iters=int(opts.get("silhouette_smooth_iters", 1)),
                qa_auto_retry=bool(opts.get("qa_auto_retry", True)),
                qa_max_retries=int(opts.get("qa_max_retries", 1)),
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


@dataclass
class JobResult:
    job_id: str
    status: str = "pending"  # pending|running|done|error|needs_review
    avatar_size: Optional[str] = None
    garment_type: Optional[str] = None
    shape_keys: dict[str, float] = field(default_factory=dict)
    fabric: dict[str, Any] = field(default_factory=dict)
    fit: dict[str, Any] = field(default_factory=dict)
    artifacts: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    qa: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    stage: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
