"""Cadangan harian database BuahSafe (dijalankan buahsafe-backup.timer).

Memakai sqlite3 Connection.backup(): salinan konsisten walau server sedang menulis.
Salinan lebih tua dari KEEP_DAYS dihapus. Setelah disalin, salinan dibuka dan
dicek `PRAGMA integrity_check` supaya backup rusak langsung ketahuan di journal.
"""
import os
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

SOURCE = Path(os.environ.get("BUAHSAFE_DB_PATH", "/srv/hdd1/buahsafe/data/buahsafe.db"))
TARGET_DIR = Path(os.environ.get("BUAHSAFE_BACKUP_DIR", "/srv/hdd1/backups/buahsafe"))
KEEP_DAYS = int(os.environ.get("BUAHSAFE_BACKUP_KEEP_DAYS", "14"))


def main() -> int:
    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    target = TARGET_DIR / f"buahsafe-{datetime.now():%Y%m%d}.db"
    with sqlite3.connect(f"file:{SOURCE}?mode=ro", uri=True) as src, sqlite3.connect(target) as dst:
        src.backup(dst)
    with sqlite3.connect(target) as check:
        status = check.execute("PRAGMA integrity_check").fetchone()[0]
        rows = check.execute("SELECT COUNT(*) FROM measurements").fetchone()[0]
    if status != "ok":
        print(f"BACKUP RUSAK {target}: {status}", file=sys.stderr)
        return 1

    cutoff = time.time() - KEEP_DAYS * 86400
    removed = [p.name for p in TARGET_DIR.glob("buahsafe-*.db") if p.stat().st_mtime < cutoff]
    for name in removed:
        (TARGET_DIR / name).unlink()
    print(f"Backup OK {target} ({target.stat().st_size // 1024} KB, {rows} pengukuran); dihapus: {removed or '-'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
