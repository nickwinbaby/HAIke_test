from datetime import datetime
import os
import tempfile
import unittest

import openpyxl

from core.cep import analyze_cep
from core.cold_start import analyze_cold_start, extract_timestamp, is_valid_nmea
from core.coordinate import (
    angle_list_to_decimal,
    bd09_to_wgs84,
    dm_to_decimal,
    dms_to_decimal,
    gcj02_to_wgs84,
    out_of_china,
    wgs84_to_bd09,
    wgs84_to_gcj02,
)
from core.excel_kml import generate_excel_kml
from core.fence_kml import (
    GeoPoint,
    build_fence_kml,
    build_point_kml,
    circle_ring,
    parse_polygon_text,
    rectangle_ring,
)
from core.fence_packet import build_40_packet, build_808_body, build_808_delete_body
from core.nmea_kml import generate_nmea_kml, parse_nmea


class CoordinateTests(unittest.TestCase):
    def test_known_conversion_and_reverse(self):
        gcj_lat, gcj_lon = wgs84_to_gcj02(39.908823, 116.397470)
        self.assertAlmostEqual(gcj_lat, 39.910226, places=5)
        self.assertAlmostEqual(gcj_lon, 116.403714, places=5)
        wgs_lat, wgs_lon = gcj02_to_wgs84(gcj_lat, gcj_lon)
        self.assertAlmostEqual(wgs_lat, 39.908823, places=4)
        self.assertAlmostEqual(wgs_lon, 116.397470, places=4)

    def test_overseas_coordinate_is_unchanged(self):
        self.assertTrue(out_of_china(40.7128, -74.0060))
        self.assertEqual(wgs84_to_gcj02(40.7128, -74.0060), (40.7128, -74.0060))

    def test_bd09_round_trip_and_angle_formats(self):
        original = (34.188178, 108.878631)
        bd_lat, bd_lon = wgs84_to_bd09(*original)
        wgs_lat, wgs_lon = bd09_to_wgs84(bd_lat, bd_lon)
        self.assertAlmostEqual(wgs_lat, original[0], places=4)
        self.assertAlmostEqual(wgs_lon, original[1], places=4)
        self.assertAlmostEqual(dms_to_decimal("34°11′21.67″"), 34.1893527778, places=8)
        self.assertAlmostEqual(dm_to_decimal("34°11.3612′"), 34.1893533333, places=8)
        self.assertAlmostEqual(dms_to_decimal("34°11′21.67″S"), -34.1893527778, places=8)
        values = angle_list_to_decimal("34°11′21.67″,108°52′43.07″", "dms")
        self.assertAlmostEqual(values[0], 34.1893527778, places=8)
        self.assertAlmostEqual(values[1], 108.8786305556, places=8)


class NmeaKmlTests(unittest.TestCase):
    SAMPLE = (
        "$GNRMC,123519.00,A,3114.1234,N,12128.5678,E,1.5,0.0,180426,,,A*00\n"
        "$GNGGA,123520.00,3114.1234,N,12128.5678,E,1,12,0.8,15.2,M,0.0,M,,*00\n"
    )

    def test_parse_and_generate(self):
        parsed = parse_nmea(self.SAMPLE.splitlines(True))
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0][2], 15.2)
        with tempfile.TemporaryDirectory() as temp_dir:
            source = os.path.join(temp_dir, "sample.txt")
            with open(source, "w", encoding="utf-8") as file_obj:
                file_obj.write(self.SAMPLE)
            result = generate_nmea_kml(source, temp_dir, datetime(2026, 1, 2, 3, 4, 5))
            self.assertEqual(result.point_count, 1)
            self.assertTrue(os.path.exists(result.tracker_file))
            self.assertTrue(os.path.exists(result.point_file))
            with open(result.point_file, "r", encoding="utf-8") as file_obj:
                point_kml = file_obj.read()
            self.assertIn("<name>1</name>", point_kml)


