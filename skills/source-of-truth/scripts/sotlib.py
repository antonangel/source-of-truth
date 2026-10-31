#!/usr/bin/env python3
"""Extraction and classification engine for the source-of-truth fact checker.

Every literal fact the checker reports is produced here: paths, hosts, IPs, ports, env vars, ids and
command lines, plus the secret tripwire, the append-only record classifier, the markdown census and
inbound-reference counting. No argument parsing and no output formatting live in this module;
`sot.py` dispatches to it and owns the CLI contract (ADR 0001).

Precision beats recall: when a number cannot be told apart from a status code, a clock, a date
fragment or an IPv6 octet it is suppressed rather than guessed at, and the suppression is counted so
a clean run cannot hide it.

Python 3.10+, standard library only.
"""

import bisect
import fnmatch
import os
import re
import subprocess
import sys
import time
from collections import namedtuple
from pathlib import Path

KINDS = ("path", "host", "ip", "port", "env", "id", "command")
PROFILES = {
    "skill": KINDS,
    "config": ("path", "host", "ip", "port", "env"),
}
EXIT_CLEAN, EXIT_MISSING, EXIT_USAGE, EXIT_SECRET = 0, 1, 2, 3

TEXT_EXT = {
    ".md", ".markdown", ".txt", ".rst", ".py", ".sh", ".bash", ".zsh", ".fish",
    ".yml", ".yaml", ".json", ".toml", ".ini", ".cfg", ".conf", ".service",
    ".nix", ".rsc", ".env", ".js", ".ts", ".go", ".rs", ".rb", ".pl", ".ps1",
}
MAX_FILE = 2_000_000

# Application data and build output are not documentation. `data` catches the docker/data volume
# trees that made a real 885-doc homelab read 1 GB of hashlists.
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "data", "vendor", "dist",
             "result"}
GENERIC_NAMES = {"README.md", "AGENTS.md", "CLAUDE.md", "SKILL.md", "index.md"}

FILE_EXT = {
    "md", "markdown", "txt", "rst", "py", "sh", "bash", "zsh", "yml", "yaml",
    "json", "toml", "ini", "cfg", "conf", "service", "nix", "rsc", "env", "js",
    "ts", "go", "rs", "rb", "pl", "log", "db", "sqlite", "html", "css", "png",
    "jpg", "jpeg", "svg", "pdf", "gz", "tar", "zip", "lock", "sum", "pem", "key",
}

PATH_RE = re.compile(r"(?<![\w./~-])(?:~|/)[A-Za-z0-9_.\-/]{3,}(?![\w./~-])")

_OCTET = r"(?:25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])"
IPV4_RE = re.compile(
    rf"(?<![\w.-])({_OCTET}(?:\.{_OCTET}){{3}}(?:/(?:3[0-2]|[12]?[0-9]))?)(?![\w-])(?!\.\w)"
)
HOST_RE = re.compile(
    r"(?<![\w.-])((?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24})"
    r"(?![\w-])"
    r"(?!\.[\w])"
)
ID_RE = re.compile(r"\b[0-9a-f]{12,}\b")
ENV_RE = re.compile(r"(?<!\w)([A-Z][A-Z0-9_]{2,})=(?!=)")
ENV_YAML_RE = re.compile(r"(?<!\w)([A-Z][A-Z0-9_]{2,}):\s+\S")
ENV_STOPWORDS = {"NOTE", "TODO", "WARNING", "FIXME", "SEE", "HTTP", "HTTPS", "SSH",
                 "TCP", "UDP", "URL", "API", "ID", "IP", "DNS", "TLS", "SSL", "LAN",
                 "WAN", "CIDR", "CPU", "RAM", "GPU", "OS"}

# Two or more colon-separated hex groups is an IPv6 address (or a clock, or a MAC). One colon is a
# host:port pair, which is why this cannot be a single-colon pattern.
IPV6_RE = re.compile(r"(?<![\w:])[0-9A-Fa-f]{0,4}(?::[0-9A-Fa-f]{0,4}){2,}(?:/[0-9]{1,3})?")
CLOCK_RE = re.compile(r"(?<![\w.])(?:[01]?\d|2[0-3]):[0-5]\d(?::[0-5]\d)?(?!\w)")

