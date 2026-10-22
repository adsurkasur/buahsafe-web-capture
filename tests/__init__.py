"""BuahSafe test suite."""
# Arahkan ke DB sementara SEBELUM import database/app: suite ini tidak boleh
# menulis ke data/buahsafe.db (dataset pengukuran nyata).
import os
import tempfile
os.environ.setdefault("BUAHSAFE_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="buahsafe-test-"), "test.db"))
