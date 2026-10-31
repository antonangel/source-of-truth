"""Static artifacts that `sot.py init` writes or prints.

Data, not logic. The class contract, two document templates, the ignore defaults, and the two blocks
the operator pastes. Keeping them here leaves `sot.py` as dispatch.
"""

DOC_CLASSES = """# Doc classes — one source of truth per fact class

Every durable fact has exactly one authoritative home. A document that restates another class's
facts is either generated or deleted; it is never maintained by hand.

## The seven classes

| class | what it owns | enforced by the checker |
|---|---|---|
| `derived` | state produced mechanically from the system; gitignored, or stamped `Generated:` | fail |
| `authority` | the declared state of the system — exactly one document | fail |
| `vocabulary` | what words mean here — exactly one document | fail |
| `navigational` | where to look; every path it names must resolve | fail |
| `decided` | a choice that cannot be re-derived, with the alternatives that lost | advisory |
| `procedural` | how to perform a class of task; prefer a skill over prose | none |
| `record` | what happened or what was proposed, frozen at authoring time | exempt |

`vendor/` and `template/` are directory attributes, not classes: neither owns a durable fact. A
vendored tree is somebody else's text and no rule applies to it.

## Declaring a class

A file's class is decided in this order:

1. **Frontmatter** — `class: <name>` in the file's YAML frontmatter.
2. **Directory map** — an optional `.sotclasses` file maps a directory to a class for every file
   inside, one `path class` pair per line. It is repository data, like `.sotignore`; the class list
   itself belongs to the tool and is not configurable.
3. **Unmapped** — reported as `info`. It is not an error; it is a prompt to classify the file the
   next time you touch it.

A header alone is not proof. `class: derived` fails the check unless the file is gitignored or
carries a `Generated:` stamp — otherwise it is a hand-written document wearing a generated label.

## Stubs

A document that has been replaced by a pointer keeps its path and declares both halves:

```yaml
class: navigational
canonical: path/to/the/authoritative/document.md
```

The checker fails when `canonical` does not resolve. That is the only thing that catches a stub whose
target was renamed, which is the most common rot after a consolidation.

## What no machine checks

Whether a document restates configuration, and whether a runbook is any good. Those are review
questions, asked once, when the document is written:

> Which fact does this document own that no other source owns?

If the answer is none, it is a copy. Say what it is a copy of, who owns the original, and when it is
refreshed — or delete it.
"""

ADR_TEMPLATE = """# ADR NNNN: <the decision in one line>

Status: proposed | accepted | superseded by ADR-NNNN
Date: YYYY-MM-DD

## Context

What is true now that makes this a decision rather than an obvious step. Include the measurement
that made it non-obvious, if there was one.

## Decision

What we will do. Number the points when there is more than one, because a later reader will cite
them by number.

## Consequences

What gets harder, what gets easier, and what this rules out. Non-obvious downstream effects only.

## Rejected alternatives

Each alternative and the reason it lost. This is the section that stops the same proposal coming
back in six months, and it is the section most often skipped.
"""

RUNBOOK_TEMPLATE = """# Runbook: <the task>

**When to use:** the trigger, in one line.
**Preconditions:** the access, backups and state that must be true before step 1.

## Steps

1. Inspect the current state.
2. Change only the approved scope.
3. Verify.

## Verifier

The command or endpoint that proves it worked, and the output you expect to see. A runbook without
a verifier is a wish.

## Rollback

The exact steps to undo this, or `unavailable` and the reason it is unavailable.

## Notes

Only the facts this runbook owns. Link the config instead of restating it; a restated port is a
second home for a fact and the two will disagree within a month.
"""

SOTIGNORE = """# One glob per line. A pattern matches a path, a basename, or a path segment.
# Directories already skipped everywhere: .git node_modules __pycache__ .venv venv data vendor
# dist result
#
# Vendored third-party documentation is not yours to classify.
external

# Add your own generated or archival trees below, one per line.
"""

AGENTS_BLOCK = """Before adding or editing a document here:
1. Declare its class in frontmatter (`class: <name>`), or place it in a directory whose class is mapped.
2. One fact, one home. A document that restates config is generated or deleted.
3. Before stubbing a document, run:
   python3 {ref} diff <doc> <target> --profile=config
"""

CI_SNIPPET = """# .github/workflows/docs.yml
name: docs
on: [push, pull_request]
jobs:
  source-of-truth:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: python3 {ref} check --all
"""

OWNED = (
    ("docs/doc-classes.md", DOC_CLASSES),
    ("docs/templates/adr.md", ADR_TEMPLATE),
    ("docs/templates/runbook.md", RUNBOOK_TEMPLATE),
    (".sotignore", SOTIGNORE),
)


def agents_block(ref: str) -> str:
    return AGENTS_BLOCK.format(ref=ref)


def ci_snippet(ref: str) -> str:
    return CI_SNIPPET.format(ref=ref)
