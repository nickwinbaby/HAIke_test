from __future__ import annotations

import runpy
import sys
from pathlib import Path


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    target = (
        project_root
        / "自动化测试"
        / "分层流程逻辑验证"
        / "基本流程测试"
        / "run_suite.py"
    )
    sys.path.insert(0, str(target.parent))
    sys.argv = [str(target)] + sys.argv[1:]
    runpy.run_path(str(target), run_name="__main__")


if __name__ == "__main__":
    main()

