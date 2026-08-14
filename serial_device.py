from __future__ import annotations

import math
import threading
import time
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


class DeviceError(RuntimeError):
    pass


def parse_data_line(line: str) -> dict[str, float | int]:
    """Parse and validate a DATA response line from AS7265x firmware.

    Expected format:
      DATA,<scan_no>,<410>,<435>,<460>,<485>,<510>,<535>,
      <560>,<585>,<610>,<645>,<680>,<705>,
      <730>,<760>,<810>,<860>,<900>,<940>
    Total fields: 20 (1 prefix + 1 scan_no + 18 spectral values)
    """
    clean_line = line.strip()
    if not clean_line.startswith("DATA,"):
        raise DeviceError(f"Format baris data tidak valid (harus diawali DATA,): {line}")

    fields = clean_line.split(",")
    expected_field_count = 2 + len(WAVELENGTHS)  # 1 prefix + 1 scan_no + 18 values = 20
    if len(fields) != expected_field_count:
        raise DeviceError(
            f"Format data tidak valid (diharapkan {expected_field_count} kolom, diterima {len(fields)}): {line}"
        )

    try:
        scan_no = int(fields[1])
        if scan_no < 0:
            raise ValueError("Nomor scan tidak boleh negatif")
    except ValueError as error:
        raise DeviceError(f"Nomor scan tidak valid ({fields[1]}): {error}") from error

    spectral_values: list[float] = []
    for index, (wavelength, field_str) in enumerate(zip(WAVELENGTHS, fields[2:]), start=2):
        try:
            val = float(field_str)
            if not math.isfinite(val):
                raise ValueError("Nilai bukan angka berhingga")
            spectral_values.append(val)
        except ValueError as error:
            raise DeviceError(
                f"Nilai spektral pada {wavelength} nm (kolom ke-{index + 1}) tidak valid ({field_str}): {error}"
            ) from error

    result: dict[str, float | int] = {"scan_no": scan_no}
    for key, val in zip(CHANNEL_KEYS, spectral_values):
        result[key] = val

    return result


class BuahSafeDevice:
    def __init__(self) -> None:
        self._serial: serial.Serial | None = None
        self._lock = threading.RLock()
        self.port: str | None = None
        self.last_error: str | None = None

    @staticmethod
    def available_ports() -> list[dict[str, str]]:
        return [
            {"device": item.device, "description": item.description}
            for item in list_ports.comports()
        ]

    @property
    def connected(self) -> bool:
        return bool(self._serial and self._serial.is_open)

    def status(self) -> dict[str, Any]:
        return {
            "connected": self.connected,
            "port": self.port,
            "last_error": self.last_error,
        }

    def connect(self, port: str) -> None:
        with self._lock:
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

                # ESP32 biasanya reset saat port serial dibuka.
                time.sleep(2.0)
                connection.reset_input_buffer()
                connection.write(b"PING\n")
                connection.flush()
                self._wait_for("ACK,PONG", timeout=8.0)
            except (serial.SerialException, OSError, DeviceError) as error:
                message = self._friendly_connection_error(port, error)
                self.last_error = message
                self.disconnect(keep_error=True)
                raise DeviceError(message) from error

    def disconnect(self, keep_error: bool = False) -> None:
        with self._lock:
            if self._serial:
                try:
                    self._serial.close()
                except serial.SerialException:
                    pass
            self._serial = None
            self.port = None
            if not keep_error:
                self.last_error = None

    def scan(self) -> dict[str, float | int]:
        with self._lock:
            if not self.connected or self._serial is None:
                raise DeviceError("ESP32 belum terhubung")

            try:
                # Bersihkan buffer serial dan flush perintah
                self._serial.reset_input_buffer()
                self._serial.write(b"SCAN\n")
                self._serial.flush()
                line = self._wait_for("DATA,", timeout=15.0, prefix=True)
                return parse_data_line(line)
            except (ValueError, serial.SerialException, OSError, DeviceError) as error:
                self.last_error = str(error)
                if isinstance(error, (serial.SerialException, OSError)):
                    self.disconnect(keep_error=True)
                raise DeviceError(f"Scan gagal: {error}") from error

    def _read_complete_line(self, deadline: float) -> str | None:
        """Read bytes until newline (\n) from serial before deadline."""
        if self._serial is None:
            return None

        buffer = bytearray()
        while time.monotonic() < deadline:
            chunk = self._serial.read_until(b"\n")
            if chunk:
                buffer.extend(chunk)
                if buffer.endswith(b"\n"):
                    return buffer.decode("utf-8", errors="replace").strip()
            # Small yield to prevent CPU pegging
            time.sleep(0.01)
        return None

    def _wait_for(self, expected: str, timeout: float, prefix: bool = False) -> str:
        if self._serial is None:
            raise DeviceError("Port serial tidak tersedia")

        deadline = time.monotonic() + timeout
        last_message = ""
        while time.monotonic() < deadline:
            line = self._read_complete_line(deadline)
            if line is None:
                continue
            if not line:
                continue
            last_message = line
            if line.startswith("FATAL,") or line.startswith("ERROR,"):
                raise DeviceError(line)
            if (prefix and line.startswith(expected)) or (not prefix and line == expected):
                return line

        detail = f" Pesan terakhir: {last_message}" if last_message else ""
        raise DeviceError(f"ESP32 tidak merespons sebelum timeout.{detail}")

    @staticmethod
    def _friendly_connection_error(port: str, error: Exception) -> str:
        detail = str(error)
        if "access is denied" in detail.lower() or "permissionerror" in detail.lower():
            return (
                f"{port} sedang digunakan aplikasi lain. Tutup Arduino Serial "
                "Monitor/Serial Plotter dan jendela BuahSafe lain, lalu coba lagi."
            )
        return f"Gagal menghubungkan ESP32 di {port}: {detail}"
