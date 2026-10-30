#!/usr/bin/env python3
"""List the environment-specific facts a doc holds that a skill does not.

Usage:
    fact-diff.py <doc.md> <skill-dir-or-SKILL.md> [--quiet]

Exit codes:
    0  no missing facts detected
    1  facts are missing: migrate them into the skill's references/ before stubbing
    2  usage error

**Exit 0 is necessary, not sufficient.** The script proves the skill contains every
path, host, id, env var, port and command line the doc states. It cannot tell you the
skill arranges them in a usable procedure, that the commands still work, or that the
doc's prose carried no meaning. Read the pair before you stub.

Why this exists: text similarity lies. Two docs describing one procedure in different
words can share a small fraction of their tokens while carrying facts the skill has
never seen. Compare facts, not prose.

Standard library only.
"""

import re
import sys
from pathlib import Path

TEXT_EXT = {
    ".md", ".markdown", ".txt", ".rst", ".py", ".sh", ".bash", ".zsh", ".fish",
    ".yml", ".yaml", ".json", ".toml", ".ini", ".cfg", ".conf", ".service",
    ".nix", ".rsc", ".env", ".js", ".ts", ".go", ".rs", ".rb", ".pl", ".ps1",
}
MAX_FILE = 2_000_000

# File extensions make a dotted token a filename, not a hostname.
FILE_EXT = {
    "md", "markdown", "txt", "rst", "py", "sh", "bash", "zsh", "yml", "yaml",
    "json", "toml", "ini", "cfg", "conf", "service", "nix", "rsc", "env", "js",
    "ts", "go", "rs", "rb", "pl", "log", "db", "sqlite", "html", "css", "png",
    "jpg", "jpeg", "svg", "pdf", "gz", "tar", "zip", "lock", "sum", "pem", "key",
}

PATH_RE = re.compile(r"(?<![\w./~-])(?:~|/)[A-Za-z0-9_.\-/]{3,}")
HOST_RE = re.compile(
    r"(?<![\w.-])((?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24})\b"
)
ID_RE = re.compile(r"\b[0-9a-f]{12,}\b")
ENV_RE = re.compile(r"(?<!\w)([A-Z][A-Z0-9_]{2,})=(?!=)")
PORT_RE = re.compile(r"(?::(\d{2,5})\b)|\bport[: ]+(\d{2,5})\b", re.I)
BACKTICK_RE = re.compile(r"`([^`\n]{2,160})`")
CMD_WORD_RE = re.compile(r"^[a-z][a-z0-9._+-]*$")


def norm(text: str) -> str:
    text = re.sub(r"[`*'\u2019\"]", "", text.lower())
    return re.sub(r"\s+", " ", text)


def as_command(line: str) -> str | None:
    line = line.strip().lstrip("$> ").strip().rstrip(".,;:")
    if not line or line.startswith(("#", "//", "-", "*")):
        return None
    if re.match(r"^[dl-][rwx-]{8,}\s", line):  # ls -l output, not a command
        return None
    words = line.split()
    if len(words) < 2 or (words[0] == "exit" and words[1] == "code"):
        return None
    head = words[0]
    if not CMD_WORD_RE.match(head) or head.endswith(":") or "=" in head:
        return None
    return line


def fenced_commands(text: str) -> set[str]:
    out, in_fence = set(), False
    for line in text.splitlines():
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            cmd = as_command(line)
            if cmd:
                out.add(cmd)
    return out


def inline_commands(text: str) -> set[str]:
    out = set()
    for m in BACKTICK_RE.finditer(text):
        cmd = as_command(m.group(1))
        if cmd:
            out.add(cmd)
    return out


def is_hostname(candidate: str) -> bool:
    if candidate.rsplit(".", 1)[-1] in FILE_EXT:
        return False
    if re.fullmatch(r"[\d.]+", candidate):
        return False
    return True


def extract(text: str) -> dict[str, set[str]]:
    paths = {m.group(0).rstrip(".,;:)]") for m in PATH_RE.finditer(text)}
    paths = {p for p in paths if not p.startswith("//")}  # URL, not a filesystem path

    hosts = set()
    for m in HOST_RE.finditer(text):
        candidate = m.group(1)
        # A camelCase dotted token is a config key, not a host.
        if candidate != candidate.lower():
            continue
        if m.start() > 0 and not text[m.start() - 1].isascii():
            continue
        tail = text[m.end():m.end() + 2]
        if len(tail) == 2 and tail[0] == "." and tail[1].isalnum():
            continue  # the dotted token continues; this is a prefix, not a host
        if is_hostname(candidate):
            hosts.add(candidate.lower())

    ports = set()
    for m in PORT_RE.finditer(text):
        value = m.group(1) or m.group(2)
        # "10:30" is a time; a port's colon is not preceded by a digit.
        if value and not (m.start() > 0 and text[m.start() - 1].isdigit()):
            ports.add(value)

    envs = {m.group(1) for m in ENV_RE.finditer(text)}
    ids = set(ID_RE.findall(text.lower()))
    commands = fenced_commands(text) | inline_commands(text)

    return {
        "path": paths, "host": hosts, "port": ports,
        "env": envs, "id": ids, "command": commands,
    }


def skill_corpus(target: Path) -> str:
    root = target.parent if target.name == "SKILL.md" else target
    chunks = []
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.suffix.lower() not in TEXT_EXT:
            continue
        try:
            if p.stat().st_size > MAX_FILE:
                continue
            chunks.append(p.read_text(errors="ignore"))
        except OSError:
            continue
    return norm("\n".join(chunks))


def present(corpus: str, value: str, kind: str) -> bool:
    needle = re.escape(norm(value))
    if kind == "path":
        return re.search(
            rf"(?<![\w./~-]){needle}(?![\w/_-])(?!\.[\w])", corpus
        ) is not None
    if kind == "host":
        return re.search(rf"(?<![\w.-]){needle}(?![\w-])(?!\.[\w])", corpus) is not None
    if kind == "env":
        return re.search(rf"(?<!\w){needle}=", corpus) is not None
    if kind == "port":
        return re.search(rf"(?<!\d){needle}(?!\d)", corpus) is not None
    if kind == "command":
        return re.search(rf"(?<!\w){needle}", corpus) is not None
    return re.search(rf"(?<!\w){needle}(?!\w)", corpus) is not None


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if not a.startswith("--")]
    quiet = "--quiet" in argv
    if len(args) != 2:
        print("usage: fact-diff.py <doc> <skill-dir-or-SKILL.md> [--quiet]", file=sys.stderr)
        return 2

    doc, target = Path(args[0]), Path(args[1])
    for p in (doc, target):
        if not p.exists():
            print(f"not found: {p}", file=sys.stderr)
            return 2

    doc_text = doc.read_text(errors="ignore")
    corpus = skill_corpus(target)
    skill_name = (target.parent if target.name == "SKILL.md" else target).name

    facts = extract(doc_text)
    total = sum(len(v) for v in facts.values())
    missing: list[tuple[str, str]] = []

    for kind, values in facts.items():
        for value in sorted(values):
            # A pointer line names its own destination; that is not a missing fact.
            if skill_name in value:
                continue
            if not present(corpus, value, kind):
                missing.append((kind, value))

    if not quiet:
        for kind, value in missing:
            print(f"{kind:<8} {value}")

    if missing:
        print(f"missing facts: {len(missing)} of {total} checked")
        return 1

    print(f"no missing facts detected ({total} checked)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
