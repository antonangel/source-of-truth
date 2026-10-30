---
name: source-of-truth
description: "Use when docs need auditing, consolidating, or cleanup: two docs disagree, a doc restates config or code, a runbook is duplicated by a skill, or an authority doc omits a live subsystem."
version: 1.0.0
license: MIT
---

# Source of Truth

A doc is a **cache**, not a source. It earns its load when the lookup is expensive: a decision's
rationale, a domain word, a pointer to the right file. Everything derivable must be **derived**,
and everything procedural belongs in a **skill**, which is executable and fails at runtime.

The failure mode is not volume, it is **two copies that can disagree**. When they do, the agent picks
one arbitrarily and quietly builds on the wrong one.

## When to Use

- A doc and a skill describe the same procedure, or a doc restates config that already exists.
- Two docs disagree, and you need to decide which one is real.
- A doc pile is being audited, archived, or "cleaned up".
- An authority doc omits a live subsystem, so readers conclude it is absent.
- A repo has an ADR pile, a glossary, and a `docs/` tree that nobody has reconciled.

## Classify the fact, then place it

Every doc states one of five kinds of fact. The class decides its home.

- **Derived** — restates code, config, or live state. Generate it or delete it. If no generator can
  produce it, it was never derived: it is a decision wearing a table.
- **Decided** — why this and not the alternative, and what it costs. One ADR. Never restated in a
  second doc; link to it instead.
- **Vocabulary** — what a word means here. One glossary. Two definitions of one term is the same bug
  as two sources of truth, in miniature.
- **Procedural** — how to do a thing. A **skill**, not prose. A skill loads on demand, is versioned
  with the code, and a wrong step fails visibly. Prose drifts silently.
- **Navigational** — where to look. `AGENTS.md`, a README, a router. Every path must resolve.

Records (plans, audits, changelogs, research) are a sixth case: they are **append-only history**.
Leave them as written, including claims that later became false — annotate at the top, never rewrite.

## The tests

- **Deletion test.** Delete the doc. If the answer is recoverable by reading code or running a
  command, it was derived. If the reason vanished with it, it was a decision.
- **Drift test.** Could two copies disagree within a month? Then one must die, now.
- **Fact-diff test.** Before replacing a doc with a pointer, extract its paths, ports, ids, and
  command lines and check each against the target. Missing facts mean the doc is not redundant — it
  is unmigrated.
- **Silence test.** A subsystem the authority doc never mentions reads as **absent**. Silence is a
  claim, and the expensive kind: nobody goes looking for what they believe is not there.

## Procedure: consolidate a doc into its skill

Run this when a doc and a skill describe the same procedure — the most common duplication in an
agent-run repo, because both are hand-maintained and only one is loaded.

1. **Survey, don't sample.** Count docs, their inbound references, and their length. A doc with zero
   inbound links is not automatically dead; it may be a record.
2. **Pair by topic, never by text similarity.** Measured overlap between genuinely duplicate doc/skill
   pairs tops out around 10% — they are paraphrases, not copies. Similarity scores will tell you the
   wrong thing.
3. **Fact-diff the pair.** `scripts/fact-diff.py <doc> <skill>` lists the tokens and commands the
   skill does not contain. Zero missing is the only safe-to-stub signal.
4. **Migrate verbatim.** Move the doc into the skill's `references/` unchanged. Do not condense: a
   summary silently deletes the working command, the exact path, the parameter that mattered.
5. **Stub the doc.** Ten lines: canonical skill, reference path, one line on what it holds, and "do
   not add procedure here". Keeping the path alive preserves every inbound link; deleting the file
   breaks them and teaches readers to distrust links.
6. **Verify, then log.** Rerun the doc lint: the finding count must not move. Confirm the path still
   exists. Commit the doc and the skill in the same turn — they are one change.

## Procedure: mechanize the rule

A doctrine that depends on taste decays. Give it one check that fails.

- Flag a doc whose class is undeclared, when its directory does not imply one.
- Flag a `class: derived` doc that no generator produces and that is not marked generated.
- Flag a pointer whose target path does not exist.
- Run it **after** a change, not as a pre-commit gate on a shared tree: a pre-push check over a
  working tree blocks an unrelated clean change behind someone else's dirt.
- Be honest about severity. A class-coverage gap is `info`; a broken pointer is real.

## Anti-patterns

- **Deleting on similarity.** Semantically duplicate docs share few tokens. Text matching finds
  copies and misses duplicates — the opposite of what you need.
- **Condensing during a move.** The compression is where the procedure dies. Move text, then prune
  with evidence.
- **Stubbing without a fact-diff.** A pointer to a skill that lacks the command is worse than the
  duplicate: it looks authoritative and cannot be followed.
- **Two histories.** A raw log and a curated summary are fine only when the doc **declares** which is
  which. Undeclared, they drift and each claims to be current.
- **Restating the environment.** A doc that copies `package.json`, a compose file, or `--help` output
  is a cache with no invalidation.
- **A doc that names a command without the command that verifies it.** Either add the verifier or
  demote the doc to a decision record.

## Before you delete anything

Run the deletion test on every candidate and expect it to fail. In practice almost no doc passes:
repos are not full of junk, they are full of procedures that were never migrated. The honest outcome
of a docs audit is usually **zero deletions and a pile of migrations**.

## Going deeper

- `scripts/fact-diff.py` — the migrate-before-stub check, run against any doc/skill pair.
- `references/consolidation-walkthrough.md` — a worked case with real numbers: 14 pairs, what the
  fact-diff caught, and the files where moving was the only safe option.
