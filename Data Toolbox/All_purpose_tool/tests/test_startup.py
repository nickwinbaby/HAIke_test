from datetime import date
import unittest
from unittest.mock import patch

import main


class StartupDateTests(unittest.TestCase):
    def test_local_dates_through_expiry_day_allow_startup(self):
        for local_day in (date(2026, 12, 30), date(2026, 12, 31)):
            with self.subTest(local_day=local_day):
                with patch("main.date") as clock, patch("app.run") as run:
                    clock.today.return_value = local_day
                    self.assertEqual(main.main([]), 0)
                    run.assert_called_once_with()

    def test_expired_date_blocks_main_and_right_click_entry_points(self):
        for args in ([], ["--compare", "left", "right"], ["--compare-item", "left"]):
            with self.subTest(args=args):
                with (
                    patch("main.date") as clock,
                    patch("main.show_expiry_notice") as notice,
                    patch("app.run") as run,
                    patch("core.shell_compare_queue.collect_shell_selection") as collect,
                ):
                    clock.today.return_value = date(2027, 1, 1)
                    self.assertEqual(main.main(args), 1)
                    notice.assert_called_once_with()
                    run.assert_not_called()
                    collect.assert_not_called()
