"""S1.5 — 원단/신축성 정규화 → 시뮬 물성."""

from __future__ import annotations

from models.fabric import resolve_fabric_props, build_fit_analysis
from pipeline.stages import StageContext


def run(ctx: StageContext) -> StageContext:
    ctx.progress("원단 물성 계산 중...")
    props = resolve_fabric_props(ctx.manifest.fabric, ctx.manifest.stretch)

    # 정규화된 비율을 manifest에 반영 (이후 단계/결과 일관성)
    ctx.manifest.fabric = props["fabric"]
    ctx.extras["fabric_props"] = props
    ctx.result.fabric = props

    analysis, summary = build_fit_analysis(props.get("summary_ko") or "", ctx.manifest.stretch)
    ctx.result.fit["fit_analysis"] = analysis
    ctx.result.fit["summary"] = summary

    if not props["fabric"]:
        ctx.result.warnings.append("원단 미입력 — cotton 기본 물성으로 시뮬")
    else:
        unknown = [
            c["key"] for c in props["composition"]
            if c["key"] not in (
                "cotton", "polyester", "linen", "wool", "denim", "knit",
                "silk", "nylon", "acrylic", "rayon", "spandex", "cashmere", "chiffon",
            )
        ]
        if unknown:
            ctx.result.warnings.append(f"미등록 원단 키(기본 물성): {', '.join(unknown)}")

    ctx.result.stage = "fabric"
    return ctx
