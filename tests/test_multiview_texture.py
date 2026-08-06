"""멀티뷰 텍스처 준비 테스트."""

import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from pipeline.schemas.manifest import JobManifest, JobResult
from pipeline.stages import StageContext
from pipeline.stages.texture import bake_texture_p0


class MultiviewTextureTests(unittest.TestCase):
    def _rgba(self, path, color, box):
        from PIL import Image
        img = Image.new("RGBA", (200, 300), (0, 0, 0, 0))
        for x in range(box[0], box[2]):
            for y in range(box[1], box[3]):
                img.putpixel((x, y), color)
        img.save(path)

    def test_front_and_back_make_atlas(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow 없음")

        out = tempfile.mkdtemp(prefix="mv_")
        front = os.path.join(out, "front.png")
        back = os.path.join(out, "back.png")
        self._rgba(front, (200, 40, 40, 255), (40, 30, 160, 270))
        self._rgba(back, (40, 40, 200, 255), (40, 30, 160, 270))

        m = JobManifest.from_dict({
            "body": {"height": 165, "weight": 55},
            "measurements": {},
            "images": {"front": front, "back": back},
            "options": {"bake_texture": True},
        })
        ctx = StageContext(
            manifest=m,
            result=JobResult(job_id=m.job_id),
            output_dir=out,
            extras={"seg_rgba": front, "seg_rgba_back": back},
        )
        r = bake_texture_p0(ctx)
        self.assertEqual(r["mode"], "multiview_atlas")
        self.assertTrue(os.path.exists(r["path"]))
        self.assertTrue(os.path.exists(r["atlas_path"]))
        with Image.open(r["atlas_path"]) as atlas:
            self.assertEqual(atlas.size[0], atlas.size[1] * 2)

    def test_front_only_darkens_back(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow 없음")

        out = tempfile.mkdtemp(prefix="mv2_")
        front = os.path.join(out, "front.png")
        self._rgba(front, (200, 40, 40, 255), (40, 30, 160, 270))
        m = JobManifest.from_dict({
            "body": {"height": 165, "weight": 55},
            "measurements": {},
            "images": {"front": front},
            "options": {"bake_texture": True},
        })
        ctx = StageContext(
            manifest=m,
            result=JobResult(job_id=m.job_id),
            output_dir=out,
            extras={"seg_rgba": front},
        )
        r = bake_texture_p0(ctx)
        self.assertIn("back_from_front_darkened", r["views"])
        self.assertTrue(os.path.exists(r["atlas_path"]))
        self.assertEqual(r["atlas_layout"], "1x2")
        self.assertIsNotNone(r["warning"])

    def test_side_makes_2x2_atlas_and_edge_blend(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow 없음")

        out = tempfile.mkdtemp(prefix="mv3_")
        front = os.path.join(out, "front.png")
        back = os.path.join(out, "back.png")
        side = os.path.join(out, "side.png")
        self._rgba(front, (200, 40, 40, 255), (40, 30, 160, 270))
        self._rgba(back, (40, 40, 200, 255), (40, 30, 160, 270))
        self._rgba(side, (40, 200, 40, 255), (40, 30, 160, 270))

        m = JobManifest.from_dict({
            "body": {"height": 165, "weight": 55},
            "measurements": {},
            "images": {"front": front, "back": back, "side": side},
            "options": {"bake_texture": True},
        })
        ctx = StageContext(
            manifest=m,
            result=JobResult(job_id=m.job_id),
            output_dir=out,
            extras={
                "seg_rgba": front,
                "seg_rgba_back": back,
                "seg_rgba_side": side,
            },
        )
        r = bake_texture_p0(ctx)
        self.assertEqual(r["mode"], "multiview_atlas_side")
        self.assertEqual(r["atlas_layout"], "2x2")
        self.assertIn("side", r["views"])
        self.assertIn("side_edge_blend", r["views"])
        self.assertTrue(os.path.exists(r["side_path"]))
        with Image.open(r["atlas_path"]) as atlas:
            self.assertEqual(atlas.size, (1024, 1024))
            # 하단 좌측 타일 중앙(측면) — 녹색 계열
            px = atlas.getpixel((256, 512 + 256))
            self.assertGreater(px[1], px[0])
            self.assertGreater(px[1], px[2])
            # 상단 좌측 타일 중앙(정면) — 빨강 계열
            px_f = atlas.getpixel((256, 256))
            self.assertGreater(px_f[0], px_f[1])


if __name__ == "__main__":
    unittest.main()
