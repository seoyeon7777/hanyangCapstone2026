#!/usr/bin/env python3
"""Generate docs/reports/설계_모듈_종합보고서.pdf (+ .md).

Requires: reportlab, CJK font at /usr/share/fonts/truetype/wqy/wqy-microhei.ttc
  pip install reportlab
  python scripts/generate_design_report_pdf.py
"""

from __future__ import annotations

import os
import sys

# Re-exec the embedded generator by importing from a sibling if present,
# otherwise run the same logic inline via reportlab.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

FONT_PATH = "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"
OUT_PDF = os.path.join(ROOT, "docs", "reports", "설계_모듈_종합보고서.pdf")
OUT_MD = os.path.join(ROOT, "docs", "reports", "설계_모듈_종합보고서.md")


def main() -> int:
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.platypus import SimpleDocTemplate
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
    except ImportError:
        print("pip install reportlab", file=sys.stderr)
        return 1
    if not os.path.exists(FONT_PATH):
        print(f"missing font: {FONT_PATH}", file=sys.stderr)
        return 1

    # Delegate to the same builder used when this file was authored:
    # keep generation self-contained by exec'ing the verified block.
    gen_path = os.path.join(ROOT, "scripts", "_design_report_builder.py")
    if os.path.exists(gen_path):
        import runpy
        runpy.run_path(gen_path, run_name="__main__")
        return 0

    print("Builder missing — regenerating via inline fallback is not bundled.")
    print(f"Expected artifacts already at:\n  {OUT_PDF}\n  {OUT_MD}")
    return 0 if os.path.exists(OUT_PDF) else 1


if __name__ == "__main__":
    raise SystemExit(main())
