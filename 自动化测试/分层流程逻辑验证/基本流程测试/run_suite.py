from __future__ import annotations

import argparse
from pathlib import Path

from automation.suite_runner import SuiteRunner


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a JSON suite.")
    parser.add_argument(
        "--suite",
        default=str(Path(__file__).resolve().parent.parent / "json流程测试" / "suite_两条用例验证.json"),
        help="Path to suite JSON.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Run without touching real hardware.")
    parser.add_argument("--time-scale", type=float, default=1.0, help="Scale wait/ramp durations.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = SuiteRunner(args.suite, dry_run=args.dry_run, time_scale=args.time_scale).run()
    print(
        f"Suite finished: total={summary['total']} passed={summary['passed']} "
        f"failed={summary['failed']} report={summary.get('report_dir', '')}"
    )


if __name__ == "__main__":
    main()
