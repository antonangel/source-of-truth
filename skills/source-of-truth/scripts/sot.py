#!/usr/bin/env python3
"""List the environment-specific facts a doc holds that a target does not.

Usage:
    fact-diff.py <doc.md> <skill-dir | SKILL.md | any-directory> [--kinds=a,b] [--quiet]

The target is normally a skill (is the doc redundant?) or a config directory (has the doc
drifted?). Every text file under it is searched.

Fact kinds: path, host, ip, port, env, id, command. `--kinds` restricts the check, e.g.
`--kinds=path,host,ip,port,env,id` when the target is a config directory, because config
files do not contain command lines.

Output: one "kind  value" line per missing fact on stdout, then a summary line.
Secret warnings go to stderr as "warning: possible secret (kind) at file:line".

Exit codes:
    0  no missing facts detected
    1  facts are missing: migrate them into the skill's references/ before stubbing
    2  usage error

**Exit 0 is necessary, not sufficient.** It proves the target contains every fact the doc
states. It cannot tell you the target arranges them into a usable procedure, that the
commands still work, or that the doc's prose carried no meaning. Read the pair first.

Secrets: a doc line that looks like a secret is reported by line and kind, its value is
never printed, and the line is left out of the fact checks. Scrub it, then run again.
This is a tripwire for docs, not a history scanner.

Known limitations:
- Config keys, parameters, image names and volume mappings are not extracted; env vars
  only in the form NAME=value. IPv6 and MAC addresses are not extracted.
- Inline backtick prose is filtered with a stopword list; a phrase whose first word is not
  a stopword (for example "run tests") can be mistaken for a command. Fenced blocks are
  unaffected.
- A doc command that is a prefix of a longer target command counts as present when the
  next character is whitespace (the boundary only blocks mid-token continuation).
- Port matching needs a port context in the target (":N", "port N", "listen N", "N:M");
  a bare number in prose does not count.
- "HH:MM" with HH <= 23 and MM <= 59 is read as a clock time in prose, and as a port
  mapping inside a fenced block, quotes or backticks.
- The secret scan errs toward warning: a phrase such as "password: stored" can trip it.

Python 3.10+, standard library only.
"""

import re
import sys
from pathlib import Path

KINDS = ("path", "host", "ip", "port", "env", "id", "command")

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

_OCTET = r"(?:25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])"
# An IPv4 address, optionally with a CIDR prefix. A "/" may precede it (a URL) and a
# sentence-final "." may follow it; a longer dotted token on either side is not an address.
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


def norm(text: str) -> str:
    text = re.sub(r"[`*'\u2019\"]", "", text.lower())
    return re.sub(r"\s+", " ", text)


def secret_lines(text: str) -> list[tuple[int, str]]:
    """Return (line number, kind) for each line that looks like it holds a secret."""
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


def is_file_ext(candidate: str) -> bool:
    return candidate.split(".")[-1] in FILE_EXT


def looks_like_version(candidate: str) -> bool:
    return bool(re.fullmatch(r"[vV]?(0|[1-9]\d*)(\.(0|[1-9]\d*)){0,2}", candidate))


def as_command(line: str) -> str | None:
    line = line.strip().lstrip("$> ").strip()
    line = re.sub(r"\s+#.*$", "", line).rstrip(".,;:")  # drop a trailing comment
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
    out: set[str] = set()
    in_fence, pending = False, ""

    def flush(candidate: str) -> None:
        cmd = as_command(candidate)
        if cmd:
            out.add(cmd)

    for line in text.splitlines():
        if line.strip().startswith("```"):
            if pending:
                flush(pending)
            in_fence, pending = not in_fence, ""
            continue
        if not in_fence:
            continue
        stripped = line.rstrip()
        if stripped.endswith("\\"):  # a continued command is one command
            pending += stripped[:-1].strip() + " "
            continue
        flush(pending + stripped.strip() if pending else line)
        pending = ""
    return out


def inline_commands(text: str) -> set[str]:
    out = set()
    for m in BACKTICK_RE.finditer(text):
        cmd = as_command(m.group(1))
        if cmd and cmd.split()[0].lower() not in INLINE_STOPWORDS:
            out.add(cmd)
    return out


def is_hostname(candidate: str) -> bool:
    if is_file_ext(candidate) or looks_like_version(candidate):
        return False
    return not re.fullmatch(r"[\d.]+", candidate)


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


def looks_like_clock(hour: str, minute: str) -> bool:
    return (hour.isdigit() and len(hour) <= 2 and int(hour) <= 23
            and len(minute) == 2 and int(minute) <= 59)


