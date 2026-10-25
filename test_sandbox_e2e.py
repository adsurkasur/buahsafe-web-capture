"""BuahSafe Local-First Automated Sandbox Testing Suite.

Mengotomasi seluruh alur pengujian integrasi lokal (End-to-End):
1. Inisialisasi database sandbox terisolasi.
2. Pengujian endpoint kesehatan & CORS.
3. Pengujian autentikasi multi-peran (Operator, Supervisor, Owner).
4. Pengujian inferensi Machine Learning SVM (RBF) 6-kanal.
5. Pengujian pindaian sensor & penyimpanan hasil prediksi.
6. Pengujian agregasi metrik analitik & armada perangkat.
7. Pengujian alur CRUD Data Master Petani Mitra.
"""
from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path

# Arahkan ke DB sementara SEBELUM import database/app: suite ini tidak boleh
# menulis ke data/buahsafe.db (dataset pengukuran nyata).
import os
import tempfile
os.environ.setdefault("BUAHSAFE_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="buahsafe-test-"), "test.db"))

# Setup path agar modul app, database, dan predictor terbaca
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import database
import predictor
from app import app


class TestBuahSafeSandbox(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Siapkan environment sandbox terisolasi."""
        print("\n=======================================================")
        print("  MEMULAI PENGUJIAN OTOMATIS LOCAL-FIRST BUAHSAFE")
        print("=======================================================")
        app.config["TESTING"] = True
        cls.client = app.test_client()
        database.initialize()
        print("[OK] Database sandbox SQLite & tabel berhasil diinisialisasi")

    def test_01_health_and_cors(self):
        """Uji endpoint status dan kepatuhan CORS untuk deployment web/Vercel."""
        res = self.client.get("/api/status", headers={"Origin": "http://localhost:5173"})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("version", data)
        self.assertIn("device", data)
        self.assertIn("summary", data)

        # Verifikasi CORS
        self.assertEqual(res.headers.get("Access-Control-Allow-Origin"), "http://localhost:5173")
        self.assertIn("GET", res.headers.get("Access-Control-Allow-Methods", ""))

        # Verifikasi CORS Preflight OPTIONS
        opt_res = self.client.open("/api/scan", method="OPTIONS", headers={"Origin": "http://localhost:5173"})
        self.assertIn(opt_res.status_code, [200, 204])
        self.assertEqual(opt_res.headers.get("Access-Control-Allow-Origin"), "http://localhost:5173")
        print("[OK] [Lolos] Health Check & CORS Preflight (Siap untuk Vercel/Client)")

    def test_02_rbac_authentication(self):
        """Uji autentikasi ketiga mode peran: Operator, Supervisor, dan Owner."""
        roles = [
            ("operator", "operator123", "operator"),
            ("supervisor", "spv123", "supervisor"),
            ("owner", "owner123", "owner"),
        ]
        for username, password, expected_role in roles:
            res = self.client.post(
                "/api/auth/login",
                data=json.dumps({"username": username, "password": password}),
                content_type="application/json",
            )
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertTrue(data.get("ok"))
            self.assertIn("token", data)
            self.assertEqual(data["user"]["role"], expected_role)

        # Uji penolakan kata sandi salah
        bad_res = self.client.post(
            "/api/auth/login",
            data=json.dumps({"username": "operator", "password": "salah_password"}),
            content_type="application/json",
        )
        self.assertEqual(bad_res.status_code, 401)
        print("[OK] [Lolos] Autentikasi Multi-Peran (Operator, Supervisor, Owner)")

    def test_03_machine_learning_inference_accuracy(self):
        """Uji inferensi model produksi pada spektrum NYATA dari buah holdout.

        AMAN_017 (sehat) dan BOSOK_004 (busuk) tidak pernah dipakai melatih model demo
        (ml/holdout_fruits.json); keduanya diputus benar dengan margin lebar.
        """
        import csv
        rows = list(csv.DictReader(open(ROOT / "output/finalised/buahsafe_dataset_gabungan_final.csv", encoding="utf-8-sig")))
        verdicts = {}
        for fruit, expected in (("AMAN_017", "NORMAL"), ("BOSOK_004", "ANOMALI")):
            row = next(r for r in rows if r["fruit_id"] == fruit)
            spectral = {k: float(v) for k, v in row.items() if k.startswith("nm")}
            res = self.client.post("/api/predict", json={"spectral": spectral})
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertEqual(data["result"], expected, fruit)
            self.assertIn("threshold", data)
            verdicts[fruit] = f"{data['result']} {data['confidence']}%"
        print(f"[OK] [Lolos] Inferensi Machine Learning pada buah holdout: {verdicts}")

    def test_04_device_fleet_and_scan_flow(self):
        """Uji pemantauan armada perangkat dan eksekusi alur scan."""
        # Ambil daftar perangkat
        dev_res = self.client.get("/api/devices")
        self.assertEqual(dev_res.status_code, 200)
        devices = dev_res.get_json()["devices"]
        self.assertGreaterEqual(len(devices), 1)
        test_device_id = devices[0]["id"]

        # Simulasikan scan buah dengan sampel data 18 kanal
        test_reading = {f"nm{wl}": 1.5 for wl in [
            410, 435, 460, 485, 510, 535, 560, 585, 610, 645, 680, 705, 730, 760, 810, 860, 900, 940
        ]}
        test_reading["scan_no"] = 1
        test_reading["temp_c"] = 28.5

        # Simpan pengukuran langsung ke database untuk verifikasi persistensi
        pred = predictor.predict(test_reading)
        m = database.insert_measurement(
            fruit_id="JB-SANDBOX-01",
            reading=test_reading,
            prediction=pred["result"],
            confidence=pred["confidence"],
            device_id=test_device_id,
            operator_id="u-op-1",
        )

        self.assertEqual(m["fruit_id"], "JB-SANDBOX-01")
        self.assertEqual(m["device_id"], test_device_id)
        self.assertEqual(m["prediction"], pred["result"])
        self.assertAlmostEqual(m["confidence"], pred["confidence"], places=1)
        print("[OK] [Lolos] Persistensi Scan & Sinkronisasi Armada Perangkat")

    def test_05_analytics_aggregation(self):
        """Uji kalkulasi agregasi analitik (pass rate, anomali, tren 14 hari)."""
        res = self.client.get("/api/analytics")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("total_scans", data)
        self.assertIn("pass_rate", data)
        self.assertIn("by_device", data)
        self.assertIn("daily", data)
        self.assertIsInstance(data["daily"], list)
        print(f"[OK] [Lolos] Agregasi Analitik (Total: {data['total_scans']}, Tingkat Kelolosan: {data['pass_rate']}%)")

    def test_06_master_data_petani(self):
        """Uji alur CRUD Data Master Petani Mitra (Fitur Owner)."""
        # Login sebagai owner untuk mendapatkan Bearer token
        login_res = self.client.post(
            "/api/auth/login",
            data=json.dumps({"username": "owner", "password": "owner123"}),
            content_type="application/json",
        )
        owner_token = login_res.get_json()["token"]
        headers = {"Authorization": f"Bearer {owner_token}"}

        # 1. Tambah petani
        create_res = self.client.post(
            "/api/master-data/petani",
            headers=headers,
            data=json.dumps({
                "name": "Kelompok Tani Bumiaji Makmur",
                "village": "Kecamatan Bumiaji, Batu",
                "phone": "0812-9988-7766",
            }),
            content_type="application/json",
        )
        self.assertEqual(create_res.status_code, 201)
        new_petani = create_res.get_json()["petani"]
        petani_id = new_petani["id"]

        # 2. List & verifikasi keberadaan
        list_res = self.client.get("/api/master-data/petani")
        self.assertEqual(list_res.status_code, 200)
        petani_list = list_res.get_json()["petani"]
        self.assertTrue(any(p["id"] == petani_id for p in petani_list))

        # 3. Hapus petani uji
        del_res = self.client.delete(f"/api/master-data/petani/{petani_id}", headers=headers)
        self.assertEqual(del_res.status_code, 200)
        print("[OK] [Lolos] Alur CRUD Data Master Petani Mitra (Mode Owner)")


if __name__ == "__main__":
    suite = unittest.TestLoader().loadTestsFromTestCase(TestBuahSafeSandbox)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    if result.wasSuccessful():
        print("\n=======================================================")
        print("  SEMUA PENGUJIAN OTOMATIS SANDBOX LOLOS (100% SUKSES) ")
        print("=======================================================\n")
        sys.exit(0)
    else:
        print("\n[!] Terdapat pengujian yang gagal.")
        sys.exit(1)
