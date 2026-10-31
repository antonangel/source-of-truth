#!/usr/bin/env python3
"""Run the fact-diff tests.

    python3 tests/run_tests.py

Every extractor kind gets a case that must be flagged and a case that must not.
Standard library only; no network, no install step.
"""

import re
import shutil
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

    # --- fix 1: the skill's own name must not swallow facts
    ("skill name does not swallow facts",
     "Backups go to /srv/backup/daily.\n\n```bash\nrestic -r /srv/backup backup --tag nightly\n```\n",
     {"SKILL.md": "Unrelated.\n"},
     {("path", "/srv/backup/daily"), ("path", "/srv/backup"),
      ("command", "restic -r /srv/backup backup --tag nightly")},
     {"skill_name": "backup"}),
    ("a pointer to the skill's own path is exempt",
     "Moved to ~/.claude/skills/backup-ops/references/runbook.md.\n",
     {"SKILL.md": "Nothing.\n"},
     set(),
     {"skill_name": "backup-ops"}),

    # --- fix 2: IPs in urls, CIDR, sentence-final periods
    ("ip inside a url",
     "Open http://192.168.1.20:8006/ui now.\n",
     {"SKILL.md": "Nothing here.\n"},
     {("ip", "192.168.1.20"), ("port", "8006")}),
    ("ip in cidr notation",
     "The LAN is 192.168.1.0/24 today.\n",
     {"SKILL.md": "Nothing here.\n"},
     {("ip", "192.168.1.0/24")}),
    ("ip before a sentence-final period",
     "The NAS is at 192.168.1.10.\n",
     {"SKILL.md": "Nothing here.\n"},
     {("ip", "192.168.1.10")}),
    ("cidr present",
     "LAN 192.168.1.0/24.\n",
     {"SKILL.md": "LAN 192.168.1.0/24.\n"},
     set()),
    ("cidr with a different prefix is a different fact",
     "LAN 192.168.1.0/24.\n",
     {"SKILL.md": "LAN 192.168.1.0/16.\n"},
     {("ip", "192.168.1.0/24")}),

    # --- fix 3: port mappings are ports, clock times are not
    ("port mappings in a fence",
     "```yaml\nports:\n  - \"81:81\"\n  - \"22:22\"\n```\n",
     {"SKILL.md": "Nothing here.\n"},
     {("port", "81"), ("port", "22")}),
    ("quoted mapping that looks like a time",
     "Map \"22:22\" for ssh.\n",
     {"SKILL.md": "Nothing here.\n"},
     {("port", "22")}),
    ("mapping 80:80 is not a time",
     "Publish `80:80` and 443:443.\n",
     {"SKILL.md": "Nothing here.\n"},
     {("port", "80"), ("port", "443")}),
    ("clock time with seconds is not a port",
     "Started at 12:30:45 sharp.\n",
     {"SKILL.md": "Nothing here.\n"},
     set()),
    ("single-digit clock time is not a port",
     "Backup runs at 9:30 each night.\n",
     {"SKILL.md": "Nothing here.\n"},
     set()),
    ("mapping present in the skill",
     "```yaml\nports:\n  - \"81:81\"\n```\n",
     {"SKILL.md": "Admin UI mapping 81:81.\n"},
     set()),

    # --- fix 4: trailing comments and continuation lines
    ("trailing comment is not part of a command",
     "```bash\ndocker compose pull   # update images\n```\n",
     {"SKILL.md": "Run `docker compose pull`.\n"},
     set()),
    ("continued command is checked whole",
     "```bash\ndocker run -d \\\n  --name foo nginx\n```\n",
     {"SKILL.md": "Nothing here.\n"},
     {("command", "docker run -d --name foo nginx")}),
    ("continued command present when the skill wraps it too",
     "```bash\ndocker run -d \\\n  --name foo nginx\n```\n",
     {"SKILL.md": "```bash\ndocker run -d \\\n  --name foo nginx\n```\n"},
     set()),
    ("continued command missing its tail is flagged",
     "```bash\ndocker run -d \\\n  --name foo nginx\n```\n",
     {"SKILL.md": "docker run -d\n"},
     {("command", "docker run -d --name foo nginx")}),
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


def run_script(doc_text: str, files: dict[str, str], skill_name: str = "skill",
               extra: tuple[str, ...] = ()) -> tuple[int, str, str]:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        doc = tmp_path / "doc.md"
        doc.write_text(doc_text)
        skill = tmp_path / skill_name
        skill.mkdir()
        for rel, content in files.items():
            target = skill / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), str(doc), str(skill), *extra],
            capture_output=True, text=True,
        )
    return proc.returncode, proc.stdout, proc.stderr


def parse_facts(stdout: str) -> set[tuple[str, str]]:
    found = set()
    for line in stdout.splitlines():
        parts = line.split(None, 1)
        if len(parts) == 2 and parts[0] in KINDS:
            found.add((parts[0], parts[1].strip()))
    return found


def run_case(doc_text: str, files: dict[str, str], **opts) -> tuple[int, set[tuple[str, str]], str]:
    rc, out, err = run_script(doc_text, files, **opts)
    return rc, parse_facts(out), out + err


