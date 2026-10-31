---
name: source-of-truth
description: "Use when homelab docs need auditing or cleanup: a stale runbook, AGENTS.md or CLAUDE.md that disagrees with compose or config, a doc duplicated by a skill, runbooks holding secrets, or consolidating docs into skills. Gives each fact one home and gates stubbing with a fact-diff."
version: 1.4.0
license: MIT
---

# Source of Truth

A homelab collects docs faster than it collects truth. The agent reads `AGENTS.md`, a memory file,
a skill and a runbook that each state the same port. When they disagree it picks one, quietly, and
builds on it. The fix is not fewer docs. It is **one home per fact**.

A doc is a **cache**, not a source. Derive what can be derived, make procedures skills, and keep
everything else short and singular.

## When to use

- A runbook looks stale, or `AGENTS.md` / `CLAUDE.md` disagrees with the compose file or config.
- A doc and a skill describe the same procedure.
- Two docs state the same port, IP, path or command, so they can disagree.
- Runbooks contain tokens, keys or passwords.
- A running service appears in no doc, so readers conclude it does not exist.

## Ground rules

1. **Dry-run first.** Produce the plan (`references/sources-and-secrets.md`) and wait for a yes
   before moving or stubbing anything.
2. **Never delete a doc.** A stub keeps its path, so every inbound link survives.
3. **Secrets before moves.** Scrub a doc's secrets before copying it anywhere. Never print a
   secret's value; the script reports file and line only.
4. **Break-glass stays readable off-host.** See `references/sources-and-secrets.md`.
5. **Stage files by name** (never a whole directory) and commit the doc and the skill together.

## Classify the fact, then place it

- **Derived**: restates config or live state (port tables, service inventories, IP lists). Generate
  it or delete it. If nothing can generate it, it was a decision wearing a table.
- **Decided**: why this and not the alternative. One ADR, linked, never restated.
- **Vocabulary**: what a word means here. One glossary.
- **Procedural**: how to do a thing. A **skill**, which loads on demand and fails visibly. Prose
  drifts silently.
- **Navigational**: where to look. `AGENTS.md`, a README. Every path must resolve.

Records (plans, audits, changelogs, incident notes) are **append-only history**. Leave them as
written, including claims that later became false. Annotate the top; never rewrite.

## Where each fact lives

| Layer | Holds | Must not hold |
|---|---|---|
| Config (compose, Nix, Ansible, proxy, DNS) | Ports, IPs, paths, versions: the truth | Rationale prose |
| `AGENTS.md` / `CLAUDE.md` | Where things live, hard rules, pointers to skills | Ports, IPs, command sequences |
| Skills | Procedures, verifiers, `references/` | Decisions, vocabulary |
| `docs/` | ADRs, glossary, append-only records | Procedures, restated config |
| Agent memory | The user's preferences and standing instructions | Infra state that config can answer |
| Stack README | One line of purpose and a pointer | Anything the compose file says |

How to derive instead of hand-write: `references/sources-and-secrets.md`.

## The four tests

- **Deletion**: delete the doc. Recoverable by reading config or running a command means it was
  derived. If the reason vanished, it was a decision.
- **Drift**: could two copies disagree within a month? Then one must go, now.
- **Fact-diff**: before replacing a doc with a pointer, check that every path, host, IP, port, env
  var, id and command it holds exists in the target. Missing facts mean the doc is unmigrated.
- **Silence**: a subsystem the authority doc never mentions reads as absent. Silence is a claim.

## Audit workflow

1. **Inventory.** `python3 scripts/sot.py inventory <repo>` lists each doc with size, age, inbound
   references, fact counts and possible secrets. It reads markdown only, prunes data and build
   directories at the walk, and honours `.sotignore`. Survey everything; do not sample.
2. **Classify** every doc: class, proper home, action. Leave records alone.
3. **Secrets pass.** Any secret warning blocks that doc until it is scrubbed. Rotate anything that
   was ever committed or synced.
4. **Pair and fact-diff.** Pair docs with skills by topic, then run the fact-diff. Overlap scores
   are a hint for finding candidates, never a verdict.
5. **Drift check** against config (below).
6. **Present the plan and wait for a yes.**
7. **Migrate verbatim** (minus secrets) into the skill's `references/`, stub the doc, verify.

Stub the doc in ten lines: canonical skill, reference path, one line on what it holds, "do not add
procedure here". Verify the target exists, then `git grep` the old path and walk every hit. Never
condense while moving: the summary deletes the command that mattered.

## Fact-diff, two uses

Two profiles mean you do not have to remember which kinds belong to which mode.

```bash
# Is the doc redundant with the skill? Exit 0 = nothing missing: necessary, not sufficient.
python3 scripts/sot.py diff docs/dns-runbook.md skills/network-ops --profile=skill

# Has the doc drifted from the config? A config dir holds no commands and no commit ids.
python3 scripts/sot.py diff docs/dns-runbook.md /srv/stack --profile=config
```

`--profile=skill` checks all seven kinds. `--profile=config` checks path, host, ip, port and env
only, because a config directory cannot hold a command line or a container id, and reporting those
as missing is drift that does not exist. `--kinds=a,b` overrides either profile.

Exit codes: `0` clean, `1` missing facts, `2` usage error, `3` the doc holds something that looks
like a secret. Exit 1 lists the missing facts one per line, each with the `doc:line` it came from.

**Precision beats recall.** A number that cannot be told apart from a status code, a clock or an
IPv6 octet is suppressed, and the count of suppressed candidates is printed so a clean exit is
never silent. Read that count; `--all` shows what was held back when you want to audit the
classifier. In drift mode a missing fact is stale, or lives outside that directory: decide, do not
auto-fix.

## Scope

Built for homelabs and small infra repos where an agent loads skills on demand. It fits less well
when documentation is the product, when a procedure must stay readable without any agent, or when
nobody reads the skill library: there duplication costs less than losing the narrative. The
doctrine is about where a fact lives, not about deleting prose.

## Anti-patterns

- **Deleting on similarity.** In the one repo where this was measured (n=1), true duplicate pairs
  shared under 10% of their tokens. Treat the score as a hint.
- **Condensing during a move.** The compression is where the procedure dies.
- **Stubbing without a fact-diff.** A pointer to a skill that lacks the command is worse than the
  duplicate: it looks authoritative and cannot be followed.
- **Two histories.** A raw log and a curated summary are fine only if the doc declares which is which.
- **Restating the environment.** A doc that copies a compose file or `--help` output has no invalidation.
- **A command without its verifier.** Add the check, or demote the doc to a decision record.
- **Migrating a secret.** Verbatim does not apply to credentials.

## References

- `references/sources-and-secrets.md`: where each kind of homelab fact is generated from, the
  scrub-first procedure and what the scanner catches, recovery docs that must outlive the agent
  host, and the plan format for step 6.
- `references/examples.md`: one invented consolidation with real script output, and a real
  14-pair run with numbers.
