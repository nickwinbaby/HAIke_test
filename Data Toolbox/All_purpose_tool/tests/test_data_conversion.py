import unittest

from core.data_conversion import (
    ascii_to_hex,
    beijing_to_unix,
    format_beijing_time,
    hex_to_ascii,
    hex_to_beijing,
    hex_timestamp_to_int,
    unix_to_beijing,
)


class DataConversionTests(unittest.TestCase):
    def test_hex_ascii_bidirectional(self):
        self.assertEqual(hex_to_ascii("48 65 6C 6C 6F"), "Hello")
        self.assertEqual(hex_to_ascii("0x48,0x69"), "Hi")
        self.assertEqual(ascii_to_hex("Hello"), "48 65 6C 6C 6F")

    def test_hex_and_ascii_validation(self):
        with self.assertRaises(ValueError):
            hex_to_ascii("123")
        with self.assertRaises(ValueError):
            hex_to_ascii("FF")
        with self.assertRaises(ValueError):
            ascii_to_hex("中文")

    def test_unix_seconds_and_milliseconds_to_beijing(self):
        seconds, seconds_unit = unix_to_beijing("0", "秒")
        milliseconds, milliseconds_unit = unix_to_beijing("1700000000000", "自动识别")
        equivalent_seconds, _ = unix_to_beijing("1700000000", "秒")
        self.assertEqual(format_beijing_time(seconds), "1970-01-01 08:00:00.000")
        self.assertEqual(seconds_unit, "秒")
        self.assertEqual(milliseconds_unit, "毫秒")
        self.assertEqual(milliseconds, equivalent_seconds)
        self.assertEqual(
            format_beijing_time(seconds, include_milliseconds=False),
            "1970-01-01 08:00:00",
        )
        with_milliseconds, _ = unix_to_beijing("1700000000123", "毫秒")
        self.assertTrue(format_beijing_time(with_milliseconds).endswith(".123"))

    def test_beijing_to_unix_seconds_and_milliseconds(self):
        self.assertEqual(beijing_to_unix("1970-01-01 08:00:00", "秒"), 0)
        self.assertEqual(beijing_to_unix("1970-01-01 08:00:00.123", "毫秒"), 123)

    def test_hex_timestamp_to_beijing(self):
        converted = hex_to_beijing("0x00")
        self.assertEqual(
            format_beijing_time(converted, include_milliseconds=False),
            "1970-01-01 08:00:00",
        )
        converted = hex_to_beijing("65 53 F1 00")
        self.assertEqual(
            format_beijing_time(converted, include_milliseconds=False),
            "2023-11-15 06:13:20",
        )
        with self.assertRaises(ValueError):
            hex_to_beijing("XYZ", "秒")

    def test_hex_timestamp_auto_detects_milliseconds(self):
        self.assertEqual(hex_timestamp_to_int("018BCFE5687B"), 1700000000123)
        converted = hex_to_beijing("018BCFE5687B")
        self.assertEqual(format_beijing_time(converted), "2023-11-15 06:13:20.123")


if __name__ == "__main__":
    unittest.main()
