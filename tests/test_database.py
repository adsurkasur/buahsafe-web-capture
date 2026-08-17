import gc
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import database
from serial_device import CHANNEL_KEYS, WAVELENGTHS


class TestDatabase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_buahsafe.db"
        self.patcher = patch.object(database, "DATABASE_PATH", self.db_path)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        gc.collect()
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_initialize_fresh_database(self):
        database.initialize()
        conn = database.connect()
        try:
            cols = [row[1] for row in conn.execute("PRAGMA table_info(measurements)").fetchall()]
            self.assertIn("id", cols)
            self.assertIn("timestamp", cols)
            self.assertIn("fruit_id", cols)
            self.assertIn("scan_no", cols)
            for key in CHANNEL_KEYS:
                self.assertIn(key, cols)
            self.assertIn("label", cols)
            self.assertNotIn("sensor_temp_c", cols)
            self.assertNotIn("r610", cols)
        finally:
            conn.close()

    def test_migration_from_legacy_as7263(self):
        # Create legacy table first
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                """
                CREATE TABLE measurements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    fruit_id TEXT NOT NULL,
                    scan_no INTEGER NOT NULL,
                    r610 REAL NOT NULL,
                    s680 REAL NOT NULL,
                    t730 REAL NOT NULL,
                    u760 REAL NOT NULL,
                    v810 REAL NOT NULL,
                    w860 REAL NOT NULL,
                    sensor_temp_c REAL NOT NULL,
                    label TEXT NOT NULL DEFAULT ''
                )
                """
            )
            conn.execute(
                """
                INSERT INTO measurements (
                    timestamp, fruit_id, scan_no, r610, s680, t730,
                    u760, v810, w860, sensor_temp_c, label
                ) VALUES ('2026-08-01T12:00:00.000', 'LEGACY_01', 1, 9.1, 11.2, 13.3, 14.4, 15.5, 16.6, 28.0, 'bagus')
                """
            )
            conn.commit()
        finally:
            conn.close()

        # Run initialize to trigger migration
        database.initialize()

        # Verify data after migration
        rows = database.all_measurements()
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["fruit_id"], "LEGACY_01")
        self.assertEqual(row["scan_no"], 1)
        self.assertEqual(row["label"], "bagus")
        self.assertAlmostEqual(row["nm610"], 9.1)
        self.assertAlmostEqual(row["nm680"], 11.2)
        self.assertAlmostEqual(row["nm730"], 13.3)
        self.assertAlmostEqual(row["nm760"], 14.4)
        self.assertAlmostEqual(row["nm810"], 15.5)
        self.assertAlmostEqual(row["nm860"], 16.6)
        # Verify newly added channels default to 0.0
        self.assertAlmostEqual(row["nm410"], 0.0)
        self.assertAlmostEqual(row["nm940"], 0.0)

    def test_insert_and_retrieve_measurement(self):
        database.initialize()
        reading = {
            "scan_no": 5,
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
        inserted = database.insert_measurement("JAMBU_001", reading)
        self.assertEqual(inserted["fruit_id"], "JAMBU_001")
        # scan_no diselaraskan dengan id baris di DB (bukan reading["scan_no"]
        # mentah dari ESP32) -- lihat insert_measurement().
        self.assertEqual(inserted["scan_no"], inserted["id"])
        self.assertEqual(inserted["label"], "")
        self.assertAlmostEqual(inserted["nm410"], 1.0)
        self.assertAlmostEqual(inserted["nm940"], 18.0)

        # Summary check
        summ = database.summary()
        self.assertEqual(summ["total_scans"], 1)
        self.assertEqual(summ["total_fruits"], 1)
        self.assertEqual(summ["unlabeled"], 1)

        # Update label
        updated = database.update_label(inserted["id"], "bagus")
        self.assertIsNotNone(updated)
        self.assertEqual(updated["label"], "bagus")
        self.assertEqual(database.summary()["unlabeled"], 0)

    def _sample_reading(self, scan_no: int) -> dict:
        reading = {"scan_no": scan_no}
        for i, key in enumerate(CHANNEL_KEYS):
            reading[key] = float(i + 1)
        return reading

    def test_delete_measurement(self):
        database.initialize()
        inserted = database.insert_measurement("JAMBU_DEL", self._sample_reading(1))

        self.assertTrue(database.delete_measurement(inserted["id"]))
        self.assertEqual(database.summary()["total_scans"], 0)
        # Deleting again returns False (already gone)
        self.assertFalse(database.delete_measurement(inserted["id"]))
        # Deleting a nonexistent id returns False
        self.assertFalse(database.delete_measurement(99999))

    def test_delete_measurements_bulk(self):
        database.initialize()
        ids = [
            database.insert_measurement("JAMBU_BULK", self._sample_reading(i))["id"]
            for i in range(1, 4)
        ]

        deleted_count = database.delete_measurements(ids[:2])
        self.assertEqual(deleted_count, 2)
        self.assertEqual(database.summary()["total_scans"], 1)
        self.assertEqual(database.delete_measurements([]), 0)

    def test_list_measurements_search_and_label_filter(self):
        database.initialize()
        a = database.insert_measurement("JAMBU_A", self._sample_reading(1))
        b = database.insert_measurement("JAMBU_B", self._sample_reading(1))
        database.update_label(a["id"], "bagus")
        database.update_label(b["id"], "rusak")

        by_search = database.list_measurements(search="JAMBU_A")
        self.assertEqual([row["fruit_id"] for row in by_search], ["JAMBU_A"])

        by_label = database.list_measurements(label="rusak")
        self.assertEqual([row["fruit_id"] for row in by_label], ["JAMBU_B"])

        self.assertEqual(database.count_measurements(search="JAMBU_A"), 1)
        self.assertEqual(database.count_measurements(label="bagus"), 1)
        self.assertEqual(database.count_measurements(), 2)

    def test_scan_no_ignores_device_reported_value_and_tracks_db_id(self):
        database.initialize()
        # ESP32 kadang reboot dan scan_no-nya reset/tidak sinkron (mis. lapor
        # "5" padahal ini row pertama, atau lapor angka yang sama berulang
        # kali). Database HARUS mengabaikan nilai mentah ini dan pakai id-nya
        # sendiri supaya selalu unik & berurutan.
        reading_a = self._sample_reading(999)
        reading_a["scan_no"] = 999
        inserted_a = database.insert_measurement("JAMBU_A", reading_a)
        self.assertEqual(inserted_a["scan_no"], inserted_a["id"])

        reading_b = self._sample_reading(1)
        reading_b["scan_no"] = 1  # firmware "reboot", counter reset ke 1 lagi
        inserted_b = database.insert_measurement("JAMBU_B", reading_b)
        self.assertEqual(inserted_b["scan_no"], inserted_b["id"])
        self.assertNotEqual(inserted_a["scan_no"], inserted_b["scan_no"])
        self.assertGreater(inserted_b["scan_no"], inserted_a["scan_no"])

    def test_scan_no_never_reused_after_delete(self):
        database.initialize()
        ids = [
            database.insert_measurement(f"JAMBU_{i}", self._sample_reading(i))["id"]
            for i in range(1, 4)
        ]
        # Hapus baris dengan scan_no TERBESAR (paling rawan menyebabkan
        # nomor didaur ulang kalau logikanya naif, mis. pakai MAX()+1).
        database.delete_measurement(ids[-1])

        new_row = database.insert_measurement("JAMBU_NEW", self._sample_reading(1))
        # id/scan_no baru harus tetap lebih besar dari yang pernah ada,
        # bukan mengisi ulang nomor yang baru dihapus.
        self.assertGreater(new_row["scan_no"], max(ids))

    def test_reset_all_measurements(self):
        database.initialize()
        for i in range(1, 4):
            database.insert_measurement(f"JAMBU_{i}", self._sample_reading(i))
        self.assertEqual(database.summary()["total_scans"], 3)

        deleted = database.reset_all_measurements()
        self.assertEqual(deleted, 3)
        self.assertEqual(database.summary(), {"total_scans": 0, "total_fruits": 0, "unlabeled": 0})
        self.assertEqual(database.all_measurements(), [])

        # Setelah reset, penomoran harus mulai dari 1 lagi (bukan lanjut
        # dari id/scan_no terakhir sebelum reset).
        fresh = database.insert_measurement("JAMBU_NEW", self._sample_reading(1))
        self.assertEqual(fresh["id"], 1)
        self.assertEqual(fresh["scan_no"], 1)

    def test_reset_all_measurements_on_empty_database(self):
        database.initialize()
        # Tidak boleh error meski belum pernah ada insert sama sekali
        # (tabel sqlite_sequence belum tentu ada).
        deleted = database.reset_all_measurements()
        self.assertEqual(deleted, 0)

    def test_list_measurements_pagination(self):
        database.initialize()
        for i in range(1, 6):
            database.insert_measurement(f"JAMBU_P{i}", self._sample_reading(i))

        page1 = database.list_measurements(limit=2, offset=0)
        page2 = database.list_measurements(limit=2, offset=2)
        self.assertEqual(len(page1), 2)
        self.assertEqual(len(page2), 2)
        self.assertNotEqual([r["id"] for r in page1], [r["id"] for r in page2])
        self.assertEqual(database.count_measurements(), 5)


if __name__ == "__main__":
    unittest.main()
