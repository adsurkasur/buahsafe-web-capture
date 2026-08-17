from __future__ import annotations

import collections
import datetime
import logging
import math
import threading
import time
import traceback
from typing import Any

import serial
from serial.tools import list_ports

WAVELENGTHS: tuple[int, ...] = (
    410,
    435,
    460,
    485,
    510,
    535,
    560,
    585,
    610,
    645,
    680,
    705,
    730,
    760,
    810,
    860,
    900,
    940,
)

CHANNEL_KEYS: tuple[str, ...] = tuple(f"nm{w}" for w in WAVELENGTHS)

logger = logging.getLogger("buahsafe.serial")


class DebugLogManager:
    """In-memory circular buffer for rich server-side debugging logs."""

    def __init__(self, maxlen: int = 300) -> None:
        self._logs: collections.deque[dict[str, Any]] = collections.deque(maxlen=maxlen)
        self._lock = threading.Lock()
        self.last_raw_line: str = ""

    def add(
        self,
        level: str,
        category: str,
        message: str,
        raw_data: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        entry = {
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
            "level": level.upper(),
            "category": category.upper(),
            "message": message,
            "raw_data": raw_data,
            "extra": extra or {},
        }
        with self._lock:
            self._logs.append(entry)
            if raw_data:
                self.last_raw_line = raw_data

        # Also print to standard python logger
        log_msg = f"[{entry['category']}] {message}"
        if raw_data:
            log_msg += f" | RAW: {raw_data[:200]}{'...' if len(raw_data) > 200 else ''}"
        if level.upper() == "ERROR":
            logger.error(log_msg)
        elif level.upper() == "WARN":
            logger.warning(log_msg)
        elif level.upper() == "DEBUG":
            logger.debug(log_msg)
        else:
            logger.info(log_msg)

    def get_logs(self, limit: int = 150) -> list[dict[str, Any]]:
        with self._lock:
            entries = list(self._logs)
        return entries[-limit:]

    def clear(self) -> None:
        with self._lock:
            self._logs.clear()


debug_logger = DebugLogManager()


class DeviceError(RuntimeError):
    def __init__(
        self,
        message: str,
        raw_line: str | None = None,
        field_count: int | None = None,
        expected_count: int | None = None,
        fields_preview: list[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.raw_line = raw_line
        self.field_count = field_count
        self.expected_count = expected_count
        self.fields_preview = fields_preview or []

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"message": self.message}
        if self.raw_line is not None:
            data["raw_line"] = self.raw_line
            data["line_length"] = len(self.raw_line)
        if self.field_count is not None:
            data["field_count"] = self.field_count
        if self.expected_count is not None:
            data["expected_count"] = self.expected_count
        if self.fields_preview:
            data["fields_preview"] = self.fields_preview[:30]
        return data


def parse_data_line(line: str, *, silent: bool = False) -> dict[str, float | int]:
    """Parse and validate a DATA response line from AS7265x firmware.

    Expected format:
      DATA,<scan_no>,<410>,<435>,<460>,<485>,<510>,<535>,
      <560>,<585>,<610>,<645>,<680>,<705>,
      <730>,<760>,<810>,<860>,<900>,<940>
    Total fields: 20 (1 prefix + 1 scan_no + 18 spectral values)

    silent: bila True, jangan tulis entry ke debug_logger. Dipakai saat fungsi
    ini dipanggil secara spekulatif (mis. mencoba memulihkan data dari baris
    terakhir setelah timeout) sehingga percobaan yang gagal tidak membanjiri
    log dengan ERROR palsu.
    """

    def log(level: str, message: str, **kwargs: Any) -> None:
        if not silent:
            debug_logger.add(level, "PARSER", message, **kwargs)

    raw_line = line.strip()
    log("DEBUG", f"Memulai parsing baris ({len(raw_line)} karakter)", raw_data=raw_line)

    # UART noise (sering muncul akibat gangguan elektris seperti relay yang
    # berisik) kadang menyisipkan 1-2 byte sampah di awal baris sebelum
    # "DATA,". Selama penanda "DATA," masih utuh di suatu tempat di awal
    # baris, potong bagian sebelumnya alih-alih langsung menolak baris ini.
    clean_line = raw_line
    if not clean_line.startswith("DATA,"):
        marker_index = clean_line.find("DATA,")
        if 0 < marker_index <= 4:
            noise = clean_line[:marker_index]
            clean_line = clean_line[marker_index:]
            log(
                "WARN",
                f"Baris data diawali {marker_index} byte noise ('{noise}') -- dipotong sebelum parsing",
                raw_data=raw_line,
            )

    if not clean_line.startswith("DATA,"):
        err = DeviceError(
            f"Format baris data tidak valid (harus diawali DATA,): {raw_line}",
            raw_line=raw_line,
        )
        log("ERROR", f"Prefix salah: {raw_line[:30]}", raw_data=raw_line)
        raise err

    fields = clean_line.split(",")
    expected_field_count = 2 + len(WAVELENGTHS)  # 1 prefix + 1 scan_no + 18 values = 20

    if len(fields) != expected_field_count:
        err = DeviceError(
            f"Format data tidak valid (diharapkan {expected_field_count} kolom, diterima {len(fields)}): {raw_line}",
            raw_line=raw_line,
            field_count=len(fields),
            expected_count=expected_field_count,
            fields_preview=fields,
        )
        log(
            "ERROR",
            f"Jumlah kolom tidak sesuai: diharapkan {expected_field_count}, diterima {len(fields)}",
            raw_data=raw_line,
            extra={"field_count": len(fields), "expected": expected_field_count},
        )
        raise err

    try:
        scan_no = int(fields[1])
        if scan_no < 0:
            raise ValueError("Nomor scan tidak boleh negatif")
    except ValueError as error:
        err = DeviceError(
            f"Nomor scan tidak valid ({fields[1]}): {error}",
            raw_line=raw_line,
            field_count=len(fields),
            expected_count=expected_field_count,
        )
        log("ERROR", f"Nomor scan tidak valid: {fields[1]}", raw_data=raw_line)
        raise err from error

    spectral_values: list[float] = []
    for index, (wavelength, field_str) in enumerate(zip(WAVELENGTHS, fields[2:]), start=2):
        try:
            val = float(field_str)
            if not math.isfinite(val):
                raise ValueError("Nilai bukan angka berhingga")
            spectral_values.append(val)
        except ValueError as error:
            err = DeviceError(
                f"Nilai spektral pada {wavelength} nm (kolom ke-{index + 1}) tidak valid ({field_str}): {error}",
                raw_line=raw_line,
                field_count=len(fields),
                expected_count=expected_field_count,
            )
            log("ERROR", f"Nilai spektral {wavelength}nm salah: '{field_str}'", raw_data=raw_line)
            raise err from error

    result: dict[str, float | int] = {"scan_no": scan_no}
    for key, val in zip(CHANNEL_KEYS, spectral_values):
        result[key] = val

    log(
        "INFO",
        f"Parsing sukses: Scan #{scan_no} (18 kanal: {spectral_values[0]:.2f}..{spectral_values[-1]:.2f})",
        raw_data=raw_line,
    )
    return result


class BuahSafeDevice:
    def __init__(self) -> None:
        self._serial: serial.Serial | None = None
        self._lock = threading.RLock()
        self.port: str | None = None
        self.last_error: str | None = None
        self.last_raw_message: str | None = None

    @staticmethod
    def available_ports() -> list[dict[str, str]]:
        ports = [
            {"device": item.device, "description": item.description}
            for item in list_ports.comports()
        ]
        debug_logger.add("DEBUG", "DEVICE", f"Deteksi port COM: {len(ports)} port ditemukan", extra={"ports": ports})
        return ports

    @property
    def connected(self) -> bool:
        return bool(self._serial and self._serial.is_open)

    def status(self) -> dict[str, Any]:
        return {
            "connected": self.connected,
            "port": self.port,
            "last_error": self.last_error,
            "last_raw_message": self.last_raw_message,
        }

    def connect(self, port: str) -> None:
        with self._lock:
            debug_logger.add("INFO", "DEVICE", f"Mencoba menghubungkan port {port} @ 115200 baud...")
            self.disconnect()
            try:
                connection = serial.Serial(
                    port=port,
                    baudrate=115200,
                    timeout=0.5,
                    write_timeout=1.0,
                )
                self._serial = connection
                self.port = port
                self.last_error = None
                self.last_raw_message = None

                debug_logger.add("INFO", "DEVICE", f"Port {port} terbuka. Menunggu reset ESP32 (2.0 detik)...")
                time.sleep(2.0)
                connection.reset_input_buffer()

                debug_logger.add("INFO", "SERIAL_TX", "Mengirim perintah PING\\n...")
                connection.write(b"PING\n")
                connection.flush()

                ack = self._wait_for("ACK,PONG", timeout=8.0)
                debug_logger.add("INFO", "DEVICE", f"Handshake sukses: {ack}")
            except (serial.SerialException, OSError, DeviceError) as error:
                message = self._friendly_connection_error(port, error)
                self.last_error = message
                debug_logger.add("ERROR", "DEVICE", f"Gagal koneksi {port}: {message}", extra={"traceback": traceback.format_exc()})
                self.disconnect(keep_error=True)
                raise DeviceError(message) from error

    def disconnect(self, keep_error: bool = False) -> None:
        with self._lock:
            if self._serial:
                try:
                    debug_logger.add("INFO", "DEVICE", f"Menutup port {self.port or 'serial'}...")
                    self._serial.close()
                except serial.SerialException as ex:
                    debug_logger.add("WARN", "DEVICE", f"Error saat menutup port: {ex}")
            self._serial = None
            self.port = None
            if not keep_error:
                self.last_error = None
                self.last_raw_message = None

    def scan(self) -> dict[str, float | int]:
        with self._lock:
            if not self.connected or self._serial is None:
                err_msg = "ESP32 belum terhubung"
                debug_logger.add("ERROR", "DEVICE", err_msg)
                raise DeviceError(err_msg)

            # Sesekali satu byte di tengah baris data rusak akibat noise
            # elektris sesaat (mis. dari relay) -- ini BUKAN masalah sensor,
            # cuma transmisi kali ini yang cacat. Daripada langsung
            # menyerahkan error mentah ke operator, coba ulang otomatis satu
            # kali sebelum benar-benar menyerah.
            max_attempts = 2
            last_error: DeviceError | None = None
            for attempt in range(1, max_attempts + 1):
                if not self.connected or self._serial is None:
                    # Koneksi putus total di tengah retry (mis. SerialException) --
                    # tidak ada gunanya coba lagi.
                    break
                try:
                    return self._perform_scan_attempt()
                except DeviceError as error:
                    last_error = error
                    if attempt < max_attempts:
                        debug_logger.add(
                            "WARN",
                            "SCAN",
                            f"Percobaan scan ke-{attempt}/{max_attempts} gagal ({error}) -- "
                            "kemungkinan noise transmisi sesaat, mencoba ulang otomatis...",
                            raw_data=error.raw_line,
                        )
                        time.sleep(0.3)
                        continue

            assert last_error is not None
            raise last_error

    def _perform_scan_attempt(self) -> dict[str, float | int]:
        assert self._serial is not None
        try:
            debug_logger.add("INFO", "DEVICE", "Memulai proses scan: membersihkan buffer input...")
            self._serial.reset_input_buffer()

            debug_logger.add("INFO", "SERIAL_TX", "Mengirim perintah SCAN\\n...")
            self._serial.write(b"SCAN\n")
            self._serial.flush()

            line = self._wait_for("DATA,", timeout=18.0, prefix=True)
            self.last_raw_message = line
            result = parse_data_line(line)
            # Scan bersih (langsung sukses, tanpa perlu recovery) -- pastikan
            # status error dari attempt/scan sebelumnya tidak "nyangkut".
            self.last_error = None
            return result
        except DeviceError as error:
            # Timeout/error kadang terjadi justru SETELAH baris DATA yang
            # lengkap & valid sempat terbaca -- misalnya jitter di batas akhir
            # timeout, atau noise sesaat di serial. _wait_for() sudah mencatat
            # baris terakhir yang diterima (error.raw_line) meski akhirnya
            # gagal cocok dengan pola yang diharapkan tepat waktu. Sebelum
            # dianggap gagal total dan membuang data yang sebenarnya sudah
            # sah, coba parse ulang baris tsb secara diam-diam. Kalau valid,
            # anggap scan ini SUKSES (ditandai sebagai recovery) -- jangan
            # buang data asli hanya karena masalah timing.
            # PENTING: hanya pakai error.raw_line (data dari attempt yang BARU
            # SAJA gagal ini). JANGAN fallback ke self.last_raw_message --
            # field itu adalah sisa dari scan SUKSES sebelumnya, dan kalau
            # dipakai di sini, timeout asli (ESP32 benar-benar tidak
            # merespons) akan disamarkan jadi "sukses" dengan data LAMA yang
            # didaur ulang -- menghasilkan record duplikat palsu di database
            # meski scan yang sebenarnya gagal total.
            candidate = error.raw_line
            recovered: dict[str, float | int] | None = None
            if candidate:
                try:
                    recovered = parse_data_line(candidate, silent=True)
                except DeviceError:
                    recovered = None

            if recovered is not None:
                self.last_raw_message = candidate
                self.last_error = None
                debug_logger.add(
                    "WARN",
                    "SCAN",
                    "Scan awalnya gagal/timeout, tapi baris data terakhir valid -- "
                    "dipulihkan sebagai SUKSES (marginal timing). Jika ini sering "
                    "terjadi, periksa kestabilan relay/koneksi serial.",
                    raw_data=candidate,
                )
                return recovered

            self.last_error = str(error)
            if error.raw_line:
                self.last_raw_message = error.raw_line
            debug_logger.add("ERROR", "SCAN", f"Scan gagal: {error}", raw_data=self.last_raw_message)
            raise
        except (ValueError, serial.SerialException, OSError) as error:
            self.last_error = str(error)
            debug_logger.add("ERROR", "SCAN", f"Scan gagal: {error}", raw_data=self.last_raw_message)
            self.disconnect(keep_error=True)
            raise DeviceError(f"Scan gagal: {error}") from error

    def _read_complete_line(
        self,
        deadline: float,
        grace_seconds: float = 2.0,
        max_grace_seconds: float = 5.0,
    ) -> str | None:
        """Read bytes until newline (\\n) from serial before deadline.

        Bytes for a line can start arriving right as the nominal deadline
        hits (warm-up + measurement timing has some natural jitter). Cutting
        it off mid-transmission would discard a scan result that was
        actually about to complete successfully. So once we've seen at
        least one non-empty chunk (a line is actively in flight), extend the
        effective deadline by a short grace window -- bounded overall by
        max_grace_seconds so a genuinely dead connection still times out.
        """
        if self._serial is None:
            return None

        buffer = bytearray()
        effective_deadline = deadline
        hard_cap = deadline + max_grace_seconds

        while time.monotonic() < effective_deadline:
            chunk = self._serial.read_until(b"\n")
            if chunk:
                buffer.extend(chunk)
                if buffer.endswith(b"\n"):
                    decoded = buffer.decode("utf-8", errors="replace").strip()
                    debug_logger.add("DEBUG", "SERIAL_RX", f"Diterima: '{decoded}' ({len(decoded)} chars)", raw_data=decoded)
                    return decoded

                # Baris belum lengkap tapi sudah mulai masuk -- beri sedikit
                # tambahan waktu supaya tidak terpotong di tengah jalan.
                extended = min(time.monotonic() + grace_seconds, hard_cap)
                if extended > effective_deadline:
                    effective_deadline = extended
            time.sleep(0.01)
        return None

    def _wait_for(self, expected: str, timeout: float, prefix: bool = False) -> str:
        if self._serial is None:
            raise DeviceError("Port serial tidak tersedia")

        deadline = time.monotonic() + timeout
        last_message = ""
        debug_logger.add("DEBUG", "DEVICE", f"Menunggu pola serial '{expected}' (timeout {timeout}s)...")

        while time.monotonic() < deadline:
            line = self._read_complete_line(deadline)
            if line is None:
                continue
            if not line:
                continue
            last_message = line
            if line.startswith("FATAL,") or line.startswith("ERROR,"):
                debug_logger.add("ERROR", "DEVICE", f"Firmware mengembalikan error: {line}", raw_data=line)
                raise DeviceError(line, raw_line=line)
            if (prefix and line.startswith(expected)) or (not prefix and line == expected):
                debug_logger.add("INFO", "DEVICE", f"Pola '{expected}' cocok dengan baris: {line[:50]}...", raw_data=line)
                return line

        detail = f" Pesan terakhir: {last_message}" if last_message else ""
        err_msg = f"ESP32 tidak merespons sebelum timeout.{detail}"
        debug_logger.add("ERROR", "DEVICE", err_msg, raw_data=last_message)
        raise DeviceError(err_msg, raw_line=last_message)

    @staticmethod
    def _friendly_connection_error(port: str, error: Exception) -> str:
        detail = str(error)
        if "access is denied" in detail.lower() or "permissionerror" in detail.lower():
            return (
                f"{port} sedang digunakan aplikasi lain. Tutup Arduino Serial "
                "Monitor/Serial Plotter dan jendela BuahSafe lain, lalu coba lagi."
            )
        return f"Gagal menghubungkan ESP32 di {port}: {detail}"
