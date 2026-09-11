#!/usr/bin/env python3
"""Inline restore: read git commit blob, format, write Apache Spark.md + _restored_output.md"""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

COMMIT = "4e09aba6d1e2c4a1261bf50fa4d951283df5e141"
REPO = Path("/Users/mchowdhury2/Documents/obsidian-notes")
REL = "Engineering Study Notes/🌊 Deep Dives for System Design/Apache Spark.md"
DIR = Path(__file__).resolve().parent
TARGET = DIR / "Apache Spark.md"
OUT = DIR / "_restored_output.md"
LOG = DIR / "_restore_result.txt"
FIX = DIR / "fix_apache_spark_formatting.py"


def load():
    spec = importlib.util.spec_from_file_location("fix", FIX)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def count_lines(text: str) -> int:
    return 0 if not text else text.count("\n") + (0 if text.endswith("\n") else 1)


def main():
    mod = load()
    before = TARGET.read_text(encoding="utf-8") if TARGET.exists() else ""
    before_lines = count_lines(before)

    source = mod.git_show_file(REPO, REL, COMMIT)
    src_name = f"git:{COMMIT[:8]}"
    if not source or source.count("\n") < 100:
        source = mod.git_show_file(REPO, REL, "HEAD")
        src_name = "git:HEAD"
    if not source or source.count("\n") < 100:
        source = mod.reconstruct_collapsed_newlines(before)
        src_name = "reconstructed"

    _, body = mod.split_frontmatter(source)
    if not body.strip():
        body = source
    cleaned_body = mod.process_body(body)
    cleaned = mod.FRONTMATTER + "\n" + cleaned_body.lstrip("\n")

    TARGET.write_text(cleaned, encoding="utf-8")
    OUT.write_text(cleaned, encoding="utf-8")

    after_lines = count_lines(cleaned)
    report = "\n".join(
        [
            f"source={src_name}",
            f"source_lines={count_lines(source)}",
            f"before_lines={before_lines}",
            f"after_lines={after_lines}",
            f"frontmatter_ok={cleaned.startswith('---\\ntitle:')}",
            f"section_21_ok={'## 21.1' in cleaned}",
            f"answers_ok={'# 64. Answers' in cleaned}",
            f"answer_fmt_ok={'### 1. **B**' in cleaned}",
            f"no_chatgpt={'chatgpt.com' not in cleaned.lower()}",
        ]
    )
    LOG.write_text(report + "\n", encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
