---
name: source-of-truth
description: "Use when docs drift from config, or a repo needs a doc contract and an audit."
version: 1.6.0
license: MIT
---

# Source of Truth

Help an operator give every durable fact exactly one home. Three verbs do the work: `init` installs
the contract, `check` enforces the mechanical part of it, `audit` produces a worklist. `diff` remains
the focused comparison of one document against one target.

Every command is read-only with respect to document bodies. The tool never decides which source is
authoritative, never judges whether a document is correct, and never edits prose.

## When to use

- The operator asks what to do about a repository of infrastructure docs.
- A runbook looks stale, or `AGENTS.md` disagrees with the compose file.
- A document and a skill describe the same procedure.
- A repository has no way to stop the next document drifting.

## The three verbs

1. **`init`** — once per repository. Writes `docs/doc-classes.md`, two templates and `.sotignore`
   only when absent; prints the `AGENTS.md` block and a CI snippet it will not write. `--print`
   writes nothing, `--hook` installs a pre-commit check, `--force` overwrites files it owns. It never
   edits `AGENTS.md`.
2. **`check`** — the standing gate. Default scope is changed documents, `--staged` is the index,
   `--all` is everything. `--strict` promotes info-tier findings to a failure.
3. **`audit`** — the invoked sweep. One row per document, ranked, each carrying the exact `diff`
   command. It **cannot pass**: exit `0` means a plan was produced.

Run the script from the skill's installed directory; never assume a fixed path:

```bash
python3 <skill>/scripts/sot.py init --print
python3 <skill>/scripts/sot.py check --staged --strict
python3 <skill>/scripts/sot.py audit --top 25
```

## Interpret results safely

- Exit `0`: clean at the current threshold. Not proof a document is correct.
- Exit `1`: findings. Quote the tier, the path and, when present, the line.
- Exit `2`: usage, path, or a directory that is not a git work tree.
- Exit `3`: possible secret-shaped content. Report the kind and `file:line` only; never the value.
- An `info` tier row is a prompt, not a defect. It means nobody has decided what this document owns.
- A skipped record or stub is not a clean check — the comparison did not run for that document.

## The class model

Seven classes are declarable; five are enforced. Say five, not seven.

| class | rule |
|---|---|
| `derived` | fails unless gitignored or stamped `Generated:` in the first 1000 characters |
| `authority` | fails if a second document declares it |
| `vocabulary` | fails if a second document declares it |
| `navigational` | fails on an unresolvable `docs/...` path or `canonical:` target |
| `decided` | advisory: duplicate decision numbers |
| `procedural` | declarable, unenforced — no machine can judge a runbook |
| `record` | exempt; records are never rewritten |

Class comes from frontmatter `class:`, then an optional `.sotclasses` directory map, then undeclared.
There is no name map: a special-cased filename is an authority the operator cannot see.

A stub keeps its path and declares `class: navigational` with `canonical: <path>`. The check fails
when that target does not resolve, which is the only thing that catches a stub whose skill was
renamed.

## `diff`, the focused comparison

One document, one target, one confirmed pair. The operator chooses both; if a target is suggested,
name it and why, then ask before running. Use `--profile=config` for a config directory and
`--profile=skill` for a skill directory.

Report the target, the profile, every finding exactly as printed with its `document:line`, and the
count. Recommend review; do not infer what to edit. If the output says an append-only record was
skipped, that is not a clean check — ask whether the operator wants it checked with `--force`.

## Ownership and preservation

"One authoritative owner per fact" does not mean one physical copy. A document may own decisions,
vocabulary, navigation, history, and operational knowledge no config can express. A deliberate copy
states its purpose, canonical owner, and refresh rule. Keep break-glass recovery readable without an
agent. Never treat a literal-check result as permission to stub or delete.

## Before any migration

Only when the operator asks for broader cleanup, present a named plan first: the exact documents and
proposed actions, each fact's current and proposed owner, what must be preserved, the links to
update, secret findings by kind and line only, and the verification and rollback steps. Wait for
explicit approval. Show the diff afterwards. Never auto-commit, schedule, or file issues.

## References

- `references/examples.md`: real output for `init`, `diff`, `check` and `audit`, generated from the CLI.
- `references/sources-and-secrets.md`: source ownership, secret handling, and the audit plan format.
- The source repository's `docs/adr/0002-three-verbs-and-the-standing-contract.md` explains why the
  three verbs are shaped this way; the ADR is not shipped with the installed skill.
