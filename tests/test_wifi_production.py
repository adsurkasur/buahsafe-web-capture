"""Mode produksi server terpisah: ESP32 lewat WiFi (long-poll) + semua API wajib login."""
import threading
import time
import unittest
from unittest.mock import patch

import app as flask_app
import database
from wifi_device import WifiDevice

KEY = "kunci-uji-perangkat"
DATA_LINE = "DATA,7," + ",".join(f"{20 + i}.5" for i in range(18))


class TestWifiProduction(unittest.TestCase):
    def setUp(self):
        database.initialize()
        self.client = flask_app.app.test_client()
        self.dev = WifiDevice("BSF-001")
        self.patches = [
            patch.object(flask_app, "PRODUCTION", True),
            patch.object(flask_app, "DEVICE_MODE", "wifi"),
            patch.object(flask_app, "DEVICE_KEY", KEY),
            patch.object(flask_app, "device", self.dev),
        ]
        for p in self.patches:
            p.start()
        token = database.create_session_token("u-op-1", "operator")
        self.op = {"Authorization": f"Bearer {token}"}

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def test_production_requires_login_on_legacy_endpoints(self):
        for path in ("/api/measurements", "/export.csv", "/api/master-data/petani", "/api/debug", "/api/status"):
            self.assertEqual(self.client.get(path).status_code, 401, path)
        self.assertEqual(self.client.patch("/api/measurements/1/label", json={"label": "normal"}).status_code, 401)
        self.assertEqual(self.client.get("/").status_code, 404)
        # Operator boleh baca, tidak boleh mengubah label dataset
        self.assertEqual(self.client.get("/api/measurements", headers=self.op).status_code, 200)
        res = self.client.patch("/api/measurements/1/label", json={"label": "normal"}, headers=self.op)
        self.assertEqual(res.status_code, 403)

    def test_device_endpoints_need_key(self):
        self.assertEqual(self.client.get("/api/device/poll").status_code, 401)
        self.assertEqual(self.client.get("/api/device/poll", headers={"X-Device-Key": "salah"}).status_code, 401)

    def test_scan_roundtrip_over_wifi(self):
        dev_headers = {"X-Device-Key": KEY}
        seen = {}

        def esp32():
            # ESP32: poll sampai dapat perintah, lalu kirim baris DATA
            for _ in range(5):
                r = self.client.get("/api/device/poll?fw=2.0.0&rssi=-60", headers=dev_headers)
                if r.status_code == 200:
                    job = r.get_json()["job"]
                    ack = self.client.post("/api/device/result", json={"job": job, "line": DATA_LINE},
                                           headers=dev_headers)
                    seen["ack"] = ack.get_json()
                    return

        self.dev._last_seen = time.monotonic()  # ESP32 baru saja poll
        t = threading.Thread(target=esp32)
        t.start()
        res = self.client.post("/api/scan", json={"fruit_id": "JB-WIFI-001"}, headers=self.op)
        t.join(10)

        self.assertEqual(res.status_code, 200, res.get_json())
        data = res.get_json()
        self.assertIn(data["prediction"]["result"], ("NORMAL", "ANOMALI"))
        self.assertAlmostEqual(data["measurement"]["nm410"], 20.5)
        # ESP32 menerima scan_no sah dari database untuk LCD
        self.assertEqual(seen["ack"]["scan_no"], data["measurement"]["scan_no"])

    def test_scan_fails_fast_when_device_offline(self):
        res = self.client.post("/api/scan", json={"fruit_id": "JB-WIFI-002"}, headers=self.op)
        self.assertEqual(res.status_code, 503)
        self.assertIn("tidak terhubung", res.get_json()["error"])


if __name__ == "__main__":
    unittest.main()
