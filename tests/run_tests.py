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
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SCRIPT = ROOT / "skills" / "source-of-truth" / "scripts" / "sot.py"
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
            [sys.executable, str(SCRIPT), "diff", str(doc), str(skill), *extra],
            capture_output=True, text=True,
        )
    return proc.returncode, proc.stdout, proc.stderr


def parse_facts(stdout: str) -> set[tuple[str, str]]:
    """Read `kind`, `value`, `doc:line` lines. The provenance field is the last token."""
    found = set()
    for line in stdout.splitlines():
        head, _, provenance = line.rpartition("  ")
        if not provenance or ":" not in provenance:
            continue
        parts = head.split(None, 1)
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
    if rc != 3:
        failures.append(f"secrets: expected exit 3 when secrets present, got {rc}\n{out}{err}")
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
        proc = subprocess.run([sys.executable, str(SCRIPT), "inventory", str(root)],
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


FIXTURE = HERE / "fixtures" / "example-stack"
GOLDEN_VS_SKILL = {
    ("host", "pihole.example.com"), ("ip", "10.0.0.1"),
    ("port", "443"), ("port", "53"), ("port", "80"), ("port", "8080"),
    ("command", "cd /opt/example/dns"), ("command", "docker compose pull"),
    ("command", "docker compose up -d pihole"),
}
GOLDEN_DRIFT = {
    ("path", "/opt/example/dns"), ("host", "pihole.example.com"), ("ip", "10.0.0.1"), ("port", "8080"),
}
DRIFT_KINDS = "--profile=config"


def run_in(cwd: Path, *args: str) -> tuple[int, str, str]:
    proc = subprocess.run([sys.executable, str(SCRIPT), "diff", *args], cwd=cwd,
                          capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


def first_check_checks() -> list[str]:
    """The documented first-run command finds one literal mismatch and writes nothing."""
    failures = []
    doc_arg = "tests/fixtures/first-check/docs/dns-runbook.md"
    target_arg = "tests/fixtures/first-check/config"
    doc = ROOT / doc_arg
    target = ROOT / target_arg
    doc_before = doc.read_bytes()
    target_before = {p.relative_to(target).as_posix(): p.read_bytes()
                     for p in target.rglob("*") if p.is_file()}
    command = [sys.executable, "skills/source-of-truth/scripts/sot.py", "diff",
               doc_arg, target_arg, "--profile=config"]
    proc = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    expected_line = f"ip       203.0.113.10  {doc_arg}:3"
    expected_output = expected_line + "\nmissing facts: 1 of 1 checked\n"
    if proc.returncode != 1 or proc.stdout != expected_output or proc.stderr:
        failures.append("first check: expected exactly one IP finding, its doc:line, no warning, "
                        f"and exit 1; got rc={proc.returncode}\n{proc.stdout}{proc.stderr}")
    if doc.read_bytes() != doc_before:
        failures.append("first check: modified the selected document")
    target_after = {p.relative_to(target).as_posix(): p.read_bytes()
                    for p in target.rglob("*") if p.is_file()}
    if target_after != target_before:
        failures.append("first check: modified the comparison target")

    # A matched control guards the clean exit and the same read-only promise.
    with tempfile.TemporaryDirectory() as tmp:
        matched_target = Path(tmp) / "config"
        matched_target.mkdir()
        matched_file = matched_target / "dns.yml"
        matched_file.write_text("resolver: 203.0.113.10\n")
        matched_before = matched_file.read_bytes()
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "diff", str(doc), str(matched_target),
             "--profile=config"], cwd=ROOT, capture_output=True, text=True,
        )
        if proc.returncode != 0 or proc.stdout != "no missing facts detected (1 checked)\n" or proc.stderr:
            failures.append("first check matched control: expected clean exit 0 with one checked fact; "
                            f"got rc={proc.returncode}\n{proc.stdout}{proc.stderr}")
        if doc.read_bytes() != doc_before or matched_file.read_bytes() != matched_before:
            failures.append("first check matched control: modified a selected input")

    readme = (ROOT / "README.md").read_text()
    demo = "python3 skills/source-of-truth/scripts/sot.py diff " + doc_arg + " " + target_arg + " --profile=config"
    if demo not in readme or expected_output.rstrip() not in readme:
        failures.append("README first check: copy-paste command or exact expected output is missing")
    return failures


