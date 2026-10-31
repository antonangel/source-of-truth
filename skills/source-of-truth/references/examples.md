# Examples: real output, generated from the CLI

Every block below is produced by running the command; nothing here is written by hand. Regenerate
with `python3 tests/regenerate_examples.py`.

## First check: one literal mismatch

Run from the repository root against the synthetic fixture. The document states one IP that the
selected config target does not contain.

```text
$ python3 skills/source-of-truth/scripts/sot.py diff tests/fixtures/first-check/docs/dns-runbook.md tests/fixtures/first-check/config --profile=config
ip       203.0.113.10  tests/fixtures/first-check/docs/dns-runbook.md:3
missing facts: 1 of 1 checked
```

Expected exit code: `1`, one missing literal fact, identified by kind and exact document line. Neither
input is modified. This comparison does not validate meaning, completeness, or live runtime state.

## `init --print`: what the contract looks like

Writes nothing. The path in the printed block is resolved at run time from where the script actually
lives, so it is correct for this install and never hardcoded.

```text
$ python3 skills/source-of-truth/scripts/sot.py init --print
source-of-truth init — .

would write       docs/doc-classes.md
would write       docs/templates/adr.md
would write       docs/templates/runbook.md
would write       .sotignore

4 would be written, 0 skipped (--print: nothing written)

paste this into AGENTS.md (this tool never edits it):

Before adding or editing a document here:
1. Declare its class in frontmatter (`class: <name>`), or place it in a directory whose class is mapped.
2. One fact, one home. A document that restates config is generated or deleted.
3. Before stubbing a document, run:
   python3 skills/source-of-truth/scripts/sot.py diff <doc> <target> --profile=config

paste this into your CI workflow (this tool never writes it):

# .github/workflows/docs.yml
name: docs
on: [push, pull_request]
jobs:
  source-of-truth:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: python3 skills/source-of-truth/scripts/sot.py check --all
```

## `check --all`: structural findings, with tiers

`info` rows do not fail the run. `--strict` would promote them and change nothing else in the output.

```text
$ python3 skills/source-of-truth/scripts/sot.py check --all
info  docs/notes.md  undeclared class (add `class: <name>` to frontmatter, or map its directory in .sotclasses)
1 findings (0 fail, 1 info)
```

## `audit`: a ranked worklist, never a verdict

Exit code `0`: a plan was produced. Each paired row carries the exact `diff` command for that pair.
Records and stubs are skipped and listed last.

```text
$ python3 skills/source-of-truth/scripts/sot.py audit
# Docs audit: .  (YYYY-MM-DD)

Ranked by class, then inbound references, then facts stated. A candidate is a candidate: run the command rather than trusting the column.

| class | facts | inbound | candidate | command | verdict |
|---|---|---|---|---|---|
| procedural | 2 | 0 | config | `python3 skills/source-of-truth/scripts/sot.py diff docs/runbook.md config --profile=config` |  |
| decided | 1 | 0 | - | - | skipped (record) |
| undeclared | 0 | 0 | - | - | no candidate |

3 documents, 1 paired, 0 stubs, 1 records.
```
