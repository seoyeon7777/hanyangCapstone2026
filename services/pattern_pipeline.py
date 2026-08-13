"""
Pattern-first 의류 베이스 파이프라인.

draft → (2D measure) → assemble 3D → (3D measure) → correct → repeat
선택적으로 Blender cloth drape를 아바타 위에 수행한다.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from typing import Any, Callable

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from models.garment_spec import GarmentSpec
from models.pattern_draft import draft_pattern, Pattern
from models.measure_garment import measure_pattern_2d, measure_mesh_obj, compare_measurements
from models.panel_mesher import assemble_pattern_mesh, save_pattern_svg
from models.fitting_model import calc_fabric_elasticity, calc_fabric_bending


ProgressCb = Callable[[str], None]


def _noop(_: str) -> None:
    pass


def run_pattern_pipeline(
    spec: GarmentSpec | dict[str, Any],
    job_id: str | None = None,
    output_root: str | None = None,
    max_iters: int = 5,
    run_drape: bool = True,
    progress: ProgressCb | None = None,
) -> dict[str, Any]:
    progress = progress or _noop
    if isinstance(spec, dict):
        spec = GarmentSpec.from_dict(spec)

    problems = spec.validate()
    if problems:
        raise ValueError("; ".join(problems))

    job_id = job_id or str(uuid.uuid4())
    output_root = output_root or os.path.join(ROOT, "outputs")
    out_dir = os.path.join(output_root, job_id)
    os.makedirs(out_dir, exist_ok=True)

    targets = spec.target_garment_cm()
    # 보정 루프가 조정하는 "제도 목표" (초기 = 스펙 목표)
    draft_targets = dict(targets)
    history: list[dict[str, Any]] = []
    pattern: Pattern | None = None
    measured_2d: dict[str, float] = {}
    measured_3d: dict[str, float] = {}
    assemble_info: dict[str, Any] = {}

    progress("패턴 제도 및 보정 루프 시작")

    for it in range(1, max_iters + 1):
        progress(f"제도 iteration {it}/{max_iters}")
        pattern = draft_pattern(spec, overrides=draft_targets)

        pattern_path = os.path.join(out_dir, f"pattern_iter{it}.json")
        with open(pattern_path, "w", encoding="utf-8") as f:
            json.dump(pattern.to_dict(), f, ensure_ascii=False, indent=2)

        svg_path = os.path.join(out_dir, f"pattern_iter{it}.svg")
        save_pattern_svg(pattern, svg_path)

        measured_2d = measure_pattern_2d(pattern)
        cmp_2d = compare_measurements(targets, measured_2d, spec.tolerance_cm)

        obj_path = os.path.join(out_dir, f"base_shell_iter{it}.obj")
        lm_path = os.path.join(out_dir, f"landmarks_iter{it}.json")
        assemble_info = assemble_pattern_mesh(pattern, obj_path, lm_path)

        measured_3d = measure_mesh_obj(obj_path, assemble_info["landmarks_cm"])
        cmp_3d = compare_measurements(targets, measured_3d, spec.tolerance_cm)

        history.append({
            "iteration": it,
            "draft_targets": dict(draft_targets),
            "measured_2d": measured_2d,
            "measured_3d": measured_3d,
            "compare_2d": cmp_2d,
            "compare_3d": cmp_3d,
            "pattern_path": pattern_path,
            "svg_path": svg_path,
            "obj_path": obj_path,
        })

        if cmp_2d["pass"] and cmp_3d["pass"]:
            progress(f"허용 오차 통과 (iteration {it})")
            break

        # 피드백: 제도 목표를 오차만큼 반대로 보정
        # measured - target = error → 다음 draft_target -= error
        for key in ("chest", "shoulder", "sleeve", "length"):
            if key not in cmp_2d["errors"]:
                continue
            err = cmp_2d["errors"][key]["error"]
            draft_targets[key] = round(draft_targets[key] - err, 3)
    else:
        progress("최대 반복 도달 — 마지막 결과 사용")

    assert pattern is not None

    # 최종 산출물 고정 이름으로 복사/저장
    final_obj = os.path.join(out_dir, "base_garment.obj")
    final_pattern = os.path.join(out_dir, "pattern.json")
    final_svg = os.path.join(out_dir, "pattern.svg")
    final_lm = os.path.join(out_dir, "landmarks.json")

    import shutil
    last = history[-1]
    shutil.copy2(last["obj_path"], final_obj)
    shutil.copy2(last["pattern_path"], final_pattern)
    shutil.copy2(last["svg_path"], final_svg)
    shutil.copy2(os.path.join(out_dir, f"landmarks_iter{last['iteration']}.json"), final_lm)

    drape_result = None
    if run_drape:
        progress("Blender 드레이프 시도")
        try:
            drape_result = _run_blender_drape(
                obj_path=final_obj,
                out_dir=out_dir,
                fabric=spec.fabric,
                avatar_size=_pick_avatar_size(spec),
            )
        except Exception as e:
            drape_result = {"ok": False, "error": str(e)}
            progress(f"드레이프 스킵/실패: {e}")

    final_cmp = compare_measurements(
        targets,
        measured_3d,
        spec.tolerance_cm,
    )

    result = {
        "job_id": job_id,
        "output_dir": out_dir,
        "spec": spec.to_dict(),
        "targets_cm": targets,
        "measured_2d_cm": measured_2d,
        "measured_3d_cm": measured_3d,
        "compare": final_cmp,
        "iterations": len(history),
        "history": history,
        "artifacts": {
            "pattern_json": final_pattern,
            "pattern_svg": final_svg,
            "base_obj": final_obj,
            "landmarks_json": final_lm,
        },
        "drape": drape_result,
    }

    report_path = os.path.join(out_dir, "report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    result["artifacts"]["report_json"] = report_path

    progress("done")
    return result


def _pick_avatar_size(spec: GarmentSpec) -> str:
    # 스펙에 height가 없으면 가슴 기준으로 대략 선택
    chest = spec.measurements_cm.get("chest", 88)
    if chest <= 84:
        return "S"
    if chest <= 92:
        return "M"
    return "L"


def _run_blender_drape(
    obj_path: str,
    out_dir: str,
    fabric: dict,
    avatar_size: str,
) -> dict[str, Any]:
    from blender.config import BLENDER_PATH, SCRIPT_DIR, BASE_DIR

    if not os.path.exists(BLENDER_PATH):
        return {"ok": False, "error": f"Blender not found: {BLENDER_PATH}"}

    avatar_blend = os.path.join(BASE_DIR, "assets", "avatars", f"body_{avatar_size}.blend")
    if not os.path.exists(avatar_blend):
        return {"ok": False, "error": f"avatar missing: {avatar_blend}"}

    draped_obj = os.path.join(out_dir, "draped_garment.obj")
    params = {
        "cloth_obj_path": obj_path,
        "avatar_blend_path": avatar_blend,
        "output_obj_path": draped_obj,
        "avatar_verts_path": os.path.join(out_dir, "avatar_verts.json"),
        "fabric_elasticity": calc_fabric_elasticity(fabric),
        "bending_stiffness": calc_fabric_bending(fabric),
        "garment_type": "top",
        "avatar_size": avatar_size,
        "length_ratio": 0.38,
    }
    params_path = os.path.join(out_dir, "drape_params.json")
    with open(params_path, "w", encoding="utf-8") as f:
        json.dump(params, f, ensure_ascii=False)

    cmd = [
        BLENDER_PATH,
        "--background",
        "--python", os.path.join(SCRIPT_DIR, "drape_pattern.py"),
        "--",
        params_path,
    ]
    proc = subprocess.run(
        cmd, capture_output=True, text=True, timeout=300,
        encoding="utf-8", errors="replace",
    )
    ok = proc.returncode == 0 and os.path.exists(draped_obj)
    return {
        "ok": ok,
        "draped_obj": draped_obj if ok else None,
        "returncode": proc.returncode,
        "stdout_tail": (proc.stdout or "")[-2000:],
        "stderr_tail": (proc.stderr or "")[-2000:],
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run pattern-first garment base pipeline")
    parser.add_argument("--chest", type=float, default=88.0)
    parser.add_argument("--shoulder", type=float, default=40.0)
    parser.add_argument("--sleeve", type=float, default=20.0)
    parser.add_argument("--length", type=float, default=65.0)
    parser.add_argument("--fit", default="regular")
    parser.add_argument("--stretch", default="medium")
    parser.add_argument("--no-drape", action="store_true")
    parser.add_argument("--job-id", default=None)
    args = parser.parse_args()

    spec = GarmentSpec(
        category="tshirt",
        fit=args.fit,
        stretch=args.stretch,
        measurements_cm={
            "chest": args.chest,
            "shoulder": args.shoulder,
            "sleeve": args.sleeve,
            "length": args.length,
        },
        fabric={"cotton": 0.95, "spandex": 0.05},
    )

    def _print(msg: str) -> None:
        print(f"[pipeline] {msg}", flush=True)

    result = run_pattern_pipeline(
        spec,
        job_id=args.job_id,
        run_drape=not args.no_drape,
        progress=_print,
    )
    print(json.dumps({
        "job_id": result["job_id"],
        "pass": result["compare"]["pass"],
        "targets_cm": result["targets_cm"],
        "measured_2d_cm": result["measured_2d_cm"],
        "measured_3d_cm": result["measured_3d_cm"],
        "compare": result["compare"],
        "iterations": result["iterations"],
        "artifacts": result["artifacts"],
        "drape_ok": (result.get("drape") or {}).get("ok"),
    }, ensure_ascii=False, indent=2))