def golden_checks() -> list[str]:
    """Regression coverage for skill/config comparisons and the reproducible quick-check example."""
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
        migrated = Path(tmp) / "example-stack"
        shutil.copytree(FIXTURE, migrated)
        scrubbed = (migrated / doc).read_text().replace("hunter2hunter2", "<password>")
        (migrated / doc).write_text(scrubbed)
        (migrated / skill / "references").mkdir()
        (migrated / skill / "references" / "dns-runbook.md").write_text(scrubbed)
        rc, out_after, err_after = run_in(migrated, doc, skill)
    real_err = err_after
    if rc != 0 or real_err.strip():
        failures.append(f"golden after migration: expected clean exit 0, got rc={rc}\n{out_after}{err_after}")

    # The published example command and output must match a real execution from the repo root.
    text = (ROOT / "skills" / "source-of-truth" / "references" / "examples.md").read_text()
    demo_doc = "tests/fixtures/first-check/docs/dns-runbook.md"
    demo_target = "tests/fixtures/first-check/config"
    demo_command = ("python3 skills/source-of-truth/scripts/sot.py diff "
                    f"{demo_doc} {demo_target} --profile=config")
    demo = subprocess.run(
        [sys.executable, str(SCRIPT), "diff", demo_doc, demo_target, "--profile=config"],
        cwd=ROOT, capture_output=True, text=True,
    )
    if demo.returncode != 1 or demo.stderr or demo_command not in text or demo.stdout.rstrip() not in text:
        failures.append("examples.md: first-check command/output is not reproducible from the repo root")
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
    installed_command = ("python3 .claude/skills/source-of-truth/scripts/sot.py diff "
                        "path/to/runbook.md path/to/config --profile=config")
    if installed_command not in readme:
        failures.append("README does not show the command for the proposed project-level skill location")

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


NOISE = HERE / "fixtures" / "real-world-noise"
NOISE_EXPECTED = {
    ("path", "/opt/stack/compose.yaml"),
    ("path", "~/.config/sot/keys.txt"),
    ("host", "edge.example.net"),
    ("ip", "10.0.0.1"),
    ("ip", "127.0.0.1"),
    ("ip", "203.0.113.10"),
    ("port", "22"),
    ("port", "53"),
    ("port", "80"),
    ("port", "5432"),
    ("port", "8080"),
    ("id", "9f2c4b7a1d3e5f60"),
}
NOISE_BANNED = {("port", v) for v in ("404", "30", "90", "10", "2026", "569", "1400", "100",
                                     "2001")}


def noise_checks() -> list[str]:
    """A document shaped like a real system reference must produce no invented facts."""
    failures = []
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "target"
        target.mkdir()
        (target / "SKILL.md").write_text("Nothing here.\n")
        proc = subprocess.run([sys.executable, str(SCRIPT), "diff",
                               str(NOISE / "doc.md"), str(target)],
                              capture_output=True, text=True)
    found = parse_facts(proc.stdout)
    if found != NOISE_EXPECTED:
        invented = found - NOISE_EXPECTED
        absent = NOISE_EXPECTED - found
        failures.append(f"noise: invented {sorted(invented)}; missed {sorted(absent)}\n{proc.stdout}")
    if found & NOISE_BANNED:
        failures.append(f"noise: junk facts survived: {sorted(found & NOISE_BANNED)}")
    if "suppressed" not in proc.stderr:
        failures.append(f"noise: suppression must be reported on stderr\n{proc.stderr}")
    if proc.returncode != 1:
        failures.append(f"noise: expected exit 1, got {proc.returncode}")
    return failures


def masking_checks() -> list[str]:
    """The masking that removes junk must never hide the fact it was protecting."""
    rc, found, out = run_case("The bastion IP is 203.0.113.10.\n", {"SKILL.md": "Nothing here.\n"})
    if rc != 1 or found != {("ip", "203.0.113.10")}:
        return [f"masking: a real IP must survive suppression, got {sorted(found)} rc={rc}\n{out}"]
    return []


def profile_checks() -> list[str]:
    doc = "Node 10.0.0.5 at postgres:5432.\n\n```bash\nsystemctl restart foo\n```\n"
    files = {"SKILL.md": "Nothing here.\n"}
    failures = []
    _, out, _ = run_script(doc, files, extra=("--profile=config",))
    leaked = {k for k, _ in parse_facts(out)} & {"id", "command"}
    if leaked:
        failures.append(f"--profile=config leaked {sorted(leaked)}: {sorted(parse_facts(out))}")
    rc, _, _ = run_script(doc, files, extra=("--profile=bogus",))
    if rc != 2:
        failures.append(f"--profile=bogus: expected exit 2, got {rc}")
    _, out, _ = run_script(doc, files, extra=("--kinds=port",))
    if parse_facts(out) != {("port", "5432")}:
        failures.append(f"--kinds=port override: {sorted(parse_facts(out))}")
    return failures


