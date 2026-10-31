# Source of Truth

An agent skill for fixing the most expensive doc problem: **two copies of the same fact, and no way to
tell which one is current.**

A doc is a cache, not a source. It earns its load when the lookup is expensive — a decision's
rationale, a domain word, a pointer to the right file. Everything derivable gets derived; everything
procedural belongs in a skill, which runs and fails visibly instead of drifting silently.

## Install

```bash
npx skills@latest add <this-repo> -a <agent>     # cursor, claude-code, codex, opencode, …
```

Or copy `skills/source-of-truth/` into your agent's skills directory. No dependencies: the one script
is Python stdlib.

## What it does

**Classifies every doc by the kind of fact it states** — derived, decided, vocabulary, procedural,
navigational — and sends it to its one home:

- derived → generated, or deleted
- decided → an ADR, linked not restated
- vocabulary → one glossary
- procedural → a **skill**, the one form that fails at runtime
- navigational → a path that must resolve

**Gives you four tests** for the ambiguous ones: the deletion test, the drift test, the fact-diff test,
and the silence test (a subsystem the authority doc never mentions reads as *absent*).

**Ships the consolidation procedure**, for the case that dominates real repos: a doc and a skill that
describe the same procedure, maintained in parallel. Survey → pair by topic → fact-diff → migrate
verbatim → stub → verify. The doc's path survives as a pointer, so every inbound link keeps working.

## The one script

```bash
python3 skills/source-of-truth/scripts/fact-diff.py docs/backup.md ~/.claude/skills/backup-ops
```

Lists the paths, hosts, IP addresses, ids, env vars, ports and command lines the doc holds that the skill does not.
**Exit 0** = no missing facts detected — necessary, not sufficient, because the script compares facts
and not usefulness. **Exit 1** = the doc is not redundant; it is unmigrated.

This exists because text similarity misled us once. In the single repo this was extracted from (n=1),
genuinely duplicate doc/skill pairs shared **under 10%** of their tokens — a similarity search would
have called them unrelated, and a naive cleanup would have deleted 20 working commands. Treat overlap
as a hint for finding candidates, never as a verdict.

## Why the deletion-first instinct is wrong

Run the deletion test on a real docs tree and almost nothing passes. Repos are not full of junk; they
are full of procedures that were never migrated. An honest docs audit ends with **zero deletions and a
pile of migrations** — which is a better result, because the knowledge moves somewhere it can be
executed.

## Contents

```
skills/source-of-truth/
├── SKILL.md                                  the doctrine: classes, tests, procedures, anti-patterns
├── references/consolidation-walkthrough.md   a worked run with real numbers
└── scripts/fact-diff.py                      the migrate-before-stub gate
```

## License

MIT.
