#!/usr/bin/env python3
"""List the environment-specific facts a doc holds that a skill does not.

Usage:
    fact-diff.py <doc.md> <skill-dir-or-SKILL.md> [--quiet]

Exit codes:
    0  no missing facts detected
    1  facts are missing: migrate them into the skill's references/ before stubbing
    2  usage error

**Exit 0 is necessary, not sufficient.** The script proves the skill contains every
path, host, ip, id, env var, port and command line the doc states. It cannot tell you
the skill arranges them in a usable procedure, that the commands still work, or that the
doc's prose carried no meaning. Read the pair before you stub.

Why this exists: text similarity lies. Two docs describing one procedure in different
words can share a small fraction of their tokens while carrying facts the skill has
never seen. Compare facts, not prose.

Standard library only.

Known limitations:
- Config keys and parameters are not extracted (only env vars of the form NAME=value).
- Exit 0 is necessary, not sufficient: the script compares facts, not usefulness.
- Inline backtick prose heuristic uses a stopword head list; a phrase whose first
  token is not a stopword (e.g. "run tests") may be misclassified as a command.
  Fenced blocks are unaffected.
- A doc command that is a prefix of a longer skill command counts as present when
  followed by whitespace/args (boundary blocks mid-token continuation only).
- Port context matching is textual; a bare number in prose is not treated as a port.
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

PATH_RE = re.compile(r"(?<![\w./~-])(?:~|/)[A-Za-z0-9_.\-/]{3,}(?![\w./~-])")

IPV4_RE = re.compile(
    r"(?<![\w./-])"
    r"(?:25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])"
    r"\.(?:25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])"
    r"\.(?:25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])"
    r"\.(?:25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])"
    r"(?![\w./-])"
)
HOST_RE = re.compile(
    r"(?<![\w.-])((?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24})"
    r"(?![\w-])"
    r"(?!\.[\w])"
)
ID_RE = re.compile(r"\b[0-9a-f]{12,}\b")
ENV_RE = re.compile(r"(?<!\w)([A-Z][A-Z0-9_]{2,})=(?!=)")
PORT_RE = re.compile(
    r":(\d{2,5})"
    r"|\bport[: ]+(\d{2,5})\b"
    r"|\blisten[: ]+(\d{2,5})\b"
    r"|\b(\d{2,5}):(\d{2,5})\b",
    re.I,
)
BACKTICK_RE = re.compile(r"`([^`\n]{2,160})`")
CMD_WORD_RE = re.compile(r"^[a-z][a-z0-9._+-]*$")
INLINE_STOPWORDS = {
    "the", "a", "an", "see", "docs", "this", "that", "these", "those",
    "read", "view", "check", "note", "above", "below", "here", "there",
}


def norm(text: str) -> str:
    text = re.sub(r"[`*'\u2019\"]", "", text.lower())
    return re.sub(r"\s+", " ", text)


def is_file_ext(candidate: str) -> bool:
    parts = candidate.split(".")
    if not parts:
        return False
    return parts[-1] in FILE_EXT


def looks_like_version(candidate: str) -> bool:
    return bool(re.fullmatch(r"^[vV]?(0|[1-9]\d*)(\.(0|[1-9]\d*)){0,2}$", candidate))


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
        if not cmd:
            continue
        head = cmd.split()[0].lower()
        if head in INLINE_STOPWORDS:
            continue
        out.add(cmd)
    return out


def is_hostname(candidate: str) -> bool:
    if is_file_ext(candidate):
        return False
    if re.fullmatch(r"[\d.]+\b", candidate):
        return False
    if looks_like_version(candidate):
        return False
    if re.fullmatch(r"\d+:\d+\b", candidate):
        return False
    return True


def extract(text: str) -> dict[str, set[str]]:
    paths = {m.group(0).rstrip(".,;:)]") for m in PATH_RE.finditer(text)}
    paths = {p for p in paths if not p.startswith("//")}  # URL, not a filesystem path

    hosts = set()
    for m in HOST_RE.finditer(text):
        candidate = m.group(1)
        if candidate != candidate.lower():
            continue
        if m.start() > 0 and not text[m.start() - 1].isascii():
            continue
        tail = text[m.end():m.end() + 2]
        if len(tail) == 2 and tail[0] == "." and tail[1].isalnum():
            continue  # the dotted token continues; this is a prefix, not a host
        if is_hostname(candidate):
            hosts.add(candidate.lower())

    ips = {m.group(0) for m in IPV4_RE.finditer(text)}

    ports = set()
    for m in PORT_RE.finditer(text):
        if m.group(1) is not None:
            value = m.group(1)
            colon_idx = m.start()
            k = colon_idx - 1
            while k >= 0 and text[k].isdigit():
                k -= 1
            hour = text[k + 1:colon_idx]
            prev_char = text[k] if k >= 0 else ""
            is_time = (
                hour.isdigit()
                and 1 <= len(hour) <= 2
                and len(value) == 2
                and (prev_char == "" or prev_char.isspace() or prev_char in "([")
            )
            if not is_time:
                ports.add(value)
        else:
            if m.group(4) is not None and m.group(5) is not None:
                if re.fullmatch(r"\d{1,2}:\d{2}", m.group(0)):
                    continue
            for g in m.groups()[1:]:
                if g is not None:
                    ports.add(g)

    envs = {m.group(1) for m in ENV_RE.finditer(text)}
    ids = set(ID_RE.findall(text.lower()))
    commands = fenced_commands(text) | inline_commands(text)

    return {
        "path": paths, "host": hosts, "ip": ips, "port": ports,
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
    if kind == "ip":
        return re.search(rf"(?<![\w.]){needle}(?![\w.])", corpus) is not None
    if kind == "env":
        return re.search(rf"(?<!\w){needle}=", corpus) is not None
    if kind == "port":
        patterns = [
            rf":{needle}(?!\d)",
            rf"\bport[: ]+{needle}\b",
            rf"\blisten[: ]+{needle}\b",
            rf"\b{needle}:{needle}\b",
            rf"\b{needle}:\d{{2,5}}\b",
            rf"\b\d{{2,5}}:{needle}\b",
        ]
        return any(re.search(p, corpus, re.I) for p in patterns)
    if kind == "command":
        return re.search(rf"(?<!\w){needle}(?![\w/-])(?!\.\w)", corpus) is not None
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
