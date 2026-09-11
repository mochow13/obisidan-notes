#!/usr/bin/env python3
"""Bulk formatting cleanup for Apache Spark.md (ChatGPT export cleanup)."""

from __future__ import annotations

import re
import sys
import zlib
from pathlib import Path

REPO = Path("/Users/mchowdhury2/Documents/obsidian-notes")
REL_PATH = "Engineering Study Notes/🌊 Deep Dives for System Design/Apache Spark.md"
FILE = Path(__file__).with_name("Apache Spark.md")

FRONTMATTER = """---
title: "Apache Spark — Architecture, Data Modeling, S3, and Production System Design"
aliases:
  - Apache Spark Deep Dive
  - Spark Staff+ Architecture
  - Spark on S3
tags:
  - distributed-systems
  - apache-spark
  - data-engineering
  - system-design
  - s3
  - streaming
  - staff-plus
created: 2026-09-11
updated: 2026-09-11
spark_version_scope: "Apache Spark 4.2.0"
status: evergreen
---
"""

LIST_ITEM_RE = re.compile(r"^(\s*)([-*+]|\d+\.)\s")
BLOCKQUOTE_RE = re.compile(r"^>\s?")
CHATGPT_LINK_RE = re.compile(
    r"\[([^\]]*)\]\((?:https?://)?(?:www\.)?chatgpt\.com[^)]*\)"
)
CHATGPT_BARE_RE = re.compile(r"https?://(?:www\.)?chatgpt\.com\S*")
ANSWER_HEADING_RE = re.compile(r"^#{2,3} Q(\d+)\s*[—-]\s*([A-D])\s*$")
SECTION_21_RE = re.compile(r"^# (21\.\d+\. .+)$")
DUPLICATE_TITLE = (
    "# Apache Spark — Architecture, Data Modeling, S3, and Production System Design"
)


def is_list_item(line: str) -> bool:
    return bool(LIST_ITEM_RE.match(line))


def is_blockquote(line: str) -> bool:
    return bool(BLOCKQUOTE_RE.match(line))


def is_empty_blockquote(line: str) -> bool:
    return bool(re.match(r"^>\s*$", line))


def read_git_object(repo: Path, sha: str) -> bytes:
    obj_path = repo / ".git" / "objects" / sha[:2] / sha[2:]
    if obj_path.exists():
        return zlib.decompress(obj_path.read_bytes())
    # packed objects not handled; caller may fall back
    raise FileNotFoundError(f"git object not found: {sha}")


def parse_tree_entries(data: bytes) -> list[tuple[str, str, str]]:
    header_end = data.index(b"\0") + 1
    body = data[header_end:]
    entries: list[tuple[str, str, str]] = []
    i = 0
    while i < len(body):
        space = body.index(b" ", i)
        mode = body[i:space].decode()
        nul = body.index(b"\0", space)
        name = body[space + 1 : nul].decode()
        sha = body[nul + 1 : nul + 21].hex()
        entries.append((mode, name, sha))
        i = nul + 21
    return entries


def git_show_file(repo: Path, rel_path: str, ref: str = "HEAD") -> str | None:
    """Return file contents at ref using pure-Python git object reads."""
    try:
        if re.fullmatch(r"[0-9a-f]{40}", ref):
            commit_sha = ref
        elif (repo / ".git" / ref).exists():
            commit_sha = (repo / ".git" / ref).read_text(encoding="utf-8").strip()
        else:
            ref_path = repo / ".git" / "refs" / "heads" / ref
            if not ref_path.exists():
                return None
            commit_sha = ref_path.read_text(encoding="utf-8").strip()

        commit_data = read_git_object(repo, commit_sha)
        tree_sha = re.search(rb"tree ([0-9a-f]{40})", commit_data).group(1).decode()

        parts = rel_path.split("/")
        current_sha = tree_sha
        for part in parts:
            tree_data = read_git_object(repo, current_sha)
            found = None
            for _mode, name, sha in parse_tree_entries(tree_data):
                if name == part:
                    found = sha
                    break
            if found is None:
                return None
            current_sha = found

        blob_data = read_git_object(repo, current_sha)
        nul = blob_data.index(b"\0")
        return blob_data[nul + 1 :].decode("utf-8")
    except Exception:
        return None


