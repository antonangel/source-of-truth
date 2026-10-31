# Source of Truth

One fact, one home. A read-only checker and an installable document contract for self-hosters who
keep infrastructure docs and text config in a local Git repo and use agents to maintain them.
Python 3.10+, standard library only. No command edits a document.

## 60 seconds

```bash
python3 .claude/skills/source-of-truth/scripts/sot.py init --print
python3 .claude/skills/source-of-truth/scripts/sot.py init --hook
```

`init` writes `docs/doc-classes.md`, two templates and `.sotignore` only when absent, installs a
pre-commit check over staged Markdown, and prints the `AGENTS.md` block and CI snippet it will not
write. Then prove the checker works — this fixture has one missing IP:

```text
$ python3 skills/source-of-truth/scripts/sot.py diff tests/fixtures/first-check/docs/dns-runbook.md tests/fixtures/first-check/config --profile=config
ip       203.0.113.10  tests/fixtures/first-check/docs/dns-runbook.md:3
missing facts: 1 of 1 checked
```

Exit `1`: one missing literal fact with its exact line, neither input modified. Exit `0` means only
that no selected literal facts were missing — not that a document is correct.

## Commands

| command | answers |
|---|---|
| `init` | where does a fact belong here, and what stops the next document drifting |
| `check` | is this document structurally valid — class declared, generated things provably generated, links resolving |
| `audit` | what should a human look at first |
| `diff` | does this document state a literal fact its target does not |
| `inventory` | size, age, inbound references, fact counts |

`check` defaults to changed documents, `--staged` to the index, `--all` to everything; `--strict`
promotes info-tier findings to a failure. `audit` exits `0` whenever it produced a plan: a ranked
worklist, never a verdict.

Seven classes are declarable and five are enforced; `init` writes the contract to
`docs/doc-classes.md`, its only home. A stub declares `class: navigational` and `canonical: <path>`.

## Install

Claude Code `2.1.49` with `.claude/skills/source-of-truth/` is the first test target and has **not**
passed end-to-end validation; it is not a support claim.

```bash
git clone https://github.com/antonangel/source-of-truth /tmp/source-of-truth
mkdir -p .claude/skills && cp -R /tmp/source-of-truth/skills/source-of-truth .claude/skills/
python3 .claude/skills/source-of-truth/scripts/sot.py diff path/to/runbook.md path/to/config --profile=config
```

## Boundaries

- Exit codes are a contract: `0` clean at the threshold, `1` findings, `2` usage, `3` possible
  secret-shaped content. Read warnings even when findings are reported; never repeat a value.
- The trigger is opt-in. `--hook` installs the pre-commit check, nothing else runs it, and
  `git commit --no-verify` bypasses it. The CI snippet is printed, not written.
- Literal, not semantic: no runtime state, no application UI or API, no judgement about whether a
  procedure is correct. The operator chooses which source is authoritative.
- Read-only: no command edits a document body. Broader cleanup needs a named plan and approval.

Fact kinds: `path`, `host`, `ip`, `port`, `env`, `id`, `command`. See the
[agent workflow](skills/source-of-truth/SKILL.md),
[secret handling](skills/source-of-truth/references/sources-and-secrets.md) and
[ADR 0002](docs/adr/0002-three-verbs-and-the-standing-contract.md).

MIT licensed.