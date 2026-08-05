#!/usr/bin/env python3
"""정확도 벤치마크 실행.

예시:
  # CPU 스위트만 (CI)
  python scripts/run_accuracy_benchmark.py --no-blender

  # Blender 캘리브 포함
  python scripts/run_accuracy_benchmark.py --blender

  # 특정 스위트
  python scripts/run_accuracy_benchmark.py --suite calibration --blender
"""

from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def main():
    ap = argparse.ArgumentParser(description="Garment accuracy benchmark")
    ap.add_argument("--cases-dir", default=os.path.join(ROOT, "benchmarks", "cases"))
    ap.add_argument("--out", default=os.path.join(ROOT, "outputs", "_accuracy"))
    ap.add_argument("--blender", action="store_true", help="Blender 캘리브/측정 케이스 실행")
    ap.add_argument("--no-blender", action="store_true", help="Blender 없이 (plant/cpu만 의미 있음)")
    ap.add_argument("--suite", action="append", default=None, help="suite 필터 (반복 가능)")
    ap.add_argument("--case", action="append", default=None, help="case id 필터")
    args = ap.parse_args()

    use_blender = bool(args.blender) and not args.no_blender
    if not args.blender and not args.no_blender:
        # 기본: blender 가능하면 사용
        from pipeline.adapters.export_adapter import blender_available
        use_blender = blender_available()

    from pipeline.eval.runner import run_benchmark

    report = run_benchmark(
        args.cases_dir,
        args.out,
        use_blender=use_blender,
        suites=args.suite,
        case_ids=args.case,
    )
    summary = report.get("summary") or {}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"report: {report.get('report_md')}")
    # CI: plant/cpu 실패 시 exit 1. blender skip은 실패로 치지 않음 unless --strict
    hard_fail = [
        r for r in report.get("results") or []
        if not r.get("passed") and not r.get("skip_reason") and not r.get("soft")
    ]
    soft_fail = [
        r for r in report.get("results") or []
        if not r.get("passed") and r.get("soft")
    ]
    if soft_fail:
        print(f"SOFT/diagnostic fails: {[r.get('id') for r in soft_fail]}")
    if hard_fail:
        print(f"FAILED cases: {[r.get('id') for r in hard_fail]}")
        sys.exit(1)


if __name__ == "__main__":
    main()
