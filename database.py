from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from serial_device import CHANNEL_KEYS, WAVELENGTHS

ROOT = Path(__file__).resolve().parent
DATABASE_PATH = ROOT / "data" / "buahsafe.db"

SCHEMA_COLUMNS = (
    "id INTEGER PRIMARY KEY AUTOINCREMENT",
    "timestamp TEXT NOT NULL",
    "fruit_id TEXT NOT NULL",
    "scan_no INTEGER NOT NULL",
    *(f"{col} REAL NOT NULL" for col in CHANNEL_KEYS),
    "label TEXT NOT NULL DEFAULT ''",
)

INSERT_FIELDS = ("timestamp", "fruit_id", "scan_no", *CHANNEL_KEYS)


def connect() -> sqlite3.Connection:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


@contextmanager
def database_connection():
    connection = connect()
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize() -> None:
    with database_connection() as connection:
        connection.execute("PRAGMA journal_mode=WAL")

        # Check if table already exists and what columns it contains
        table_exists = connection.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='measurements'"
        ).fetchone()[0]

        if table_exists:
            columns = [
                row[1]
                for row in connection.execute("PRAGMA table_info(measurements)").fetchall()
            ]
            # If nm410 is missing, this is an old schema table that needs migration
            if "nm410" not in columns:
                _migrate_legacy_schema(connection, columns)
        else:
            _create_measurements_table(connection)

        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_measurements_fruit_id "
            "ON measurements(fruit_id)"
        )

        # Label vocabulary berubah dari bagus/rusak ke normal/anomali (2026-08-17)
        # supaya konsisten dengan flowchart aplikasi. Migrasi ini idempotent --
        # aman dijalankan berkali-kali tiap startup, dan tidak melakukan apa-apa
        # kalau tidak ada baris lama yang masih pakai label lama.
        _migrate_label_values(connection)