def reconstruct_collapsed_newlines(text: str) -> str:
    """Best-effort recovery when a bad replace_all removed all newlines."""
    if text.count("\n") > 50:
        return text

    text = text.replace("---title:", "---\ntitle:")
    text = re.sub(r"(aliases|tags):\s{2}-", r"\1:\n  -", text)
    text = re.sub(
        r"(staff-plus)(created|updated|spark_version_scope|status)",
        r"\1\n\2",
        text,
    )
    text = text.replace('status: evergreen---', "status: evergreen\n---")

    # Horizontal rules before headings
    text = re.sub(r"---(#{1,3}\s)", r"---\n\n\1", text)

    # Major section headings (# N. ...)
    text = re.sub(r"([.!?])(# \d+\.\s)", r"\1\n\n\2", text)
    text = re.sub(r"([.!?])(## \d+\.\d+)", r"\1\n\n\2", text)

    # Subheadings after prose
    text = re.sub(r"([.!?])(### )", r"\1\n\n\3", text)
    text = re.sub(r"([.!?])(## )", r"\1\n\n\2", text)

    # Callouts and blockquotes
    text = re.sub(r"([.!?])(> \[!)", r"\1\n\n\2", text)
    text = re.sub(r"(>)(\[!)", r"\1\n\2")
    text = re.sub(r"(>)(> )", r"\1\n\2", text)
    text = re.sub(r"(>)(>)$", r"\1\n\2", text)

    # Code fences
    text = re.sub(r"([.!?])(```)", r"\1\n\n\2", text)
    text = re.sub(r"(```)([a-z]+)", r"\1\n\2", text)
    text = re.sub(r"(```)([A-Za-z])", r"\1\n\2", text)

    # Paragraph breaks before list items that lost leading "- Xx" from bad joins
    fixes = [
        (r"\.erations\b", ".\n- Operations"),
        (r"\.gh-throughput\b", ".\n- High-throughput"),
        (r"\.termediate\b", ".\n- Intermediate"),
        (r"\.gnificant\b", ".\n- Significant"),
        (r"\.rkloads\b", ".\n- Workloads"),
        (r"\.cal uses\b", ".\n\nTypical uses"),
        (r"include:- Batch", "include:\n\n- Batch"),
        (r"\.rge-scale\b", ".\n- Large-scale"),
        (r"\.ta-lake\b", ".\n- Data-lake"),
        (r"\.storical\b", ".\n- Historical"),
        (r"\.C processing\b", ".\n- ETL/CDC processing"),
        (r"\.ssionization\b", ".\n- Sessionization"),
        (r"\.reaming\b", ".\n- Streaming"),
        (r"\.g/event\b", ".\n- Log/event"),
        (r"\.k is usually\b", ".\n\nSpark is usually"),
        (r"\.int reads\b", ".\n- Point reads"),
        (r"\.b-millisecond\b", ".\n- Sub-millisecond"),
        (r"\.ne-grained\b", ".\n- Fine-grained"),
        (r"\.stributed\b", ".\n- Distributed"),
        (r"\.ny workloads\b", ".\n- Many workloads"),
        (r"\.tip\]", ".\n\n> [!tip]"),
        (r";de-effect-free", ";\n- side-effect-free"),
        (r";arse-grained", ";\n- coarse-grained"),
        (r";producible", ";\n- reproducible"),
        (r"\.orks badly\b", ".\n\nWorks badly"),
        (r";intaining\b", ";\n- maintaining"),
        (r";nstructing\b", ";\n- constructing"),
        (r";heduling\b", ";\n- scheduling"),
        (r";viding\b", ";\n- dividing"),
        (r";ordinating\b", ";\n- coordinating"),
        (r";llecting\b", ";\n- collecting"),
        (r";ceiving\b", ";\n- receiving"),
        (r";rform\b", ";\n- perform"),
        (r";ad source\b", ";\n- read source"),
        (r";oduce\b", ";\n- produce"),
        (r";tch\b", ";\n- fetch"),
        (r";che\b", ";\n- cache"),
        (r";ill\b", ";\n- spill"),
        (r";mmunicate\b", ";\n- communicate"),
        (r"\.iple tasks\b", ".\n\nMultiple tasks"),
        (r";ge task\b", ";\n- large task"),
        (r";ragglers\b", ";\n- stragglers"),
        (r";mory pressure\b", ";\n- memory pressure"),
        (r";ny files\b", ";\n- many files"),
        (r";cessive metadata\b", ";\n- excessive metadata"),
        (r";cessive remote\b", ";\n- excessive remote"),
        (r"\.correct partition\b", ".\n\nThe correct partition"),
        (r";roupBy", ";\n- `groupBy`"),
        (r";istinct", ";\n- `distinct`"),
        (r";partitioning", ";\n- repartitioning"),
        (r";rting", ";\n- sorting"),
        (r";ny aggregations", ";\n- many aggregations"),
        (r"\.fle is expensive\b", ".\n\nShuffle is expensive"),
        (r";artitioning records", ";\n- partitioning records"),
        (r";orting/aggregation", ";\n- sorting/aggregation"),
        (r";ocal disk", ";\n- local disk"),
        (r";etwork transfer", ";\n- network transfer"),
        (r";educe-side", ";\n- reduce-side"),
        (r";eserialization", ";\n- deserialization"),
        (r";dditional in-memory", ";\n- additional in-memory"),
        (r";pill and merge", ";\n- spill and merge"),
        (r"\.k's RDD\b", ".\n\nSpark's RDD"),
        (r"; function for computing", ";\n- a compute function for computing"),
        (r";ependencies on parent", ";\n- dependencies on parent"),
        (r";ptionally, a partitioner", ";\n- optionally, a partitioner"),
        (r";ptionally, preferred locations", ";\n- optionally, preferred locations"),
        (r"\. is an exceptionally\b", ".\n\nThis is an exceptionally"),
        (r";e-aggregation", ";\n- pre-aggregation"),
        (r";edicate pushdown", ";\n- predicate pushdown"),
        (r";ojection pushdown", ";\n- projection pushdown"),
        (r";rtial aggregation", ";\n- partial aggregation"),
        (r";cal filtering", ";\n- local filtering"),
        (r";oom filters", ";\n- bloom filters"),
        (r";p-side joins", ";\n- map-side joins"),
        (r"\. 8\. DataFrame\b", ".\n\n---\n\n# 8. DataFrame"),
        (r";edicates", ";\n- predicates"),
        (r";ouping keys", ";\n- grouping keys"),
        (r";gregate expressions", ";\n- aggregate expressions"),
        (r";ta types", ";\n- data types"),
        (r";in predicates", ";\n- join predicates"),
        (r"\. knowledge lets\b", ".\n\nThis knowledge lets"),
        (r";sh filters", ";\n- push filters"),
        (r";order or select", ";\n- reorder or select"),
        (r";oose join", ";\n- choose join"),
        (r";verage statistics", ";\n- leverage statistics"),
        (r";nerate optimized", ";\n- generate optimized"),
        (r";apt portions", ";\n- adapt portions"),
        (r"\. an opaque\b", ".\n\nAgainst an opaque"),
        (r";lumns", ";\n- columns"),
        (r";nctions", ";\n- functions"),
        (r";ojection pruning", ";\n- projection pruning"),
        (r";nstant folding", ";\n- constant folding"),
        (r";lter movement", ";\n- filter movement"),
        (r";rt-merge join", ";\n- sort-merge join"),
        (r";uffled hash join", ";\n- shuffled hash join"),
        (r";ans", ";\n- scans"),
        (r";changes", ";\n- exchanges"),
        (r";sh aggregation", ";\n- hash aggregation"),
        (r";duced Python", ";\n- reduced Python"),
        (r";tter memory", ";\n- better memory"),
        (r";che-aware", ";\n- cache-aware"),
        (r";nerated code", ";\n- generated code"),
        (r"\. explains an important\b", ".\n\nThis explains an important"),
        (r";lter pushdown", ";\n- filter pushdown"),
        (r";gregate pushdown", ";\n- aggregate pushdown"),
        (r";rtitioning", ";\n- partitioning"),
        (r";dering", ";\n- ordering"),
        (r";talog operations", ";\n- catalog operations"),
        (r";lumnar scans", ";\n- columnar scans"),
        (r";w-level operations", ";\n- row-level operations"),
        (r";reaming integration", ";\n- streaming integration"),
        (r"\.itecturally:", ".\n\nArchitecturally:"),
        (r";plicit predicates", ";\n- explicit predicates"),
        (r";ntrolled partitioned", ";\n- controlled partitioned"),
        (r";te limits", ";\n- rate limits"),
        (r";tracts/CDC", ";\n- contracts/CDC"),
        (r"\. 12\. Partitioning", ".\n\n---\n\n# 12. Partitioning"),
        (r";tadata", ";\n- metadata"),
        (r";le count", ";\n- file count"),
        (r";sting cost", ";\n- listing cost"),
        (r";mmit overhead", ";\n- commit overhead"),
        (r"# 12\.3 Streaming", "\n\n## 12.3 Streaming"),
        (r";ecutor memory", ";\n- executor memory"),
        (r";twork", ";\n- network"),
        (r"# 15\.2 Sort-merge", "\n\n## 15.2 Sort-merge"),
        (r";ew partition handling", ";\n- skew partition handling"),
        (r";anging certain join", ";\n- changing certain join"),
        (r";timizing skewed", ";\n- optimizing skewed"),
        (r"\.e-aggregation", ".\n- pre-aggregation"),
        (r"\.lt hot keys", ".\n- salt hot keys"),
        (r"\.olate known", ".\n- isolate known"),
        (r"\.oadcast the opposite", ".\n- broadcast the opposite"),
        (r"\.ange the data model", ".\n- change the data model"),
        (r"\.e two-phase", ".\n- use two-phase"),
        (r"\.ple salting", ".\n- simple salting"),
        (r";sk scheduling", ";\n- task scheduling"),
        (r";le opening", ";\n- file opening"),
        (r";ble metadata", ";\n- table metadata"),
        (r";iver planning", ";\n- driver planning"),
        (r";oter reads", ";\n- footer reads"),
        (r";mmit overhead\.actical", ";\n- commit overhead.\n\nA practical"),
        (r";unded throughput", ";\n- bounded throughput"),
        (r";rge task working", ";\n- large task working"),
        (r";ngle-straggler", ";\n- single-straggler"),
        (r"\.an be valid\b", ".\n\nIt can be valid"),
        (r";ansactional table", ";\n- transactional table"),
        (r";chive packaging", ";\n- archive packaging"),
        (r";tabase load", ";\n- database load"),
        (r";rtitioned export", ";\n- partitioned export"),
        (r"\. 21\. Spark on Amazon S3", ".\n\n---\n\n# 21. Spark on Amazon S3"),
        (r";ansactional multi-file", ";\n- transactional multi-file"),
        (r";w-level update", ";\n- row-level update"),
        (r";ncurrent writer", ";\n- concurrent writer"),
        (r";hema history", ";\n- schema history"),
        (r";apshot rollback", ";\n- snapshot rollback"),
        (r"\.dern table abstraction\b", ".\n\nA modern table abstraction"),
        (r";twork charges", ";\n- network charges"),
        (r";roughput variability", ";\n- throughput variability"),
        (r"\?at happens", "?\n- What happens"),
        (r"\? it discarded", "?\n  - Is it discarded"),
        (r"\?n reports", "?\n- Can reports"),
        (r"\?w does a replay", "?\n- How does a replay"),
        (r"\. 27\. Streaming State", ".\n\n---\n\n# 27. Streaming State"),
        (r";duplication", ";\n- deduplication"),
        (r";ream-stream joins", ";\n- stream-stream joins"),
        (r";bitrary keyed", ";\n- arbitrary keyed"),
        (r"\.e changes the resource\b", ".\n\nThis changes the resource"),
        (r";mmit information", ";\n- commit information"),
        (r";erator state", ";\n- operator state"),
        (r";ery metadata", ";\n- query metadata"),
        (r"\.t it like durable\b", ".\n\nTreat it like durable"),
        (r";arch engine", ";\n- search engine"),
        (r";y/value store", ";\n- key/value store"),
        (r";AP serving engine", ";\n- OLAP serving engine"),
        (r";ecomputed cache", ";\n- precomputed cache"),
        (r"\.er than launch\b", ".\n\nrather than launch"),
        (r";urce bugs", ";\n- source bugs"),
        (r";richment changes", ";\n- enrichment changes"),
        (r";d deployments", ";\n- bad deployments"),
        (r";storical corrections", ";\n- historical corrections"),
        (r"\. 32\. Replayability", ".\n\n---\n\n# 32. Replayability"),
        (r";g correction", ";\n- bug correction"),
        (r";gration validation", ";\n- migration validation"),
        (r";saster recovery", ";\n- disaster recovery"),
        (r";terministic comparison", ";\n- deterministic comparison"),
        (r";ature regeneration", ";\n- feature regeneration"),
        (r"\.taff\+ level, replay\b", ".\n\nAt Staff+ level, replay"),
        (r";unded concurrency", ";\n- bounded concurrency"),
        (r";parate checkpoints", ";\n- separate checkpoints"),
        (r"; request pressure", ";\n- S3 request pressure"),
        (r";talog load", ";\n- catalog load"),
        (r";wnstream write amplification", ";\n- downstream write amplification"),
        (r";ble commit frequency", ";\n- table commit frequency"),
        (r";A isolation", ";\n- SLA isolation"),
        (r"important\]  >", "> [!important]\n>"),
        (r";ins", ";\n- joins"),
        (r";rting", ";\n- sorting"),
        (r";gregation", ";\n- aggregation"),
        (r";rtain shared blocks", ";\n- certain shared blocks"),
        (r"\.k 4\.2 defaults", ".\n\nSpark 4.2 defaults"),
        (r";ched data", ";\n- cached data"),
        (r";M/user objects", ";\n- JVM/user objects"),
        (r";amework metadata", ";\n- framework metadata"),
        (r";thon workers", ";\n- Python workers"),
        (r";f-heap/native", ";\n- off-heap/native"),
        (r";ffers", ";\n- buffers"),
        (r"\.k:", ".\n\nThink:"),
        (r"\. 36\. Caching", ".\n\n---\n\n# 36. Caching"),
        (r";ict more valuable", ";\n- evict more valuable"),
        (r";mpete with execution", ";\n- compete with execution"),
        (r";crease GC", ";\n- increase GC"),
        (r";terialize data", ";\n- materialize data"),
        (r";uffle tracking", ";\n- shuffle tracking"),
        (r";commissioning with shuffle-block", ";\n- decommissioning with shuffle-block"),
        (r";itable custom", ";\n- suitable custom"),
        (r"\.k 4\.2 has shuffle tracking\b", ".\n\nSpark 4.2 has shuffle tracking"),
        (r";ss of cached blocks", ";\n- loss of cached blocks"),
        (r";uffle recovery", ";\n- shuffle recovery"),
        (r";computation", ";\n- recomputation"),
        (r";duced capacity", ";\n- reduced capacity"),
        (r";raggler duration", ";\n- straggler duration"),
        (r";age completion latency", ";\n- stage completion latency"),
        (r"# 40\.4 Step 4", "\n\n## 40.4 Step 4"),
        (r";uffle read/write", ";\n- shuffle read/write"),
        (r";tch wait", ";\n- batch wait"),
        (r";ill", ";\n- spill"),
        (r";put bytes", ";\n- input bytes"),
        (r";tput bytes", ";\n- output bytes"),
        (r"; time", ";\n- GC time"),
        (r";tries", ";\n- retries"),
        (r";cality", ";\n- locality"),
        (r";ew", ";\n- skew"),
        (r"\.eful alert\b", ".\n\nA useful alert"),
        (r";mory use", ";\n- memory use"),
        (r";M GC", ";\n- JVM GC"),
        (r";cal-disk pressure", ";\n- local-disk pressure"),
        (r";uffle service behavior", ";\n- shuffle service behavior"),
        (r";sk failure rate", ";\n- task failure rate"),
        (r"# 41\.4 Driver health", "\n\n## 41.4 Driver health"),
        (r"# 41\.5 Structured Streaming", "\n\n## 41.5 Structured Streaming"),
        (r";sk/event backlog", ";\n- task/event backlog"),
        (r";ery planning time", ";\n- query planning time"),
        (r";talog/listing latency", ";\n- catalog/listing latency"),
        (r";mber of tasks/files", ";\n- number of tasks/files"),
        (r";oadcast construction", ";\n- broadcast construction"),
        (r";ocessing rate", ";\n- processing rate"),
        (r";put rows", ";\n- output rows"),
        (r";tch duration", ";\n- batch duration"),
        (r";eration duration", ";\n- operation duration"),
        (r";termark gap", ";\n- watermark gap"),
        (r";ate rows", ";\n- state rows"),
        (r";ate memory", ";\n- state memory"),
        (r";ws removed by watermark", ";\n- rows removed by watermark"),
        (r"\.ationally, also track:", ".\n\nOperationally, also track:"),
        (r";parate read/write roles", ";\n- separate read/write roles"),
        (r";cket policy", ";\n- bucket policy"),
        (r";S permissions", ";\n- KMS permissions"),
        (r";dit logging", ";\n- audit logging"),
        (r";edential rotation", ";\n- credential rotation"),
        (r"; access", ";\n- network access"),
        (r";ent-log sensitivity", ";\n- event-log sensitivity"),
        (r"\.k itself supports\b", ".\n\nSpark itself supports"),
        (r";mespaces", ";\n- namespaces"),
        (r";de pools", ";\n- node pools"),
        (r";rkload classes", ";\n- workload classes"),
        (r";counts/clusters", ";\n- accounts/clusters"),
        (r";nding on blast-radius", ";\n- depending on blast-radius"),
        (r";wer startup overhead", ";\n- lower startup overhead"),
        (r";eful for interactive", ";\n- useful for interactive"),
        (r"\.s:- noisy", ".\n\nDisadvantages:\n\n- noisy"),
        (r";brary/version coupling", ";\n- library/version coupling"),
        (r";ng-lived state", ";\n- long-lived state"),
        (r";curity complexity", ";\n- security complexity"),
        (r";erational drift", ";\n- operational drift"),
        (r"\.phemeral application-oriented\b", ".\n\n### Ephemeral application-oriented"),
        (r";producibility", ";\n- reproducibility"),
        (r";dependent dependencies", ";\n- independent dependencies"),
        (r";eaner teardown", ";\n- cleaner teardown"),
        (r";sier cost attribution", ";\n- easier cost attribution"),
        (r"\.s:- startup latency", ".\n\nDisadvantages:\n\n- startup latency"),
        (r";age/dependency distribution", ";\n- image/dependency distribution"),
        (r";ntrol-plane pressure", ";\n- control-plane pressure"),
        (r"\.mmon production preference\b", ".\n\nA common production preference"),
        (r";dependent resource sizing", ";\n- independent resource sizing"),
        (r";eckpoint boundaries", ";\n- checkpoint boundaries"),
        (r";parate deployability", ";\n- separate deployability"),
        (r";earer ownership", ";\n- clearer ownership"),
        (r";chestration complexity", ";\n- orchestration complexity"),
        (r";artup overhead", ";\n- startup overhead"),
        (r";terialization latency", ";\n- materialization latency"),
        (r"\.right boundary\b", ".\n\nThe right boundary"),
        (r"\?o owns the schema", "?\n- Who owns the schema"),
        (r"\?n downstream consumers", "?\n- Can downstream consumers"),
        (r"\?at is its retention", "?\n- What is its retention"),
        (r"\? it transactionally published", "?\n- Is it transactionally published"),
        (r"\?at quality guarantees", "?\n- What quality guarantees"),
        (r"\.ot create layers\b", ".\n\nDo not create layers"),
        (r";apshot expiration", ";\n- snapshot expiration"),
        (r";phan cleanup", ";\n- orphan cleanup"),
        (r";atistics", ";\n- statistics"),
        (r";tadata maintenance", ";\n- metadata maintenance"),
        (r";hema evolution", ";\n- schema evolution"),
        (r"\. 52\. Schema Evolution", ".\n\n---\n\n# 52. Schema Evolution"),
        (r"\?n old and new readers", "?\n- Can old and new readers"),
        (r"\?ll historical partitions", "?\n- Will historical partitions"),
        (r"\?es the table format", "?\n- Does the table format"),
        (r"\?ll downstream consumers", "?\n- Will downstream consumers"),
        (r"\? rollback possible", "?\n- Is rollback possible"),
        (r"\?er additive evolution", "?\n- Prefer additive evolution"),
        (r";timizer choices", ";\n- optimizer choices"),
        (r";nnector behavior", ";\n- connector behavior"),
        (r";ble integrations", ";\n- table integrations"),
        (r";ructured Streaming compatibility", ";\n- Structured Streaming compatibility"),
        (r"\.he maintains component-specific\b", ".\n\nApache maintains component-specific"),
        (r";plicit retry units", ";\n- explicit retry units"),
        (r";ntrolled storage pressure", ";\n- controlled storage pressure"),
        (r";sier progress accounting", ";\n- easier progress accounting"),
        (r";edictable parallelism", ";\n- predictable parallelism"),
        (r"\?% of executors disappear", "?\n- 50% of executors disappear"),
        (r"\?e driver disappears", "?\n- the driver disappears"),
        (r"\? throttles requests", "?\n- S3 throttles requests"),
        (r"\?fka is unavailable", "?\n- Kafka is unavailable"),
        (r"\?talog is unavailable", "?\n- catalog is unavailable"),
        (r"\?rget table commit fails", "?\n- target table commit fails"),
        (r"\?e key becomes", "?\n- one key becomes"),
        (r"\?2-year backfill begins", "?\n- a 2-year backfill begins"),
        (r"\. 59\. Production Heuristics", ".\n\n---\n\n# 59. Production Heuristics"),
        (r";ew;", ";\n- skew;"),
        (r";orage throughput", ";\n- storage throughput"),
        (r";twork;", ";\n- network;"),
        (r";e huge task", ";\n- one huge task"),
        (r";iver planning", ";\n- driver planning"),
        (r";wnstream service", ";\n- downstream service"),
        (r";uffle fetch", ";\n- shuffle fetch"),
        (r";rial phases", ";\n- materialization phases"),
        (r"# \"S3 is eventually consistent", "\n\n## \"S3 is eventually consistent"),
        (r"\?at fraction is scanned", "?\n- What fraction is scanned"),
        (r"\?at is the largest expected key", "?\n- What is the largest expected key"),
        (r"\? data bounded or unbounded", "?\n- Is data bounded or unbounded"),
        (r"\?at freshness SLA exists", "?\n- What freshness SLA exists"),
        (r"\?at creates storage partitions", "?\n- What creates storage partitions"),
        (r"\?e any keys highly skewed", "?\n- Are any keys highly skewed"),
        (r"\?n partition counts adapt", "?\n- Can partition counts adapt"),
        (r"\?w many bytes cross the network", "?\n- How many bytes cross the network"),
        (r"\? local pre-aggregation possible", "?\n- Is local pre-aggregation possible"),
        (r"\?n storage partitioning eliminate exchanges", "?\n- Can storage partitioning eliminate exchanges"),
        (r"\?e table/column statistics available", "?\n- Are table/column statistics available"),
        (r"\? either side safely broadcastable", "?\n- Is either side safely broadcastable"),
        (r"\?at happens when a dimension suddenly grows 20×", "?\n- What happens when a dimension suddenly grows 20×"),
        (r"\?at are typical file sizes", "?\n- What are typical file sizes"),
        (r"\?e writes using an object-store-safe commit protocol", "?\n- Are writes using an object-store-safe commit protocol"),
        (r"\? a transactional table format required", "?\n- Is a transactional table format required"),
        (r"\?at happens under S3 request throttling", "?\n- What happens under S3 request throttling"),
        (r"\?at is the sink's retry behavior", "?\n- What is the sink's retry behavior"),
        (r"\?at determines state retention", "?\n- What determines state retention"),
        (r"\?at is the late-data policy", "?\n- What is the late-data policy"),
        (r"\?w large can the checkpoint/state store grow", "?\n- How large can the checkpoint/state store grow"),
        (r"\?at is the unit of idempotency", "?\n- What is the unit of idempotency"),
        (r"\?at happens after driver failure", "?\n- What happens after driver failure"),
        (r"\?n a partially published output be read", "?\n- Can a partially published output be read"),
        (r"\?ich metrics identify skew", "?\n- Which metrics identify skew"),
        (r"\?n you distinguish compute saturation from S3 saturation", "?\n- Can you distinguish compute saturation from S3 saturation"),
        (r"\?w is a failed partition/date replayed", "?\n- How is a failed partition/date replayed"),
        (r"\?n old and new jobs coexist", "?\n- Can old and new jobs coexist"),
        (r"\?w are streaming checkpoints migrated", "?\n- How are streaming checkpoints migrated"),
        (r"\?w are large backfills isolated", "?\n- How are large backfills isolated"),
        (r"\. 62\. Key Takeaways", ".\n\n---\n\n# 62. Key Takeaways"),
        (r"\.he driver is Spark's application control plane", ".\n2. The driver is Spark's application control plane"),
        (r"\.ctions create jobs", ".\n3. Actions create jobs"),
        (r"\.artitions define parallel work", ".\n4. Partitions define parallel work"),
        (r"\.DD lineage trades", ".\n5. RDD lineage trades"),
        (r"\.ataFrame/SQL gives", ".\n6. DataFrame/SQL gives"),
        (r"\.huffle is one of the central", ".\n7. Shuffle is one of the central"),
        (r"\.ata skew must be modeled", ".\n8. Data skew must be modeled"),
        (r"\.hysical data layout is part", ".\n9. Physical data layout is part"),
        (r"\. 66\. Further Questions", ".\n\n---\n\n# 66. Further Questions"),
        (r"\?w does Spark's map-output tracking", "?\n- How does Spark's map-output tracking"),
        (r"\?w should shuffle architecture change", "?\n- How should shuffle architecture change"),
        (r"\? what scale does driver-side file planning", "?\n- At what scale does driver-side file planning"),
        (r"\?w should Spark and Trino/Presto coexist", "?\n- How should Spark and Trino/Presto coexist"),
        (r"\?w do Iceberg, Delta Lake, and Hudi differ", "?\n- How do Iceberg, Delta Lake, and Hudi differ"),
        (r"\?w should one model S3 request cost", "?\n- How should one model S3 request cost"),
        (r"\?at is the best architecture for replaying petabytes", "?\n- What is the best architecture for replaying petabytes"),
        (r"\?en should streaming state move", "?\n- When should streaming state move"),
        (r"\?at invariants are required to make `foreachBatch`", "?\n- What invariants are required to make `foreachBatch`"),
        (r"\?w can storage partitioning and Spark's Storage Partition Join", "?\n- How can storage partitioning and Spark's Storage Partition Join"),
        (r"\?at correctness tests are necessary before changing a partition transform", "?\n- What correctness tests are necessary before changing a partition transform"),
        (r"\?w should Spark jobs expose data lineage", "?\n- How should Spark jobs expose data lineage"),
        (r"\?en is Flink a better streaming engine", "?\n- When is Flink a better streaming engine"),
        (r"\?en is a dedicated distributed SQL engine preferable", "?\n- When is a dedicated distributed SQL engine preferable"),
        (r"## Q(\d+)", r"\n\n## Q\1"),
        (r"### Q(\d+) — ([A-D])", r"\n\n### Q\1 — \2"),
        (r"---## Q", r"\n\n---\n\n## Q"),
        (r"---# 64\. Answers", r"\n\n---\n\n# 64. Answers"),
        (r"---# 65\.", r"\n\n---\n\n# 65."),
        (r"---# 66\.", r"\n\n---\n\n# 66."),
        (r"## Primary Apache Spark material-", r"\n\n## Primary Apache Spark material\n\n-"),
        (r"oundational research-", r"\n\n### Foundational research\n\n-"),
        (r"3 / Hadoop primary material-", r"\n\n### S3 / Hadoop primary material\n\n-"),
        (r"able formats-", r"\n\n### Table formats\n\n-"),
        (r"Guide\*\*:", "Guide**: "),
        (r"definitions\.Apache", "definitions.\n- **Apache"),
        (r"aggregations\.Apache", "aggregations.\n- **Apache"),
        (r"properties\.Apache", "properties.\n- **Apache"),
        (r"execution\.Apache", "execution.\n- **Apache"),
        (r"Join\.Apache", "Join.\n- **Apache"),
        (r"overhead\.Apache", "overhead.\n- **Apache"),
        (r"semantics\.Apache", "semantics.\n- **Apache"),
        (r"logs\.Apache", "logs.\n- **Apache"),
        (r"controls\.oundational", "controls.\n\n### Foundational"),
        (r"model\.Armbrust", "model.\n- **Armbrust"),
        (r"Catalyst\.Armbrust", "Catalyst.\n- **Armbrust"),
        (r"model\.Apache Spark Project Tungsten", "model.\n- **Apache Spark Project Tungsten"),
        (r"generation\.3 / Hadoop", "generation.\n\n### S3 / Hadoop"),
        (r"semantics\.Hadoop", "semantics.\n- **Hadoop"),
        (r"performance\.Hadoop", "performance.\n- **Hadoop"),
        (r"them\.Hadoop", "them.\n- **Hadoop"),
        (r"guidance\.able formats", "guidance.\n\n### Table formats"),
        (r"rename\.Apache Iceberg Structured", "rename.\n- **Apache Iceberg Structured"),
        (r"workloads\.Delta Lake", "workloads.\n- **Delta Lake"),
        (r"requirements\. 66\.", "requirements.\n\n---\n\n# 66."),
    ]
    for pattern, repl in fixes:
        text = re.sub(pattern, repl, text)

    # Quiz answer options
    text = re.sub(r"(\?)(A\. )", r"\1\n\nA. ", text)
    text = re.sub(r"(  )(B\. )", r"\n\nB. ", text)
    text = re.sub(r"(  )(C\. )", r"\n\nC. ", text)
    text = re.sub(r"(  )(D\. )", r"\n\nD. ", text)

    return text