def pointer_checks() -> list[str]:
    """A doc pointing at its replacement by absolute path is not drifted."""
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "skills" / "network-ops"
        target.mkdir(parents=True)
        (target / "SKILL.md").write_text("Nothing.\n")
        doc = Path(tmp) / "doc.md"
        doc.write_text(f"Moved to {target}/references/runbook.md.\n")
        proc = subprocess.run([sys.executable, str(SCRIPT), "diff", str(doc), str(target)],
                              capture_output=True, text=True)
    if proc.returncode != 0:
        return [f"pointer: absolute path to the target reported as missing\n{proc.stdout}{proc.stderr}"]
    return []


def perf_checks() -> list[str]:
    """Inventory must stay linear: 600 docs plus a data directory, inside a budget."""
    failures = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "docs").mkdir()
        filler = ("A paragraph of prose that stands in for a runbook body. " * 40) + "\n"
        count = 600
        for i in range(count):
            nxt = f"docs/d{i + 1:04d}.md" if i + 1 < count else ""
            (root / "docs" / f"d{i:04d}.md").write_text(f"# Doc {i}\n{filler}See {nxt}.\n")
        (root / "docker" / "data").mkdir(parents=True)
        (root / "docker" / "data" / "blob.txt").write_text("x" * 10_000)
        started = time.time()
        proc = subprocess.run([sys.executable, str(SCRIPT), "inventory", str(root)],
                              capture_output=True, text=True)
        elapsed = time.time() - started
    if proc.returncode != 0:
        failures.append(f"perf: inventory failed rc={proc.returncode}\n{proc.stderr}")
        return failures
    if elapsed > 15:
        failures.append(f"perf: inventory took {elapsed:.1f}s for {count} docs; budget is 15s")
    if f"{count} docs" not in proc.stdout:
        failures.append(f"perf: expected {count} docs in the summary\n{proc.stdout[-400:]}")
    if "blob.txt" in proc.stdout:
        failures.append("perf: application data was censused")
    if "1 with no inbound references" not in proc.stdout:
        failures.append(f"perf: expected exactly one orphan\n{proc.stdout[-300:]}")
    return failures


def version_checks() -> list[str]:
    """The version in the skill and the changelog are the same fact; they may not disagree."""
    skill = (ROOT / "skills" / "source-of-truth" / "SKILL.md").read_text()
    changelog = (ROOT / "CHANGELOG.md").read_text()
    v_skill = re.search(r"^version:\s*([0-9]+\.[0-9]+\.[0-9]+)", skill, re.M)
    v_log = re.search(r"^##\s*([0-9]+\.[0-9]+\.[0-9]+)", changelog, re.M)
    if not v_skill or not v_log:
        return ["version: could not read a version from SKILL.md or CHANGELOG.md"]
    if v_skill.group(1) != v_log.group(1):
        return [f"version: SKILL.md says {v_skill.group(1)}, CHANGELOG.md says {v_log.group(1)}"]
    return []


def self_inventory_checks() -> list[str]:
    """CI proves the tool on this repository: it finishes, it honours .sotignore, and the only
    documents allowed to carry something secret-shaped are the fixtures that demonstrate it."""
    proc = subprocess.run([sys.executable, str(SCRIPT), "inventory", str(ROOT)],
                          capture_output=True, text=True)
    failures = []
    if proc.returncode != 0:
        return [f"self-inventory: exit {proc.returncode}\n{proc.stderr}"]
    offenders = []
    for line in proc.stdout.splitlines():
        parts = line.split()
        if len(parts) == 8 and parts[0].isdigit():
            path, secrets = parts[7], int(parts[6])
            if secrets and not path.startswith("tests/fixtures/"):
                offenders.append(path)
    if offenders:
        failures.append(f"self-inventory: secrets outside the fixtures: {offenders}")
    if ".scratch/" in proc.stdout:
        failures.append("self-inventory: .sotignore was not honoured for .scratch/")
    if "docs" not in proc.stdout.split("\n")[-2]:
        failures.append(f"self-inventory: summary line missing\n{proc.stdout[-200:]}")
    return failures


# --------------------------------------------------------------------------- v1.6 verbs

