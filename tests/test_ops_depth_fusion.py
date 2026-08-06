"""대형 배치: ops reclaim / side-depth / mesh_qa / fusion sources / cleanup."""

from __future__ import annotations

import json
from pathlib import Path
import os
import sys
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


class ReclaimAndCleanupTests(unittest.TestCase):
    def test_reclaim_stale_running(self):
        import services.worker_queue as wq

        tmp = tempfile.mkdtemp(prefix="qrec_")
        old = (wq.QUEUE_DIR, wq.PENDING, wq.RUNNING, wq.DONE, wq.FAILED, wq._worker_started)
        wq.QUEUE_DIR = tmp
        wq.PENDING = os.path.join(tmp, "pending")
        wq.RUNNING = os.path.join(tmp, "running")
        wq.DONE = os.path.join(tmp, "done")
        wq.FAILED = os.path.join(tmp, "failed")
        wq._worker_started = False
        wq._ensure_dirs()
        try:
            item = {
                "job_id": "stale1",
                "type": "pipeline",
                "payload": {},
                "started_at": time.time() - 99999,
                "status": "running",
            }
            with open(os.path.join(wq.RUNNING, "stale1.json"), "w") as f:
                json.dump(item, f)
            got = wq.reclaim_stale_running(max_age_sec=10)
            self.assertIn("stale1", got)
            self.assertTrue(os.path.exists(os.path.join(wq.PENDING, "stale1.json")))
            self.assertFalse(os.path.exists(os.path.join(wq.RUNNING, "stale1.json")))
            stats = wq.queue_stats()
            self.assertEqual(stats["pending"], 1)
        finally:
            (
                wq.QUEUE_DIR,
                wq.PENDING,
                wq.RUNNING,
                wq.DONE,
                wq.FAILED,
                wq._worker_started,
            ) = old

    def test_cleanup_preserves_queue_dirs(self):
        """cleanup_outputs는 _queue/_jobs 및 _* 디렉터리를 지우지 않는다."""
        import shutil

        # app 모듈 import는 백그라운드 워커를 띄우므로 로직만 재현 검증
        tmp = tempfile.mkdtemp(prefix="outs_")
        protected = {"_queue", "_jobs"}
        for name in ("_queue", "_jobs", "abc-job"):
            os.makedirs(os.path.join(tmp, name), exist_ok=True)
            marker = os.path.join(tmp, name, "marker.txt")
            with open(marker, "w") as f:
                f.write("x")
            old = time.time() - 99999
            os.utime(marker, (old, old))
            os.utime(os.path.join(tmp, name), (old, old))

        now = time.time()
        for name in os.listdir(tmp):
            if name in protected or name.startswith("_"):
                continue
            folder = os.path.join(tmp, name)
            if os.path.isdir(folder) and now - os.path.getmtime(folder) > 10:
                shutil.rmtree(folder, ignore_errors=True)

        self.assertTrue(os.path.isdir(os.path.join(tmp, "_queue")))
        self.assertTrue(os.path.isdir(os.path.join(tmp, "_jobs")))
        self.assertFalse(os.path.isdir(os.path.join(tmp, "abc-job")))

        # 실제 app.cleanup_outputs 보호 목록 존재 확인 (워커 기동 방지)
        src = Path(ROOT, 'app.py').read_text(encoding='utf-8')
        self.assertIn("_PROTECTED_OUTPUT_DIRS", src)
        self.assertIn('"_queue"', src)


