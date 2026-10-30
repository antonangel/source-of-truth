#!/usr/bin/env python3
"""List the environment-specific facts a doc holds that a skill does not.

Usage:
    fact-diff.py <doc.md> <skill-dir-or-SKILL.md> [--quiet]

Exit 0 when the skill (SKILL.md plus every file in its references/) contains
all the paths, hosts, ids and command lines the doc states — the doc can be
replaced by a pointer. Exit 1 when facts are missing: migrate them into the
skill's references/ first, then stub.  Exit 2 on a usage error.

The point is that text similarity lies. Two docs describing one procedure in
different words can share under 10% of their tokens while carrying facts the
skill has never seen. Compare facts, not prose.
"""

import re
import sys
from pathlib import Path

TOKEN = re.compile(
    r"""
      (?P<path>(?:~|/)[A-Za-z0-9_.\-/]{6,})     # /abs/or/~/paths
    | (?P<ip>\b\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?\b)
    | (?P<host>\b[a-z0-9\-]+(?:\.[a-z0-9\-]+)+\.(?:is|local|lan|internal|com|org|io)\b)
    | (?P<id>\b[0-9a-f]{12,}\b)               # commit shas, job ids, digests
    | (?P<port>\b(?:listen|port)[ =:]\d{2,5}\b)
    """,
    re.X | re.I,
)

COMMAND = re.compile(
    r"^\s*(?:sudo\s+)?(?:docker|systemctl|ssh|nixos-|nix-|curl|wget|psql|sqlite3|"
    r"git|kubectl|helm|python3?|node|npm|pnpm|make|cargo|go)\b"
)


def norm(text: str) -> str:
    return re.sub(r"[`*\u2019'\"]", "", text).lower()


def skill_corpus(target: Path) -> str:
    if target.is_file():
        return target.read_text(errors="ignore")
    parts = []
    for p in sorted(target.rglob("*.md")):
        parts.append(p.read_text(errors="ignore"))
    return "\n".join(parts)


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if not a.startswith("--")]
    quiet = "--quiet" in argv
    if len(args) != 2:
        print(__doc__.strip().splitlines()[2].strip(), file=sys.stderr)
        return 2

    doc, target = Path(args[0]), Path(args[1])
    for p in (doc, target):
        if not p.exists():
            print(f"not found: {p}", file=sys.stderr)
            return 2

    doc_text = doc.read_text(errors="ignore")
    corpus = norm(skill_corpus(target))
    skill_name = (target.parent if target.name == "SKILL.md" else target).name

    tokens = {m.group(0) for m in TOKEN.finditer(doc_text)}
    commands = {
        line.strip() for line in doc_text.splitlines() if COMMAND.match(line)
    }

    # A pointer line names its own destination; that is not a missing fact.
    missing_tokens = sorted(
        t for t in tokens if norm(t) not in corpus and skill_name not in t
    )
    missing_commands = sorted(c for c in commands if norm(c)[:50] not in corpus)

    if not quiet:
        for t in missing_tokens:
            print(f"token   {t}")
        for c in missing_commands:
            print(f"command {c[:120]}")

    total = len(missing_tokens) + len(missing_commands)
    if total:
        print(
            f"UNSAFE to stub: {total} fact(s) missing "
            f"({len(missing_tokens)} tokens, {len(missing_commands)} commands)"
        )
        return 1

    print(f"safe to stub: all {len(tokens)} token(s) and {len(commands)} command(s) present")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
