from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from serial_device import CHANNEL_KEYS, WAVELENGTHS

ROOT = Path(__file__).resolve().parent
# BUAHSAFE_DB_PATH memisahkan DB uji/sandbox dari DB dataset operasional.
DATABASE_PATH = Path(os.environ.get("BUAHSAFE_DB_PATH") or ROOT / "data" / "buahsafe.db")

SCHEMA_COLUMNS = (
    "id INTEGER PRIMARY KEY AUTOINCREMENT",
    "timestamp TEXT NOT NULL",
    "fruit_id TEXT NOT NULL",
    "scan_no INTEGER NOT NULL",
    *(f"{col} REAL NOT NULL" for col in CHANNEL_KEYS),
    "label TEXT NOT NULL DEFAULT ''",
    "diameter_cm REAL",
    "rotasi_sensor TEXT NOT NULL DEFAULT ''",
    "rotasi_buah TEXT NOT NULL DEFAULT ''",
    "jarak_cm REAL",
    "prediction TEXT NOT NULL DEFAULT ''",
    "confidence REAL",
    "device_id TEXT NOT NULL DEFAULT 'BSF-001'",
    "operator_id TEXT NOT NULL DEFAULT ''",
)

INSERT_FIELDS = ("timestamp", "fruit_id", "scan_no", *CHANNEL_KEYS)
# Prediksi untuk buah conveyor yang gagal diukur sensor: hanya penanda urutan, bukan data spektral
FAILED_SCAN = "GAGAL"


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
                columns = [
                    row[1]
                    for row in connection.execute("PRAGMA table_info(measurements)").fetchall()
                ]
            # Kolom pengukuran fisik manual operator (jangkar sortasi fisik
            # jambu), ditambahkan/diubah 2026-08-17 s/d 2026-08-19. Migrasi
            # idempotent lewat ALTER TABLE ADD COLUMN -- aman dijalankan
            # berkali-kali, tidak menyentuh data spektral/label yang sudah ada.
            #
            # CATATAN NON-DESTRUKTIF: kolom lama `rotasi` (field rotasi
            # tunggal, sebelum dipecah jadi Rotasi Sensor/Rotasi Buah),
            # `elevasi_cm`, dan `tinggi_cm` SENGAJA TIDAK PERNAH di-DROP di
            # sini walau sudah tidak dipakai aplikasi -- kalau kolom itu ada
            # (dari versi sebelumnya) dan sudah terisi data, data itu tetap
            # utuh tersimpan di database, hanya tidak lagi dibaca/ditulis.
            had_legacy_rotasi = "rotasi" in columns
            if "diameter_cm" not in columns:
                connection.execute("ALTER TABLE measurements ADD COLUMN diameter_cm REAL")
            if "rotasi_sensor" not in columns:
                connection.execute(
                    "ALTER TABLE measurements ADD COLUMN rotasi_sensor TEXT NOT NULL DEFAULT ''"
                )
            if "rotasi_buah" not in columns:
                connection.execute(
                    "ALTER TABLE measurements ADD COLUMN rotasi_buah TEXT NOT NULL DEFAULT ''"
                )
            if "jarak_cm" not in columns:
                connection.execute("ALTER TABLE measurements ADD COLUMN jarak_cm REAL")
            if "prediction" not in columns:
                connection.execute(
                    "ALTER TABLE measurements ADD COLUMN prediction TEXT NOT NULL DEFAULT ''"
                )
            if "confidence" not in columns:
                connection.execute("ALTER TABLE measurements ADD COLUMN confidence REAL")
            if "device_id" not in columns:
                connection.execute(
                    "ALTER TABLE measurements ADD COLUMN device_id TEXT NOT NULL DEFAULT 'BSF-001'"
                )
            if "operator_id" not in columns:
                connection.execute(
                    "ALTER TABLE measurements ADD COLUMN operator_id TEXT NOT NULL DEFAULT ''"
                )

            if had_legacy_rotasi:
                # Migrasi satu-kali: pindahkan nilai `rotasi` lama (field
                # tunggal) ke `rotasi_buah` -- representasi paling dekat
                # dengan makna aslinya (orientasi buah saat discan). Guard
                # WHERE rotasi_buah kosong membuat ini idempotent dan tidak
                # pernah menimpa nilai rotasi_buah yang sudah diisi manual.
                connection.execute(
                    "UPDATE measurements SET rotasi_buah = rotasi "
                    "WHERE (rotasi_buah IS NULL OR rotasi_buah = '') "
                    "AND rotasi IS NOT NULL AND rotasi != ''"
                )
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

        # Inisialisasi tabel operasional multi-peran (users, devices, petani)
        _init_auxiliary_tables(connection)


