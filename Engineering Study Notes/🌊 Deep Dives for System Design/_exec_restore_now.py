#!/usr/bin/env python3
"""One-off: load_source from commit + process_body -> Apache Spark.md + log."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

COMMIT = "4e09aba6d1e2c4a1261bf50fa4d951283df5e141"
DIR = Path(__file__).resolve().parent
FIX = DIR / "fix_apache_spark_formatting.py"
TARGET = DIR / "Apache Spark.md"
LOG = DIR / "_restore_result.txt"


def load_mod():
    spec = importlib.util.spec_from_file_location("fix", FIX)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def count_lines(text: str) -> int:
    if not text:
        return 0
    return text.count("\n") + (0 if text.endswith("\n") else 1)


def main() -> int:
    mod = load_mod()
    before = TARGET.read_text(encoding="utf-8") if TARGET.exists() else ""
    before_lines = count_lines(before)

    source = mod.git_show_file(mod.REPO, mod.REL_PATH, COMMIT)
    src_name = f"git:{COMMIT[:8]}"
    if not source or source.count("\n") < 100:
        source = mod.git_show_file(mod.REPO, mod.REL_PATH, "HEAD")
        src_name = "git:HEAD"
    if not source or source.count("\n") < 100:
        source, src_name = mod.load_source_text()
        src_name = f"load_source_text:{src_name}"

    _, body = mod.split_frontmatter(source)
    if not body.strip():
        body = source

    cleaned_body = mod.process_body(body)
    cleaned = mod.FRONTMATTER + "\n" + cleaned_body.lstrip("\n")
    TARGET.write_text(cleaned, encoding="utf-8")

    after_lines = count_lines(cleaned)
    checks = {
        "source": src_name,
        "source_lines": count_lines(source),
        "before_lines": before_lines,
        "after_lines": after_lines,
        "frontmatter_ok": cleaned.startswith("---\ntitle:"),
        "no_dup_h1": cleaned.count("# Apache Spark — Architecture") <= 1,
        "section_21_ok": "## 21.1" in cleaned,
        "answers_ok": "# 64. Answers" in cleaned,
        "answer_fmt_ok": "### 1. **B**" in cleaned,
        "no_chatgpt": "chatgpt.com" not in cleaned.lower(),
    }
    report = "\n".join(f"{k}={v}" for k, v in checks.items()) + "\n"
    LOG.write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
