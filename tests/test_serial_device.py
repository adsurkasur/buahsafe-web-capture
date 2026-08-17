import time
import unittest
from unittest.mock import MagicMock, patch

from serial_device import (
    CHANNEL_KEYS,
    WAVELENGTHS,
    BuahSafeDevice,
    DeviceError,
    debug_logger,
    parse_data_line,
)


class TestSerialDevice(unittest.TestCase):
    def test_parse_valid_18_channel_data(self):
        line = (
            "DATA,1,1.0,2.0,3.0,4.0,5.0,6.0,7.0,8.0,9.0,"
            "10.0,11.0,12.0,13.0,14.0,15.0,16.0,17.0,18.0"
        )
        parsed = parse_data_line(line)
        self.assertEqual(parsed["scan_no"], 1)
        expected_mapping = {
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
        for key, expected_val in expected_mapping.items():
            self.assertIn(key, parsed)
            self.assertAlmostEqual(parsed[key], expected_val)

        # Check exact wavelength order matches
        self.assertEqual(len(parsed), 19)  # 1 scan_no + 18 channels

    def test_parse_too_few_spectral_values(self):
        # Only 17 values
        line = "DATA,1," + ",".join(str(float(i)) for i in range(1, 18))
        with self.assertRaises(DeviceError) as ctx:
            parse_data_line(line)
        self.assertIn("diharapkan 20 kolom", str(ctx.exception))

    def test_parse_legacy_as7263_format_fails(self):
        # Old 6-channel + temp format (9 fields)
        line = "DATA,1,10.5,20.2,30.1,40.4,50.8,60.9,28.5"
        with self.assertRaises(DeviceError) as ctx:
            parse_data_line(line)
        self.assertIn("diharapkan 20 kolom", str(ctx.exception))

    def test_parse_too_many_spectral_values(self):
        # 19 values (21 fields total)
        line = "DATA,1," + ",".join(str(float(i)) for i in range(1, 20))
        with self.assertRaises(DeviceError) as ctx:
            parse_data_line(line)
        self.assertIn("diharapkan 20 kolom", str(ctx.exception))

    def test_parse_invalid_non_numeric_value(self):
        line = (
            "DATA,1,1.0,2.0,INVALID,4.0,5.0,6.0,7.0,8.0,9.0,"
            "10.0,11.0,12.0,13.0,14.0,15.0,16.0,17.0,18.0"
        )
        with self.assertRaises(DeviceError) as ctx:
            parse_data_line(line)
        self.assertIn("460 nm", str(ctx.exception))

    def test_parse_nan_or_inf_fails(self):
        line = (
            "DATA,1,1.0,2.0,nan,4.0,5.0,6.0,7.0,8.0,9.0,"
            "10.0,11.0,12.0,13.0,14.0,15.0,16.0,17.0,18.0"
        )
        with self.assertRaises(DeviceError):
            parse_data_line(line)

        line_inf = (
            "DATA,1,1.0,2.0,inf,4.0,5.0,6.0,7.0,8.0,9.0,"
            "10.0,11.0,12.0,13.0,14.0,15.0,16.0,17.0,18.0"
        )
        with self.assertRaises(DeviceError):
            parse_data_line(line_inf)

    def test_parse_invalid_scan_number(self):
        line = (
            "DATA,abc,1.0,2.0,3.0,4.0,5.0,6.0,7.0,8.0,9.0,"
            "10.0,11.0,12.0,13.0,14.0,15.0,16.0,17.0,18.0"
        )
        with self.assertRaises(DeviceError) as ctx:
            parse_data_line(line)
        self.assertIn("Nomor scan tidak valid", str(ctx.exception))

    def test_parse_negative_scan_number(self):
        line = (
            "DATA,-5,1.0,2.0,3.0,4.0,5.0,6.0,7.0,8.0,9.0,"
            "10.0,11.0,12.0,13.0,14.0,15.0,16.0,17.0,18.0"
        )
        with self.assertRaises(DeviceError) as ctx:
            parse_data_line(line)
        self.assertIn("Nomor scan tidak valid", str(ctx.exception))

    def test_parse_invalid_prefix(self):
        line = (
            "STATUS,1,1.0,2.0,3.0,4.0,5.0,6.0,7.0,8.0,9.0,"
            "10.0,11.0,12.0,13.0,14.0,15.0,16.0,17.0,18.0"
        )
        with self.assertRaises(DeviceError) as ctx:
            parse_data_line(line)
        self.assertIn("harus diawali DATA,", str(ctx.exception))

    def test_wait_for_firmware_error_handling(self):
        device = BuahSafeDevice()
        mock_serial = MagicMock()
        device._serial = mock_serial

        # ERROR,AS7265X_NOT_READY
        mock_serial.read_until.return_value = b"ERROR,AS7265X_NOT_READY\r\n"
        with self.assertRaises(DeviceError) as ctx:
            device._wait_for("DATA,", timeout=1.0, prefix=True)
        self.assertEqual(str(ctx.exception), "ERROR,AS7265X_NOT_READY")

        # FATAL,AS7265X_I2C_0x49_NOT_FOUND
        mock_serial.read_until.return_value = b"FATAL,AS7265X_I2C_0x49_NOT_FOUND\r\n"
        with self.assertRaises(DeviceError) as ctx:
            device._wait_for("ACK,PONG", timeout=1.0)
        self.assertEqual(str(ctx.exception), "FATAL,AS7265X_I2C_0x49_NOT_FOUND")

    @patch("serial_device.serial.Serial")
    @patch("serial_device.time.sleep")
    def test_connect_handshake_success(self, mock_sleep, mock_serial_cls):
        mock_inst = MagicMock()
        mock_serial_cls.return_value = mock_inst
        mock_inst.is_open = True
        mock_inst.read_until.return_value = b"ACK,PONG\r\n"

        device = BuahSafeDevice()
        device.connect("COM3")

        self.assertTrue(device.connected)
        self.assertEqual(device.port, "COM3")
        mock_inst.write.assert_called_with(b"PING\n")

    def test_device_scan_flow(self):
        device = BuahSafeDevice()
        mock_serial = MagicMock()
        mock_serial.is_open = True
        mock_serial.in_waiting = 0
        device._serial = mock_serial

        sample_line = (
            b"DATA,42,1.1,2.2,3.3,4.4,5.5,6.6,7.7,8.8,9.9,"
            b"10.1,11.2,12.3,13.4,14.5,15.6,16.7,17.8,18.9\r\n"
        )
        mock_serial.read_until.return_value = sample_line

        result = device.scan()
        self.assertEqual(result["scan_no"], 42)
        self.assertAlmostEqual(result["nm410"], 1.1)
        self.assertAlmostEqual(result["nm940"], 18.9)
        mock_serial.write.assert_called_with(b"SCAN\n")

    def test_device_scan_multi_chunk_assembly(self):
        device = BuahSafeDevice()
        mock_serial = MagicMock()
        mock_serial.is_open = True
        mock_serial.in_waiting = 0
        device._serial = mock_serial

        # First read_until timed out with partial bytes, second finished with newline
        chunk1 = b"DATA,42,1.1,2.2,3.3,4.4,5.5,6.6,7.7,8.8,9.9,"
        chunk2 = b"10.1,11.2,12.3,13.4,14.5,15.6,16.7,17.8,18.9\r\n"
        mock_serial.read_until.side_effect = [chunk1, chunk2]

        result = device.scan()
        self.assertEqual(result["scan_no"], 42)
        self.assertAlmostEqual(result["nm410"], 1.1)
        self.assertAlmostEqual(result["nm940"], 18.9)

    # --- Hardening: recover valid data instead of hard-failing on timeout ---

    def test_parse_tolerates_leading_noise_byte(self):
        # UART noise sesekali menyisipkan 1 byte sampah sebelum "DATA,".
        line = (
            "\x00DATA,1,1.0,2.0,3.0,4.0,5.0,6.0,7.0,8.0,9.0,"
            "10.0,11.0,12.0,13.0,14.0,15.0,16.0,17.0,18.0"
        )
        parsed = parse_data_line(line)
        self.assertEqual(parsed["scan_no"], 1)
        self.assertAlmostEqual(parsed["nm410"], 1.0)
        self.assertAlmostEqual(parsed["nm940"], 18.0)

    def test_read_complete_line_grace_window_recovers_late_line(self):
        device = BuahSafeDevice()
        mock_serial = MagicMock()
        device._serial = mock_serial

        # Chunk pertama (belum ada newline) baru datang saat deadline nominal
        # nyaris habis; chunk kedua menyelesaikan baris sesaat sesudahnya.
        chunk1 = b"DATA,7,1.0,2.0,3.0,4.0,5.0,6.0,7.0,8.0,9.0,"
        chunk2 = b"10.0,11.0,12.0,13.0,14.0,15.0,16.0,17.0,18.0\r\n"
        mock_serial.read_until.side_effect = [chunk1, chunk2]

        deadline = time.monotonic() + 0.05
        result = device._read_complete_line(deadline, grace_seconds=1.0, max_grace_seconds=2.0)

        self.assertIsNotNone(result)
        self.assertTrue(result.startswith("DATA,7,"))
        self.assertTrue(result.endswith("18.0"))

    def test_read_complete_line_still_times_out_when_truly_dead(self):
        device = BuahSafeDevice()
        mock_serial = MagicMock()
        device._serial = mock_serial
        # Tidak pernah ada data sama sekali.
        mock_serial.read_until.return_value = b""

        deadline = time.monotonic() + 0.05
        result = device._read_complete_line(deadline, grace_seconds=0.2, max_grace_seconds=0.5)
        self.assertIsNone(result)

    def test_scan_recovers_valid_data_after_apparent_timeout(self):
        device = BuahSafeDevice()
        mock_serial = MagicMock()
        mock_serial.is_open = True
        mock_serial.in_waiting = 0
        device._serial = mock_serial

        # Kasus nyata yang dilaporkan: raw_line lengkap & valid (169 char),
        # tapi _wait_for() sempat melempar timeout karena pola tidak cocok
        # tepat waktu.
        valid_line = (
            "DATA,5,0.829432,1.865169,14.141210,0.000000,2.894009,2.089023,"
            "2.059999,1.506729,3.467611,2.103488,6.079141,0.417066,0.782507,"
            "0.845497,0.797302,1.158727,0.611499,0.000000"
        )
        timeout_error = DeviceError(
            "ESP32 tidak merespons sebelum timeout.",
            raw_line=valid_line,
        )
        with patch.object(device, "_wait_for", side_effect=timeout_error):
            result = device.scan()

        self.assertEqual(result["scan_no"], 5)
        self.assertAlmostEqual(result["nm410"], 0.829432)
        self.assertAlmostEqual(result["nm940"], 0.0)
        # Recovery berarti scan dianggap sukses -- tidak ada error tersimpan.
        self.assertIsNone(device.last_error)
        self.assertEqual(device.last_raw_message, valid_line)

    def test_scan_does_not_recover_from_empty_timeout(self):
        device = BuahSafeDevice()
        mock_serial = MagicMock()
        mock_serial.is_open = True
        mock_serial.in_waiting = 0
        device._serial = mock_serial

        timeout_error = DeviceError("ESP32 tidak merespons sebelum timeout.", raw_line="")
        with patch.object(device, "_wait_for", side_effect=timeout_error), \
                patch("serial_device.time.sleep"):
            with self.assertRaises(DeviceError):
                device.scan()
        self.assertIsNotNone(device.last_error)

    def test_scan_does_not_recover_from_garbled_line(self):
        device = BuahSafeDevice()
        mock_serial = MagicMock()
        mock_serial.is_open = True
        mock_serial.in_waiting = 0
        device._serial = mock_serial

        timeout_error = DeviceError(
            "ESP32 tidak merespons sebelum timeout.",
            raw_line="DATA,5,garbage,only,few,fields",
        )
        with patch.object(device, "_wait_for", side_effect=timeout_error), \
                patch("serial_device.time.sleep"):
            with self.assertRaises(DeviceError):
                device.scan()
        self.assertIsNotNone(device.last_error)

    def test_scan_auto_retries_once_on_transient_failure_then_succeeds(self):
        device = BuahSafeDevice()
        mock_serial = MagicMock()
        mock_serial.is_open = True
        mock_serial.in_waiting = 0
        device._serial = mock_serial

        valid_line = (
            "DATA,9,1.0,2.0,3.0,4.0,5.0,6.0,7.0,8.0,9.0,"
            "10.0,11.0,12.0,13.0,14.0,15.0,16.0,17.0,18.0"
        )
        # Percobaan pertama gagal total (bukan sesuatu yang bisa dipulihkan
        # dari raw_line), percobaan kedua (retry otomatis) sukses bersih.
        with patch.object(
            device,
            "_wait_for",
            side_effect=[
                DeviceError("ESP32 tidak merespons sebelum timeout.", raw_line=""),
                valid_line,
            ],
        ), patch("serial_device.time.sleep"):
            result = device.scan()

        self.assertEqual(result["scan_no"], 9)
        self.assertIsNone(device.last_error)

    def test_scan_does_not_reuse_stale_last_raw_message_on_genuine_timeout(self):
        # Regresi untuk bug nyata: scan pertama sukses (last_raw_message
        # terisi). Scan KEDUA gagal total (ESP32 hang sungguhan, 0 byte
        # masuk -- raw_line kosong). Sebelum fix, kode ini keliru fallback ke
        # last_raw_message lama dan mengembalikannya sebagai "sukses" --
        # menghasilkan data duplikat palsu di database. Sekarang harus benar2
        # melempar error, bukan mendaur ulang data basi.
        device = BuahSafeDevice()
        mock_serial = MagicMock()
        mock_serial.is_open = True
        mock_serial.in_waiting = 0
        device._serial = mock_serial

        first_line = (
            "DATA,9,1.0,2.0,3.0,4.0,5.0,6.0,7.0,8.0,9.0,"
            "10.0,11.0,12.0,13.0,14.0,15.0,16.0,17.0,18.0"
        )
        with patch.object(device, "_wait_for", return_value=first_line):
            first_result = device.scan()
        self.assertEqual(first_result["scan_no"], 9)
        self.assertEqual(device.last_raw_message, first_line)

        genuine_timeout = DeviceError("ESP32 tidak merespons sebelum timeout.", raw_line="")
        with patch.object(device, "_wait_for", side_effect=genuine_timeout), \
                patch("serial_device.time.sleep"):
            with self.assertRaises(DeviceError):
                device.scan()

    def test_scan_gives_up_after_max_attempts(self):
        device = BuahSafeDevice()
        mock_serial = MagicMock()
        mock_serial.is_open = True
        mock_serial.in_waiting = 0
        device._serial = mock_serial

        timeout_error = DeviceError("ESP32 tidak merespons sebelum timeout.", raw_line="")
        with patch.object(device, "_wait_for", side_effect=timeout_error), \
                patch("serial_device.time.sleep") as mock_sleep:
            with self.assertRaises(DeviceError):
                device.scan()
        # 3 percobaan total -> 2 kali sleep di antara percobaan
        self.assertEqual(mock_sleep.call_count, 2)

    # --- Hardening lanjutan: RESCAN, sinkronisasi LCD, deteksi reboot ---

    def test_scan_first_attempt_sends_scan_not_rescan(self):
        device = BuahSafeDevice()
        mock_serial = MagicMock()
        mock_serial.is_open = True
        mock_serial.in_waiting = 0
        device._serial = mock_serial

        sample_line = (
            "DATA,1,1.0,2.0,3.0,4.0,5.0,6.0,7.0,8.0,9.0,"
            "10.0,11.0,12.0,13.0,14.0,15.0,16.0,17.0,18.0"
        )
        with patch.object(device, "_wait_for", return_value=sample_line):
            device.scan()
        mock_serial.write.assert_called_with(b"SCAN\n")

    def test_scan_retry_sends_rescan_not_scan(self):
        # Percobaan kedua (retry otomatis) harus memakai command RESCAN,
        # bukan SCAN -- supaya firmware tahu ini pengulangan dan bisa
        # menampilkan "Mencoba ulang..." di LCD, bukan seolah scan baru.
        device = BuahSafeDevice()
        mock_serial = MagicMock()
        mock_serial.is_open = True
        mock_serial.in_waiting = 0
        device._serial = mock_serial

        valid_line = (
            "DATA,9,1.0,2.0,3.0,4.0,5.0,6.0,7.0,8.0,9.0,"
            "10.0,11.0,12.0,13.0,14.0,15.0,16.0,17.0,18.0"
        )
        with patch.object(
            device,
            "_wait_for",
            side_effect=[
                DeviceError("ESP32 tidak merespons sebelum timeout.", raw_line=""),
                valid_line,
            ],
        ), patch("serial_device.time.sleep"):
            device.scan()

        calls = [call.args[0] for call in mock_serial.write.call_args_list]
        self.assertEqual(calls, [b"SCAN\n", b"RESCAN\n"])

    def test_drain_and_check_reboot_logs_warning_on_boot_signature(self):
        device = BuahSafeDevice()
        mock_serial = MagicMock()
        mock_serial.is_open = True
        mock_serial.in_waiting = 40
        mock_serial.read.return_value = b"\r\nBOOT,BUAHSAFE_AS7265X\r\nREADY,BUAHSAFE_AS7265X_V1\r\n"
        device._serial = mock_serial

        device._drain_and_check_reboot()

        mock_serial.read.assert_called_with(40)
        mock_serial.reset_input_buffer.assert_called_once()
        recent = debug_logger.get_logs(10)
        self.assertTrue(any(
            entry["level"] == "WARN" and "reboot terdeteksi" in entry["message"]
            for entry in recent
        ))

    def test_drain_and_check_reboot_silent_when_no_pending_bytes(self):
        device = BuahSafeDevice()
        mock_serial = MagicMock()
        mock_serial.is_open = True
        mock_serial.in_waiting = 0
        device._serial = mock_serial

        debug_logger.clear()
        device._drain_and_check_reboot()

        mock_serial.read.assert_not_called()
        mock_serial.reset_input_buffer.assert_called_once()
        self.assertEqual(debug_logger.get_logs(10), [])

    def test_notify_saved_writes_ack_when_connected(self):
        device = BuahSafeDevice()
        mock_serial = MagicMock()
        mock_serial.is_open = True
        device._serial = mock_serial

        device.notify_saved(42)

        mock_serial.write.assert_called_with(b"SAVED,42\n")
        mock_serial.flush.assert_called()

    def test_notify_saved_noop_when_not_connected(self):
        device = BuahSafeDevice()
        device._serial = None

        # Tidak boleh raise walau device belum/tidak terhubung sama sekali --
        # ini best-effort, bukan operasi kritis.
        device.notify_saved(1)

    def test_notify_saved_failure_does_not_raise(self):
        device = BuahSafeDevice()
        mock_serial = MagicMock()
        mock_serial.is_open = True
        mock_serial.write.side_effect = OSError("port hilang")
        device._serial = mock_serial

        # Gagal kirim ack tidak boleh melempar exception -- data sudah aman
        # di database, ini cuma sinkronisasi tampilan LCD yang best-effort.
        device.notify_saved(1)


if __name__ == "__main__":
    unittest.main()