def find_ports(text: str) -> set[str]:
    fences = fence_spans(text)
    masked = IPV4_RE.sub(lambda m: "x" * len(m.group(0)), text)  # same offsets, no octets
    ports: set[str] = set()
    for m in PORT_RE.finditer(masked):
        hour = minute = None
        hour_start = 0
        if m.group(4) is not None:                    # N:M, a mapping or a clock time
            hour, minute, hour_start = m.group(4), m.group(5), m.start()
            values = (m.group(4), m.group(5))
        elif m.group(1) is not None:                  # :N
            k = m.start()
            while k > 0 and masked[k - 1].isdigit():
                k -= 1
            if k > 0 and masked[k - 1] == ":":
                continue                              # 12:30:45 or an address, not a port
            hour, minute, hour_start = masked[k:m.start()], m.group(1), k
            values = (m.group(1),)
        else:                                         # "port N" or "listen N"
            values = tuple(g for g in (m.group(2), m.group(3)) if g)
        if hour is not None and looks_like_clock(hour, minute) \
                and not in_code_context(text, hour_start, fences):
            continue
        ports.update(v for v in values if int(v) <= 65535)
    return ports


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

    return {
        "path": paths,
        "host": hosts,
        "ip": {m.group(1) for m in IPV4_RE.finditer(text)},
        "port": find_ports(text),
        "env": {m.group(1) for m in ENV_RE.finditer(text)},
        "id": set(ID_RE.findall(text.lower())),
        "command": fenced_commands(text) | inline_commands(text),
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
            text = p.read_text(errors="ignore")
        except OSError:
            continue
        chunks.append(re.sub(r"\\[ \t]*\r?\n[ \t]*", " ", text))  # join continued lines
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


def parse_args(argv: list[str]):
    paths: list[str] = []
    quiet, kinds = False, None
    for arg in argv[1:]:
        if arg == "--quiet":
            quiet = True
        elif arg.startswith("--kinds="):
            kinds = [k.strip() for k in arg.split("=", 1)[1].split(",") if k.strip()]
            if not kinds or any(k not in KINDS for k in kinds):
                return None
        elif arg.startswith("--"):
            return None
        else:
            paths.append(arg)
    return (paths, quiet, kinds) if len(paths) == 2 else None


def diff_main(argv: list[str]) -> int:
    parsed = parse_args(argv)
    if parsed is None:
        print("usage: fact-diff.py <doc> <skill-dir-or-SKILL.md-or-dir> [--kinds=a,b] [--quiet]\n"
              f"kinds: {', '.join(KINDS)}", file=sys.stderr)
        return 2
    (doc_arg, target_arg), quiet, kinds = parsed

    doc, target = Path(doc_arg), Path(target_arg)
    for p in (doc, target):
        if not p.exists():
            print(f"not found: {p}", file=sys.stderr)
            return 2

    doc_text = doc.read_text(errors="ignore")
    secrets = secret_lines(doc_text)
    for number, kind in secrets:
        print(f"warning: possible secret ({kind}) at {doc}:{number}", file=sys.stderr)
    flagged = {number for number, _ in secrets}
    clean = "\n".join("" if i in flagged else line
                      for i, line in enumerate(doc_text.splitlines(), 1))

    corpus = skill_corpus(target)
    skill_name = (target.parent if target.name == "SKILL.md" else target).resolve().name
    # A pointer line names the skill's own path. That is its destination, not a missing fact.
    pointer = re.compile(rf"(?<![\w-])skills/{re.escape(skill_name)}(?![\w-])")

    facts = {k: v for k, v in extract(clean).items() if kinds is None or k in kinds}
    total = sum(len(v) for v in facts.values())
    missing: list[tuple[str, str]] = []
    for kind, values in facts.items():
        for value in sorted(values):
            if pointer.search(value):
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



import time as _time

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv"}
GENERIC_NAMES = {"README.md", "AGENTS.md", "CLAUDE.md", "SKILL.md", "index.md"}


def inventory_main(argv: list[str]) -> int:
    root = Path(argv[1]) if len(argv) > 1 and not argv[1].startswith("--") else Path(".")
    # support: sot.py inventory <repo>
    args = [a for a in argv[1:] if not a.startswith("--")]
    if args:
        root = Path(args[0])
    if len(args) > 1 or not root.is_dir():
        print("usage: sot.py inventory [repo-dir]", file=sys.stderr)
        return 2
    texts = {}
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.suffix.lower() not in (TEXT_EXT | {".md", ".markdown"}):
            continue
        if SKIP_DIRS & set(p.relative_to(root).parts):
            continue
        try:
            if p.stat().st_size > MAX_FILE:
                continue
            texts[p] = p.read_text(errors="ignore")
        except OSError:
            texts[p] = ""
    now = _time.time()
    rows = []
    for path, text in texts.items():
        if path.suffix.lower() not in {".md", ".markdown"}:
            continue
        rel = path.relative_to(root).as_posix()
        needles = [rel] if path.name in GENERIC_NAMES else [rel, path.name]
        inbound = sum(1 for other, body in texts.items()
                      if other != path and any(n in body for n in needles))
        facts = extract(text)
        rows.append((
            len(text.splitlines()), int((now - path.stat().st_mtime) / 86400), inbound,
            len(facts["ip"]), len(facts["port"]), len(facts["command"]),
            len(secret_lines(text)), rel,
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
    # normalize: if first extra is subcommand, strip it for diff_main which expects argv[0]=prog
    import sys as _sys
    a = _sys.argv
    if len(a) > 1 and a[1] == "inventory":
        _sys.exit(inventory_main(['sot.py'] + a[2:]))
    if len(a) > 1 and a[1] == "diff":
        _sys.exit(diff_main(["sot.py"] + a[2:]))
    _sys.exit(diff_main(a))