def _init_auxiliary_tables(connection: sqlite3.Connection) -> None:
    """Inisialisasi tabel operasional users, auth_tokens, devices, dan petani_mitra."""
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            password TEXT NOT NULL DEFAULT '',
            password_hash TEXT NOT NULL DEFAULT '',
            salt TEXT NOT NULL DEFAULT '',
            role TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            last_login TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        )
        """
    )

    # Migrasi kolom tambahan pada users jika tabel sudah ada sebelumnya
    user_cols = {col["name"] for col in connection.execute("PRAGMA table_info(users)").fetchall()}
    if "password_hash" not in user_cols:
        connection.execute("ALTER TABLE users ADD COLUMN password_hash TEXT NOT NULL DEFAULT ''")
    if "salt" not in user_cols:
        connection.execute("ALTER TABLE users ADD COLUMN salt TEXT NOT NULL DEFAULT ''")
    if "is_active" not in user_cols:
        connection.execute("ALTER TABLE users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")
    if "last_login" not in user_cols:
        connection.execute("ALTER TABLE users ADD COLUMN last_login TEXT NOT NULL DEFAULT ''")

    # Inisialisasi atau migrasi akun awal dengan password PBKDF2 hash
    now_iso = datetime.now().isoformat()
    defaults = [
        ("u-op-1", "operator", "Budi Santoso", "operator123", "operator"),
        ("u-sv-1", "supervisor", "Sari Wijaya", "spv123", "supervisor"),
        ("u-ow-1", "owner", "Pak Hendra", "owner123", "owner"),
    ]
    for uid, uname, name, raw_pwd, role in defaults:
        row = connection.execute("SELECT id, password, password_hash, salt FROM users WHERE username = ?", (uname,)).fetchone()
        if not row:
            salt_hex, hash_hex = hash_password(raw_pwd)
            connection.execute(
                """INSERT INTO users (id, username, name, password, password_hash, salt, role, is_active, last_login, created_at)
                   VALUES (?, ?, ?, '', ?, ?, ?, 1, '', ?)""",
                (uid, uname, name, hash_hex, salt_hex, role, now_iso),
            )
        elif not row["password_hash"]:
            # Migrasi akun lama yang belum ber-hash
            salt_hex, hash_hex = hash_password(raw_pwd)
            connection.execute(
                "UPDATE users SET password_hash = ?, salt = ?, password = '', is_active = 1 WHERE id = ?",
                (hash_hex, salt_hex, row["id"]),
            )

    # Tabel sesi auth_tokens untuk Bearer Token 24 jam
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS auth_tokens (
            token TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            role TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_tokens_expires ON auth_tokens(expires_at)"
    )

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS devices (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            location TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'online',
            last_seen TEXT NOT NULL,
            total_scans INTEGER NOT NULL DEFAULT 0,
            firmware_version TEXT NOT NULL DEFAULT 'v1.2.4',
            install_date TEXT NOT NULL
        )
        """
    )
    device_count = connection.execute("SELECT COUNT(*) FROM devices").fetchone()[0]
    if device_count == 0:
        now_iso = datetime.now().isoformat()
        connection.executemany(
            """INSERT INTO devices (id, name, location, status, last_seen, total_scans, firmware_version, install_date)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                ("BSF-001", "Meja Sortasi A", "Lantai Produksi", "online", now_iso, 0, "v1.2.4", now_iso),
            ],
        )

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS petani_mitra (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            village TEXT NOT NULL,
            phone TEXT NOT NULL,
            joined TEXT NOT NULL
        )
        """
    )
    petani_count = connection.execute("SELECT COUNT(*) FROM petani_mitra").fetchone()[0]
    if petani_count == 0:
        connection.executemany(
            "INSERT INTO petani_mitra (id, name, village, phone, joined) VALUES (?, ?, ?, ?, ?)",
            [
                ("p1", "Pak Karto", "Desa Sukamulya", "0812-3344-5566", "2024-03-12"),
                ("p2", "Bu Lestari", "Desa Cibeureum", "0813-1122-3344", "2024-05-20"),
                ("p3", "Pak Surya", "Desa Cikondang", "0857-9988-7766", "2024-07-02"),
            ],
        )


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


