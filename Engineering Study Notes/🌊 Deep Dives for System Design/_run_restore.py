#!/usr/bin/env python3
"""One-off: restore Apache Spark.md from git commit and run formatter."""

from __future__ import annotations

import importlib.util
from pathlib import Path

COMMIT = "4e09aba6d1e2c4a1261bf50fa4d951283df5e141"
REPO = Path("/Users/mchowdhury2/Documents/obsidian-notes")
REL_PATH = "Engineering Study Notes/🌊 Deep Dives for System Design/Apache Spark.md"
DIR = Path(__file__).resolve().parent
TARGET = DIR / "Apache Spark.md"
LOG = DIR / "_restore_result.txt"
FIX = DIR / "fix_apache_spark_formatting.py"


def load_module():
    spec = importlib.util.spec_from_file_location("fix_apache_spark", FIX)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def count_lines(text: str) -> int:
    if not text:
        return 0
    return text.count("\n") + (0 if text.endswith("\n") else 1)


def main() -> int:
    mod = load_module()
    before = TARGET.read_text(encoding="utf-8") if TARGET.exists() else ""
    before_lines = count_lines(before)

    source = mod.git_show_file(REPO, REL_PATH, COMMIT)
    source_name = f"git commit {COMMIT[:8]}"
    if not source or source.count("\n") < 100:
        source = mod.git_show_file(REPO, REL_PATH, "HEAD")
        source_name = "git HEAD"
    if not source or source.count("\n") < 100:
        source = mod.reconstruct_collapsed_newlines(before)
        source_name = "reconstructed local"

    _, body = mod.split_frontmatter(source)
    if not body:
        body = source

    cleaned_body = mod.process_body(body)
    cleaned = mod.FRONTMATTER + "\n" + cleaned_body.lstrip("\n")
    TARGET.write_text(cleaned, encoding="utf-8")

    after_lines = count_lines(cleaned)
    checks = [
        f"frontmatter_ok={cleaned.startswith('---\ntitle:')}",
        f"no_duplicate_h1={'# Apache Spark — Architecture, Data Modeling' not in cleaned.split('---', 2)[-1][:800]}",
        f"section_21_ok={'## 21.1' in cleaned}",
        f"answers_ok={'# 64. Answers' in cleaned}",
        f"answer_format_ok={'### 1. **B**' in cleaned}",
        f"no_chatgpt={'chatgpt.com' not in cleaned.lower()}",
    ]
    report = "\n".join(
        [
            f"source={source_name}",
            f"source_lines={count_lines(source)}",
            f"before_lines={before_lines}",
            f"after_lines={after_lines}",
            f"lines_removed={before_lines - after_lines}",
            *checks,
        ]
    )
    LOG.write_text(report + "\n", encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
