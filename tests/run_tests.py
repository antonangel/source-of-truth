#!/usr/bin/env python3
"""Run the fact-diff fixture tests.

    python3 tests/run_tests.py

Standard library only; no network, no install step.
"""

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SCRIPT = ROOT / "skills" / "source-of-truth" / "scripts" / "fact-diff.py"
FIX = HERE / "fixture"

# Facts the fixture doc holds that the fixture skill does not.
EXPECTED_MISSING = [
    "qc-verify --strict",   # inline backtick command
    "edge.example.net",     # non-.com host
    "/srv/backups",         # prefix-path false pass: skill only has /srv/backups/daily
]
# Facts that are present, including one only in the skill's scripts/ folder.
EXPECTED_PRESENT = [
    "nix build .#queue-service",
    "qc-read --tail 50",
    "api.example.com",
    "/etc/queue/config.yaml",
    "QUEUE_TOKEN",
    "9443",
]


def run(doc: str) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), str(FIX / doc), str(FIX / "skill")],
        capture_output=True, text=True,
    )
    return proc.returncode, proc.stdout + proc.stderr


def main() -> int:
    failures: list[str] = []

    rc, out = run("doc.md")
    if rc != 1:
        failures.append(f"doc.md: expected exit 1, got {rc}\n{out}")
    for needle in EXPECTED_MISSING:
        if needle not in out:
            failures.append(f"doc.md: expected the script to flag {needle!r}\n{out}")
    for needle in EXPECTED_PRESENT:
        if needle in out:
            failures.append(f"doc.md: false positive on {needle!r}\n{out}")

    rc2, out2 = run("complete-doc.md")
    if rc2 != 0:
        failures.append(f"complete-doc.md: expected exit 0, got {rc2}\n{out2}")

    if failures:
        for f in failures:
            print(f"FAIL {f}")
        print(f"\n{len(failures)} failure(s)")
        return 1

    print(f"PASS doc.md flags {len(EXPECTED_MISSING)} facts, ignores {len(EXPECTED_PRESENT)}")
    print("PASS complete-doc.md exits 0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