def strip_chatgpt_artifacts(text: str) -> str:
    text = CHATGPT_LINK_RE.sub(r"\1", text)
    text = re.sub(r"\[↩\]\([^)]*chatgpt[^)]*\)", "", text, flags=re.IGNORECASE)
    text = CHATGPT_BARE_RE.sub("", text)
    text = re.sub(r"\s+\]", "]", text)
    return text


def split_frontmatter(text: str) -> tuple[str | None, str]:
    if not text.startswith("---"):
        return None, text
    end = text.find("\n---", 3)
    if end == -1:
        return None, text
    body_start = end + 4
    if body_start < len(text) and text[body_start] == "\n":
        body_start += 1
    return text[: body_start], text[body_start:]


def strip_trailing_whitespace(lines: list[str]) -> list[str]:
    return [line.rstrip() for line in lines]


def remove_whitespace_only_lines(lines: list[str]) -> list[str]:
    return ["" if line.strip() == "" and line != "" else line for line in lines]


def tighten_list_spacing(lines: list[str]) -> list[str]:
    """Remove blank lines ONLY between consecutive list items."""
    if not lines:
        return lines

    result: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.strip() == "" and result:
            prev = result[-1]
            j = i + 1
            while j < len(lines) and lines[j].strip() == "":
                j += 1
            nxt = lines[j] if j < len(lines) else ""
            if is_list_item(prev) and is_list_item(nxt):
                i += 1
                continue
        result.append(line)
        i += 1
    return result


