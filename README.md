# Source of Truth

Infrastructure knowledge integrity for AI agents and the people who operate infrastructure.

Documentation drifts. A runbook says one port and compose says another; `AGENTS.md` describes a
service you retired; the same procedure lives in a doc and a skill and the two disagree. An agent
still has to decide, and it may build on the wrong copy. This repository gives each class of fact
one home, a deterministic check for what is mechanical, and a procedure for moving knowledge
without losing any.

## One home per fact class

| Information | Authoritative home |
|---|---|
| Current technical configuration | compose, Nix, proxy and DNS config |
| Decisions and their rationale | ADRs |
| Shared vocabulary | one glossary |
| Operational procedure | agent skills |
| Navigation | `AGENTS.md`, README |
| History | append-only records, never rewritten |

A document may point at a fact owned elsewhere. It may not keep a second copy of it.

## What ships

- **The skill** — `skills/source-of-truth/SKILL.md`: classify, audit, plan, migrate, verify, and say when to stop for approval.
- **The check** — `scripts/sot.py`: inventory a repository, or compare one doc against what should supersede it. Python 3.10+, standard library only.

## Install

Claude Code:
```bash
git clone https://github.com/antonangel/source-of-truth
cp -r source-of-truth/skills/source-of-truth ~/.claude/skills/
```

Other agents: copy `skills/source-of-truth/` wherever your agent loads skills from.

## Try it on your own repo

Markdown only, data and build directories pruned, `.sotignore` honoured:

```bash
python3 skills/source-of-truth/scripts/sot.py inventory .
```

One row per doc: size, age, inbound links, facts stated, possible secrets. Most repos show orphans
on the first run. Then compare a doc against the skill that should supersede it:

```bash
python3 skills/source-of-truth/scripts/sot.py diff docs/runbook.md skills/some-skill --profile=skill
```

Each line is a fact the doc states, the skill lacks, and the line it came from. For drift rather
than duplication use `--profile=config`, which drops commands and commit ids a config directory
cannot hold.
Fact kinds: `path`, `host`, `ip`, `port`, `env`, `id`, `command`.

## Measured

One homelab, 889 docs: 304 that nothing links to, 113 holding something secret-looking, 7.2s and 8.7s on two runs. Run it on your own repo; one repository measured once is a data point, not a benchmark.

## Limits

- Exit 0 is necessary, not sufficient: it compares facts, not usefulness. Read the pair.
- Precision beats recall: an ambiguous number is suppressed and counted, never guessed at.
- Config keys, image names, IPv6 and MAC addresses are not extracted, and the secret scan is a tripwire for docs rather than a history scanner.

MIT licensed.
