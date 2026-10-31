# Source of Truth

An agent skill for homelabs whose docs have started lying to the agent that reads them.

Your runbook says one port and the compose file says another. `AGENTS.md` describes a service you
retired. The same restore procedure lives in a doc and in a skill, and they disagree. Nobody can say
which copy is current, so the agent picks one and builds on it.

## What it does

- Gives every fact one home: generated from config, an ADR, a glossary, a skill, or a pointer
  ([classes and layer map](skills/source-of-truth/SKILL.md#classify-the-fact-then-place-it)).
- Runs an audit that ends in a written plan you approve before anything moves
  ([workflow](skills/source-of-truth/SKILL.md#audit-workflow)).
- Checks nothing is lost: `sot.py diff` lists what a doc states that its replacement does not.
- Catches drift from your config, such as a runbook that says 8080 where compose maps 8081.
- Scrubs secrets before a doc is copied, and keeps recovery steps readable when the agent host is
  down ([sources and secrets](skills/source-of-truth/references/sources-and-secrets.md)).

It never deletes a doc. The path survives as a pointer, so links keep working.

## Install

Claude Code:

```bash
git clone https://github.com/antonangel/source-of-truth
cp -r source-of-truth/skills/source-of-truth ~/.claude/skills/
```

Other agents: copy the `skills/source-of-truth/` folder to wherever your agent loads skills from.
Check its documentation for the directory.

## Try it

The repo bundles an invented homelab. From `tests/fixtures/example-stack`:

```bash
python3 ../../../skills/source-of-truth/scripts/sot.py diff docs/dns-runbook.md skills/network-ops
python3 ../../../skills/source-of-truth/scripts/sot.py diff docs/dns-runbook.md config --kinds=path,host,ip,port,env,id
```

The first shows what the doc holds that the skill lacks. The second finds the stale port. Full output
and the migration that follows: [examples](skills/source-of-truth/references/examples.md).

## Scripts

Python 3.10+, standard library only.

- `scripts/sot.py inventory [repo]` (also `scripts/doc-inventory.py` shim): each doc with size,
  age, inbound references, fact counts and possible secrets.
- `scripts/sot.py diff <doc> <skill-or-config-dir> [--kinds=a,b]` (also `scripts/fact-diff.py`
  shim): exit 0 when nothing is missing, 1 when facts are. Secret warnings go to stderr, by line,
  never with the value.

Fact kinds: `path`, `host`, `ip`, `port`, `env`, `id`, `command`.

Run the tests with `python3 tests/run_tests.py`.

## Limits

- Exit 0 is necessary, not sufficient: it compares facts, not usefulness. Read the pair.
- Config keys, image names, IPv6 and MAC addresses are not extracted.
- The secret scan is a tripwire for docs, not a history scanner.
- Built for homelabs and small infra repos where an agent loads skills on demand.

MIT licensed.
