#!/usr/bin/env python3
"""Regenerate references/examples.md from real CLI output.

Every example is produced by running the CLI, never written by hand. Two normalisations keep the
file stable across machines: the throwaway repository's absolute path becomes `example-repo`, and
the audit's date becomes `YYYY-MM-DD`.
"""
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/source-of-truth"
SCRIPT = SKILL / "scripts/sot.py"
DOC = "tests/fixtures/first-check/docs/dns-runbook.md"
TARGET = "tests/fixtures/first-check/config"
REL = "skills/source-of-truth/scripts/sot.py"


def run(args, cwd):
    return subprocess.run([sys.executable, *args], cwd=cwd, capture_output=True, text=True)


def build_repo(tmp: Path) -> Path:
    """A small repository that exercises every rule the examples need."""
    repo = tmp / "example-repo"
    (repo / "docs" / "adr").mkdir(parents=True)
    (repo / "config").mkdir(parents=True)
    (repo / "skills" / "source-of-truth").mkdir(parents=True)
    shutil.copytree(SKILL / "scripts", repo / "skills" / "source-of-truth" / "scripts")
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, capture_output=True)

    (repo / "config" / "compose.yml").write_text(
        "services:\n  web:\n    ports:\n      - \"8080:80\"\n")
    (repo / "docs" / "runbook.md").write_text(
        "---\nclass: procedural\n---\n# Deploy the web tier\n"
        "The proxy listens on port 8080 and 10.0.0.5 holds the database.\n")
    (repo / "docs" / "adr" / "0001-port-choice.md").write_text(
        "---\nclass: decided\n---\n# ADR 0001: port 8080\n")
    (repo / "docs" / "notes.md").write_text("# Notes\nNothing declared here.\n")
    return repo


def normalise(text: str, repo: Path) -> str:
    text = text.replace(str(repo), "example-repo")
    return re.sub(r"\(\d{4}-\d{2}-\d{2}\)", "(YYYY-MM-DD)", text)


def main() -> int:
    first = run([str(SCRIPT), "diff", DOC, TARGET, "--profile=config"], ROOT)
    expected = f"ip       203.0.113.10  {DOC}:3\nmissing facts: 1 of 1 checked\n"
    if first.returncode != 1 or first.stdout != expected or first.stderr:
        raise SystemExit(f"first-check fixture changed unexpectedly:\n{first.stdout}{first.stderr}")

    with tempfile.TemporaryDirectory(dir="/tmp") as tmp:
        repo = build_repo(Path(tmp))
        init = run([REL, "init", "--print"], repo)
        check = run([REL, "check", "--all"], repo)
        audit = run([REL, "audit"], repo)
        for name, proc in (("init", init), ("check", check), ("audit", audit)):
            if proc.returncode != 0:
                raise SystemExit(f"{name} exited {proc.returncode}:\n{proc.stdout}{proc.stderr}")

        init_out = normalise(init.stdout, repo).rstrip()
        check_out = normalise(check.stdout, repo).rstrip()
        audit_out = normalise(audit.stdout, repo).rstrip()

    text = f"""# Examples: real output, generated from the CLI

Every block below is produced by running the command; nothing here is written by hand. Regenerate
with `python3 tests/regenerate_examples.py`.

## First check: one literal mismatch

Run from the repository root against the synthetic fixture. The document states one IP that the
selected config target does not contain.

```text
$ python3 {REL} diff {DOC} {TARGET} --profile=config
{first.stdout.rstrip()}
```

Expected exit code: `1`, one missing literal fact, identified by kind and exact document line. Neither
input is modified. This comparison does not validate meaning, completeness, or live runtime state.

## `init --print`: what the contract looks like

Writes nothing. The path in the printed block is resolved at run time from where the script actually
lives, so it is correct for this install and never hardcoded.

```text
$ python3 {REL} init --print
{init_out}
```

## `check --all`: structural findings, with tiers

`info` rows do not fail the run. `--strict` would promote them and change nothing else in the output.

```text
$ python3 {REL} check --all
{check_out}
```

## `audit`: a ranked worklist, never a verdict

Exit code `0`: a plan was produced. Each paired row carries the exact `diff` command for that pair.
Records and stubs are skipped and listed last.

```text
$ python3 {REL} audit
{audit_out}
```
"""
    target = SKILL / "references" / "examples.md"
    target.write_text(text)
    print(f"wrote {target} ({len(text.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
