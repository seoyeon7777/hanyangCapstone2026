"""Flask health / reclaim API 스모크 (워커 비활성)."""

from __future__ import annotations

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["PIPELINE_DISABLE_WORKER"] = "1"
os.environ["PIPELINE_QUEUE"] = "thread"


class HealthApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import app

        cls.client = app.test_client()

    def test_health_returns_json(self):
        res = self.client.get("/api/health")
        self.assertIn(res.status_code, (200, 503))
        data = res.get_json()
        self.assertIn("blender_ok", data)
        self.assertIn("queue", data)
        self.assertIn("ok", data)

    def test_queue_endpoint(self):
        res = self.client.get("/api/pipeline/queue")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("pending", data)
        self.assertIn("mode", data)

    def test_ops_dashboard(self):
        res = self.client.get("/api/ops/dashboard")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("health", data)
        self.assertIn("progress", data)
        self.assertIn("p0_percent", data["progress"])
        self.assertIn("alerts", data)

    def test_health_ops_progress_parity(self):
        from services.ops_snapshot import PROGRESS

        h = self.client.get("/api/health").get_json()
        d = self.client.get("/api/ops/dashboard").get_json()
        self.assertEqual(h.get("blender_ok"), d["health"].get("blender_ok"))
        self.assertEqual(h.get("queue_mode"), d["health"].get("queue_mode"))
        self.assertEqual(d["progress"]["p0_percent"], PROGRESS["p0_percent"])
        self.assertEqual(d["progress"]["p1_percent"], PROGRESS["p1_percent"])
        self.assertEqual(d["progress"]["p2_percent"], PROGRESS["p2_percent"])
        self.assertEqual(d["progress"]["vision_percent"], PROGRESS["vision_percent"])

    def test_ops_page(self):
        res = self.client.get("/ops")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Pipeline Ops", res.data)


if __name__ == "__main__":
    unittest.main()
