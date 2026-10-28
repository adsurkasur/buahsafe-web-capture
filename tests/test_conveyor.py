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

    def test_firmware_payload_and_lcd_fields(self):
        """Badan permintaan persis seperti reportFruit() firmware 2.2.0; balasan dibaca seperti jsonField()."""
        line = "DATA,7," + ",".join(f"{30 + i:.6f}" for i in range(18))
        body = (f'{{"line":"{line}","fw":"2.2.0-conveyor","trigger_ms":820,"measure_ms":610,'
                f'"settle_ms":300,"samples":1,"lamp_mode":0}}')
        res = self.client.post("/api/device/auto-scan", data=body, content_type="application/json", headers=DEV)
        self.assertEqual(res.status_code, 200)
        text = res.get_data(as_text=True)

        def json_field(key):  # port jsonField() di buahsafe_wifi.ino
            needle = f'"{key}":'
            at = text.find(needle)
            if at < 0:
                return ""
            at += len(needle)
            while text[at] == " ":
                at += 1
            if text[at] == '"':
                return text[at + 1:text.index('"', at + 1)]
            end = at
            while text[end] not in ",}":
                end += 1
            return text[at:end]

        self.assertTrue(json_field("seq").isdigit())
        self.assertIn(json_field("result"), ("NORMAL", "ANOMALI"))
        self.assertLessEqual(len(f"Yakin {json_field('confidence')}%"), 16)  # muat di baris 2 LCD 16x2
        self.assertLessEqual(len(f"#{json_field('seq')} ANOMALI"), 16)

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

    def test_auto_scan_direct_json_channels_and_predict(self):
        # Payload 6 kanal langsung dari ESP32 AS7263 / asic_final_alat
        payload = {
            "nm610": 28.5, "nm680": 29.1, "nm730": 75.2,
            "nm760": 78.4, "nm810": 88.6, "nm860": 76.2,
            "fw": "asic-2.2.0-conveyor"
        }
        res = self.client.post("/api/device/auto-scan", json=payload, headers=DEV)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["ok"])
        self.assertTrue(data["fruit_id"].startswith(f"CV-{TODAY}-"))
        self.assertIn(data["result"], ("NORMAL", "ANOMALI"))
        self.assertEqual(data["label"], data["result"])
        self.assertIsInstance(data["prob"], float)
        self.assertIn("seq", data)
        self.assertIn("confidence", data)

        # Uji juga endpoint publik /api/predict
        pred_res = self.client.post("/api/predict", json=payload)
        self.assertEqual(pred_res.status_code, 200)
        pred_data = pred_res.get_json()
        self.assertIn("label", pred_data)
        self.assertIn("prob", pred_data)
        self.assertEqual(pred_data["label"], pred_data["result"])


if __name__ == "__main__":
    unittest.main()
