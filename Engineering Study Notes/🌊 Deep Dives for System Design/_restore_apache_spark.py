#!/usr/bin/env python3
"""Restore Apache Spark.md from git HEAD, then run formatting cleanup."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

FIX_SCRIPT = Path(__file__).with_name("fix_apache_spark_formatting.py")


def main() -> int:
    if not FIX_SCRIPT.exists():
        print(f"Missing formatter: {FIX_SCRIPT}", file=sys.stderr)
        return 1
    return int(runpy.run_path(str(FIX_SCRIPT), run_name="__main__")["main"]())


if __name__ == "__main__":
    raise SystemExit(main())
