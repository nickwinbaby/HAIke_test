from __future__ import annotations

import argparse
from pathlib import Path

from automation.case_runner import CaseRunner, load_case


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a single JSON case.")
    parser.add_argument(
        "--case",
        default=str(Path(__file__).resolve().parent.parent / "json流程测试" / "case_完整电源CAN流程.json"),
        help="Path to case JSON.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Run without touching real hardware.")
    parser.add_argument("--time-scale", type=float, default=1.0, help="Scale wait/ramp durations.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    case = load_case(args.case)
    runner = CaseRunner(case, dry_run=args.dry_run, time_scale=args.time_scale)
    runner.run()


if __name__ == "__main__":
    main()