class ExcelKmlTests(unittest.TestCase):
    def test_generate_two_kml_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = os.path.join(temp_dir, "gps.xlsx")
            workbook = openpyxl.Workbook()
            sheet = workbook.active
            sheet.append(["经度", "纬度", "经度值", "纬度值", "GPS时间", "卫星数", "高度"])
            sheet.append(["E", "N", 121.5, 31.2, "12:00:00", 12, 10.5])
            sheet.append(["W", "S", 10.0, 20.0, "12:00:01", 10, 9.5])
            workbook.save(source)
            result = generate_excel_kml(source, temp_dir)
            self.assertEqual(result.point_count, 2)
            self.assertEqual(result.warnings, ())
            self.assertTrue(os.path.exists(result.tracker_file))
            self.assertTrue(os.path.exists(result.point_file))

    def test_generate_simple_coordinate_kml_with_remark(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = os.path.join(temp_dir, "simple.xlsx")
            workbook = openpyxl.Workbook()
            sheet = workbook.active
            sheet.append(["经度", "纬度", "备注"])
            sheet.append([108.878631, 34.188178, "测试位置A"])
            workbook.save(source)
            result = generate_excel_kml(source, temp_dir, "simple")
            self.assertEqual(result.point_count, 1)
            with open(result.point_file, "r", encoding="utf-8") as file_obj:
                kml_text = file_obj.read()
            self.assertIn("测试位置A", kml_text)
            self.assertIn("108.878631,34.188178", kml_text)
            self.assertIn("<name>1</name>", kml_text)
            self.assertNotIn("<name>点1</name>", kml_text)

    def test_generate_simple_coordinate_kml_without_remark_column(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = os.path.join(temp_dir, "simple_without_remark.xlsx")
            workbook = openpyxl.Workbook()
            sheet = workbook.active
            sheet.append(["经度", "纬度"])
            sheet.append([108.878631, 34.188178])
            workbook.save(source)
            result = generate_excel_kml(source, temp_dir, "simple")
            self.assertEqual(result.point_count, 1)
            self.assertEqual(result.warnings, ())
            with open(result.point_file, "r", encoding="utf-8") as file_obj:
                kml_text = file_obj.read()
            self.assertIn("108.878631,34.188178", kml_text)
            self.assertNotIn("备注:", kml_text)


class CepTests(unittest.TestCase):
    def test_complete_analysis_outputs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = os.path.join(temp_dir, "cep.txt")
            lines = []
            for index in range(20):
                latitude = 3114.1000 + index * 0.0002
                longitude = 12128.5000 + index * 0.0002
                lines.append(
                    f"$GNGGA,1235{index:02d}.00,{latitude:.4f},N,{longitude:.4f},E,1,12,0.8,15.2,M,0.0,M,,*00\n"
                )
            with open(source, "w", encoding="utf-8") as file_obj:
                file_obj.writelines(lines)

            result = analyze_cep(
                source,
                (31 + 14.1 / 60, 121 + 28.5 / 60),
                "$GNGGA",
                temp_dir,
                datetime(2026, 1, 2, 3, 4, 5),
            )
            self.assertEqual(result.point_count, 20)
            self.assertTrue(os.path.exists(result.scatter_file))
            self.assertTrue(os.path.exists(result.bar_file))
            self.assertTrue(os.path.exists(result.satellite_file))


class FenceKmlTests(unittest.TestCase):
    def test_circle_rectangle_polygon_and_point_kml(self):
        center = GeoPoint(31.230416, 121.473701)
        circle = circle_ring(center, 100)
        self.assertEqual(len(circle), 73)
        self.assertEqual(circle[0], circle[-1])

        rectangle = rectangle_ring(GeoPoint(31.24, 121.46), GeoPoint(31.22, 121.49))
        self.assertEqual(len(rectangle), 5)
        self.assertEqual(rectangle[0], rectangle[-1])

        polygon = parse_polygon_text("31.23,121.47\n31.24,121.48\n31.22,121.49")
        self.assertEqual(len(polygon), 4)
        fence_xml = build_fence_kml(polygon, "测试围栏")
        point_xml = build_point_kml([center], "测试点")
        self.assertIn("测试围栏", fence_xml.getroot().find("{*}Document/{*}name").text)
        self.assertEqual(point_xml.getroot().find("{*}Document/{*}Placemark/{*}name").text, "点 1")


class FencePacketTests(unittest.TestCase):
    def test_40_circle_matches_legacy_packet(self):
        row = {
            "fence_id": "1", "report_type": "03", "fence_type": "01", "key": "404", "radius": "100",
            "gps": [{"lon_dir": "东经", "lon": "108.878631", "lat_dir": "北纬", "lat": "34.188178"}],
        }
        result = build_40_packet(
            major_minor="F10F", op_type="02", total_fence="1", msg_index="1", rows=[row]
        )
        self.assertEqual(result, "F10F020101010110030101940B00A622B780342AC1000064")

    def test_40_total_fence_count_is_limited_to_1_through_40(self):
        row = {
            "fence_id": "1", "report_type": "03", "fence_type": "01", "key": "404", "radius": "100",
            "gps": [{"lon_dir": "东经", "lon": "108.878631", "lat_dir": "北纬", "lat": "34.188178"}],
        }
        for invalid in ("0", "41", "-1", "abc", ""):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(ValueError, "待操作围栏总数"):
                    build_40_packet(total_fence=invalid, rows=[row])
        self.assertTrue(build_40_packet(total_fence="1", rows=[row]).startswith("F10F020101"))
        self.assertTrue(build_40_packet(total_fence="40", rows=[row]).startswith("F10F022801"))

    def test_40_operation_specific_shapes_and_unique_geo_ids(self):
        self.assertEqual(build_40_packet(op_type="01"), "F10F01")
        self.assertEqual(
            build_40_packet(op_type="03", total_fence="2", msg_index="1", delete_ids=[1, 40]),
            "F10F030201020128",
        )
        with self.assertRaisesRegex(ValueError, "不能重复"):
            build_40_packet(op_type="03", total_fence="2", msg_index="1", delete_ids=[1, 1])

    def test_40_circle_radius_is_limited_by_key_404(self):
        row = {
            "fence_id": "1", "report_type": "01", "fence_type": "01", "key": "404",
            "radius": "20",
            "gps": [{"lon_dir": "东经", "lon": "108.878631", "lat_dir": "北纬", "lat": "34.188178"}],
        }
        self.assertIn("000014", build_40_packet(op_type="02", rows=[row]))
        row["radius"] = "16777215"
        self.assertIn("FFFFFF", build_40_packet(op_type="02", rows=[row]))
        for invalid in ("0", "19", "16777216"):
            with self.subTest(invalid=invalid):
                row["radius"] = invalid
                with self.assertRaisesRegex(ValueError, "半径"):
                    build_40_packet(op_type="02", rows=[row])

    def test_808_reference_vectors(self):
        common = dict(operation="0", fence_id="1", enter_alarm=True, leave_alarm=True)
        message_id, body = build_808_body(
            shape="circle", points=[(31.230416, 121.473701)], radius="500", **common
        )
        self.assertEqual(message_id, "8600")
        self.assertEqual(body, "000100000001002801DC89D0073D8AA5000001F4")
        message_id, body = build_808_body(
            shape="rect", points=[(31.24, 121.46), (31.22, 121.49)], **common
        )
        self.assertEqual((message_id, body), (
            "8602", "000100000001002801DCAF40073D552001DC6120073DCA50"
        ))
        message_id, body = build_808_body(
            shape="poly", fence_id="1", enter_alarm=True, leave_alarm=True,
            points=[(31.24, 121.46), (31.22, 121.49), (31.21, 121.47)],
        )
        self.assertEqual((message_id, body), (
            "8604", "000000010028000301DCAF40073D552001DC6120073DCA5001DC3A10073D7C30"
        ))
        with self.assertRaisesRegex(ValueError, "3~10"):
            build_808_body(shape="poly", points=[(31.2, 121.4)] * 11)
        self.assertEqual(
            build_808_delete_body(shape="circle", fence_ids=["1", "2"]),
            ("8601", "020000000100000002"),
        )
        self.assertEqual(build_808_delete_body(shape="circle", fence_ids=[]), ("8601", "00"))
        self.assertEqual(build_808_delete_body(shape="circle", fence_ids=["0"]), ("8601", "00"))
        self.assertEqual(build_808_delete_body(shape="rect", fence_ids=["1", "0", "2"]), ("8603", "00"))
        self.assertEqual(build_808_delete_body(shape="poly", fence_ids=["3"]), ("8605", "0100000003"))


class ColdStartTests(unittest.TestCase):
    def test_timestamp_and_fix_rules(self):
        self.assertEqual(
            extract_timestamp("[2026-04-18 10:00:01.250] boot"),
            datetime(2026, 4, 18, 10, 0, 1, 250000),
        )
        valid = "$GNGGA,100005.00,3114.1234,N,12128.5678,E,1,12,0.8,15.2,M,0.0,M,,*00"
        dead_reckoning = "$GNGGA,100005.00,3114.1234,N,12128.5678,E,6,12,0.8,15.2,M,0.0,M,,*00"
        self.assertTrue(is_valid_nmea(valid))
        self.assertFalse(is_valid_nmea(dead_reckoning))
        self.assertTrue(is_valid_nmea(dead_reckoning, skip_loc_check=True))

    def test_analyze_report(self):
        log_text = (
            "[2026-04-18 10:00:00.000] Welcome to boot rom\n"
            "[2026-04-18 10:00:03.500] $GNGGA,100003.50,3114.1234,N,12128.5678,E,1,12,0.8,15.2,M,0.0,M,,*00\n"
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            source = os.path.join(temp_dir, "cold.log")
            with open(source, "w", encoding="utf-8") as file_obj:
                file_obj.write(log_text)
            result = analyze_cold_start(source, "Welcome to boot rom", "$GNGGA", False)
            self.assertEqual(result.boot_total_count, 1)
            self.assertEqual(result.records, (3.5,))
            self.assertIn("平均启动耗时：3.500 s", result.report)


if __name__ == "__main__":
    unittest.main()

