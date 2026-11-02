"""Unit tests executed inside the image during the deployment pipeline's test stage."""

import unittest

import service
from fastapi.testclient import TestClient


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(service.app)

    def test_health_reports_degraded_when_platform_unreachable(self):
        service.PLATFORM_URL = "http://127.0.0.1:9"
        body = self.client.get("/health").json()
        self.assertEqual(body["status"], "degraded")
        self.assertFalse(body["platform_reachable"])

    def test_health_payload_ok_requires_token(self):
        service.TOKEN = ""
        self.assertEqual(service.health_payload(True, None)["status"], "degraded")
        service.TOKEN = "t"
        self.assertEqual(service.health_payload(True, None)["status"], "ok")

    def test_ask_validates_input(self):
        self.assertEqual(self.client.post("/ask", json={"question": ""}).status_code, 422)

    def test_index_renders(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("<form", r.text)


if __name__ == "__main__":
    unittest.main()
