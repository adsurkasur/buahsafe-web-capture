import gc
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import app as flask_app
import database
from serial_device import CHANNEL_KEYS, DeviceError


class TestApp(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_app_buahsafe.db"
        self.db_patcher = patch.object(database, "DATABASE_PATH", self.db_path)
        self.db_patcher.start()
        database.initialize()
        self.client = flask_app.app.test_client()

    def tearDown(self):
        self.db_patcher.stop()
        gc.collect()
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_status_endpoint(self):
        response = self.client.get("/api/status")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("device", data)
        self.assertIn("summary", data)

    def test_ports_endpoint(self):
        with patch.object(flask_app.device, "available_ports", return_value=[{"device": "COM3", "description": "USB"}]):
            response = self.client.get("/api/ports")
            self.assertEqual(response.status_code, 200)
            data = response.get_json()
            self.assertEqual(data["ports"], [{"device": "COM3", "description": "USB"}])

    def test_connect_validation(self):
        response = self.client.post("/api/connect", json={})
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.get_json())

    def test_scan_fruit_id_validation(self):
        # Invalid fruit_id
        response = self.client.post("/api/scan", json={"fruit_id": ""})
        self.assertEqual(response.status_code, 400)

        response = self.client.post("/api/scan", json={"fruit_id": "$$INVALID$$"})
        self.assertEqual(response.status_code, 400)

    def test_scan_success_flow(self):
        mock_reading = {
            "scan_no": 1,
            "nm410": 1.0,
            "nm435": 2.0,
            "nm460": 3.0,
            "nm485": 4.0,
            "nm510": 5.0,
            "nm535": 6.0,
            "nm560": 7.0,
            "nm585": 8.0,
            "nm610": 9.0,
            "nm645": 10.0,
            "nm680": 11.0,
            "nm705": 12.0,
            "nm730": 13.0,
            "nm760": 14.0,
            "nm810": 15.0,
            "nm860": 16.0,
            "nm900": 17.0,
            "nm940": 18.0,
        }
        with patch.object(flask_app.device, "scan", return_value=mock_reading), \
                patch.object(flask_app.device, "notify_saved") as mock_notify:
            response = self.client.post("/api/scan", json={"fruit_id": "JAMBU_001"})
            self.assertEqual(response.status_code, 200)
            data = response.get_json()
            self.assertIn("measurement", data)
            measurement = data["measurement"]
            self.assertEqual(measurement["fruit_id"], "JAMBU_001")
            self.assertAlmostEqual(measurement["nm410"], 1.0)
            self.assertAlmostEqual(measurement["nm940"], 18.0)
            self.assertNotIn("sensor_temp_c", measurement)
            # Firmware harus diberi tahu scan_no yang SAH (dari database) supaya
            # LCD bisa sinkron, bukan pakai counter lokal firmware.
            mock_notify.assert_called_once_with(measurement["scan_no"])

    def test_scan_device_error_handled(self):
        with patch.object(flask_app.device, "scan", side_effect=DeviceError("AS7265X not ready")):
            response = self.client.post("/api/scan", json={"fruit_id": "JAMBU_001"})
            self.assertEqual(response.status_code, 503)
            data = response.get_json()
            self.assertIn("error", data)
            self.assertIn("AS7265X not ready", data["error"])

    def test_export_csv_format(self):
        # Insert a sample reading
        reading = {
            "scan_no": 1,
            "nm410": 1.1,
            "nm435": 2.2,
            "nm460": 3.3,
            "nm485": 4.4,
            "nm510": 5.5,
            "nm535": 6.6,
            "nm560": 7.7,
            "nm585": 8.8,
            "nm610": 9.9,
            "nm645": 10.1,
            "nm680": 11.2,
            "nm705": 12.3,
            "nm730": 13.4,
            "nm760": 14.5,
            "nm810": 15.6,
            "nm860": 16.7,
            "nm900": 17.8,
            "nm940": 18.9,
        }
        database.insert_measurement("JAMBU_TEST", reading)

        response = self.client.get("/export.csv")
        self.assertEqual(response.status_code, 200)
        content = response.data.decode("utf-8-sig")
        lines = content.strip().split("\r\n") if "\r\n" in content else content.strip().split("\n")
        header = lines[0].split(",")
        expected_header = [
            "timestamp",
            "fruit_id",
            "scan_no",
            *CHANNEL_KEYS,
            "label",
        ]
        self.assertEqual(header, expected_header)
        data_row = lines[1].split(",")
        self.assertEqual(data_row[1], "JAMBU_TEST")
        self.assertEqual(data_row[2], "1")
        self.assertEqual(data_row[3], "1.1")
        self.assertEqual(data_row[20], "18.9")

    def test_debug_api(self):
        response = self.client.get("/api/debug")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("logs", data)
        self.assertIn("system", data)
        self.assertIsInstance(data["logs"], list)

    def test_debug_clear_api(self):
        response = self.client.post("/api/debug/clear")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["status"], "cleared")

    def _sample_reading(self, scan_no: int = 1) -> dict:
        reading = {"scan_no": scan_no}
        for key in CHANNEL_KEYS:
            reading[key] = 1.0
        return reading

    def test_delete_measurement_endpoint(self):
        inserted = database.insert_measurement("JAMBU_DEL", self._sample_reading())

        response = self.client.delete(f"/api/measurements/{inserted['id']}")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["deleted_id"], inserted["id"])
        self.assertEqual(data["summary"]["total_scans"], 0)

        # Deleting again -> 404
        response = self.client.delete(f"/api/measurements/{inserted['id']}")
        self.assertEqual(response.status_code, 404)

    def test_bulk_delete_measurement_endpoint(self):
        ids = [
            database.insert_measurement("JAMBU_BULK", self._sample_reading(i))["id"]
            for i in range(1, 4)
        ]

        response = self.client.post(
            "/api/measurements/bulk-delete", json={"ids": ids[:2]}
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["deleted_count"], 2)
        self.assertEqual(data["summary"]["total_scans"], 1)

        # Empty list -> 400
        response = self.client.post("/api/measurements/bulk-delete", json={"ids": []})
        self.assertEqual(response.status_code, 400)

    def test_reset_measurements_endpoint(self):
        for i in range(1, 4):
            database.insert_measurement(f"JAMBU_{i}", self._sample_reading(i))

        response = self.client.delete("/api/measurements")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["deleted_count"], 3)
        self.assertEqual(data["summary"]["total_scans"], 0)

        # Database sudah bersih -- reset lagi harus tetap aman (bukan error).
        response = self.client.delete("/api/measurements")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["deleted_count"], 0)

        # Penomoran mulai dari 1 lagi setelah reset.
        fresh = database.insert_measurement("JAMBU_NEW", self._sample_reading(1))
        self.assertEqual(fresh["scan_no"], 1)

    def test_measurements_search_label_and_pagination(self):
        a = database.insert_measurement("JAMBU_SEARCH", self._sample_reading(1))
        database.insert_measurement("OTHER_FRUIT", self._sample_reading(1))
        database.update_label(a["id"], "bagus")

        response = self.client.get("/api/measurements?q=SEARCH")
        data = response.get_json()
        self.assertEqual(len(data["measurements"]), 1)
        self.assertEqual(data["measurements"][0]["fruit_id"], "JAMBU_SEARCH")
        self.assertEqual(data["total"], 1)

        response = self.client.get("/api/measurements?label=bagus")
        data = response.get_json()
        self.assertEqual(len(data["measurements"]), 1)
        self.assertEqual(data["measurements"][0]["fruit_id"], "JAMBU_SEARCH")

        response = self.client.get("/api/measurements?limit=1&offset=0")
        data = response.get_json()
        self.assertEqual(len(data["measurements"]), 1)
        self.assertEqual(data["total"], 2)


if __name__ == "__main__":
    unittest.main()
