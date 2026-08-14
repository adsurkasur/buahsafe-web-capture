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
        self.assertEqual(inserted["scan_no"], 5)
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


if __name__ == "__main__":
    unittest.main()
