"""텍스처 준비 / 세그멘테이션 단위 테스트."""

import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from pipeline.schemas.manifest import JobManifest, JobResult, PipelineOptions
from pipeline.stages import StageContext
from pipeline.stages.texture import bake_texture_p0
from pipeline.adapters.vision_adapter import segment_garment, classify_garment


class ClassifyTests(unittest.TestCase):
    def test_hint(self):
        c = classify_garment("/tmp/x.jpg", hint="hoodie")
        self.assertEqual(c["label"], "hoodie")
        self.assertEqual(c["confidence"], 1.0)


class TextureBakeTests(unittest.TestCase):
    def test_no_image_solid(self):
        m = JobManifest.from_dict({
            "body": {"height": 165, "weight": 55},
            "measurements": {},
            "images": {},
            "options": {"bake_texture": True},
        })
        out = tempfile.mkdtemp(prefix="tex_")
        ctx = StageContext(manifest=m, result=JobResult(job_id=m.job_id), output_dir=out)
        r = bake_texture_p0(ctx)
        self.assertEqual(r["mode"], "solid")
        self.assertIsNone(r["path"])

    def test_front_image_makes_albedo(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow 없음")
        out = tempfile.mkdtemp(prefix="tex_")
        img_path = os.path.join(out, "front.png")
        # 간단한 빨간 티 실루엣
        img = Image.new("RGBA", (200, 300), (0, 0, 0, 0))
        for x in range(40, 160):
            for y in range(30, 270):
                img.putpixel((x, y), (200, 40, 40, 255))
        img.save(img_path)

        m = JobManifest.from_dict({
            "body": {"height": 165, "weight": 55},
            "measurements": {"shoulder": 44, "chest": 100, "sleeve": 20, "length": 65},
            "images": {"front": img_path},
            "options": {"bake_texture": True},
        })
        ctx = StageContext(
            manifest=m,
            result=JobResult(job_id=m.job_id),
            output_dir=out,
            extras={"seg_rgba": img_path},
        )
        r = bake_texture_p0(ctx)
        self.assertEqual(r["mode"], "front_cropped_square")
        self.assertTrue(os.path.exists(r["path"]))


class SegmentTests(unittest.TestCase):
    def test_passthrough_without_crash(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow 없음")
        out = tempfile.mkdtemp(prefix="seg_")
        src = os.path.join(out, "in.png")
        Image.new("RGB", (64, 64), (10, 100, 200)).save(src)
        mask = os.path.join(out, "mask.png")
        r = segment_garment(src, mask)
        # rembg may or may not work; either ok path is fine
        self.assertIn(r["engine"], ("rembg", "passthrough"))
        self.assertTrue(r.get("rgba_path") is None or os.path.exists(r["rgba_path"]))


if __name__ == "__main__":
    unittest.main()