PORT_KEYWORD_RE = re.compile(r"\b(?:port|listen|expose|publish)\s*[:=]?\s*(\d{2,5})\b", re.I)
PORT_FLAG_RE = re.compile(r"(?:--port|-p)\s+(\d{2,5})\b")
PORT_MAP_RE = re.compile(r"(?<![\w.])(\d{2,5}):(\d{2,5})(?:/(?:tcp|udp))?(?!\w)(?!\.\w)", re.I)
PORT_COLON_RE = re.compile(r":(\d{2,5})\b")
PORT_CONTEXT_RE = re.compile(r"(?:-p\b|--publish\b|publish\b|ports?\s*:|expose\b)", re.I)

BACKTICK_RE = re.compile(r"`([^`\n]{2,160})`")
CMD_WORD_RE = re.compile(r"^[a-z][a-z0-9._+-]*$")
INLINE_STOPWORDS = {
    "the", "a", "an", "see", "docs", "this", "that", "these", "those",
    "read", "view", "check", "note", "above", "below", "here", "there",
}

CRED_RE = re.compile(
    r"\w*(?:pass(?:word|wd|phrase)?|secret|token|api[_-]?key|apikey|psk|private[_-]?key"
    r"|auth[_-]?key)\w*[\"']?\s*[:=]\s*[\"']?(<[^>\n]*>|[^\s\"',;]+)",
    re.I,
)
PLACEHOLDER_RE = re.compile(
    r"^(?:<[^>]*>|\$\{?\w*\}?|\{\{.*|\.{2,}|x{3,}|\*{3,}|changeme|change-me|your[-_\w]*"
    r"|example|redacted|placeholder|todo|none|null|true|false|required|secret|password|token)$",
    re.I,
)
SECRET_PATTERNS = (
    ("private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("token", re.compile(
        r"\b(?:ghp_|gho_|ghs_|github_pat_|glpat-|xox[baprs]-|tskey-[a-z]+-)[A-Za-z0-9_-]{8,}"
        r"|\bAKIA[0-9A-Z]{16}\b|\bsk-[A-Za-z0-9_-]{20,}")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}")),
    ("url credentials", re.compile(r"://[^/\s:@]+:[^/\s@]+@")),
)

RECORD_PATH_PARTS = {"audits", "plans", "adr", "adrs", "changelog", "incidents",
                     "proposals", "records", "audit", "plan"}
RECORD_MARKERS = ("append-only", "append only", "record:", "this is a record")


# --------------------------------------------------------------------------- text helpers

def norm(text: str) -> str:
    text = re.sub(r"[`*'\u2019\"]", "", text.lower())
    return re.sub(r"\s+", " ", text)


def line_starts(text: str) -> list[int]:
    starts = [0]
    starts.extend(m.end() for m in re.finditer("\n", text))
    return starts


def line_at(starts: list[int], pos: int) -> int:
    return bisect.bisect_right(starts, pos)


def fence_spans(text: str) -> list[tuple[int, int]]:
    spans, offset, start = [], 0, None
    for line in text.splitlines(keepends=True):
        if line.strip().startswith("```"):
            if start is None:
                start = offset + len(line)
            else:
                spans.append((start, offset))
                start = None
        offset += len(line)
    if start is not None:
        spans.append((start, offset))
    return spans


def in_code_context(text: str, pos: int, fences: list[tuple[int, int]]) -> bool:
    if any(start <= pos < end for start, end in fences):
        return True
    return pos > 0 and text[pos - 1] in "\"'`"


