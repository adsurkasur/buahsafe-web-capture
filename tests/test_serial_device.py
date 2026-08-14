import unittest
from unittest.mock import MagicMock, patch

from serial_device import (
    CHANNEL_KEYS,
    WAVELENGTHS,
    BuahSafeDevice,
    DeviceError,
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
        device._serial = mock_serial

        # First read_until timed out with partial bytes, second finished with newline
        chunk1 = b"DATA,42,1.1,2.2,3.3,4.4,5.5,6.6,7.7,8.8,9.9,"
        chunk2 = b"10.1,11.2,12.3,13.4,14.5,15.6,16.7,17.8,18.9\r\n"
        mock_serial.read_until.side_effect = [chunk1, chunk2]

        result = device.scan()
        self.assertEqual(result["scan_no"], 42)
        self.assertAlmostEqual(result["nm410"], 1.1)
        self.assertAlmostEqual(result["nm940"], 18.9)


if __name__ == "__main__":
    unittest.main()
