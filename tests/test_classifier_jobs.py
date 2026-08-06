"""분류 feature model / job_store 테스트."""

import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


class FeatureClassifierTests(unittest.TestCase):
    def test_tall_bipodal_prefers_pants(self):
        try:
            from PIL import Image, ImageDraw
        except ImportError:
            self.skipTest("Pillow 없음")
        from pipeline.adapters.garment_classifier import classify_image_ml

        out = tempfile.mkdtemp(prefix="clf_")
        path = os.path.join(out, "pants.png")
        img = Image.new("RGBA", (120, 280), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        # torso
        d.rectangle([40, 20, 80, 100], fill=(40, 40, 200, 255))
        # two legs
        d.rectangle([35, 100, 55, 260], fill=(40, 40, 200, 255))
        d.rectangle([65, 100, 85, 260], fill=(40, 40, 200, 255))
        img.save(path)
        r = classify_image_ml(path)
        self.assertIsNotNone(r)
        self.assertEqual(r["source"], "feature_model")
        # pants should be top or near-top
        self.assertIn(r["label"], ("pants", "shorts", "dress", "hoodie"))

    def test_wide_short_prefers_tshirtish(self):
        try:
            from PIL import Image, ImageDraw
        except ImportError:
            self.skipTest("Pillow 없음")
        from pipeline.adapters.garment_classifier import classify_image_ml
        out = tempfile.mkdtemp(prefix="clf2_")
        path = os.path.join(out, "tee.png")
        img = Image.new("RGBA", (200, 160), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rectangle([30, 40, 170, 140], fill=(200, 40, 40, 255))
        img.save(path)
        r = classify_image_ml(path)
        self.assertIsNotNone(r)
        self.assertIn(r["label"], ("tshirt", "hoodie", "jacket", "skirt"))


class JobStoreTests(unittest.TestCase):
    def test_save_load_retry(self):
        from services import job_store as js
        # isolate store dir
        tmp = tempfile.mkdtemp(prefix="jobs_")
        old = js.STORE_DIR
        js.STORE_DIR = tmp
        try:
            js.save_job("abc", {"status": "error", "manifest": {"body": {"height": 165, "weight": 55}}, "error": "x"})
            loaded = js.load_job("abc")
            self.assertEqual(loaded["status"], "error")
            marked = js.mark_retry("abc")
            self.assertEqual(marked["retries"], 1)
            self.assertEqual(marked["status"], "queued_retry")
            recent = js.list_recent(5)
            self.assertTrue(any(j["job_id"] == "abc" for j in recent))
        finally:
            js.STORE_DIR = old


if __name__ == "__main__":
    unittest.main()
