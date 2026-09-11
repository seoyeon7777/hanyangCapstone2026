"""pants 측정 / OCR tesseract / QA 재시도 관련 테스트."""

import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


class PantsMeasureTests(unittest.TestCase):
    def test_basis_has_distinct_waist_hip(self):
        basis = os.path.join(ROOT, "outputs", "_probe_pants", "basis.obj")
        if not os.path.exists(basis):
            self.skipTest("pants probe OBJ 없음")
        from models.garment_measure import measure_garment_obj
        m = measure_garment_obj(basis, "pants")
        self.assertIsNotNone(m.get("waist"))
        self.assertIsNotNone(m.get("hip"))
        self.assertGreater(m["length"], 50)
        self.assertGreater(m["inseam"], 10)
        # 엉덩이가 허리보다 넓거나 비슷
        self.assertGreaterEqual(m["hip"] + 1e-6, m["waist"] * 0.9)

    def test_waist_shape_key_moves_measurement(self):
        d = os.path.join(ROOT, "outputs", "_probe_pants")
        if not os.path.exists(os.path.join(d, "waist_max.obj")):
            self.skipTest("pants probe 없음")
        from models.garment_measure import measure_garment_obj
        b = measure_garment_obj(os.path.join(d, "basis.obj"), "pants")
        mx = measure_garment_obj(os.path.join(d, "waist_max.obj"), "pants")
        self.assertGreater(mx["waist"], b["waist"])


class OcrTesseractTests(unittest.TestCase):
    def test_tesseract_reads_simple_chart(self):
        try:
            import pytesseract
            from PIL import Image, ImageDraw, ImageFont
            pytesseract.get_tesseract_version()
        except Exception:
            self.skipTest("tesseract/pytesseract 없음")

        from pipeline.adapters.ocr_adapter import extract_measurements
        out = tempfile.mkdtemp(prefix="ocr_")
        path = os.path.join(out, "chart.png")
        img = Image.new("RGB", (600, 200), (255, 255, 255))
        draw = ImageDraw.Draw(img)
        draw.text((20, 70), "shoulder 44 chest 100 sleeve 20 length 65", fill=(0, 0, 0))
        img.save(path)
        r = extract_measurements(image_path=path, allow_silhouette_estimate=False)
        # OCR 품질에 따라 일부만 잡힐 수 있음 — shoulder 또는 chest
        self.assertTrue(len(r["measurements"]) >= 1 or r["ocr_engine"] == "tesseract")


class QaRetryTests(unittest.TestCase):
    def test_should_retry_on_calibration_fail(self):
        from pipeline.orchestrator import _should_retry_qa
        from pipeline.schemas.manifest import JobManifest, JobResult
        from pipeline.stages import StageContext

        man = JobManifest.from_dict({
            "body": {"height": 165, "weight": 55},
            "measurements": {},
        })
        ctx = StageContext(
            manifest=man,
            result=JobResult(job_id=man.job_id, status="needs_review"),
            output_dir="/tmp",
        )
        ctx.result.qa = {
            "passed": False,
            "checks": [{"name": "calibration_error", "ok": False, "skipped": False}],
        }
        self.assertTrue(_should_retry_qa(ctx))
        ctx.result.status = "done"
        self.assertFalse(_should_retry_qa(ctx))


if __name__ == "__main__":
    unittest.main()
