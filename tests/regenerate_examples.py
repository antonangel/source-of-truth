#!/usr/bin/env python3
"""Regenerate the minimal first-check example from real CLI output."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/source-of-truth/scripts/sot.py"
DOC = "tests/fixtures/first-check/docs/dns-runbook.md"
TARGET = "tests/fixtures/first-check/config"
COMMAND = ("python3 skills/source-of-truth/scripts/sot.py diff "
           f"{DOC} {TARGET} --profile=config")


def main() -> int:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "diff", DOC, TARGET, "--profile=config"],
        cwd=ROOT, capture_output=True, text=True,
    )
    expected = (
        f"ip       203.0.113.10  {DOC}:3\n"
        "missing facts: 1 of 1 checked\n"
    )
    if proc.returncode != 1 or proc.stdout != expected or proc.stderr:
        raise SystemExit(f"first-check fixture changed unexpectedly:\n{proc.stdout}{proc.stderr}")

    text = f"""# First check: one literal mismatch

Run this exact command from the repository root against the synthetic fixture. The source document contains one IP that the selected config target does not contain.

```text
$ {COMMAND}
{proc.stdout.rstrip()}
```

Expected exit code: `1`, meaning one missing literal fact. The finding identifies the fact kind and its exact document line. This comparison does not validate meaning, semantic correctness, completeness, or live runtime state. It does not edit either input.
"""
    target = ROOT / "skills/source-of-truth/references/examples.md"
    target.write_text(text)
    print(f"wrote {target} ({len(text.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
