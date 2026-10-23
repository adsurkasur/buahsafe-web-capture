"""Transport perangkat lewat WiFi: ESP32 di lokasi mitra, server di tempat lain.

ESP32 tidak bisa dihubungi dari server (ada di balik NAT jaringan mitra), jadi
arahnya dibalik: ESP32 yang terus bertanya ke server (long-poll HTTPS).

  1. Operator menekan scan  -> app memanggil WifiDevice.scan() dan menunggu.
  2. ESP32 GET /api/device/poll  -> menerima {"command": "SCAN", "job": ...}.
  3. ESP32 memindai, POST /api/device/result berisi baris DATA yang sama persis
     dengan protokol serial -> scan() kembali dengan bacaan tervalidasi.
  4. Setelah record tersimpan, notify_saved(n) menjawab POST tadi dengan scan_no
     sah dari database (setara "SAVED,<n>" pada protokol serial) untuk LCD.

Antarmuka publiknya sama dengan BuahSafeDevice sehingga app.py tidak perlu
membedakan jalur USB dan WiFi. State ada di memori proses: jalankan server
dengan SATU worker (thread boleh banyak).
"""
from __future__ import annotations

import threading
import time
import uuid
from datetime import datetime
from typing import Any

from serial_device import DeviceError, debug_logger, parse_data_line

# Long-poll ESP32 memakan <= POLL_WAIT_S, lalu langsung bertanya lagi; perangkat
# dianggap offline kalau tidak bertanya selama ini.
POLL_WAIT_S = 10.0
OFFLINE_AFTER_S = POLL_WAIT_S + 15.0
# Firmware: warm-up lampu 3 s + pengukuran ~1-2 s + jeda poll + latensi jaringan
SCAN_TIMEOUT_S = 15.0
SAVE_ACK_WAIT_S = 4.0


class WifiDevice:
    def __init__(self, device_id: str = "BSF-001") -> None:
        self.device_id = device_id
        self.port = "wifi"
        self.last_error: str | None = None
        self.last_raw_message: str | None = None
        self._cond = threading.Condition()
        self._scan_lock = threading.Lock()  # satu meja = satu scan pada satu waktu
        self._last_seen = 0.0
        self._info: dict[str, Any] = {}
        self._job: str | None = None
        self._job_taken = False
        self._result: dict[str, Any] | None = None
        self._saved: dict[str, int | None] = {}

    # ---------- antarmuka yang dipakai app.py ----------

    @property
    def connected(self) -> bool:
        return time.monotonic() - self._last_seen < OFFLINE_AFTER_S if self._last_seen else False

    def status(self) -> dict[str, Any]:
        age = time.monotonic() - self._last_seen if self._last_seen else None
        return {
            "connected": self.connected,
            "port": self.port,
            "mode": "wifi",
            "device_id": self.device_id,
            "seconds_since_seen": round(age, 1) if age is not None else None,
            "last_error": self.last_error,
            "last_raw_message": self.last_raw_message,
            **self._info,
        }

    @staticmethod
    def available_ports() -> list[dict[str, str]]:
        return []

    def connect(self, port: str) -> None:
        raise DeviceError("Mode WiFi: ESP32 tersambung sendiri ke server, tidak perlu memilih port.")

    def disconnect(self, keep_error: bool = False) -> None:
        return None

    def scan(self) -> dict[str, float | int]:
        if not self._scan_lock.acquire(timeout=SCAN_TIMEOUT_S):
            raise DeviceError("Pemindai masih memproses buah sebelumnya. Tunggu sebentar lalu ulangi.")
        try:
            if not self.connected:
                raise DeviceError(
                    "Alat pemindai di meja sortasi tidak terhubung ke server. "
                    "Periksa listrik dan WiFi alat, lalu tunggu layar LCD menampilkan 'Siap'."
                )
            job = uuid.uuid4().hex[:12]
            with self._cond:
                self._job, self._result, self._job_taken = job, None, False
                self._cond.notify_all()  # bangunkan long-poll yang sedang menunggu
                ok = self._cond.wait_for(lambda: self._result is not None, timeout=SCAN_TIMEOUT_S)
                result, self._job, self._result = self._result, None, None
            if not ok or result is None:
                self.last_error = "Alat tidak mengirim hasil scan tepat waktu"
                raise DeviceError(self.last_error + ". Ulangi pemindaian.")
            if result.get("error"):
                self.last_error = f"Alat melaporkan galat: {result['error']}"
                raise DeviceError(self.last_error)
            self.last_error = None
            self._saved[job] = None
            return result["reading"]
        finally:
            self._scan_lock.release()

    def notify_saved(self, scan_no: int, job: str | None = None) -> None:
        with self._cond:
            for key in ([job] if job else list(self._saved)):
                if key in self._saved and self._saved[key] is None:
                    self._saved[key] = scan_no
            self._cond.notify_all()

    # ---------- dipanggil endpoint /api/device/* ----------

    def poll(self, info: dict[str, Any]) -> dict[str, Any] | None:
        """Long-poll dari ESP32. Kembalikan perintah atau None bila tidak ada."""
        self._last_seen = time.monotonic()
        self._info = {"firmware": info.get("fw"), "rssi": info.get("rssi"), "ip": info.get("ip"),
                      "last_poll": datetime.now().isoformat(timespec="seconds")}
        with self._cond:
            self._cond.wait_for(lambda: self._job is not None and not self._job_taken, timeout=POLL_WAIT_S)
            self._last_seen = time.monotonic()
            if self._job is None or self._job_taken:
                return None
            self._job_taken = True  # poll ulang tidak boleh memicu scan ganda
            return {"command": "SCAN", "job": self._job}

    def submit(self, job: str, line: str | None, error: str | None) -> tuple[bool, int | None]:
        """Terima hasil scan; tunggu sebentar scan_no dari database untuk LCD."""
        self._last_seen = time.monotonic()
        with self._cond:
            if job != self._job:
                return False, None  # job kedaluwarsa (operator sudah menerima timeout)
            if error:
                self._result = {"error": error[:80]}
            else:
                self.last_raw_message = line
                try:
                    self._result = {"reading": parse_data_line(line or "")}
                except DeviceError as err:
                    self._result = {"error": str(err)}
            self._cond.notify_all()
            if "error" in self._result:
                return True, None
            self._cond.wait_for(lambda: self._saved.get(job) is not None, timeout=SAVE_ACK_WAIT_S)
            return True, self._saved.pop(job, None)


if __name__ == "__main__":
    # Swa-uji alur lengkap tanpa ESP32: poll -> scan -> submit -> ack
    dev = WifiDevice()
    line = "DATA,1," + ",".join(["1.5"] * 18)
    out: dict[str, Any] = {}

    def fake_esp32():
        cmd = dev.poll({"fw": "test"})
        out["cmd"] = cmd
        out["ack"] = dev.submit(cmd["job"], line, None)

    assert not dev.connected
    dev._last_seen = time.monotonic()
    t = threading.Thread(target=fake_esp32)
    t.start()
    time.sleep(0.1)
    reading = dev.scan()
    assert reading["nm940"] == 1.5 and out["cmd"]["command"] == "SCAN"
    dev.notify_saved(42)
    t.join(5)
    assert out["ack"] == (True, 42), out
    print("wifi_device self-check OK")
