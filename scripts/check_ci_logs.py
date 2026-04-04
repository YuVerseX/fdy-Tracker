"""在 CI 中扫描测试日志，遇到已知危险模式直接失败。"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


DEFAULT_FORBIDDEN_PATTERNS = [
    ("unique_constraint", re.compile(r"UNIQUE constraint failed", re.IGNORECASE)),
    ("sqlalchemy_warning", re.compile(r"\bSAWarning\b")),
    ("python_traceback", re.compile(r"Traceback \(most recent call last\):")),
    ("asgi_exception", re.compile(r"Exception in ASGI application")),
    ("async_task_exception", re.compile(r"Task exception was never retrieved")),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="扫描 CI 日志中的危险模式")
    parser.add_argument("logfile", help="待扫描的日志文件路径")
    parser.add_argument("--label", default="ci-log", help="日志标签，便于输出定位")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    log_path = Path(args.logfile)
    if not log_path.exists():
        print(f"[{args.label}] 日志文件不存在: {log_path}", file=sys.stderr)
        return 2

    content = log_path.read_text(encoding="utf-8", errors="replace")
    hits: list[tuple[int, str, str]] = []
    for line_number, line in enumerate(content.splitlines(), start=1):
        for pattern_name, pattern in DEFAULT_FORBIDDEN_PATTERNS:
            if pattern.search(line):
                hits.append((line_number, pattern_name, line.strip()))

    if not hits:
        print(f"[{args.label}] 日志扫描通过，未发现危险模式。")
        return 0

    print(f"[{args.label}] 发现 {len(hits)} 处危险日志，CI 失败：", file=sys.stderr)
    for line_number, pattern_name, line in hits[:20]:
        print(f"  - line {line_number} [{pattern_name}] {line}", file=sys.stderr)
    if len(hits) > 20:
        print(f"  - ... 其余 {len(hits) - 20} 处命中已省略", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
