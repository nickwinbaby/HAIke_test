import unittest
from unittest.mock import patch
from pathlib import Path

from terminal_split_cli import LAYOUTS, _is_file, _parse_dirs, build_wt_args


class TerminalSplitTests(unittest.TestCase):
    def test_every_layout_builds_expected_pane_count(self):
        for count, layouts in LAYOUTS.items():
            for layout in layouts:
                with self.subTest(count=count, layout=layout):
                    args = build_wt_args(count, layout, [None] * count)
                    self.assertEqual(args.count("powershell.exe"), count)
                    self.assertEqual(args.count("split-pane"), count - 1)

    def test_unicode_and_space_directory_is_single_argument(self):
        path = Path(r"E:\B-后装产品\1 - 版本目录\1 - 软件版本")
        args = build_wt_args(2, "columns", [path, None])
        self.assertIn(str(path), args)
        self.assertEqual(args[args.index("-d") + 1], str(path))
        self.assertNotIn("Set-Location", " ".join(args))
        self.assertNotIn("-Command", args)

    def test_each_selected_directory_gets_own_d_flag(self):
        directories = [Path(rf"C:\工作目录 {index}") for index in range(1, 7)]
        args = build_wt_args(6, "grid-3x2", directories)
        self.assertEqual(args.count("-d"), 6)
        for path in directories:
            self.assertIn(str(path), args)

    def test_empty_cli_directory_keeps_default(self):
        directories = _parse_dirs(["", "."], 2)
        self.assertIsNone(directories[0])
        self.assertTrue(directories[1].is_absolute())

    def test_default_target_is_new_window(self):
        args = build_wt_args(2, "rows", [None, None])
        self.assertEqual(args[:2], ["-w", "new"])

    def test_grid_directories_are_created_in_visual_order(self):
        directories = [Path(f"pane-{index}") for index in range(1, 7)]
        cases = {
            (3, "right-large"): ["pane-1", "pane-3", "pane-2"],
            (4, "grid"): ["pane-1", "pane-3", "pane-4", "pane-2"],
            (5, "grid-3-2"): ["pane-1", "pane-4", "pane-5", "pane-2", "pane-3"],
            (5, "grid-2-3"): ["pane-1", "pane-3", "pane-2", "pane-4", "pane-5"],
            (6, "grid-3x2"): ["pane-1", "pane-4", "pane-5", "pane-6", "pane-2", "pane-3"],
        }
        for (count, layout), expected_creation_order in cases.items():
            with self.subTest(count=count, layout=layout):
                args = build_wt_args(count, layout, directories[:count])
                actual = [args[index + 1] for index, item in enumerate(args) if item == "-d"]
                self.assertEqual(actual, expected_creation_order)

    def test_four_pane_grid_uses_unambiguous_focus_sequence(self):
        args = build_wt_args(4, "grid", [None] * 4)
        focus_directions = [
            args[index + 1]
            for index, item in enumerate(args)
            if item == "move-focus"
        ]
        self.assertEqual(focus_directions, ["up"])
        split_directions = [
            args[index + 1]
            for index, item in enumerate(args)
            if item == "split-pane"
        ]
        self.assertEqual(split_directions, ["-H", "-V", "-V"])

    def test_invalid_layout_is_rejected(self):
        with self.assertRaises(ValueError):
            build_wt_args(3, "grid", [None] * 3)

    def test_inaccessible_windows_app_alias_is_ignored(self):
        with patch.object(Path, "is_file", side_effect=OSError("inaccessible alias")):
            self.assertFalse(_is_file(Path(r"C:\WindowsApps\wt.exe")))


if __name__ == "__main__":
    unittest.main()