LEGACY = HERE / "fixtures" / "legacy-tree"
LEGACY_EXPECTED = {
    ("info", "docs/adr/0001-choice.md"),
    ("fail", "docs/authority-a.md"),
    ("fail", "docs/derived-hand.md"),
    ("fail", "docs/nav-dead.md"),
    ("info", "docs/plain.md"),
    ("fail", "docs/stub.md"),
}


def sot(*args, cwd, script=None):
    return subprocess.run([sys.executable, str(script or SCRIPT), *args], cwd=cwd,
                          capture_output=True, text=True)


def git(*args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


def new_repo(tmp: Path, scripts: bool = False) -> Path:
    repo = Path(tmp) / "repo"
    (repo / "docs").mkdir(parents=True)
    git("init", "-q", "-b", "main", cwd=repo)
    git("config", "user.email", "t@example.com", cwd=repo)
    git("config", "user.name", "t", cwd=repo)
    if scripts:
        shutil.copytree(SCRIPT.parent, repo / "skills" / "source-of-truth" / "scripts",
                        ignore=shutil.ignore_patterns("__pycache__"))
    return repo


def _findings(stdout: str) -> set[tuple[str, str]]:
    out = set()
    for line in stdout.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[0] in ("fail", "info"):
            out.add((parts[0], parts[1].split(":")[0]))
    return out


def check_checks() -> list[str]:
    """The class rules fire where they should and stay silent where they should."""
    failures = []
    proc = sot("check", "--all", str(LEGACY), cwd=ROOT)
    if proc.returncode != 1:
        failures.append(f"legacy-tree: expected exit 1, got {proc.returncode}\n{proc.stdout}")
    found = _findings(proc.stdout)
    if found != LEGACY_EXPECTED:
        failures.append(f"legacy-tree findings: missing {sorted(LEGACY_EXPECTED - found)}; "
                        f"unexpected {sorted(found - LEGACY_EXPECTED)}\n{proc.stdout}")
    for quiet in ("derived-ok", "nav-ok", "procedural.md", "record.md"):
        if quiet in proc.stdout:
            failures.append(f"legacy-tree: {quiet} should produce no finding\n{proc.stdout}")

    with tempfile.TemporaryDirectory(dir="/tmp") as tmp:
        repo = new_repo(Path(tmp))
        (repo / "docs" / "bare.md").write_text("# no class\n")
        warn = sot("check", "--all", cwd=repo)
        strict = sot("check", "--all", "--strict", cwd=repo)
        if warn.returncode != 0:
            failures.append(f"undeclared class must not fail by default: exit {warn.returncode}")
        if strict.returncode != 1:
            failures.append(f"--strict must fail an info-tier finding: exit {strict.returncode}")
        if warn.stdout != strict.stdout:
            failures.append("--strict changed the output, not just the exit code")

        (repo / "docs" / "gen.md").write_text("---\nclass: derived\n---\n# hand written\n")
        proc = sot("check", "--all", cwd=repo)
        if "not provably generated" not in proc.stdout:
            failures.append("a hand-written derived document must fail outside a work tree too")
        (repo / "docs" / "gen.md").write_text("---\nclass: derived\n---\nGenerated: x\n# ok\n")
        if "docs/gen.md" in sot("check", "--all", cwd=repo).stdout:
            failures.append("a stamped derived document must pass")

        (repo / "docs" / "leak.md").write_text("---\nclass: procedural\n---\ntoken: ghp_"
                                               "abcdefghijklmnopqrstuvwxyz0123\n")
        proc = sot("check", "--all", cwd=repo)
        if proc.returncode != 3:
            failures.append(f"secret-shaped content must exit 3, got {proc.returncode}")
        if "ghp_" in proc.stdout or "ghp_" in proc.stderr:
            failures.append("the secret value was printed")

    with tempfile.TemporaryDirectory(dir="/tmp") as tmp:
        plain = Path(tmp) / "notgit"
        (plain / "docs").mkdir(parents=True)
        (plain / "docs" / "x.md").write_text("---\nclass: procedural\n---\n")
        if sot("check", cwd=plain).returncode != 2:
            failures.append("check outside a work tree must exit 2, not report clean")
        (plain / "docs" / "hand.md").write_text("---\nclass: derived\n---\n# hand written\n")
        proc = sot("check", "--all", cwd=plain)
        if proc.returncode != 1 or "not provably generated" not in proc.stdout:
            failures.append("outside a work tree a hand-written derived document must fail, not pass: "
                            "git check-ignore exits 0 when there is no repository")

    with tempfile.TemporaryDirectory(dir="/tmp") as tmp:
        repo = new_repo(Path(tmp))
        (repo / "docs" / "old-bad.md").write_text("---\nclass: notes\n---\n")
        (repo / "docs" / "touched.md").write_text("---\nclass: procedural\n---\nok\n")
        git("add", "-A", cwd=repo)
        git("commit", "-qm", "init", cwd=repo)
        (repo / "docs" / "touched.md").write_text("---\nclass: procedural\n---\nchanged\n")
        proc = sot("check", cwd=repo)
        if "old-bad" in proc.stdout:
            failures.append("an untouched document must never be failed by the default scope")
        if "main..working tree" not in proc.stderr:
            failures.append(f"the chosen git base must be printed: {proc.stderr!r}")
    return failures


def init_checks() -> list[str]:
    """init writes only what is absent, never AGENTS.md, and resolves its own path."""
    failures = []
    with tempfile.TemporaryDirectory(dir="/tmp") as tmp:
        repo = new_repo(Path(tmp), scripts=True)
        rel = "skills/source-of-truth/scripts/sot.py"
        before = git("status", "--porcelain", cwd=repo).stdout
        proc = sot("init", "--print", cwd=repo, script=rel)
        if proc.returncode != 0:
            failures.append(f"init --print exited {proc.returncode}\n{proc.stderr}")
        if git("status", "--porcelain", cwd=repo).stdout != before:
            failures.append("init --print wrote to the working tree")
        if str(repo) in proc.stdout:
            failures.append("init --print leaked an absolute path for a script inside the repo")
        if rel not in proc.stdout:
            failures.append("init --print did not use the path relative to the git root")

        proc = sot("init", cwd=repo, script=rel)
        written = sorted(p.name for p in repo.rglob("*") if p.is_file() and ".git" not in p.parts)
        for name in ("doc-classes.md", "adr.md", "runbook.md", ".sotignore"):
            if not any(written_path.endswith(name) for written_path in written):
                failures.append(f"init did not write {name}: {written}")
        if (repo / "AGENTS.md").exists():
            failures.append("init created AGENTS.md; it must only print the block")

        again = sot("init", cwd=repo, script=rel)
        if again.returncode != 0 or again.stdout.count("skip (exists)") != 4:
            failures.append(f"second init must skip four files: {again.stdout}")

        (repo / ".sotignore").write_text("hand edited\n")
        sot("init", "--force", cwd=repo, script=rel)
        if (repo / ".sotignore").read_text() == "hand edited\n":
            failures.append("--force did not restore a file it owns")

    with tempfile.TemporaryDirectory(dir="/tmp") as tmp:
        plain = Path(tmp) / "notgit"
        plain.mkdir()
        if sot("init", cwd=plain).returncode != 2:
            failures.append("init outside a work tree must exit 2")
    return failures


def audit_checks() -> list[str]:
    """audit ranks, never judges, and every command it emits runs."""
    failures = []
    proc = sot("audit", str(LEGACY), cwd=ROOT)
    if proc.returncode != 0:
        failures.append(f"audit must exit 0 on a tree with findings, got {proc.returncode}")
    if "| class | facts | inbound | candidate | command | verdict |" not in proc.stdout:
        failures.append("audit is missing its row header")
    rows = [line for line in proc.stdout.splitlines() if line.startswith("| ") and "---" not in line]
    if len(rows) < 2:
        failures.append(f"audit produced no rows\n{proc.stdout}")
    if "skipped (record)" not in proc.stdout:
        failures.append("audit did not skip a record document")
    if "skipped (stub)" not in proc.stdout:
        failures.append("audit did not skip a stub")

    commands = re.findall(r"`(python3 [^`]+)`", proc.stdout)
    for command in commands:
        args = command.split()
        if args[0] != "python3":
            continue
        done = subprocess.run([sys.executable, *args[1:]], cwd=ROOT, capture_output=True, text=True)
        if done.returncode not in (0, 1):
            failures.append(f"audit emitted a command that cannot run ({done.returncode}): {command}")

    with tempfile.TemporaryDirectory(dir="/tmp") as tmp:
        repo = new_repo(Path(tmp))
        (repo / "docs" / "a.md").write_text("---\nclass: procedural\n---\nport 8080\n")
        (repo / "config").mkdir()
        (repo / "config" / "compose.yml").write_text("ports:\n  - \"8080:80\"\n")
        before = set(p.name for p in repo.iterdir())
        proc = sot("audit", cwd=repo)
        if proc.returncode != 0:
            failures.append(f"audit exited {proc.returncode}")
        if set(p.name for p in repo.iterdir()) != before:
            failures.append("audit wrote to the repository without --out")
        out = repo / "plan.md"
        proc = sot("audit", "--out", str(out), cwd=repo)
        if not out.exists() or str(out) not in proc.stdout:
            failures.append("audit --out did not write the plan or name it")
        top = sot("audit", "--top", "1", cwd=repo)
        if "showing 1 of" not in top.stdout:
            failures.append(f"audit --top did not report the cap: {top.stdout[:200]}")
    return failures


def hook_checks() -> list[str]:
    """The hook blocks a staged violation, ignores an unstaged one, and never eats a commit."""
    failures = []
    with tempfile.TemporaryDirectory(dir="/tmp") as tmp:
        repo = new_repo(Path(tmp), scripts=True)
        rel = "skills/source-of-truth/scripts/sot.py"
        proc = sot("init", "--hook", cwd=repo, script=rel)
        hook = repo / ".git" / "hooks" / "pre-commit"
        if proc.returncode != 0 or not hook.exists():
            failures.append(f"init --hook did not install a hook: {proc.stderr}")
        elif not hook.stat().st_mode & 0o111:
            failures.append("the installed hook is not executable")

        (repo / "docs" / "bare.md").write_text("# no class\n")
        git("add", "docs/bare.md", cwd=repo)
        blocked = git("commit", "-m", "bare", cwd=repo)
        if blocked.returncode == 0:
            failures.append("a staged undeclared document did not block the commit")

        (repo / "docs" / "bare.md").write_text("---\nclass: procedural\n---\n# ok\n")
        git("add", "docs/bare.md", cwd=repo)
        if git("commit", "-m", "bare", cwd=repo).returncode != 0:
            failures.append("adding a class did not let the same commit through")

        (repo / "docs" / "unstaged.md").write_text("# undeclared, never staged\n")
        (repo / "docs" / "ok.md").write_text("---\nclass: procedural\n---\n")
        git("add", "docs/ok.md", cwd=repo)
        if git("commit", "-m", "ok", cwd=repo).returncode != 0:
            failures.append("an unstaged violation blocked the commit; staged-only must hold")

        again = sot("init", "--hook", cwd=repo, script=rel)
        if "skip (managed)" not in again.stdout:
            failures.append("re-running init --hook over its own hook is not idempotent")

    with tempfile.TemporaryDirectory(dir="/tmp") as tmp:
        repo = new_repo(Path(tmp), scripts=True)
        (repo / ".git" / "hooks").mkdir(parents=True, exist_ok=True)
        mine = repo / ".git" / "hooks" / "pre-commit"
        mine.write_text("#!/bin/sh\necho mine\n")
        proc = sot("init", "--hook", cwd=repo, script="skills/source-of-truth/scripts/sot.py")
        if proc.returncode != 2:
            failures.append(f"an unmanaged hook must be refused with exit 2, got {proc.returncode}")
        if mine.read_text() != "#!/bin/sh\necho mine\n":
            failures.append("an unmanaged hook was overwritten")
    return failures


def main() -> int:
    failures: list[str] = []
    passed = 0

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
            passed += 1

    rc, found, out = run_case(SMOKE_DOC, {"SKILL.md": "Nothing here.\n"})
    if found != SMOKE_EXPECTED or rc != 1:
        failures.append(
            f"smoke: expected {sorted(SMOKE_EXPECTED)}, got {sorted(found)} (rc={rc})\n{out}"
        )
    else:
        print(f"PASS smoke flags {len(SMOKE_EXPECTED)} facts")

    for label, check in (("secrets", secret_checks), ("--kinds", kinds_checks),
                         ("inventory", inventory_checks), ("first check", first_check_checks),
                         ("homelab golden", golden_checks), ("readme", readme_checks),
                         ("real-world noise", noise_checks), ("masking safety", masking_checks),
                         ("profiles", profile_checks),
                         ("pointer paths", pointer_checks), ("inventory speed", perf_checks),
                         ("version agreement", version_checks), ("self inventory", self_inventory_checks),
                         ("init", init_checks), ("check", check_checks),
                         ("audit", audit_checks), ("pre-commit hook", hook_checks)):
        found_failures = check()
        failures.extend(found_failures)
        if not found_failures:
            print(f"PASS {label}")
            passed += 1

    if failures:
        print()
        for f in failures:
            print(f"FAIL {f}")
        print(f"\n{len(failures)} failure(s)")
        return 1

    print(f"\n{passed} check(s) passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
