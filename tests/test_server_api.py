"""Unit tests for BuahSafe multi-role API, ML inference, and analytics endpoints."""
import json
import tempfile
import unittest
from pathlib import Path
from app import app
import database
import predictor


_ORIGINAL_DB_PATH = database.DATABASE_PATH


def make_test_client(db_path: Path):
    database.DATABASE_PATH = db_path
    database.initialize()
    app.config["TESTING"] = True
    return app.test_client()


class TestServerAPI(unittest.TestCase):
    def setUp(self):
        database.DATABASE_PATH = _ORIGINAL_DB_PATH
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
        # 18 kanal lengkap seperti yang dikirim firmware
        sample = {ch: 30.0 for ch in predictor.ALL_18_CHANNELS}
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

    def test_predict_uses_artifact_threshold(self):
        from unittest.mock import patch
        sample = {ch: 30.0 for ch in predictor.ALL_18_CHANNELS}
        artifact = predictor.load_model()
        # Ambang tepat di bawah/di atas probabilitas sampel ini (tidak bergantung pada model yang aktif)
        prob = predictor.predict(sample)["probabilities"]["anomali"] / 100
        with patch.dict(artifact, {"threshold": prob - 0.01}):
            self.assertEqual(predictor.predict(sample)["result"], "ANOMALI")
        with patch.dict(artifact, {"threshold": prob + 0.01}):
            self.assertEqual(predictor.predict(sample)["result"], "NORMAL")

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

    def test_active_batch_and_grade_pricing_endpoints(self):
        try:
            test_active_batch_and_grade_pricing_endpoints()
        finally:
            database.DATABASE_PATH = _ORIGINAL_DB_PATH


def test_active_batch_and_grade_pricing_endpoints():
    """Uji pengaturan batch petani aktif dan skema harga multi-grade kustom."""
    with tempfile.TemporaryDirectory() as tmpdir:
        client = make_test_client(Path(tmpdir) / "test_batch_pricing.db")

        # 1. Default active batch kosong / umum
        res = client.get("/api/batch/active")
        assert res.status_code == 200
        data = res.get_json()
        assert "batch" in data
        assert data["batch"]["petani_id"] == ""

        # 2. Set active batch ke petani mitra p1 (Pak Karto)
        token_res = client.post(
            "/api/auth/login",
            json={"username": "operator", "password": "operator123"},
        )
        op_token = token_res.get_json()["token"]
        res = client.post(
            "/api/batch/active",
            json={"petani_id": "p1", "batch_code": "BATCH-PAGI-01"},
            headers={"Authorization": f"Bearer {op_token}"},
        )
        assert res.status_code == 200
        batch = res.get_json()["batch"]
        assert batch["petani_id"] == "p1"
        assert batch["petani_name"] == "Pak Karto"
        assert batch["batch_id"] == "BATCH-PAGI-01"

        # 3. Default grade pricing tersedia dengan unit 'kg' dan minimal 1 grade
        res = client.get("/api/settings/pricing")
        assert res.status_code == 200
        pricing = res.get_json()["pricing"]
        assert pricing["unit"] in ("kg", "butir")
        assert len(pricing["grades"]) >= 1

        # 4. Simpan kustomisasi grade pricing (3 grade non-afkir + harga afkir)
        owner_login = client.post(
            "/api/auth/login",
            json={"username": "owner", "password": "owner123"},
        )
        owner_token = owner_login.get_json()["token"]
        custom_pricing = {
            "unit": "kg",
            "avg_weight_g": 280,
            "grades": [
                {"id": "g-super", "name": "Grade Super", "price": 22000},
                {"id": "g-a", "name": "Grade A", "price": 18000},
                {"id": "g-b", "name": "Grade B", "price": 13000},
            ],
            "afkir_price": 3000,
        }
        res = client.put(
            "/api/settings/pricing",
            json=custom_pricing,
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert res.status_code == 200
        saved = res.get_json()["pricing"]
        assert saved["avg_weight_g"] == 280
        assert len(saved["grades"]) == 3
        assert saved["afkir_price"] == 3000


if __name__ == "__main__":
    unittest.main()