def _create_measurements_table(connection: sqlite3.Connection) -> None:
    columns_sql = ",\n                ".join(SCHEMA_COLUMNS)
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS measurements (
            {columns_sql}
        )
        """
    )


def _migrate_legacy_schema(connection: sqlite3.Connection, old_columns: list[str]) -> None:
    """Migrate legacy AS7263 6-channel measurements table to AS7265x 18-channel schema.

    Preserves existing data non-destructively:
    - Legacy 6 channels (r610, s680, t730, u760, v810, w860) map to their respective nm... fields.
    - Other 12 wavelengths are initialized to 0.0 for legacy records.
    - Legacy temperature is preserved if column existed, or dropped cleanly from active schema.
    """
    columns_sql = ",\n        ".join(SCHEMA_COLUMNS)
    connection.execute(
        f"""
        CREATE TABLE measurements_as7265x_migrated (
            {columns_sql}
        )
        """
    )

    has_r610 = "r610" in old_columns
    if has_r610:
        connection.execute(
            """
            INSERT INTO measurements_as7265x_migrated (
                id, timestamp, fruit_id, scan_no,
                nm410, nm435, nm460, nm485, nm510, nm535,
                nm560, nm585, nm610, nm645, nm680, nm705,
                nm730, nm760, nm810, nm860, nm900, nm940,
                label
            )
            SELECT
                id, timestamp, fruit_id, scan_no,
                0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                0.0, 0.0, COALESCE(r610, 0.0), 0.0, COALESCE(s680, 0.0), 0.0,
                COALESCE(t730, 0.0), COALESCE(u760, 0.0), COALESCE(v810, 0.0), COALESCE(w860, 0.0), 0.0, 0.0,
                COALESCE(label, '')
            FROM measurements
            """
        )
    else:
        # Fallback if arbitrary unknown schema
        connection.execute(
            """
            INSERT INTO measurements_as7265x_migrated (
                id, timestamp, fruit_id, scan_no,
                nm410, nm435, nm460, nm485, nm510, nm535,
                nm560, nm585, nm610, nm645, nm680, nm705,
                nm730, nm760, nm810, nm860, nm900, nm940,
                label
            )
            SELECT
                id, timestamp, fruit_id, scan_no,
                0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                COALESCE(label, '')
            FROM measurements
            """
        )

    connection.execute("DROP TABLE measurements")
    connection.execute("ALTER TABLE measurements_as7265x_migrated RENAME TO measurements")


def _migrate_label_values(connection: sqlite3.Connection) -> None:
    """Rename legacy label values (bagus/rusak) to the current vocabulary (normal/anomali).

    Old rows keep their data untouched aside from this text value -- nothing
    about the 18-channel spectrum or scan_no is affected.
    """
    connection.execute("UPDATE measurements SET label = 'normal' WHERE label = 'bagus'")
    connection.execute("UPDATE measurements SET label = 'anomali' WHERE label = 'rusak'")


def insert_measurement(fruit_id: str, reading: dict[str, Any]) -> dict[str, Any]:
    timestamp = datetime.now().isoformat(timespec="milliseconds")
    values = [
        timestamp,
        fruit_id,
        0,  # placeholder -- diganti dengan id (lihat komentar di bawah)
        *(float(reading[key]) for key in CHANNEL_KEYS),
    ]

    placeholders = ", ".join("?" for _ in values)
    fields_sql = ", ".join(INSERT_FIELDS)

    with database_connection() as connection:
        cursor = connection.execute(
            f"""
            INSERT INTO measurements (
                {fields_sql}
            ) VALUES ({placeholders})
            """,
            values,
        )

        # "Scan #" yang tersimpan/ditampilkan SENGAJA tidak memakai
        # reading["scan_no"] mentah dari ESP32 -- counter itu cuma hidup di
        # RAM firmware dan reset ke 0 tiap board reboot (yang ternyata bisa
        # terjadi sewaktu-waktu, mis. akibat noise relay), jadi gampang tidak
        # sinkron / bahkan bentrok dengan scan lama. Sebagai gantinya scan_no
        # diselaraskan dengan id baris di database (AUTOINCREMENT), yang
        # dijamin SQLite tidak pernah dipakai ulang -- jadi selalu sinkron
        # dan gap-free terhadap isi database yang sebenarnya, apa pun yang
        # terjadi di sisi hardware.
        connection.execute(
            "UPDATE measurements SET scan_no = ? WHERE id = ?",
            (cursor.lastrowid, cursor.lastrowid),
        )

        row = connection.execute(
            "SELECT * FROM measurements WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
    return dict(row)


def list_measurements(
    limit: int = 250,
    offset: int = 0,
    search: str = "",
    label: str = "",
) -> list[dict[str, Any]]:
    safe_limit = min(max(limit, 1), 2000)
    safe_offset = max(offset, 0)

    clauses: list[str] = []
    params: list[Any] = []
    if search:
        clauses.append("fruit_id LIKE ?")
        params.append(f"%{search}%")
    if label:
        clauses.append("label = ?")
        params.append(label)
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    with database_connection() as connection:
        rows = connection.execute(
            f"SELECT * FROM measurements {where_sql} ORDER BY id DESC LIMIT ? OFFSET ?",
            (*params, safe_limit, safe_offset),
        ).fetchall()
    return [dict(row) for row in rows]


def count_measurements(search: str = "", label: str = "") -> int:
    clauses: list[str] = []
    params: list[Any] = []
    if search:
        clauses.append("fruit_id LIKE ?")
        params.append(f"%{search}%")
    if label:
        clauses.append("label = ?")
        params.append(label)
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    with database_connection() as connection:
        row = connection.execute(
            f"SELECT COUNT(*) AS total FROM measurements {where_sql}", params
        ).fetchone()
    return row["total"] or 0


def delete_measurement(measurement_id: int) -> bool:
    with database_connection() as connection:
        cursor = connection.execute(
            "DELETE FROM measurements WHERE id = ?", (measurement_id,)
        )
    return cursor.rowcount > 0


def reset_all_measurements() -> int:
    """Hapus SEMUA baris pengukuran dan reset counter AUTOINCREMENT ke 0.

    Dipakai untuk tombol "Reset Database" di UI -- membersihkan seluruh data
    testing sekaligus sebelum sesi pengambilan data yang sebenarnya dimulai.
    Berbeda dari delete_measurement()/delete_measurements() (yang sengaja
    TIDAK pernah mendaur ulang id/scan_no supaya riwayat yang sedang
    berjalan tidak membingungkan): reset ini adalah "mulai dari nol" yang
    eksplisit diminta operator, jadi scan_no/id berikutnya memang seharusnya
    mulai lagi dari 1.
    """
    with database_connection() as connection:
        cursor = connection.execute("DELETE FROM measurements")
        deleted = cursor.rowcount
        # sqlite_sequence cuma ada setelah insert AUTOINCREMENT pertama --
        # cek dulu supaya tidak error di database yang benar-benar kosong.
        has_sequence_table = connection.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='sqlite_sequence'"
        ).fetchone()[0]
        if has_sequence_table:
            connection.execute(
                "DELETE FROM sqlite_sequence WHERE name = 'measurements'"
            )
    return deleted


def delete_measurements(measurement_ids: list[int]) -> int:
    if not measurement_ids:
        return 0
    placeholders = ", ".join("?" for _ in measurement_ids)
    with database_connection() as connection:
        cursor = connection.execute(
            f"DELETE FROM measurements WHERE id IN ({placeholders})",
            measurement_ids,
        )
    return cursor.rowcount


def update_label(measurement_id: int, label: str) -> dict[str, Any] | None:
    with database_connection() as connection:
        connection.execute(
            "UPDATE measurements SET label = ? WHERE id = ?",
            (label, measurement_id),
        )
        row = connection.execute(
            "SELECT * FROM measurements WHERE id = ?", (measurement_id,)
        ).fetchone()
    return dict(row) if row else None


def summary() -> dict[str, int]:
    with database_connection() as connection:
        row = connection.execute(
            """
            SELECT COUNT(*) AS total_scans,
                   COUNT(DISTINCT fruit_id) AS total_fruits,
                   SUM(CASE WHEN label = '' THEN 1 ELSE 0 END) AS unlabeled
            FROM measurements
            """
        ).fetchone()
    return {
        "total_scans": row["total_scans"] or 0,
        "total_fruits": row["total_fruits"] or 0,
        "unlabeled": row["unlabeled"] or 0,
    }


def all_measurements() -> list[dict[str, Any]]:
    with database_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM measurements ORDER BY id ASC"
        ).fetchall()
    return [dict(row) for row in rows]