def secret_checks() -> list[str]:
    """Secrets are warned about on stderr, by line, and never echoed anywhere."""
    fake_token = "gh" + "p_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4"      # built at runtime so no
    fake_key = "-----BEGIN " + "OPENSSH PRIVATE KEY-----"           # scanner flags this file
    doc = (
        "Set WEBPASSWORD=hunter2hunter2 before start.\n"
        f"The token {fake_token} was pasted here.\n"
        f"{fake_key}\n"
        "Backups use postgres://admin:s3cretpass@db.lan/app nightly.\n"
        "password: ${DB_PASSWORD} is fine.\n"
        "api_key=<your key> is fine.\n"
    )
    rc, out, err = run_script(doc, {"SKILL.md": "Nothing here.\n"})
    failures = []
    flagged = {int(m) for m in re.findall(r":(\d+)$", err, re.M)}
    if flagged != {1, 2, 3, 4}:
        failures.append(f"secrets: expected warnings on lines 1-4, got {sorted(flagged)}\n{err}")
    if "possible secret" not in err:
        failures.append("secrets: warning text missing")
    for leaked in ("hunter2", fake_token, "s3cretpass", "OPENSSH"):
        if leaked in out + err:
            failures.append(f"secrets: value leaked into output: {leaked[:6]}...")
    if parse_facts(out):
        failures.append(f"secrets: flagged lines must be left out of the fact checks, got {parse_facts(out)}")
    if rc != 0:
        failures.append(f"secrets: expected exit 0 with only secret lines, got {rc}\n{out}{err}")
    return failures


def kinds_checks() -> list[str]:
    doc = "Node 10.0.0.5 and /srv/x/y and `systemctl restart foo`.\n"
    files = {"SKILL.md": "Nothing here.\n"}
    failures = []
    rc, out, _ = run_script(doc, files, extra=("--kinds=ip",))
    if rc != 1 or parse_facts(out) != {("ip", "10.0.0.5")}:
        failures.append(f"--kinds=ip: expected only the ip, got {parse_facts(out)} rc={rc}")
    rc, out, _ = run_script(doc, files, extra=("--kinds=path,ip",))
    if parse_facts(out) != {("ip", "10.0.0.5"), ("path", "/srv/x/y")}:
        failures.append(f"--kinds=path,ip: wrong facts {parse_facts(out)}")
    rc, _, err = run_script(doc, files, extra=("--kinds=bogus",))
    if rc != 2:
        failures.append(f"--kinds=bogus: expected usage error 2, got {rc}")
    return failures


def inventory_checks() -> list[str]:
    inventory = SCRIPT.parent / "doc-inventory.py"
    failures = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        files = {
            "docs/a.md": "See docs/b.md. Node 10.0.0.5:9000.\n```bash\nsystemctl restart foo\n```\n",
            "docs/b.md": "WEBPASSWORD=hunter2hunter2\n",
            "docs/orphan.md": "Nothing links here.\n",
            "skills/x/SKILL.md": "Details in a.md.\n",
            ".git/hidden.md": "Must be skipped.\n",
        }
        for rel, content in files.items():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_text(content)
        proc = subprocess.run([sys.executable, str(inventory), str(root)],
                              capture_output=True, text=True)
    rows = {}
    for line in proc.stdout.splitlines():
        parts = line.split()
        if parts and parts[0].isdigit() and len(parts) == 8:
            rows[parts[7]] = [int(x) for x in parts[:7]]
    if proc.returncode != 0 or set(rows) != {"docs/a.md", "docs/b.md", "docs/orphan.md", "skills/x/SKILL.md"}:
        failures.append(f"inventory: wrong rows {sorted(rows)} rc={proc.returncode}\n{proc.stdout}{proc.stderr}")
        return failures
    lines, age, inbound, ips, ports, cmds, secrets = range(7)
    if rows["docs/a.md"][ips:cmds + 1] != [1, 1, 1] or rows["docs/a.md"][inbound] != 1:
        failures.append(f"inventory: docs/a.md row wrong: {rows['docs/a.md']}")
    if rows["docs/b.md"][inbound] != 1 or rows["docs/b.md"][secrets] != 1:
        failures.append(f"inventory: docs/b.md row wrong: {rows['docs/b.md']}")
    if rows["docs/orphan.md"][inbound] != 0:
        failures.append(f"inventory: orphan should have no inbound references: {rows['docs/orphan.md']}")
    if "hunter2" in proc.stdout or proc.stdout.index("docs/a.md") > proc.stdout.index("docs/orphan.md"):
        failures.append("inventory: secret leaked or rows not sorted by facts stated")
    return failures


FIXTURE = HERE / "fixtures" / "homelab"
GOLDEN_VS_SKILL = {
    ("host", "pihole.lan"), ("ip", "192.168.1.1"),
    ("port", "443"), ("port", "53"), ("port", "80"), ("port", "8080"),
    ("command", "cd /srv/stack/dns"), ("command", "docker compose pull"),
    ("command", "docker compose up -d pihole"),
}
GOLDEN_DRIFT = {
    ("path", "/srv/stack/dns"), ("host", "pihole.lan"), ("ip", "192.168.1.1"), ("port", "8080"),
}
DRIFT_KINDS = "--kinds=path,host,ip,port,env,id"