def blocked_spans(text: str, fences: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Regions where a number is not a port: IPv6 literals, and clocks outside code.

    A clock inside a fence or a backtick is a port mapping, not a time: `"22:22"` publishes 22.
    """
    spans = [(m.start(), m.end()) for m in IPV6_RE.finditer(text)]
    spans.extend((m.start(), m.end()) for m in CLOCK_RE.finditer(text)
                 if not in_code_context(text, m.start(), fences))
    spans.sort()
    return spans


def in_spans(spans: list[tuple[int, int]], pos: int) -> bool:
    i = bisect.bisect_right(spans, (pos, sys.maxsize)) - 1
    return i >= 0 and spans[i][0] <= pos < spans[i][1]


# --------------------------------------------------------------------------- ports

def _colon_is_port(text: str, colon_pos: int, value: str) -> bool:
    """A `:N` counts as a port only when its left side is address-shaped.

    Precision beats recall here: `http_status:404` is a status code, and calling it a port is the
    kind of wrong line that makes an operator stop reading the output.
    """
    i = colon_pos
    while i > 0 and (text[i - 1].isalnum() or text[i - 1] in "._-[]"):
        i -= 1
    token = text[i:colon_pos]
    if not token:
        return False
    number = int(value)
    if token == "localhost":
        return True
    if token.startswith("[") or token.endswith("]"):
        return True                                    # bracketed IPv6 literal
    if re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", token):
        return True                                    # IPv4 literal
    if text[max(0, i - 4):i].endswith("://"):
        return True                                    # a URL authority accepts any port
    return number >= 1024                              # a name: only when it cannot be a status code


def find_ports(text: str) -> tuple[dict[str, int], int]:
    """Return ({port: first position}, suppressed candidate count).

    Candidates from four patterns are merged and swept in source order, longest-first at equal
    starts, so `-p 8080:80` is decided as one mapping and the `:80` inside it is never re-decided.
    A linear sweep matters: the previous keep-a-list-and-scan design was quadratic per document.
    """
    fences = fence_spans(text)
    spans = blocked_spans(text, fences)

    candidates: list[tuple[int, int, str, tuple[int, ...], tuple[str, ...]]] = []
    for m in PORT_KEYWORD_RE.finditer(text):
        candidates.append((m.start(), m.end(), "single", (m.start(1),), (m.group(1),)))
    for m in PORT_FLAG_RE.finditer(text):
        candidates.append((m.start(), m.end(), "single", (m.start(1),), (m.group(1),)))
    for m in PORT_MAP_RE.finditer(text):
        candidates.append((m.start(), m.end(), "map", (m.start(1), m.start(2)),
                           (m.group(1), m.group(2))))
    for m in PORT_COLON_RE.finditer(text):
        candidates.append((m.start(), m.end(), "colon", (m.start(1),), (m.group(1),)))
    candidates.sort(key=lambda c: (c[0], -(c[1] - c[0])))

    ports: dict[str, int] = {}
    suppressed = 0
    cursor = -1

    def add(value: str, pos: int) -> None:
        if int(value) <= 65535 and value not in ports:
            ports[value] = pos

    for start, end, kind, positions, values in candidates:
        if start < cursor:
            continue                                   # inside a decision already made
        cursor = end
        if any(in_spans(spans, p) for p in positions):
            suppressed += 1
            continue
        if kind == "single":
            add(values[0], positions[0])
        elif kind == "map":
            context = (in_code_context(text, start, fences)
                       or PORT_CONTEXT_RE.search(text[max(0, start - 60):start]))
            if context:
                add(values[0], positions[0])
                add(values[1], positions[1])
            else:
                suppressed += 1
        elif _colon_is_port(text, start, values[0]):
            add(values[0], positions[0])
        else:
            suppressed += 1

    return ports, suppressed


# --------------------------------------------------------------------------- commands

def as_command(line: str) -> str | None:
    line = line.strip().lstrip("$> ").strip()
    line = re.sub(r"\s+#.*$", "", line).rstrip(".,;:")
    if not line or line.startswith(("#", "//", "-", "*")):
        return None
    if re.match(r"^[dl-][rwx-]{8,}\s", line):
        return None
    words = line.split()
    if len(words) < 2 or (words[0] == "exit" and words[1] == "code"):
        return None
    head = words[0]
    if not CMD_WORD_RE.match(head) or head.endswith(":") or "=" in head:
        return None
    return line


def fenced_commands(text: str) -> dict[str, int]:
    out: dict[str, int] = {}
    starts = line_starts(text)
    in_fence, pending, pending_start = False, "", 0
    offset = 0

    def flush(candidate: str, pos: int) -> None:
        cmd = as_command(candidate)
        if cmd:
            out.setdefault(cmd, line_at(starts, pos))

    for line in text.splitlines(keepends=True):
        if line.strip().startswith("```"):
            if pending:
                flush(pending, pending_start)
            in_fence, pending = not in_fence, ""
            offset += len(line)
            continue
        if not in_fence:
            offset += len(line)
            continue
        stripped = line.rstrip("\n").rstrip()
        if not pending:
            pending_start = offset
        if stripped.endswith("\\"):
            pending += stripped[:-1].strip() + " "
        else:
            flush(pending + stripped.strip() if pending else stripped, pending_start)
            pending = ""
        offset += len(line)
    if pending:
        flush(pending, pending_start)
    return out


def inline_commands(text: str) -> dict[str, int]:
    out: dict[str, int] = {}
    starts = line_starts(text)
    for m in BACKTICK_RE.finditer(text):
        cmd = as_command(m.group(1))
        if cmd and cmd.split()[0].lower() not in INLINE_STOPWORDS:
            out.setdefault(cmd, line_at(starts, m.start()))
    return out


# --------------------------------------------------------------------------- extraction

def is_file_ext(candidate: str) -> bool:
    return candidate.split(".")[-1] in FILE_EXT


def looks_like_version(candidate: str) -> bool:
    return bool(re.fullmatch(r"[vV]?(0|[1-9]\d*)(\.(0|[1-9]\d*)){0,2}", candidate))


def is_hostname(candidate: str) -> bool:
    if is_file_ext(candidate) or looks_like_version(candidate):
        return False
    return not re.fullmatch(r"[\d.]+", candidate)


SYSTEM_ROOTS = {"etc", "srv", "var", "home", "opt", "usr", "nix", "tmp", "root", "run", "dev",
                "proc", "sys", "mnt", "media", "boot", "bin", "sbin", "lib", "lib64", "snap"}


def is_path_fact(value: str) -> bool:
    """A route, a config key or a URL fragment is not a filesystem path.

    Without this, `https://host/v1/config` and a backticked `/reconcile` endpoint both read as
    paths, and a run against a config directory fills with facts nobody can act on.
    """
    if value.startswith("~"):
        return value == "~" or value[1:2] == "/"
    if not value.startswith("/"):
        return False
    segments = [s for s in value.split("/") if s]
    if not segments:
        return False
    if "." in segments[-1] and not segments[-1].endswith("."):
        return True
    return segments[0] in SYSTEM_ROOTS


def extract(text: str) -> dict[str, dict[str, int]]:
    """Return {kind: {value: line}} for every fact kind, always all seven keys."""
    starts = line_starts(text)

    def put(store: dict[str, int], value: str, pos: int) -> None:
        store.setdefault(value, line_at(starts, pos))

    paths: dict[str, int] = {}
    for m in PATH_RE.finditer(text):
        value = m.group(0).rstrip(".,;:)]")
        if not value.startswith("//") and is_path_fact(value):
            put(paths, value, m.start())

    hosts: dict[str, int] = {}
    for m in HOST_RE.finditer(text):
        candidate = m.group(1)
        if candidate != candidate.lower():
            continue
        if m.start() > 0 and not text[m.start() - 1].isascii():
            continue
        tail = text[m.end():m.end() + 2]
        if len(tail) == 2 and tail[0] == "." and tail[1].isalnum():
            continue
        if is_hostname(candidate):
            put(hosts, candidate.lower(), m.start())

    ips: dict[str, int] = {}
    for m in IPV4_RE.finditer(text):
        put(ips, m.group(1), m.start())

    envs: dict[str, int] = {}
    for m in ENV_RE.finditer(text):
        put(envs, m.group(1), m.start())
    for m in ENV_YAML_RE.finditer(text):
        name = m.group(1)
        if name not in ENV_STOPWORDS:
            put(envs, name, m.start())

    raw_ports, _ = find_ports(text)
    ports = {value: line_at(starts, pos) for value, pos in raw_ports.items()}

    ids: dict[str, int] = {}
    for m in ID_RE.finditer(text.lower()):
        put(ids, m.group(0), m.start())

    commands = fenced_commands(text)
    for cmd, line in inline_commands(text).items():
        commands.setdefault(cmd, line)

    return {
        "path": paths,
        "host": hosts,
        "ip": ips,
        "port": ports,
        "env": envs,
        "id": ids,
        "command": commands,
    }


# --------------------------------------------------------------------------- matching

def secret_lines(text: str) -> list[tuple[int, str]]:
    found = []
    for number, line in enumerate(text.splitlines(), 1):
        kind = next((k for k, rx in SECRET_PATTERNS if rx.search(line)), None)
        if kind is None:
            for m in CRED_RE.finditer(line):
                value = m.group(1).strip("\"'")
                if len(value) >= 4 and not PLACEHOLDER_RE.match(value):
                    kind = "credential assignment"
                    break
        if kind:
            found.append((number, kind))
    return found


def is_record(doc_path, text: str) -> bool:
    try:
        parts = {part.lower() for part in Path(doc_path).parts}
    except Exception:
        parts = set()
    if parts & RECORD_PATH_PARTS:
        return True
    name = Path(doc_path).name.lower()
    if re.match(r"^\d{4}[-_]", name):
        return True
    low = text.lower()
    return any(m in low for m in RECORD_MARKERS)


def skill_corpus(target: Path) -> str:
    root = target.parent if target.name == "SKILL.md" else target
    chunks = []
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.suffix.lower() not in TEXT_EXT:
            continue
        try:
            if p.stat().st_size > MAX_FILE:
                continue
            text = p.read_text(errors="ignore")
        except OSError:
            continue
        if p.suffix.lower() in {".yml", ".yaml"}:
            text = re.sub(r"(?m)^(\s*)([A-Z][A-Z0-9_]{2,}):\s", r"\1\2=", text)
        if p.suffix.lower() == ".nix":
            text = re.sub(r"([A-Z][A-Z0-9_]{2,})\s+=\s+", r"\1=", text)
        chunks.append(re.sub(r"\\[ \t]*\r?\n[ \t]*", " ", text))
    return norm("\n".join(chunks))


def present(corpus: str, value: str, kind: str) -> bool:
    needle = re.escape(norm(value))
    if kind == "path":
        return re.search(rf"(?<![\w./~-]){needle}(?![\w/_-])(?!\.[\w])", corpus) is not None
    if kind == "host":
        return re.search(rf"(?<![\w.-]){needle}(?![\w-])(?!\.[\w])", corpus) is not None
    if kind == "ip":
        return re.search(rf"(?<![\w.-]){needle}(?![\w-])(?!\.\w)", corpus) is not None
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


def pointer_needles(target: Path) -> tuple[str, ...]:
    """Paths that name the target itself. A doc pointing at its own replacement is not drifted."""
    root = (target.parent if target.name == "SKILL.md" else target).resolve()
    return (f"skills/{root.name}", str(root))


def is_pointer(value: str, needles: tuple[str, ...]) -> bool:
    if any(n in value for n in needles):
        return True
    if value.startswith(("~", "/")):
        try:
            return str(Path(value).expanduser()) in needles
        except (OSError, RuntimeError):
            return False
    return False


# --------------------------------------------------------------------------- inventory

def load_ignore(root: Path) -> list[str]:
    f = root / ".sotignore"
    if not f.is_file():
        return []
    patterns = []
    for line in f.read_text(errors="ignore").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            patterns.append(line.rstrip("/"))
    return patterns


def ignored_name(name: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(name, p) or fnmatch.fnmatch(name.rstrip("/"), p)
               for p in patterns)


def ignored_path(rel: str, name: str, patterns: list[str]) -> bool:
    for p in patterns:
        if fnmatch.fnmatch(rel, p) or fnmatch.fnmatch(name, p) \
                or any(fnmatch.fnmatch(part, p) for part in rel.split("/")):
            return True
    return False


MD_TOKEN_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_./~-]*\.(?:md|markdown)\b", re.I)


def census(root: Path, patterns: list[str]) -> dict[str, tuple[Path, str]]:
    """Walk the tree, pruning data directories instead of visiting then discarding them.

    Descending into a docker data volume and filtering afterwards is what made a real repository
    read 112,000 files and 1 GB of application data.
    """
    docs: dict[str, tuple[Path, str]] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames
                             if d.lower() not in SKIP_DIRS and not ignored_name(d, patterns))
        for name in sorted(filenames):
            if not name.lower().endswith((".md", ".markdown")):
                continue
            path = Path(dirpath) / name
            rel = path.relative_to(root).as_posix()
            if ignored_path(rel, name, patterns):
                continue
            try:
                if path.stat().st_size > MAX_FILE:
                    continue
                docs[rel] = (path, path.read_text(errors="ignore"))
            except OSError:
                continue
    return docs


def inbound_counts(docs: dict[str, tuple[Path, str]]) -> dict[str, int]:
    """One token pass per document, resolved against the census.

    The earlier version scanned every file body once per document, which is quadratic and never
    finished on a real repository.
    """
    by_name: dict[str, list[str]] = {}
    for rel in docs:
        by_name.setdefault(rel.rsplit("/", 1)[-1], []).append(rel)
    counts = {rel: 0 for rel in docs}
    for rel, (_, body) in docs.items():
        hits = set()
        for token in MD_TOKEN_RE.findall(body):
            token = token.lstrip("./")
            if token in docs:
                hits.add(token)
                continue
            for cand in by_name.get(token.rsplit("/", 1)[-1], ()):
                if cand == token or cand.endswith("/" + token) or token.endswith("/" + cand):
                    hits.add(cand)
        hits.discard(rel)
        for hit in hits:
            counts[hit] += 1
    return counts


# --------------------------------------------------------------------------- document classes

DOC_CLASSES = ("authority", "decided", "derived", "navigational",
               "procedural", "record", "vocabulary")
ENFORCED = frozenset({"derived", "authority", "vocabulary", "navigational"})
ADVISORY = frozenset({"decided"})
EXEMPT = frozenset({"procedural", "record"})
SINGLETON_CLASSES = ("authority", "vocabulary")

GENERATED_STAMP_RE = re.compile(r"^\s*(?:>|\*|-)?\s*Generated:", re.I | re.M)
DOCS_PATH_RE = re.compile(r"(?<![\w./~-])(docs/[A-Za-z0-9_./-]*[A-Za-z0-9_-])")
TRAILING_PUNCT = ".,;:)]}'\"`"

Finding = namedtuple("Finding", "tier code path line message")


def frontmatter(text: str) -> dict[str, str]:
    """Parse the leading `---` block only: a `class:` in prose is not a declaration."""
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    out: dict[str, str] = {}
    for line in text[3:end].splitlines():
        if not line.strip() or line[0] in " \t#" or line.startswith("- "):
            continue
        if ":" in line:
            key, value = line.split(":", 1)
            out[key.strip().lower()] = value.strip().strip("'\"")
    return out


def load_dir_map(root: Path) -> dict[str, str]:
    """Optional `.sotclasses`: one `path class` pair per line.

    The taxonomy stays tool-owned; only the mapping is repository data, like `.sotignore`. A map
    the code reads is fine where a *class list* the code reads would be a second authority.
    """
    f = root / ".sotclasses"
    if not f.is_file():
        return {}
    out: dict[str, str] = {}
    for line in f.read_text(errors="ignore").splitlines():
        line = line.split("#", 1)[0].strip()
        parts = line.split()
        if len(parts) == 2:
            out[parts[0].strip("/")] = parts[1].lower()
    return out


def classify(rel: str, text: str, dir_map: dict[str, str]) -> str | None:
    declared = frontmatter(text).get("class")
    if declared:
        return declared.lower()
    for prefix in sorted(dir_map, key=len, reverse=True):
        if rel == prefix or rel.startswith(prefix + "/"):
            return dir_map[prefix]
    return None


def declared_classes(root: Path, patterns: list[str]) -> dict[str, list[str]]:
    """Which documents declare which class, from the frontmatter window only.

    The singleton rules (authority, vocabulary) need the whole repository even when `check` was
    pointed at three changed files, and reading 2 KB per document keeps that scan in milliseconds
    where the full census costs seconds.
    """
    out: dict[str, list[str]] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames
                             if d.lower() not in SKIP_DIRS and not ignored_name(d, patterns))
        for name in sorted(filenames):
            if not name.lower().endswith((".md", ".markdown")):
                continue
            path = Path(dirpath) / name
            rel = path.relative_to(root).as_posix()
            if ignored_path(rel, name, patterns):
                continue
            try:
                with path.open(errors="ignore") as handle:
                    head = handle.read(2048)
            except OSError:
                continue
            declared = frontmatter(head).get("class")
            if declared:
                out.setdefault(declared.lower(), []).append(rel)
    return out


def doc_paths(text: str):
    """Every `docs/...` path a document names, with its line."""
    starts = line_starts(text)
    for match in DOCS_PATH_RE.finditer(text):
        yield match.group(1).rstrip(TRAILING_PUNCT), line_at(starts, match.start())


# --------------------------------------------------------------------------- git probes

def _git(root: Path, *args: str) -> str | None:
    proc = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    return proc.stdout.strip() if proc.returncode == 0 else None


def is_git_work_tree(root: Path) -> bool:
    return _git(root, "rev-parse", "--is-inside-work-tree") == "true"


def git_toplevel(root: Path) -> Path | None:
    top = _git(root, "rev-parse", "--show-toplevel")
    return Path(top) if top else None


def is_ignored(root: Path, rel: str) -> bool:
    """`git check-ignore` exits 0 outside a work tree, so prove the tree and the untracked state
    first — otherwise a hand-written file passes as generated."""
    if not is_git_work_tree(root):
        return False
    if _git(root, "ls-files", "--error-unmatch", rel) is not None:
        return False
    return subprocess.run(["git", "-C", str(root), "check-ignore", "-q", rel],
                          capture_output=True).returncode == 0


def _relative_to_root(top: Path, root: Path, listing: str | None) -> list[str]:
    out: list[str] = []
    for line in (listing or "").splitlines():
        line = line.strip()
        if not line:
            continue
        rel = os.path.relpath(top / line, root).replace(os.sep, "/")
        if not rel.startswith(".."):
            out.append(rel)
    return out


def check_scope(root: Path, mode: str) -> tuple[list[str] | None, str, str | None]:
    """Return (paths, description, error). `paths is None` means the whole repository."""
    if mode == "all":
        return None, "whole repository", None
    if not is_git_work_tree(root):
        return None, "", f"not a git work tree: {root}"
    top = git_toplevel(root)
    if top is None:
        return None, "", f"not a git work tree: {root}"
    if mode == "staged":
        listing = _git(top, "diff", "--cached", "--name-only", "--diff-filter=AM")
        return _relative_to_root(top, root, listing), "index vs HEAD", None
    for base in ("@{upstream}", "main", "master", "HEAD"):
        listing = _git(top, "diff", "--diff-filter=AM", "--name-only", base)
        if listing is not None:
            return _relative_to_root(top, root, listing), f"{base}..working tree", None
    return None, "", "no git base found (tried @{upstream}, main, master, HEAD)"


# --------------------------------------------------------------------------- check

def check_docs(root: Path, paths: list[str] | None) -> tuple[list[Finding], list[tuple[str, int, str]]]:
    """Structural findings for the selected documents, plus secret hits. Read-only."""
    patterns = load_ignore(root)
    dir_map = load_dir_map(root)

    if paths is None:
        docs = census(root, patterns)
    else:
        docs = {}
        for rel in paths:
            path = root / rel
            if path.is_file() and path.suffix.lower() in (".md", ".markdown"):
                try:
                    docs[rel] = (path, path.read_text(errors="ignore"))
                except OSError:
                    continue

    findings: list[Finding] = []
    secrets: list[tuple[str, int, str]] = []

    declared = declared_classes(root, patterns)
    for cls in SINGLETON_CLASSES:
        owners = sorted(declared.get(cls, []))
        if len(owners) > 1:
            findings.append(Finding(
                "fail", "singleton", owners[0], 0,
                f"class '{cls}' is declared by {len(owners)} documents: " + ", ".join(owners)))

    decision_numbers: dict[str, list[str]] = {}

    for rel in sorted(docs):
        _, text = docs[rel]
        cls = classify(rel, text, dir_map)

        for number, kind in secret_lines(text):
            secrets.append((rel, number, kind))

        if cls is None:
            findings.append(Finding(
                "info", "undeclared", rel, 0,
                "undeclared class (add `class: <name>` to frontmatter, or map its directory in "
                ".sotclasses)"))
            continue
        if cls not in DOC_CLASSES:
            findings.append(Finding(
                "fail", "unknown-class", rel, 0,
                f"unknown class '{cls}'; expected one of " + ", ".join(DOC_CLASSES)))
            continue

        if cls == "derived" and not (GENERATED_STAMP_RE.search(text[:1000]) or is_ignored(root, rel)):
            findings.append(Finding(
                "fail", "derived", rel, 0,
                "declares class 'derived' but is not provably generated (gitignored, or a "
                "`Generated:` stamp in the first 1000 characters)"))

        if cls == "navigational":
            for value, line in doc_paths(text):
                if not (root / value).exists():
                    findings.append(Finding("fail", "dead-path", rel, line,
                                            f"path does not resolve: {value}"))

        canonical = frontmatter(text).get("canonical")
        if canonical:
            target = canonical.lstrip("./")
            if not (root / target).exists():
                findings.append(Finding("fail", "canonical", rel, 0,
                                        f"canonical target does not resolve: {canonical}"))

        if cls == "decided":
            match = re.match(r"(\d+)", Path(rel).name)
            if match:
                decision_numbers.setdefault(match.group(1), []).append(rel)

    for number, owners in sorted(decision_numbers.items()):
        if len(owners) > 1:
            findings.append(Finding(
                "info", "decision-number", sorted(owners)[0], 0,
                f"decision number {number} is used by " + ", ".join(sorted(owners))))

    findings.sort(key=lambda f: (f.path, f.line, f.code))
    return findings, secrets


# --------------------------------------------------------------------------- audit

AuditRow = namedtuple("AuditRow", "cls facts inbound candidate command verdict")

CLASS_ORDER = {name: index for index, name in enumerate(DOC_CLASSES)}


def _dir_corpus(path: Path, patterns: list[str], budget: int = 4_000_000) -> str:
    """Concatenated text of one candidate target directory, pruned like the census."""
    if not path.is_dir():
        return ""
    chunks: list[str] = []
    size = 0
    for dirpath, dirnames, filenames in os.walk(path):
        dirnames[:] = sorted(d for d in dirnames
                             if d.lower() not in SKIP_DIRS and not ignored_name(d, patterns))
        for name in sorted(filenames):
            if Path(name).suffix.lower() not in TEXT_EXT:
                continue
            file_path = Path(dirpath) / name
            rel = file_path.relative_to(path).as_posix()
            if ignored_path(rel, name, patterns):
                continue
            try:
                if file_path.stat().st_size > MAX_FILE:
                    continue
                text = file_path.read_text(errors="ignore")
            except OSError:
                continue
            chunks.append(text)
            size += len(text)
            if size > budget:
                return "\n".join(chunks)
    return "\n".join(chunks)


def _candidate_dirs(root: Path) -> list[str]:
    """Each top-level directory, then the repo root.

    A `diff` target must be a directory. Specific directories come first so that a tie with the
    root — which contains everything — resolves to the narrower, more useful target.
    """
    out: list[str] = []
    for entry in sorted(root.iterdir()):
        if (entry.is_dir() and not entry.name.startswith(".")
                and entry.name.lower() not in SKIP_DIRS):
            out.append(entry.name)
    out.append(".")
    return out


def audit_rows(root: Path, script_ref: str) -> tuple[list[AuditRow], dict[str, int]]:
    """One row per document, ranked. Never a verdict: every row carries the command to check it."""
    patterns = load_ignore(root)
    dir_map = load_dir_map(root)
    docs = census(root, patterns)
    counts = inbound_counts(docs)

    candidates = _candidate_dirs(root)
    cand_facts = {c: extract(_dir_corpus(root / c, patterns)) for c in candidates}

    rows: list[AuditRow] = []
    summary = {"records": 0, "stubs": 0, "paired": 0}

    for rel in sorted(docs):
        path, text = docs[rel]
        cls = classify(rel, text, dir_map) or "undeclared"
        facts = extract(text)
        total = sum(len(values) for values in facts.values())
        inbound = counts.get(rel, 0)

        if cls == "record" or is_record(path, text):
            summary["records"] += 1
            rows.append(AuditRow(cls, total, inbound, "-", "-", "skipped (record)"))
            continue
        if frontmatter(text).get("canonical"):
            summary["stubs"] += 1
            rows.append(AuditRow(cls, total, inbound, "-", "-", "skipped (stub)"))
            continue

        own = rel.split("/", 1)[0] if "/" in rel else "."
        best, best_score = "-", 0
        for candidate, cand in cand_facts.items():
            if candidate == own:
                continue
            score = sum(1 for kind, values in facts.items()
                        for value in values if value in cand.get(kind, {}))
            if score > best_score:
                best, best_score = candidate, score

        if best == "-":
            rows.append(AuditRow(cls, total, inbound, "-", "-", "no candidate"))
            continue

        command = f"python3 {script_ref} diff {rel} {best} --profile=config"
        summary["paired"] += 1
        rows.append(AuditRow(cls, total, inbound, best, command, ""))

    rows.sort(key=lambda r: (r.verdict != "",
                             CLASS_ORDER.get(r.cls, len(CLASS_ORDER)),
                             -r.inbound, -r.facts, r.command))
    return rows, summary