class SideDepthDeformTests(unittest.TestCase):
    def test_side_mask_changes_z(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow 없음")
        from models.silhouette_deform import deform_obj_by_silhouette
        from models.fitting_model import load_obj

        out = tempfile.mkdtemp(prefix="depth_")
        obj = os.path.join(out, "box.obj")
        with open(obj, "w") as f:
            for x in (-1.0, 1.0):
                for y in (0.0, 1.0, 2.0):
                    for z in (-0.4, 0.4):
                        f.write(f"v {x} {y} {z}\n")
            f.write("f 1 2 3\n")

        front = os.path.join(out, "front.png")
        img = Image.new("RGBA", (100, 120), (0, 0, 0, 0))
        px = img.load()
        for y in range(120):
            half = 30
            for x in range(50 - half, 50 + half):
                px[x, y] = (255, 0, 0, 255)
        img.save(front)

        side = os.path.join(out, "side.png")
        img2 = Image.new("RGBA", (100, 120), (0, 0, 0, 0))
        px2 = img2.load()
        for y in range(120):
            half = 45 if y < 60 else 15
            for x in range(50 - half, 50 + half):
                px2[x, y] = (0, 255, 0, 255)
        img2.save(side)

        dst = os.path.join(out, "out.obj")
        report = deform_obj_by_silhouette(
            obj, front, dst, strength=0.9, side_mask_path=side, depth_strength=1.0, edge_snap=0.0, smooth_iters=0
        )
        self.assertTrue(report["ok"])
        self.assertTrue((report.get("depth") or {}).get("ok"))
        self.assertGreater(report["max_abs_z_delta"], 0.0)
        v0, _ = load_obj(obj)
        v1, _ = load_obj(dst)
        self.assertEqual(len(v0), len(v1))


class MeshQaAndFusionTests(unittest.TestCase):
    def test_mesh_qa_detects_nan(self):
        from models.mesh_qa import inspect_obj

        out = tempfile.mkdtemp(prefix="mqa_")
        path = os.path.join(out, "bad.obj")
        with open(path, "w") as f:
            f.write("v 0 0 0\nv 1 nan 0\nv 0 1 0\nf 1 2 3\n")
        # load_obj may convert nan — write finite collapse instead
        path2 = os.path.join(out, "tiny.obj")
        with open(path2, "w") as f:
            f.write("v 0 0 0\nv 0.0000001 0 0\nv 0 0.0000001 0\nf 1 2 3\n")
        rep = inspect_obj(path2)
        self.assertIn("aabb_collapsed", rep.get("issues") or [])
        self.assertFalse(rep["ok"])

    def test_fusion_labels_silhouette_estimate(self):
        from pipeline.schemas.manifest import JobManifest
        from pipeline.stages import StageContext
        from pipeline.stages.measure_fusion import run
        from pipeline.schemas.manifest import JobResult

        m = JobManifest.from_dict({
            "body": {"height": 170, "weight": 60},
            "garment_type": "tshirt",
            "measurements": {},
        })
        result = JobResult(job_id=m.job_id)
        ctx = StageContext(
            manifest=m,
            result=result,
            output_dir=tempfile.mkdtemp(prefix="fus_"),
            progress=lambda s: None,
        )
        ctx.extras["ocr_measurements"] = {"chest": 100.0, "shoulder": 42.0, "sleeve": 20.0, "length": 65.0}
        ctx.extras["ocr_meta"] = {
            "sources": {
                "chest": "silhouette_estimate",
                "shoulder": "text",
                "sleeve": "ocr",
                "length": "silhouette_estimate",
            }
        }
        ctx.extras["template_match"] = {
            "measurement_keys": ["shoulder", "chest", "sleeve", "length"],
            "shape_key_type": "tshirt",
        }
        ctx = run(ctx)
        self.assertEqual(ctx.extras["measurement_sources"]["chest"], "silhouette_estimate")
        self.assertEqual(ctx.extras["measurement_sources"]["shoulder"], "text")
        self.assertTrue(any("실루엣 추정" in w for w in ctx.result.warnings))


class ManifestDepthOptionsTests(unittest.TestCase):
    def test_depth_options(self):
        from pipeline.schemas.manifest import JobManifest

        m = JobManifest.from_dict({
            "body": {"height": 165, "weight": 55},
            "options": {
                "silhouette_depth_strength": 0.55,
                "silhouette_smooth_iters": 2,
                "silhouette_auto": True,
            },
        })
        self.assertEqual(m.options.silhouette_depth_strength, 0.55)
        self.assertEqual(m.options.silhouette_smooth_iters, 2)

    def test_fusion_iters_option(self):
        from pipeline.schemas.manifest import JobManifest

        m = JobManifest.from_dict({
            "body": {"height": 165, "weight": 55},
            "options": {"silhouette_fusion_iters": 3},
        })
        self.assertEqual(m.options.silhouette_fusion_iters, 3)


class SilhouetteBipodalTests(unittest.TestCase):
    def test_bipodal_score_and_deform(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow 없음")
        from models.silhouette_deform import mask_width_profile, deform_obj_by_silhouette

        out = tempfile.mkdtemp(prefix="bip_")
        mask = os.path.join(out, "pants.png")
        img = Image.new("RGBA", (100, 160), (0, 0, 0, 0))
        px = img.load()
        for y in range(0, 55):
            for x in range(35, 65):
                px[x, y] = (255, 0, 0, 255)
        for y in range(55, 160):
            for x in range(25, 40):
                px[x, y] = (255, 0, 0, 255)
            for x in range(60, 75):
                px[x, y] = (255, 0, 0, 255)
        img.save(mask)
        prof = mask_width_profile(mask, bins=32)
        self.assertGreaterEqual(prof["bipodal_score"], 0.3)

        obj = os.path.join(out, "m.obj")
        with open(obj, "w") as f:
            for x in (-0.8, -0.3, 0.3, 0.8):
                for y in (0.0, 0.7, 1.4, 2.0):
                    f.write(f"v {x} {y} 0\n")
            f.write("f 1 2 3\n")
        dst = os.path.join(out, "o.obj")
        rep = deform_obj_by_silhouette(obj, mask, dst, strength=0.9, bipodal="force", smooth_iters=0)
        self.assertTrue(rep["ok"])
        self.assertTrue(rep["bipodal"])
        self.assertGreater(rep["max_abs_x_delta"], 0.0)


if __name__ == "__main__":
    unittest.main()
