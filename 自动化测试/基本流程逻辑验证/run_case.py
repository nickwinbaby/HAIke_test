from __future__ import annotations

import argparse
from pathlib import Path

from automation.runner import RuntimeOptions, StepRunner, load_case


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run hardware automation test case.")
    parser.add_argument(
        "--case",
        default=str(Path(__file__).with_name("case_voltage_can.json")),
        help="Path to the JSON test case.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Run without touching real hardware.")
    parser.add_argument("--manual", action="store_true", help="Pause after each step.")
    parser.add_argument(
        "--time-scale",
        type=float,
        default=1.0,
        help="Scale wait/ramp duration, e.g. 0.01 for a fast dry run.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    case = load_case(args.case)
    runner = StepRunner(
        case,
        RuntimeOptions(
            dry_run=args.dry_run,
            manual=args.manual,
            time_scale=args.time_scale,
        ),
    )
    runner.run()


if __name__ == "__main__":
    main()

