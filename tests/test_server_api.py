"""Unit tests for BuahSafe multi-role API, ML inference, and analytics endpoints."""
import json
import unittest
from app import app
import database


class TestServerAPI(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()
        database.initialize()

    def test_cors_headers_present(self):
        response = self.client.get("/api/status", headers={"Origin": "http://localhost:5173"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("Access-Control-Allow-Origin"), "http://localhost:5173")
        self.assertIn("GET", response.headers.get("Access-Control-Allow-Methods", ""))

    def test_cors_rejects_unknown_origin(self):
        response = self.client.get("/api/measurements", headers={"Origin": "https://evil.example"})
        self.assertIsNone(response.headers.get("Access-Control-Allow-Origin"))

    def test_cors_preflight_options(self):
        response = self.client.open("/api/scan", method="OPTIONS", headers={"Origin": "http://localhost:5173"})
        self.assertIn(response.status_code, [200, 204])
        self.assertEqual(response.headers.get("Access-Control-Allow-Origin"), "http://localhost:5173")

    def test_auth_login_success(self):
        response = self.client.post(
            "/api/auth/login",
            data=json.dumps({"username": "operator", "password": "operator123"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data.get("ok"))
        self.assertEqual(data["user"]["role"], "operator")

    def test_auth_login_invalid(self):
        response = self.client.post(
            "/api/auth/login",
            data=json.dumps({"username": "operator", "password": "wrongpassword"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 401)
        data = response.get_json()
        self.assertFalse(data.get("ok"))

    def test_api_predict_pure_ml(self):
        # 6 kanal atau 18 kanal dict
        sample = {
            "nm610": 1.5,
            "nm680": 1.2,
            "nm730": 5.4,
            "nm760": 0.8,
            "nm810": 2.1,
            "nm860": 1.4,
        }
        response = self.client.post(
            "/api/predict",
            data=json.dumps({"spectral": sample}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("result", data)
        self.assertIn(data["result"], ["NORMAL", "ANOMALI"])
        self.assertIn("confidence", data)
        self.assertGreaterEqual(data["confidence"], 0.0)

    def test_api_devices(self):
        response = self.client.get("/api/devices")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("devices", data)
        self.assertGreaterEqual(len(data["devices"]), 1)

    def test_api_analytics(self):
        response = self.client.get("/api/analytics")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("total_scans", data)
        self.assertIn("pass_rate", data)
        self.assertIn("by_device", data)

    def test_api_petani_crud(self):
        # Dapatkan token owner
        login_res = self.client.post(
            "/api/auth/login",
            data=json.dumps({"username": "owner", "password": "owner123"}),
            content_type="application/json",
        )
        token = login_res.get_json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Tambah
        add_res = self.client.post(
            "/api/master-data/petani",
            headers=headers,
            data=json.dumps({"name": "Pak Tani Uji", "village": "Desa Bumiaji", "phone": "08123456789"}),
            content_type="application/json",
        )
        self.assertEqual(add_res.status_code, 201)
        petani_id = add_res.get_json()["petani"]["id"]

        # List
        list_res = self.client.get("/api/master-data/petani")
        self.assertEqual(list_res.status_code, 200)
        names = [p["name"] for p in list_res.get_json()["petani"]]
        self.assertIn("Pak Tani Uji", names)

        # Hapus
        del_res = self.client.delete(f"/api/master-data/petani/{petani_id}", headers=headers)
        self.assertEqual(del_res.status_code, 200)


if __name__ == "__main__":
    unittest.main()
