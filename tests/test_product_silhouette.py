"""제품 실루엣 보정 단위 테스트."""

import os
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import sys

sys.path.insert(0, ROOT)

from models.product_silhouette import (
    flatten_upper_garment_vertices,
    apply_product_silhouette_obj,
)


class ProductSilhouetteTests(unittest.TestCase):
    def test_expands_pinched_waist(self):
        # synthetic hourglass: wide hem, narrow waist, medium chest
        verts = []
        for y, half_w in [(0.0, 1.0), (0.5, 0.45), (0.75, 0.8), (1.0, 0.5)]:
            for x in (-half_w, half_w):
                for z in (-0.2, 0.2):
                    verts.append([x, y, z])
        # add bust peak
        verts.append([0.0, 0.7, 0.9])

        out, meta = flatten_upper_garment_vertices(verts, strength=1.0)
        self.assertTrue(meta["applied"])
        # waist verts (y=0.5) should get wider
        waist = [v for v in out if abs(v[1] - 0.5) < 1e-6]
        waist_w = max(abs(v[0]) for v in waist)
        self.assertGreater(waist_w, 0.45 + 0.05)

    def test_obj_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "t.obj")
            with open(path, "w", encoding="utf-8") as f:
                f.write("v -1.0 0.0 0.0\n")
                f.write("v 1.0 0.0 0.0\n")
                f.write("v -0.4 0.5 0.0\n")
                f.write("v 0.4 0.5 0.0\n")
                f.write("v -0.8 0.75 0.0\n")
                f.write("v 0.8 0.75 0.0\n")
                f.write("v -0.5 1.0 0.0\n")
                f.write("v 0.5 1.0 0.0\n")
                f.write("f 1 3 4\n")
            meta = apply_product_silhouette_obj(path, strength=1.0)
            self.assertTrue(meta.get("applied"))
            with open(path, encoding="utf-8") as f:
                vs = [ln for ln in f if ln.startswith("v ")]
            self.assertEqual(len(vs), 8)


if __name__ == "__main__":
    unittest.main()
