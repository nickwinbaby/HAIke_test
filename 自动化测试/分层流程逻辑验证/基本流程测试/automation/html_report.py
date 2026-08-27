from __future__ import annotations

from html import escape
from typing import Any


def render_html_report(summary: dict[str, Any]) -> str:
    rows = []
    for result in summary["results"]:
        rows.append(
            f"<tr><td>{escape(result['name'])}</td><td>{escape(result['status'])}</td>"
            f"<td>{escape(result['started_at'])}</td><td>{escape(result['finished_at'])}</td>"
            f"<td>{escape(str(result['duration_seconds']))}</td><td>{escape(result.get('error', ''))}</td></tr>"
        )

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>{escape(summary['suite_name'])}</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; color: #222; }}
    h1 {{ margin: 0 0 12px; }}
    .meta {{ margin: 0 0 18px; color: #555; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #ccc; padding: 8px; text-align: left; vertical-align: top; }}
    th {{ background: #f4f6f8; }}
    .pass {{ color: #0a7a0a; font-weight: bold; }}
    .fail {{ color: #b00020; font-weight: bold; }}
  </style>
</head>
<body>
  <h1>{escape(summary['suite_name'])}</h1>
  <div class="meta">
    Total: {summary['total']} | Passed: {summary['passed']} | Failed: {summary['failed']} |
    Start: {escape(summary['started_at'])} | End: {escape(summary['finished_at'])}
  </div>
  <table>
    <thead>
      <tr>
        <th>Case</th><th>Status</th><th>Start</th><th>End</th><th>Duration(s)</th><th>Error</th>
      </tr>
    </thead>
    <tbody>
      {''.join(rows)}
    </tbody>
  </table>
</body>
</html>
"""

