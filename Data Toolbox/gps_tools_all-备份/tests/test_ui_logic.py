import unittest

from ui.panels import ExcelKmlPanel, FenceKmlPanel


class FakeVar:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class FakeText:
    def __init__(self):
        self.value = ""

    def delete(self, *_args):
        self.value = ""

    def insert(self, _index, value):
        self.value = value


class UiLogicTests(unittest.TestCase):
    def test_excel_format_hint_follows_selected_mode(self):
        panel = type("Panel", (), {})()
        panel.data_format_label = FakeVar("4.0 工具导出的 GPS 数据")
        panel.data_format_hint = FakeVar()
        ExcelKmlPanel.on_data_format_selected(panel)
        self.assertEqual(panel.data_format_hint.get(), "4.0工具3.1章节导出的EXCEL")

        panel.data_format_label.set("仅经纬度数据")
        ExcelKmlPanel.on_data_format_selected(panel)
        self.assertEqual(panel.data_format_hint.get(), "必需列：经度、纬度；备注列可选")

    def test_map_backfills_each_fence_type(self):
        panel = type("Panel", (), {})()
        panel.SHAPE_LABELS = FenceKmlPanel.SHAPE_LABELS
        panel.status_var = FakeVar()
        panel.center_lat_var = FakeVar()
        panel.center_lon_var = FakeVar()
        panel.radius_var = FakeVar()
        panel.nw_lat_var = FakeVar()
        panel.nw_lon_var = FakeVar()
        panel.se_lat_var = FakeVar()
        panel.se_lon_var = FakeVar()
        panel.polygon_text = FakeText()
        panel.selected_shape = None
        panel.set_shape = lambda shape, update_name=True: setattr(panel, "selected_shape", shape)

        FenceKmlPanel.apply_map_result(panel, {
            "fences": [
                {"shape": "circle", "points": [[34.1, 108.1]], "radius": 120},
                {"shape": "rect", "points": [[34.0, 108.0], [34.2, 108.3]]},
                {"shape": "poly", "points": [[34.1, 108.1], [34.2, 108.2], [34.0, 108.3]]},
            ]
        })

        self.assertEqual(panel.center_lat_var.get(), "34.100000")
        self.assertEqual(panel.radius_var.get(), "120")
        self.assertEqual(panel.nw_lat_var.get(), "34.200000")
        self.assertEqual(panel.se_lon_var.get(), "108.300000")
        self.assertEqual(panel.polygon_text.value.count("\n"), 2)
        self.assertEqual(panel.selected_shape, "polygon")
        self.assertEqual(panel.status_var.get(), "已回填 3 种围栏：圆形、矩形、多边形")


if __name__ == "__main__":
    unittest.main()