def tighten_callout_spacing(lines: list[str]) -> list[str]:
    result: list[str] = []
    for line in lines:
        if is_empty_blockquote(line) and result and is_blockquote(result[-1]):
            j = len(result) - 1
            while j >= 0 and is_blockquote(result[j]):
                if is_list_item(
                    result[j][1:].lstrip()
                    if result[j].startswith(">")
                    else result[j]
                ):
                    break
                j -= 1
            else:
                result.append(line)
                continue
            continue
        result.append(line)
    return result


def normalize_headings(lines: list[str]) -> list[str]:
    out: list[str] = []
    for line in lines:
        m21 = SECTION_21_RE.match(line)
        if m21:
            out.append(f"## {m21.group(1)}")
            continue
        m_ans = ANSWER_HEADING_RE.match(line)
        if m_ans:
            qnum, letter = m_ans.groups()
            out.append(f"### {int(qnum)}. **{letter}**")
            continue
        out.append(line)
    return out


def remove_duplicate_title(lines: list[str]) -> list[str]:
    out: list[str] = []
    removed = False
    for line in lines:
        if not removed and line.strip() == DUPLICATE_TITLE:
            removed = True
            continue
        out.append(line)
    return out


def collapse_excessive_blank_lines(lines: list[str], max_run: int = 2) -> list[str]:
    result: list[str] = []
    blank_run = 0
    for line in lines:
        if line.strip() == "":
            blank_run += 1
            if blank_run <= max_run:
                result.append("")
        else:
            blank_run = 0
            result.append(line)
    return result


