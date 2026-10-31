# Before and after: one DNS runbook

An invented example: one doc, one skill, no real hosts. The files are in
`tests/fixtures/example-stack/` and the output below is checked against them by the test suite.

## Before

`docs/dns-runbook.md` describes the Pi-hole restart, the published ports and the admin address. The
`network-ops` skill covers the same job in different words. Run the fact-diff:

```text
$ python3 scripts/sot.py diff docs/dns-runbook.md skills/network-ops
host     pihole.example.com
ip       10.0.0.1
port     443
port     53
port     80
port     8080
command  cd /opt/example/dns
command  docker compose pull
command  docker compose up -d pihole
missing facts: 9 of 13 checked
```

On stderr, one more line:

```text
warning: possible secret (credential assignment) at docs/dns-runbook.md:24
```

The doc is not redundant. Nine facts exist only in the doc, and line 24 holds a password.

## Scrub, then migrate

Replace the password with a placeholder, rotate the old one, copy the doc into
`skills/network-ops/references/dns-runbook.md` unchanged, and turn `docs/dns-runbook.md` into a
pointer:

```markdown
# DNS and proxy runbook (moved)

Canonical home: the `network-ops` skill.
Full original text: `skills/network-ops/references/dns-runbook.md`.
Holds: DNS restart procedure, published ports, admin UI address.
Do not add procedure to this file.
```

## After

```text
$ python3 scripts/sot.py diff docs/dns-runbook.md skills/network-ops
no missing facts detected (14 checked)
```

(Run it on the original text, before it becomes the pointer.)

The doc is still at its path, so nothing that linked to it broke. The procedure has one home.

## And the drift check

The same doc against the compose directory:

```text
$ python3 scripts/sot.py diff docs/dns-runbook.md config --kinds=path,host,ip,port,env,id
path     /opt/example/dns
host     pihole.example.com
ip       10.0.0.1
port     8080
missing facts: 4 of 9 checked
```

Port `8080` is the useful line. The runbook says the admin UI is on 8080; the compose file maps
`8081:80`. The doc was stale, and an agent following it would have been wrong.


# Consolidation walkthrough

A real run, kept for the numbers rather than the story: a single-node homelab repo, 27 runbooks,
334 skills, and a doctrine that said procedural docs belong in skills.

## What the measurement said

- Best text overlap between any runbook and its obvious skill: **9.9%**.
- Genuine duplicates, not copies: both sides hand-maintained, both drifting, neither derived from
  the other. A similarity search would have called them unrelated.
- A fact-diff of all 14 candidate pairs: **every one** carried between 4 and 20 facts the skill
  lacked — health-command lines, compose paths, container addresses, systemd unit names.

Conclusion that changed the plan: stubbing on similarity would have deleted working procedure.
Every pair needed migration first.

## What the migration looked like

Two shapes, chosen by what the doc held:

1. **Move verbatim into `references/`** — for anything with a template, a YAML pattern, or a research
   trail. The original text arrives unchanged; the skill gains an index line pointing at it.
2. **Fold into the skill body** — for a short state block: the numbers, the classifier command, the
   one rule that was missing. About 15 lines, no prose loss.

Either way the doc became a ten-line pointer: canonical skill, reference path, what it holds, and
the sentence "do not add procedure to this file".

## Result

- 14 docs converted, in four commits.
- `docs/runbooks/`: 3,771 → 2,230 lines. File count unchanged at 27, so every inbound link resolved.
- Skills gained 1,545 lines across `references/` and a dozen index lines.
- The repo's drift-check finding count never moved: 86 before, 86 after, through every step.

## What went wrong, worth repeating

- **A summary would have been a deletion.** The first plan was to condense each doc into a paragraph.
  The fact-diff showed that removing a paragraph removes the commands in it.
- **`git add` on a tracked skill directory stages the whole directory**, including another session's
  uncommitted `SKILL.md`. One 5-line patch committed as `SKILL.md | 74 ++++`. Stage
  `<skill>/SKILL.md` and `<skill>/references/<file>` by name.
- **A doc that exists only as a pointer still needs its path.** Deleting it breaks every link that
  named it, and the readers who follow those links learn not to trust the next one.
