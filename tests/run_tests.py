#!/usr/bin/env python3
"""Run the fact-diff tests.

    python3 tests/run_tests.py

Every extractor kind gets a case that must be flagged and a case that must not.
Standard library only; no network, no install step.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SCRIPT = ROOT / "skills" / "source-of-truth" / "scripts" / "fact-diff.py"
KINDS = {"path", "host", "ip", "port", "env", "id", "command"}

# (name, doc text, {skill-relative-path: content}, expected {(kind, value)})
CASES = [
    ("path flagged",
     "Data lives in /srv/other.\n",
     {"SKILL.md": "Data lives in /srv/backups.\n"},
     {("path", "/srv/other")}),
    ("path present",
     "Config is /etc/queue/config.yaml.\n",
     {"SKILL.md": "Config is /etc/queue/config.yaml.\n"},
     set()),
    ("path prefix is not a match",
     "Backups at /srv/backups.\n",
     {"SKILL.md": "Backups at /srv/backups/daily.\n"},
     {("path", "/srv/backups")}),

    ("host flagged",
     "The edge node is edge.example.net.\n",
     {"SKILL.md": "The API is api.example.com.\n"},
     {("host", "edge.example.net")}),
    ("host present",
     "The API is api.example.com.\n",
     {"SKILL.md": "The API is api.example.com.\n"},
     set()),

    ("ip flagged bare",
     "Node 10.0.0.5 answers.\n",
     {"SKILL.md": "Nothing here.\n"},
     {("ip", "10.0.0.5")}),
    ("ip and port flagged",
     "Node 10.0.0.5:9000 answers.\n",
     {"SKILL.md": "Nothing here.\n"},
     {("ip", "10.0.0.5"), ("port", "9000")}),
    ("time is not a port",
     "Rotation starts at 10:30 sharp.\n",
     {"SKILL.md": "Nothing here.\n"},
     set()),
    ("versions are not ips",
     "Pinned v1.2.3 and 1.2.3 today.\n",
     {"SKILL.md": "Nothing here.\n"},
     set()),
    ("ip present in scripts",
     "Node 10.0.0.5 answers.\n",
     {"SKILL.md": "Nothing here.\n", "scripts/probe.sh": "curl http://10.0.0.5/health\n"},
     set()),

    ("ip boundary not a prefix",
     "Node 10.0.0.5 answers.\n",
     {"SKILL.md": "Node 10.0.0.50 answers.\n"},
     {("ip", "10.0.0.5")}),

    ("port flagged without context",
     "Listen on port 9443.\n",
     {"SKILL.md": "The 9443 release changed things.\n"},
     {("port", "9443")}),
    ("port present in context",
     "Listen on port 9443.\n",
     {"SKILL.md": "It listens on port 9443.\n"},
     set()),

    ("env flagged",
     "Set QUEUE_TOKEN=abc before starting.\n",
     {"SKILL.md": "Set the token before starting.\n"},
     {("env", "QUEUE_TOKEN")}),
    ("env present",
     "Set QUEUE_TOKEN=abc before starting.\n",
     {"SKILL.md": "Set QUEUE_TOKEN=<token> before starting.\n"},
     set()),

    ("id flagged",
     "Commit 9f2c4b7a1d3e5f60 deployed.\n",
     {"SKILL.md": "A commit deployed.\n"},
     {("id", "9f2c4b7a1d3e5f60")}),
    ("id present",
     "Commit 9f2c4b7a1d3e5f60 deployed.\n",
     {"SKILL.md": "Commit 9f2c4b7a1d3e5f60 deployed.\n"},
     set()),

    ("fenced command flagged",
     "Run this:\n\n```bash\nsystemctl restart foo\n```\n",
     {"SKILL.md": "Nothing here.\n"},
     {("command", "systemctl restart foo")}),
    ("command present in scripts",
     "Run this:\n\n```bash\nsystemctl restart foo\n```\n",
     {"SKILL.md": "Nothing here.\n", "scripts/run.sh": "systemctl restart foo\n"},
     set()),
    ("command trailing boundary",
     "Run this:\n\n```bash\nrm -rf /tmp/xyz\n```\n",
     {"SKILL.md": "Nothing here.\n", "scripts/run.sh": "rm -rf /tmp/xyz-other\n"},
     {("command", "rm -rf /tmp/xyz"), ("path", "/tmp/xyz")}),
    ("sentence period does not break a command",
     "Run this:\n\n```bash\ndocker compose up -d.\n```\n",
     {"SKILL.md": "Then `docker compose up -d` finishes it.\n"},
     set()),

    ("inline command flagged",
     "Run `systemctl restart foo` now.\n",
     {"SKILL.md": "Nothing here.\n"},
     {("command", "systemctl restart foo")}),
    ("inline hyphenated command flagged",
     "Run `qc-verify --strict` first.\n",
     {"SKILL.md": "Nothing here.\n"},
     {("command", "qc-verify --strict")}),
    ("inline nix command flagged",
     "Build with `nix build .#queue-service` once.\n",
     {"SKILL.md": "Nothing here.\n"},
     {("command", "nix build .#queue-service")}),
    ("inline prose is not a command",
     "Read `the config file`, `docs below` and `see above`.\n",
     {"SKILL.md": "Nothing here.\n"},
     set()),
]

SMOKE_DOC = """Node edge.example.net at 10.0.0.5:9000.

