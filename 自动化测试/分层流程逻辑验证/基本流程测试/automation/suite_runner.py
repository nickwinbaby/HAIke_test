from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from .case_runner import CaseRunner, load_case
from .html_report import render_html_report


def load_suite(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as file:
        return json.load(file)


class SuiteRunner:
    def __init__(self, suite_path: str | Path, dry_run: bool = False, time_scale: float = 1.0):
        self.suite_path = Path(suite_path)
        self.dry_run = dry_run
        self.time_scale = time_scale
        self.suite = load_suite(self.suite_path)
        self.results: list[dict[str, Any]] = []

    def run(self) -> dict[str, Any]:
        started_at = datetime.now()
        base_dir = self.suite_path.parent
        cases = self.suite.get("cases", [])
        interval_seconds = float(self.suite.get("case_interval_seconds", 0))
        for index, case_ref in enumerate(cases):
            case_path = (base_dir / case_ref).resolve()
            case = load_case(case_path)
            runner = CaseRunner(case, dry_run=self.dry_run, time_scale=self.time_scale)
            result = runner.run()
            result["case_path"] = str(case_path)
            self.results.append(result)
            if index < len(cases) - 1 and interval_seconds > 0:
                scaled_interval = max(0.0, interval_seconds * self.time_scale)
                now = datetime.now().strftime("%H:%M:%S")
                print(f"[{now}] Case interval: waiting {scaled_interval:.2f}s.", flush=True)
                time.sleep(scaled_interval)

        finished_at = datetime.now()
        summary = {
            "suite_name": self.suite.get("name", self.suite_path.stem),
            "suite_path": str(self.suite_path),
            "case_interval_seconds": interval_seconds,
            "started_at": started_at.isoformat(timespec="seconds"),
            "finished_at": finished_at.isoformat(timespec="seconds"),
            "duration_seconds": round((finished_at - started_at).total_seconds(), 3),
            "total": len(self.results),
            "passed": sum(1 for item in self.results if item["status"] == "PASS"),
            "failed": sum(1 for item in self.results if item["status"] == "FAIL"),
            "results": self.results,
        }
        self._write_report(summary)
        return summary

    def _write_report(self, summary: dict[str, Any]) -> None:
        report_dir = Path(__file__).resolve().parents[1] / "reports" / datetime.now().strftime("%Y%m%d_%H%M%S")
        report_dir.mkdir(parents=True, exist_ok=True)
        (report_dir / "result.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        (report_dir / "report.html").write_text(render_html_report(summary), encoding="utf-8")
        summary["report_dir"] = str(report_dir)
