#!/usr/bin/env python3
"""Regenerate skills/source-of-truth/references/examples.md from real script output.

The examples file is a claim about what the tool prints. Generating it means it cannot drift.
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path("/home/angel/source-of-truth")
SCRIPT = ROOT / "skills/source-of-truth/scripts/sot.py"
FIXTURE = ROOT / "tests/fixtures/example-stack"
DOC = "docs/dns-runbook.md"
SKILL = "skills/network-ops"


def run(cwd: Path, *args: str) -> tuple[int, str, str]:
    proc = subprocess.run([sys.executable, str(SCRIPT), "diff", *args], cwd=cwd,
                          capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


def block(command: str, stdout: str, stderr: str = "") -> str:
    body = stdout.rstrip("\n")
    extra = ""
    if stderr.strip():
        extra = "\n\nOn stderr:\n\n```text\n" + stderr.strip() + "\n```"
    return f"```text\n$ {command}\n{body}\n```{extra}"


def main() -> int:
    rc_before, out_before, err_before = run(FIXTURE, DOC, SKILL)
    rc_drift, out_drift, err_drift = run(FIXTURE, DOC, "config", "--profile=config")

    with tempfile.TemporaryDirectory() as tmp:
        migrated = Path(tmp) / "example-stack"
        shutil.copytree(FIXTURE, migrated)
        scrubbed = (migrated / DOC).read_text().replace("hunter2hunter2", "<password>")
        (migrated / DOC).write_text(scrubbed)
        (migrated / SKILL / "references").mkdir()
        (migrated / SKILL / "references" / "dns-runbook.md").write_text(scrubbed)
        rc_after, out_after, err_after = run(migrated, DOC, SKILL)

    assert rc_before == 1, rc_before
    assert rc_drift == 1, rc_drift
    assert rc_after == 0 and not err_after.strip(), (rc_after, err_after)

    cmd_a = f"python3 scripts/sot.py diff {DOC} {SKILL}"
    cmd_b = f"python3 scripts/sot.py diff {DOC} config --profile=config"

    text = f"""# Before and after: one DNS runbook

An invented example: one doc, one skill, no real hosts. The files are in
`tests/fixtures/example-stack/` and the output below is generated from them by
`tests/regenerate_examples.py`, then compared against real output by the test suite.

## Before

`docs/dns-runbook.md` describes the Pi-hole restart, the published ports and the admin address. The
`network-ops` skill covers the same job in different words. Run the fact-diff:

{block(cmd_a, out_before, err_before)}

Every line ends with the document and line the fact came from, so a finding can be judged in
context without re-reading the file. The doc is not redundant: nine facts exist only in the doc, and
line 24 holds a password.

## Scrub, then migrate

Replace the password with a placeholder, rotate the old one, copy the doc into
`{SKILL}/references/dns-runbook.md` unchanged, and turn `{DOC}` into a pointer:

```markdown
# DNS and proxy runbook (moved)

Canonical home: the `network-ops` skill.
Full original text: `{SKILL}/references/dns-runbook.md`.
Holds: DNS restart procedure, published ports, admin UI address.
Do not add procedure to this file.
```

## After

{block(cmd_a, out_after)}

Run against the original text, before it becomes the pointer. The doc is still at its path, so
nothing that linked to it broke, and the procedure has one home.

## And the drift check

The same doc against the compose directory:

{block(cmd_b, out_drift, err_drift)}

Port `8080` is the useful line. The runbook says the admin UI is on 8080; the compose file maps
`8081:80`. The doc was stale, and an agent following it would have been wrong.

`--profile=config` is why there are no commit ids or command lines in that output: a config
directory cannot hold them, so comparing them would report drift that does not exist.

# Consolidation walkthrough

A real run, kept for the numbers rather than the story: a single-node homelab repo, 27 runbooks,
334 skills, and a doctrine that said procedural docs belong in skills.

## What the measurement said

- Best text overlap between any runbook and its obvious skill: **9.9%**.
- Genuine duplicates, not copies: both sides hand-maintained, both drifting, neither derived from
  the other. A similarity search would have called them unrelated.
- A fact-diff of all 14 candidate pairs: **every one** carried between 4 and 20 facts the skill
  lacked: health-command lines, compose paths, container addresses, systemd unit names.

Conclusion that changed the plan: stubbing on similarity would have deleted working procedure.
Every pair needed migration first.

## What the migration looked like

Two shapes, chosen by what the doc held:

1. **Move verbatim into `references/`** for anything with a template, a YAML pattern, or a research
   trail. The original text arrives unchanged; the skill gains an index line pointing at it.
2. **Fold into the skill body** for a short state block: the numbers, the classifier command, the
   one rule that was missing. About 15 lines, no prose loss.

Either way the doc became a ten-line pointer: canonical skill, reference path, what it holds, and
the sentence "do not add procedure to this file".

## Result

- 14 docs converted, in four commits.
- `docs/runbooks/`: 3,771 -> 2,230 lines. File count unchanged at 27, so every inbound link
  resolved.
- Skills gained 1,545 lines across `references/` and a dozen index lines.
- The repo's drift-check finding count never moved: 86 before, 86 after, through every step.

## What went wrong, worth repeating

- **A summary would have been a deletion.** The first plan was to condense each doc into a
  paragraph. The fact-diff showed that removing a paragraph removes the commands in it.
- **`git add` on a tracked skill directory stages the whole directory**, including another
  session's uncommitted `SKILL.md`. One 5-line patch committed as `SKILL.md | 74 ++++`. Stage
  `<skill>/SKILL.md` and `<skill>/references/<file>` by name.
- **A doc that exists only as a pointer still needs its path.** Deleting it breaks every link that
  named it, and the readers who follow those links learn not to trust the next one.
"""
    target = ROOT / "skills/source-of-truth/references/examples.md"
    target.write_text(text)
    print(f"wrote {target} ({len(text.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
