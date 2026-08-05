"""실루엣 디폼 / 진행률 유틸 테스트."""

import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


class ProgressUtilTests(unittest.TestCase):
    def test_stage_percents_monotonic(self):
        from pipeline.progress import (
            STAGE_ORDER,
            stage_start_percent,
            stage_end_percent,
            format_progress_event,
            parse_progress_event,
        )

        prev = -1
        for name in STAGE_ORDER:
            s = stage_start_percent(name)
            e = stage_end_percent(name)
            self.assertGreaterEqual(s, prev)
            self.assertGreaterEqual(e, s)
            prev = e
        self.assertEqual(stage_end_percent(STAGE_ORDER[-1]), 100)

        ev = format_progress_event(42, "테스트")
        pct, msg = parse_progress_event(ev)
        self.assertEqual(pct, 42)
        self.assertEqual(msg, "테스트")


class SilhouetteDeformTests(unittest.TestCase):
    def test_deform_widens_where_mask_is_wide(self):
        try:
            from PIL import Image
            import numpy as np
        except ImportError:
            self.skipTest("Pillow/numpy 없음")

        from models.silhouette_deform import deform_obj_by_silhouette
        from models.fitting_model import load_obj as load_obj2

        out = tempfile.mkdtemp(prefix="sil_")
        # 단순 박스 OBJ
        obj = os.path.join(out, "box.obj")
        with open(obj, "w") as f:
            verts = []
            for x in (-1.0, 1.0):
                for y in (0.0, 1.0, 2.0):
                    for z in (-0.2, 0.2):
                        verts.append((x, y, z))
                        f.write(f"v {x} {y} {z}\n")
            f.write("f 1 2 3\n")

        # 마스크: 이미지 위(넓은) / 아래(좁은)
        mask = os.path.join(out, "mask.png")
        img = Image.new("RGBA", (100, 120), (0, 0, 0, 0))
        px = img.load()
        for y in range(120):
            half = 40 if y < 40 else (25 if y < 80 else 12)
            for x in range(50 - half, 50 + half):
                px[x, y] = (255, 0, 0, 255)
        img.save(mask)

        dst = os.path.join(out, "deformed.obj")
        report = deform_obj_by_silhouette(obj, mask, dst, strength=1.0)
        self.assertTrue(os.path.exists(dst))
        self.assertTrue(report["ok"])
        self.assertGreater(report["max_abs_x_delta"], 0.0)

        v0, _ = load_obj2(obj)
        v1, _ = load_obj2(dst)
        self.assertEqual(len(v0), len(v1))


if __name__ == "__main__":
    unittest.main()
