#!/usr/bin/env python3
"""Inventory the Markdown docs in a repo: the numbers an audit starts from.

Usage:
    doc-inventory.py [repo-dir]

One row per Markdown file:
    lines    line count
    age_d    days since the file's mtime (unreliable after a fresh clone)
    inbound  other text files that mention its path, or its file name unless the name is
             generic (README.md, AGENTS.md, CLAUDE.md, SKILL.md, index.md)
    ips, ports, cmds   facts the doc states, as counted by fact-diff.py
    secrets  lines that look like secrets (a count; values are never printed)

Sorted by facts stated, most first: the docs most likely to be duplicated, or to rot, are at
the top. Zero inbound references does not mean dead: it may be a record.

Python 3.10+, standard library only.
"""

import importlib.util
import sys
import time
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "fact_diff", Path(__file__).resolve().parent / "fact-diff.py")
fd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fd)

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv"}
GENERIC = {"README.md", "AGENTS.md", "CLAUDE.md", "SKILL.md", "index.md"}
MARKDOWN = {".md", ".markdown"}


def read(path: Path) -> str:
    try:
        return "" if path.stat().st_size > fd.MAX_FILE else path.read_text(errors="ignore")
    except OSError:
        return ""


def main(argv: list[str]) -> int:
    root = Path(argv[1]) if len(argv) > 1 else Path(".")
    if len(argv) > 2 or not root.is_dir():
        print("usage: doc-inventory.py [repo-dir]", file=sys.stderr)
        return 2

    texts = {
        p: read(p) for p in sorted(root.rglob("*"))
        if p.is_file() and p.suffix.lower() in fd.TEXT_EXT | MARKDOWN
        and not SKIP_DIRS & set(p.relative_to(root).parts)
    }
    now, rows = time.time(), []
    for path, text in texts.items():
        if path.suffix.lower() not in MARKDOWN:
            continue
        rel = path.relative_to(root).as_posix()
        needles = [rel] if path.name in GENERIC else [rel, path.name]
        inbound = sum(1 for other, body in texts.items()
                      if other != path and any(n in body for n in needles))
        facts = fd.extract(text)
        rows.append((
            len(text.splitlines()), int((now - path.stat().st_mtime) / 86400), inbound,
            len(facts["ip"]), len(facts["port"]), len(facts["command"]),
            len(fd.secret_lines(text)), rel,
        ))

    rows.sort(key=lambda r: (-(r[3] + r[4] + r[5]), r[7]))
    print(f"{'lines':>6} {'age_d':>6} {'inbound':>8} {'ips':>4} {'ports':>6} {'cmds':>5} "
          f"{'secrets':>8}  path")
    for lines, age, inbound, ips, ports, cmds, secrets, rel in rows:
        print(f"{lines:>6} {age:>6} {inbound:>8} {ips:>4} {ports:>6} {cmds:>5} {secrets:>8}  {rel}")
    orphans = sum(1 for r in rows if r[2] == 0)
    with_secrets = sum(1 for r in rows if r[6])
    print(f"\n{len(rows)} docs, {with_secrets} with possible secrets, "
          f"{orphans} with no inbound references")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
