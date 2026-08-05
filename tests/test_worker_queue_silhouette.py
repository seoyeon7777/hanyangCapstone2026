"""디스크 워커 큐 / 실루엣 auto·edge-snap / 분류기 학습 테스트."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


class WorkerQueueTests(unittest.TestCase):
    def setUp(self):
        import services.worker_queue as wq

        self.wq = wq
        self.tmp = tempfile.mkdtemp(prefix="q_")
        self._old = (
            wq.QUEUE_DIR,
            wq.PENDING,
            wq.RUNNING,
            wq.DONE,
            wq.FAILED,
            wq._worker_started,
        )
        wq.QUEUE_DIR = self.tmp
        wq.PENDING = os.path.join(self.tmp, "pending")
        wq.RUNNING = os.path.join(self.tmp, "running")
        wq.DONE = os.path.join(self.tmp, "done")
        wq.FAILED = os.path.join(self.tmp, "failed")
        wq._worker_started = False
        wq._ensure_dirs()

    def tearDown(self):
        (
            self.wq.QUEUE_DIR,
            self.wq.PENDING,
            self.wq.RUNNING,
            self.wq.DONE,
            self.wq.FAILED,
            self.wq._worker_started,
        ) = self._old

    def test_enqueue_claim_complete(self):
        jid = self.wq.enqueue("pipeline", {"job_id": "j1", "x": 1}, job_id="j1")
        self.assertEqual(jid, "j1")
        stats = self.wq.queue_stats()
        self.assertEqual(stats["pending"], 1)
        item = self.wq.claim_next()
        self.assertIsNotNone(item)
        self.assertEqual(item["job_id"], "j1")
        self.assertEqual(self.wq.queue_stats()["running"], 1)
        self.wq.complete("j1", ok=True)
        self.assertEqual(self.wq.queue_stats()["done"], 1)
        self.assertEqual(self.wq.queue_stats()["running"], 0)

    def test_run_one_unknown_type_fails(self):
        self.wq.enqueue("nope", {"a": 1}, job_id="bad")
        ok = self.wq.run_one()
        self.assertTrue(ok)
        self.assertEqual(self.wq.queue_stats()["failed"], 1)

    def test_use_disk_queue_env(self):
        old = os.environ.get("PIPELINE_QUEUE")
        try:
            os.environ["PIPELINE_QUEUE"] = "thread"
            self.assertFalse(self.wq.use_disk_queue())
            os.environ["PIPELINE_QUEUE"] = "disk"
            self.assertTrue(self.wq.use_disk_queue())
        finally:
            if old is None:
                os.environ.pop("PIPELINE_QUEUE", None)
            else:
                os.environ["PIPELINE_QUEUE"] = old


class SilhouetteAutoEdgeTests(unittest.TestCase):
    def test_auto_enable_and_edge_snap(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow 없음")

        from models.silhouette_deform import (
            deform_obj_by_silhouette,
            should_auto_enable,
            mask_quality_score,
            mask_width_profile,
        )
        from models.fitting_model import load_obj

        out = tempfile.mkdtemp(prefix="sil2_")
        obj = os.path.join(out, "box.obj")
        with open(obj, "w") as f:
            for x in (-1.0, 1.0):
                for y in (0.0, 1.0, 2.0):
                    for z in (-0.2, 0.2):
                        f.write(f"v {x} {y} {z}\n")
            f.write("f 1 2 3\n")

        mask = os.path.join(out, "mask.png")
        img = Image.new("RGBA", (100, 160), (0, 0, 0, 0))
        px = img.load()
        for y in range(160):
            half = 38 if y < 50 else (28 if y < 110 else 18)
            for x in range(50 - half, 50 + half):
                px[x, y] = (255, 0, 0, 255)
        img.save(mask)

        decision = should_auto_enable(mask, min_score=0.2)
        self.assertTrue(decision["enable"])
        self.assertGreater(decision["score"], 0.2)

        profile = mask_width_profile(mask)
        self.assertGreater(mask_quality_score(profile), 0.2)

        dst = os.path.join(out, "edge.obj")
        report = deform_obj_by_silhouette(obj, mask, dst, strength=0.8, edge_snap=0.6)
        self.assertTrue(report["ok"])
        self.assertIn("edge_snap_abs_max", report)
        self.assertTrue(os.path.exists(dst))
        v0, _ = load_obj(obj)
        v1, _ = load_obj(dst)
        self.assertEqual(len(v0), len(v1))


class ClassifierTrainTests(unittest.TestCase):
    def test_train_synthetic_improves_or_runs(self):
        from scripts.train_garment_classifier import build_dataset, train

        ds = build_dataset(None, synthetic_per_class=6, seed=3)
        self.assertGreaterEqual(len(ds), 20)
        weights, metrics = train(ds, epochs=12, lr=0.1, seed=3)
        self.assertEqual(len(weights), 7)
        self.assertIn("tshirt", weights)
        self.assertGreaterEqual(metrics["train_acc"], 0.35)

    def test_load_custom_weights_roundtrip(self):
        from pipeline.adapters import garment_classifier as gc
        import copy

        tmp = tempfile.mkdtemp(prefix="w_")
        path = os.path.join(tmp, "w.json")
        backup = copy.deepcopy(gc._WEIGHTS)
        payload = {lab: {"bias": 0.0, "w": [0.0] * 7} for lab in gc.LABELS}
        payload["pants"]["bias"] = 5.0
        with open(path, "w") as f:
            json.dump(payload, f)
        try:
            gc.load_custom_weights(path)
            self.assertEqual(gc._WEIGHTS["pants"]["bias"], 5.0)
        finally:
            gc._WEIGHTS = backup


class ManifestSilhouetteOptionsTests(unittest.TestCase):
    def test_options_parse(self):
        from pipeline.schemas.manifest import JobManifest

        m = JobManifest.from_dict(
            {
                "body": {"height": 170, "weight": 60},
                "measurements": {},
                "options": {
                    "silhouette_auto": True,
                    "silhouette_edge_snap": 0.5,
                    "silhouette_auto_min_score": 0.3,
                },
            }
        )
        self.assertTrue(m.options.silhouette_auto)
        self.assertEqual(m.options.silhouette_edge_snap, 0.5)
        self.assertEqual(m.options.silhouette_auto_min_score, 0.3)


if __name__ == "__main__":
    unittest.main()
