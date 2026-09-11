"""OCR / 분류 테스트."""

import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from pipeline.adapters.ocr_adapter import parse_measurement_text, extract_measurements
from pipeline.adapters.vision_adapter import classify_garment


class OcrParseTests(unittest.TestCase):
    def test_korean_size_chart(self):
        text = "어깨 44 가슴둘레 100cm 소매길이 20 총기장 65"
        m = parse_measurement_text(text)
        self.assertEqual(m["shoulder"], 44)
        self.assertEqual(m["chest"], 100)
        self.assertEqual(m["sleeve"], 20)
        self.assertEqual(m["length"], 65)

    def test_pants_keys(self):
        text = "허리:72 엉덩이 96 인심 74cm 총기장 98"
        m = parse_measurement_text(text)
        self.assertEqual(m["waist"], 72)
        self.assertEqual(m["hip"], 96)
        self.assertEqual(m["inseam"], 74)

    def test_extract_prefers_text(self):
        r = extract_measurements(
            measurement_text="어깨 45 가슴 102",
            allow_silhouette_estimate=False,
        )
        self.assertEqual(r["measurements"]["shoulder"], 45)
        self.assertTrue(r["text_used"])
        self.assertEqual(r["sources"]["shoulder"], "text")


class ClassifyTests(unittest.TestCase):
    def test_korean_hint(self):
        r = classify_garment("/tmp/x.jpg", hint="후드티")
        self.assertEqual(r["label"], "hoodie")
        self.assertEqual(r["confidence"], 1.0)

    def test_filename_pants(self):
        path = os.path.join(tempfile.gettempdir(), "blue_pants_front.jpg")
        open(path, "wb").close()
        r = classify_garment(path)
        self.assertEqual(r["label"], "pants")
        self.assertEqual(r["source"], "filename")


if __name__ == "__main__":
    unittest.main()