def run_in(cwd: Path, *args: str) -> tuple[int, str, str]:
    proc = subprocess.run([sys.executable, str(SCRIPT), *args], cwd=cwd,
                          capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


def golden_checks() -> list[str]:
    """A realistic homelab doc, skill and compose file with exact expected results,
    plus the claim that references/before-after-homelab.md shows real output."""
    failures = []
    doc, skill, config = "docs/dns-runbook.md", "skills/network-ops", "config"

    rc, out, err = run_in(FIXTURE, doc, skill)
    if rc != 1 or parse_facts(out) != GOLDEN_VS_SKILL:
        failures.append(f"golden vs skill: got {sorted(parse_facts(out))} rc={rc}\n{out}")
    if f"possible secret (credential assignment) at {doc}:24" not in err or "hunter2" in out + err:
        failures.append(f"golden: secret warning missing or leaking\n{err}")

    rc, out_drift, _ = run_in(FIXTURE, doc, config, DRIFT_KINDS)
    if rc != 1 or parse_facts(out_drift) != GOLDEN_DRIFT:
        failures.append(f"golden drift: got {sorted(parse_facts(out_drift))} rc={rc}\n{out_drift}")

    # The migrated state: secret scrubbed, doc copied verbatim into the skill's references/.
    with tempfile.TemporaryDirectory() as tmp:
        migrated = Path(tmp) / "homelab"
        shutil.copytree(FIXTURE, migrated)
        scrubbed = (migrated / doc).read_text().replace("hunter2hunter2", "<password>")
        (migrated / doc).write_text(scrubbed)
        (migrated / skill / "references").mkdir()
        (migrated / skill / "references" / "dns-runbook.md").write_text(scrubbed)
        rc, out_after, err_after = run_in(migrated, doc, skill)
    if rc != 0 or err_after:
        failures.append(f"golden after migration: expected clean exit 0, got rc={rc}\n{out_after}{err_after}")

    # Every example in the before/after reference must equal what the script prints.
    text = (ROOT / "skills" / "source-of-truth" / "references" / "before-after-homelab.md").read_text()
    blocks = re.findall(r"```text\n\$ python3 scripts/fact-diff\.py [^\n]*\n(.*?)```", text, re.S)
    actual = [out, out_after, out_drift]
    if len(blocks) != 3:
        failures.append(f"before-after-homelab.md: expected 3 command examples, found {len(blocks)}")
    else:
        for name, shown, real in zip(("before", "after", "drift"), blocks, actual):
            if shown.strip() != real.strip():
                failures.append(f"before-after-homelab.md {name} example is out of date:\n"
                                f"--- doc\n{shown}--- script\n{real}")
    if "docs/dns-runbook.md:24" not in text:
        failures.append("before-after-homelab.md: secret warning line missing")
    return failures


def readme_checks() -> list[str]:
    """The README is derived from the skill: it may not claim what the script does not do,
    restate the skill's own lines, or link to files that are not there."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("fact_diff", SCRIPT)
    fd = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fd)

    failures = []
    readme = (ROOT / "README.md").read_text()
    skill = (ROOT / "skills" / "source-of-truth" / "SKILL.md").read_text()

    line = re.search(r"^\s*Fact kinds:(.*)$", readme, re.M)
    listed = set(re.findall(r"`([a-z]+)`", line.group(1))) if line else set()
    if listed != set(fd.KINDS) or set(fd.extract("")) != set(fd.KINDS):
        failures.append(f"README lists fact kinds {sorted(listed)}; the script extracts {sorted(fd.KINDS)}")

    for text in readme.splitlines():
        if len(text.strip()) >= 60 and not text.lstrip().startswith(("```", "|")) \
                and text.strip() in skill:
            failures.append(f"README restates a line from SKILL.md: {text.strip()[:60]}...")

    for target in re.findall(r"\]\(([^)#]+)(?:#[^)]*)?\)", readme):
        if not target.startswith(("http://", "https://")) and not (ROOT / target).exists():
            failures.append(f"README links to a missing file: {target}")
    if len(readme.splitlines()) > 70:
        failures.append(f"README is {len(readme.splitlines())} lines; keep it under 70")
    return failures


def main() -> int:
    failures: list[str] = []

    for name, doc, files, expected, *opt in CASES:
        rc, found, out = run_case(doc, files, **(opt[0] if opt else {}))
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

    for label, check in (("secrets", secret_checks), ("--kinds", kinds_checks), ("inventory", inventory_checks), ("homelab golden", golden_checks), ("readme", readme_checks)):
        found_failures = check()
        failures.extend(found_failures)
        if not found_failures:
            print(f"PASS {label}")

    if failures:
        print()
        for f in failures:
            print(f"FAIL {f}")
        print(f"\n{len(failures)} failure(s)")
        return 1

    print(f"\n{len(CASES) + 6} check(s) passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
