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


if __name__ == "__main__":
    unittest.main()