def normalize_answer_key_heading(lines: list[str]) -> list[str]:
    out: list[str] = []
    for line in lines:
        if line.strip() == "# 64. Answer Key":
            out.append("# 64. Answers")
        else:
            out.append(line)
    return out


def process_body(body: str) -> str:
    body = strip_chatgpt_artifacts(body)
    lines = body.splitlines()
    lines = strip_trailing_whitespace(lines)
    lines = remove_whitespace_only_lines(lines)
    lines = remove_duplicate_title(lines)
    lines = normalize_headings(lines)
    lines = normalize_answer_key_heading(lines)
    lines = tighten_list_spacing(lines)
    lines = tighten_callout_spacing(lines)
    lines = collapse_excessive_blank_lines(lines)
    text = "\n".join(lines)
    if text and not text.endswith("\n"):
        text += "\n"
    return text


def load_source_text() -> tuple[str, str]:
    """Return (text, source_description)."""
    git_text = git_show_file(REPO, REL_PATH)
    if git_text and git_text.count("\n") > 100:
        return git_text, "git HEAD"

    if FILE.exists():
        local = FILE.read_text(encoding="utf-8")
        if local.count("\n") > 100:
            return local, "local file"
        return reconstruct_collapsed_newlines(local), "reconstructed local file"

    raise FileNotFoundError(f"Could not load {FILE}")


def main() -> int:
    if not FILE.exists():
        print(f"File not found: {FILE}", file=sys.stderr)
        return 1

    original = FILE.read_text(encoding="utf-8")
    before_lines = original.count("\n") + (0 if original.endswith("\n") else 1)

    try:
        source_text, source = load_source_text()
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 1

    print(f"Source: {source}")

    _, body = split_frontmatter(source_text)
    if body == source_text:
        body = source_text
        if body.startswith("---"):
            body = split_frontmatter(body)[1]

    cleaned_body = process_body(body)
    cleaned = FRONTMATTER + "\n" + cleaned_body.lstrip("\n")
    FILE.write_text(cleaned, encoding="utf-8")

    after_lines = cleaned.count("\n") + (0 if cleaned.endswith("\n") else 1)
    print(f"File: {FILE}")
    print(f"Before lines: {before_lines}")
    print(f"After lines: {after_lines}")
    print(f"Lines removed: {before_lines - after_lines}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