Listen 8080.

```bash
    docker ps
```

Commit 9f2c4b7a1d3e5f60, then `systemctl restart foo`.
"""
SMOKE_EXPECTED = {
    ("host", "edge.example.net"),
    ("ip", "10.0.0.5"),
    ("port", "9000"),
    ("port", "8080"),
    ("id", "9f2c4b7a1d3e5f60"),
    ("command", "docker ps"),
    ("command", "systemctl restart foo"),
}


def run_case(doc_text: str, files: dict[str, str]) -> tuple[int, set[tuple[str, str]], str]:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        doc = tmp_path / "doc.md"
        doc.write_text(doc_text)
        skill = tmp_path / "skill"
        skill.mkdir()
        for rel, content in files.items():
            target = skill / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), str(doc), str(skill)],
            capture_output=True, text=True,
        )
    found = set()
    for line in proc.stdout.splitlines():
        parts = line.split(None, 1)
        if len(parts) == 2 and parts[0] in KINDS:
            found.add((parts[0], parts[1].strip()))
    return proc.returncode, found, proc.stdout + proc.stderr


def main() -> int:
    failures: list[str] = []

    for name, doc, files, expected in CASES:
        rc, found, out = run_case(doc, files)
        want_rc = 1 if expected else 0
        if rc != want_rc:
            failures.append(f"{name}: expected exit {want_rc}, got {rc}\n{out}")
        if found != expected:
            missing = expected - found
            extra = found - expected
            detail = []
            if missing:
                detail.append(f"not flagged: {sorted(missing)}")
            if extra:
                detail.append(f"false positive: {sorted(extra)}")
            failures.append(f"{name}: {'; '.join(detail)}\n{out}")
        else:
            print(f"PASS {name}")

    rc, found, out = run_case(SMOKE_DOC, {"SKILL.md": "Nothing here.\n"})
    if found != SMOKE_EXPECTED or rc != 1:
        failures.append(
            f"smoke: expected {sorted(SMOKE_EXPECTED)}, got {sorted(found)} (rc={rc})\n{out}"
        )
    else:
        print(f"PASS smoke flags {len(SMOKE_EXPECTED)} facts")

    if failures:
        print()
        for f in failures:
            print(f"FAIL {f}")
        print(f"\n{len(failures)} failure(s)")
        return 1

    print(f"\n{len(CASES) + 1} case(s) passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