def insert_measurement(
    fruit_id: str,
    reading: dict[str, Any],
    prediction: str = "",
    confidence: float | None = None,
    device_id: str = "BSF-001",
    operator_id: str = "",
) -> dict[str, Any]:
    timestamp = datetime.now().isoformat(timespec="milliseconds")
    values = [
        timestamp,
        fruit_id,
        0,  # placeholder -- diganti dengan id (lihat komentar di bawah)
        *(float(reading[key]) for key in CHANNEL_KEYS),
        str(prediction or ""),
        float(confidence) if confidence is not None else None,
        str(device_id or "BSF-001"),
        str(operator_id or ""),
    ]

    extended_fields = (*INSERT_FIELDS, "prediction", "confidence", "device_id", "operator_id")
    placeholders = ", ".join("?" for _ in values)
    fields_sql = ", ".join(extended_fields)

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

        # Sinkronkan status dan jumlah pindaian pada armada device
        if device_id:
            connection.execute(
                "UPDATE devices SET total_scans = total_scans + 1, last_seen = ?, status = 'online' WHERE id = ?",
                (timestamp, device_id),
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


def update_diameter(measurement_id: int, diameter_cm: float | None) -> dict[str, Any] | None:
    """Simpan diameter buah (cm) yang diukur manual oleh operator.

    diameter_cm boleh None -- artinya belum diukur/dikosongkan kembali.
    """
    with database_connection() as connection:
        connection.execute(
            "UPDATE measurements SET diameter_cm = ? WHERE id = ?",
            (diameter_cm, measurement_id),
        )
        row = connection.execute(
            "SELECT * FROM measurements WHERE id = ?", (measurement_id,)
        ).fetchone()
    return dict(row) if row else None


def update_rotasi_sensor(measurement_id: int, rotasi_sensor: str) -> dict[str, Any] | None:
    """Simpan orientasi rotasi SENSOR saat pemindaian (A/B/C/D, atau '' jika kosong)."""
    with database_connection() as connection:
        connection.execute(
            "UPDATE measurements SET rotasi_sensor = ? WHERE id = ?",
            (rotasi_sensor, measurement_id),
        )
        row = connection.execute(
            "SELECT * FROM measurements WHERE id = ?", (measurement_id,)
        ).fetchone()
    return dict(row) if row else None


def update_rotasi_buah(measurement_id: int, rotasi_buah: str) -> dict[str, Any] | None:
    """Simpan orientasi rotasi BUAH saat pemindaian (A/B/C/D, atau '' jika kosong)."""
    with database_connection() as connection:
        connection.execute(
            "UPDATE measurements SET rotasi_buah = ? WHERE id = ?",
            (rotasi_buah, measurement_id),
        )
        row = connection.execute(
            "SELECT * FROM measurements WHERE id = ?", (measurement_id,)
        ).fetchone()
    return dict(row) if row else None


def update_jarak(measurement_id: int, jarak_cm: float | None) -> dict[str, Any] | None:
    """Simpan jarak sensor ke jambu (cm) yang diukur manual oleh operator.

    jarak_cm boleh None -- artinya belum diukur/dikosongkan kembali.
    """
    with database_connection() as connection:
        connection.execute(
            "UPDATE measurements SET jarak_cm = ? WHERE id = ?",
            (jarak_cm, measurement_id),
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
            "SELECT * FROM measurements WHERE prediction != ? ORDER BY id ASC", (FAILED_SCAN,)
        ).fetchall()
    return [dict(row) for row in rows]


# ---------------------------------------------------------------------------
# Layanan Multi-Peran & Agregasi Analitik (Operator, Supervisor, Owner)
# ---------------------------------------------------------------------------

def hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    if salt is None:
        salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
    return salt.hex(), dk.hex()


def verify_password(password: str, salt_hex: str, hash_hex: str) -> bool:
    try:
        salt = bytes.fromhex(salt_hex)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
        return secrets.compare_digest(dk.hex(), hash_hex)
    except Exception:
        return False


def get_user_by_username(username: str) -> dict[str, Any] | None:
    with database_connection() as connection:
        row = connection.execute(
            """SELECT id, username, name, password, password_hash, salt, role, is_active, last_login, created_at
               FROM users WHERE username = ?""",
            (username.strip().lower(),),
        ).fetchone()
    return dict(row) if row else None


def authenticate_user(username: str, password: str) -> tuple[dict[str, Any] | None, str | None]:
    clean_user = username.strip().lower()
    clean_pass = password.strip()
    if not clean_user or not clean_pass:
        return None, "Nama pengguna dan kata sandi wajib diisi"

    user = get_user_by_username(clean_user)
    if not user:
        return None, "Nama pengguna atau kata sandi tidak cocok"

    if not user.get("is_active", 1):
        return None, "Akun telah dinonaktifkan. Silakan hubungi Pemilik/Owner."

    # Periksa hash PBKDF2
    valid = False
    if user.get("password_hash") and user.get("salt"):
        valid = verify_password(clean_pass, user["salt"], user["password_hash"])
    elif user.get("password"):
        # Fallback migrasi jika password polos masih ada
        valid = (user["password"] == clean_pass)
        if valid:
            salt_hex, hash_hex = hash_password(clean_pass)
            with database_connection() as connection:
                connection.execute(
                    "UPDATE users SET password_hash = ?, salt = ?, password = '' WHERE id = ?",
                    (hash_hex, salt_hex, user["id"]),
                )

    if not valid:
        return None, "Nama pengguna atau kata sandi tidak cocok"

    now_iso = datetime.now().isoformat()
    with database_connection() as connection:
        connection.execute("UPDATE users SET last_login = ? WHERE id = ?", (now_iso, user["id"]))

    return {
        "id": user["id"],
        "username": user["username"],
        "name": user["name"],
        "role": user["role"],
        "last_login": now_iso,
    }, None


def create_session_token(user_id: str, role: str, hours: int = 24) -> str:
    token = secrets.token_hex(32)
    created_at = datetime.now().isoformat()
    expires_at = (datetime.now() + timedelta(hours=hours)).isoformat()
    with database_connection() as connection:
        connection.execute(
            "INSERT INTO auth_tokens (token, user_id, role, expires_at, created_at) VALUES (?, ?, ?, ?, ?)",
            (token, user_id, role, expires_at, created_at),
        )
    return token


def validate_session_token(token: str) -> dict[str, Any] | None:
    if not token or not isinstance(token, str):
        return None
    clean_token = token.strip()
    now_iso = datetime.now().isoformat()
    with database_connection() as connection:
        row = connection.execute(
            """
            SELECT t.token, t.role, t.expires_at, u.id, u.username, u.name, u.is_active
            FROM auth_tokens t
            JOIN users u ON t.user_id = u.id
            WHERE t.token = ? AND t.expires_at > ? AND u.is_active = 1
            """,
            (clean_token, now_iso),
        ).fetchone()
    return dict(row) if row else None


def revoke_session_token(token: str) -> bool:
    if not token:
        return False
    with database_connection() as connection:
        cursor = connection.execute("DELETE FROM auth_tokens WHERE token = ?", (token.strip(),))
    return cursor.rowcount > 0


def create_user(username: str, name: str, password: str, role: str) -> tuple[dict[str, Any] | None, str | None]:
    clean_u = username.strip().lower()
    clean_n = name.strip()
    clean_p = password.strip()
    clean_r = role.strip().lower()

    if not clean_u or len(clean_u) < 3:
        return None, "Nama pengguna minimal 3 karakter"
    if not clean_n:
        return None, "Nama lengkap wajib diisi"
    if len(clean_p) < 6:
        return None, "Kata sandi minimal 6 karakter"
    if clean_r not in ("operator", "supervisor", "owner"):
        return None, "Peran harus operator, supervisor, atau owner"

    salt_hex, hash_hex = hash_password(clean_p)
    new_id = f"u-{clean_r[:2]}-{secrets.token_hex(4)}"
    now_iso = datetime.now().isoformat()

    try:
        with database_connection() as connection:
            connection.execute(
                """
                INSERT INTO users (id, username, name, password, password_hash, salt, role, is_active, last_login, created_at)
                VALUES (?, ?, ?, '', ?, ?, ?, 1, '', ?)
                """,
                (new_id, clean_u, clean_n, hash_hex, salt_hex, clean_r, now_iso),
            )
        return {
            "id": new_id,
            "username": clean_u,
            "name": clean_n,
            "role": clean_r,
            "is_active": 1,
            "created_at": now_iso,
        }, None
    except sqlite3.IntegrityError:
        return None, f"Nama pengguna '{clean_u}' sudah digunakan"


def update_user_password(user_id: str, new_password: str) -> tuple[bool, str | None]:
    clean_p = new_password.strip()
    if len(clean_p) < 6:
        return False, "Kata sandi baru minimal 6 karakter"

    salt_hex, hash_hex = hash_password(clean_p)
    with database_connection() as connection:
        cursor = connection.execute(
            "UPDATE users SET password_hash = ?, salt = ?, password = '' WHERE id = ?",
            (hash_hex, salt_hex, user_id),
        )
        connection.execute("DELETE FROM auth_tokens WHERE user_id = ?", (user_id,))
    if cursor.rowcount == 0:
        return False, "Pengguna tidak ditemukan"
    return True, None


def delete_user(user_id: str) -> bool:
    with database_connection() as connection:
        cursor = connection.execute(
            "UPDATE users SET is_active = 0 WHERE id = ?",
            (user_id,),
        )
        connection.execute("DELETE FROM auth_tokens WHERE user_id = ?", (user_id,))
    return cursor.rowcount > 0


def list_users() -> list[dict[str, Any]]:
    with database_connection() as connection:
        rows = connection.execute(
            "SELECT id, username, name, role, is_active, last_login, created_at FROM users WHERE is_active = 1 ORDER BY id ASC"
        ).fetchall()
    return [dict(row) for row in rows]


def list_devices() -> list[dict[str, Any]]:
    with database_connection() as connection:
        rows = connection.execute(
            "SELECT id, name, location, status, last_seen, total_scans, firmware_version, install_date FROM devices ORDER BY id ASC"
        ).fetchall()
    return [dict(row) for row in rows]


def next_daily_seq(prefix: str) -> int:
    """Nomor urut berikutnya untuk ID buah otomatis <prefix>-YYYYMMDD-NNNN hari ini."""
    like = f"{prefix}-{datetime.now():%Y%m%d}-%"
    with database_connection() as connection:
        last = connection.execute(
            "SELECT MAX(CAST(SUBSTR(fruit_id, -4) AS INTEGER)) FROM measurements WHERE fruit_id LIKE ?", (like,)
        ).fetchone()[0]
    return (last or 0) + 1


def set_device_name(device_id: str, name: str) -> bool:
    with database_connection() as connection:
        cursor = connection.execute("UPDATE devices SET name = ? WHERE id = ?", (name, device_id))
    return cursor.rowcount > 0


def update_device_status(device_id: str, status: str) -> bool:
    with database_connection() as connection:
        cursor = connection.execute(
            "UPDATE devices SET status = ?, last_seen = ? WHERE id = ?",
            (status, datetime.now().isoformat(), device_id),
        )
    return cursor.rowcount > 0


def list_petani() -> list[dict[str, Any]]:
    with database_connection() as connection:
        rows = connection.execute(
            "SELECT id, name, village, phone, joined FROM petani_mitra ORDER BY joined DESC, id DESC"
        ).fetchall()
    return [dict(row) for row in rows]


def add_petani(name: str, village: str, phone: str) -> dict[str, Any]:
    new_id = f"p{datetime.now().strftime('%y%m%d%H%M%S')}"
    joined = datetime.now().strftime("%Y-%m-%d")
    with database_connection() as connection:
        connection.execute(
            "INSERT INTO petani_mitra (id, name, village, phone, joined) VALUES (?, ?, ?, ?, ?)",
            (new_id, name.strip(), village.strip() or "—", phone.strip() or "—", joined),
        )
    return {"id": new_id, "name": name.strip(), "village": village.strip(), "phone": phone.strip(), "joined": joined}


def delete_petani(petani_id: str) -> bool:
    with database_connection() as connection:
        cursor = connection.execute("DELETE FROM petani_mitra WHERE id = ?", (petani_id,))
    return cursor.rowcount > 0


def get_analytics_summary() -> dict[str, Any]:
    """Agregasi metrik untuk dashboard eksekutif dan supervisor."""
    with database_connection() as connection:
        verdict = "COALESCE(NULLIF(prediction, ''), UPPER(label))"
        total_scans = connection.execute("SELECT COUNT(*) FROM measurements").fetchone()[0] or 0
        normal_scans = connection.execute(
            f"SELECT COUNT(*) FROM measurements WHERE {verdict} = 'NORMAL'"
        ).fetchone()[0] or 0
        anomali_scans = connection.execute(
            f"SELECT COUNT(*) FROM measurements WHERE {verdict} = 'ANOMALI'"
        ).fetchone()[0] or 0

        # Pass rate hanya dari baris yang sudah punya putusan; baris akuisisi dataset tanpa label tidak dihitung
        classified = normal_scans + anomali_scans
        pass_rate = round((normal_scans / classified * 100), 1) if classified > 0 else 0.0

        # Ringkasan per device
        device_rows = connection.execute(
            """
            SELECT d.id, d.name, d.status, COUNT(m.id) as total_scans,
                   SUM(CASE WHEN COALESCE(NULLIF(m.prediction, ''), UPPER(m.label)) = 'NORMAL' THEN 1 ELSE 0 END) as normal_scans
            FROM devices d
            LEFT JOIN measurements m ON d.id = m.device_id
            GROUP BY d.id
            """
        ).fetchall()
        by_device = [
            {
                "id": r["id"],
                "name": r["name"],
                "status": r["status"],
                "total_scans": r["total_scans"] or 0,
                "pass_rate": round(((r["normal_scans"] or 0) / max(r["total_scans"] or 1, 1)) * 100, 1),
            }
            for r in device_rows
        ]

        # 14 hari terakhir
        daily_rows = connection.execute(
            """
            SELECT SUBSTR(timestamp, 1, 10) as day,
                   COUNT(*) as total,
                   SUM(CASE WHEN COALESCE(NULLIF(prediction, ''), UPPER(label)) = 'NORMAL' THEN 1 ELSE 0 END) as normal,
                   SUM(CASE WHEN COALESCE(NULLIF(prediction, ''), UPPER(label)) = 'ANOMALI' THEN 1 ELSE 0 END) as anomali
            FROM measurements
            GROUP BY day
            ORDER BY day DESC
            LIMIT 14
            """
        ).fetchall()
        daily = [
            {
                "day": r["day"],
                "NORMAL": r["normal"] or 0,
                "ANOMALI": r["anomali"] or 0,
                "total": r["total"] or 0,
            }
            for r in reversed(daily_rows)
        ]

    return {
        "total_scans": total_scans,
        "normal_scans": normal_scans,
        "anomali_scans": anomali_scans,
        "pass_rate": pass_rate,
        "by_device": by_device,
        "daily": daily,
    }

