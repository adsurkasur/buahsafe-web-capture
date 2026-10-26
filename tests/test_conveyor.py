"""Mode conveyor: ESP32 dipicu PIR, server membuat ID buah berurutan dan memberi putusan."""
import unittest
from datetime import datetime
from unittest.mock import patch

import app as flask_app
import database
from wifi_device import WifiDevice

KEY = "kunci-uji-conveyor"
DEV = {"X-Device-Key": KEY}
LINE = "DATA,1," + ",".join(f"{30 + i}.5" for i in range(18))
TODAY = f"{datetime.now():%Y%m%d}"


class TestConveyor(unittest.TestCase):
    def setUp(self):
        database.initialize()
        with database.database_connection() as c:
            c.execute("DELETE FROM measurements WHERE fruit_id LIKE 'CV-%' OR fruit_id LIKE 'SIM-%'")
        self.client = flask_app.app.test_client()
        self.dev = WifiDevice("BSF-001", "conveyor")
        self.patches = [patch.object(flask_app, "PRODUCTION", True), patch.object(flask_app, "DEVICE_MODE", "conveyor"),
                        patch.object(flask_app, "DEVICE_KEY", KEY), patch.object(flask_app, "device", self.dev)]
        for p in self.patches:
            p.start()
        self.op = {"Authorization": f"Bearer {database.create_session_token('u-op-1', 'operator')}"}
        self.spv = {"Authorization": f"Bearer {database.create_session_token('u-sv-1', 'supervisor')}"}

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def scan(self, fw="2.1.0-conveyor", line=LINE, headers=DEV):
        return self.client.post("/api/device/auto-scan", json={"line": line, "fw": fw, "trigger_ms": 820, "measure_ms": 610},
                                headers=headers)

    def test_heartbeat_marks_device_online(self):
        self.assertFalse(self.dev.connected)
        self.assertEqual(self.client.get("/api/device/poll?fw=2.1.0-conveyor", headers=DEV).status_code, 204)
        self.assertTrue(self.dev.connected)
        self.assertEqual(self.client.get("/api/device/poll", headers={"X-Device-Key": "salah"}).status_code, 401)

    def test_auto_scan_assigns_daily_sequence(self):
        first, second = self.scan().get_json(), self.scan().get_json()
        self.assertEqual(first["fruit_id"], f"CV-{TODAY}-0001")
        self.assertEqual(second["fruit_id"], f"CV-{TODAY}-0002")
        self.assertIn(first["result"], ("NORMAL", "ANOMALI"))
        self.assertEqual(self.dev.status()["last_trigger_ms"], 820)  # data kalibrasi tercatat
        self.assertTrue(self.scan(fw="sim-2.0").get_json()["fruit_id"].startswith(f"SIM-{TODAY}-"))

    def test_auto_scan_rejects_bad_key_and_bad_line(self):
        self.assertEqual(self.scan(headers={"X-Device-Key": "salah"}).status_code, 401)
        self.assertEqual(self.scan(line="DATA,1,2,3").status_code, 400)

    def test_ml_failure_never_defaults_to_normal(self):
        with patch.object(flask_app.predictor, "predict", side_effect=RuntimeError("model rusak")):
            res = self.scan()
        self.assertEqual(res.status_code, 503)
        self.assertNotIn("result", res.get_json())
        row = database.list_measurements(search=res.get_json()["fruit_id"])[0]
        self.assertEqual(row["prediction"], "")

    def test_sensor_failure_keeps_queue_order_but_not_dataset(self):
        ok = self.scan().get_json()
        fail = self.client.post("/api/device/auto-scan", json={"error": "AS7265X_NOT_READY"}, headers=DEV).get_json()
        after = self.scan().get_json()
        self.assertEqual((ok["seq"], fail["seq"], after["seq"]), (1, 2, 3))
        self.assertEqual(fail["result"], "GAGAL")
        exported = [r["fruit_id"] for r in database.all_measurements()]
        self.assertNotIn(fail["fruit_id"], exported)
        self.assertIn(after["fruit_id"], exported)

    def test_owner_can_disconnect_device(self):
        owner = {"Authorization": f"Bearer {database.create_session_token('u-ow-1', 'owner')}"}
        self.client.get("/api/device/poll?fw=2.1.0-conveyor", headers=DEV)
        self.assertEqual(self.client.post("/api/device/enabled", json={"enabled": False}, headers=self.spv).status_code, 403)
        self.assertEqual(self.client.post("/api/device/enabled", json={"enabled": False}, headers=owner).status_code, 200)
        try:
            self.assertFalse(self.dev.connected)
            self.assertEqual(self.client.get("/api/device/poll", headers=DEV).status_code, 423)
            self.assertEqual(self.scan().status_code, 423)
            self.assertFalse(self.client.get("/api/status", headers=owner).get_json()["device"]["enabled"])
        finally:
            self.client.post("/api/device/enabled", json={"enabled": True}, headers=owner)
        self.assertEqual(self.client.get("/api/device/poll", headers=DEV).status_code, 204)

    def test_manual_scan_disabled(self):
        res = self.client.post("/api/scan", json={"fruit_id": "JB-1"}, headers=self.op)
        self.assertEqual(res.status_code, 409)

    def test_simulation_request_reaches_simulator_only(self):
        self.assertEqual(self.client.post("/api/device/simulate", json={"count": 5}, headers=self.spv).status_code, 409)
        self.client.get("/api/device/poll?fw=sim-2.0", headers=DEV)
        self.assertEqual(self.client.post("/api/device/simulate", json={"count": 5}, headers=self.op).status_code, 403)
        self.assertEqual(self.client.post("/api/device/simulate", json={"count": 5}, headers=self.spv).status_code, 202)
        res = self.client.get("/api/device/poll?fw=sim-2.0", headers=DEV)
        self.assertEqual(res.get_json(), {"simulate": 5})
        self.assertEqual(self.client.get("/api/device/poll?fw=sim-2.0", headers=DEV).status_code, 204)


if __name__ == "__main__":
    unittest.main()
