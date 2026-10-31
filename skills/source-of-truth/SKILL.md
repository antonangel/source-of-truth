---
name: source-of-truth
description: "Use when comparing a chosen doc to config or a skill."
version: 1.5.0
license: MIT
---

# Source of Truth: selected-document fact check

Help a self-hoster check one chosen infrastructure document against one chosen local config or skill source. The bundled CLI detects literal fact-presence discrepancies; it does not judge correctness, authority, semantics, or live state.

## When to use

- The operator wants to compare one named runbook or infrastructure document with one named config or skill.
- The operator asks for a documentation review or consolidation plan. Use the read-only comparison first when they identify a specific document and target; keep broader guidance optional and human-reviewed.

Do not turn whole-repository inventory into the default. `scripts/sot.py inventory <repo>` is a separate, explicit operation.

## Selected-source comparison

1. Confirm the document and comparison target. The operator chooses both. If both are missing, ask for both together before searching or running a check; if one is missing, ask for that input. A target may be a config directory, a skill directory, a `SKILL.md`, or another supported local text target.
2. If the operator asks for help choosing a target, make a narrow suggestion from the selected document's references or a focused search. Name the candidate path and why it appears relevant, then ask the operator to confirm it. Do not compare against a guessed source.
3. Treat the operator-confirmed target as the source for this comparison only; target selection does not prove authority for every fact. If it matters and the operator has not made that explicit, ask. Configuration can express desired state; runtime or an application UI/API can express observed state; documents may own decisions, navigation, history, and knowledge no other source can express. The CLI does not infer authority. If the requested source is unavailable to local text inspection, say so and do not substitute another source silently.
4. Choose `--profile=config` for a config target or `--profile=skill` for a skill target. Run the bundled script from the selected installation:

   ```bash
   python3 .claude/skills/source-of-truth/scripts/sot.py diff <document-path> <confirmed-target-path> --profile=config
   ```

   In the selected Claude Code project-install target, the intended script location is `.claude/skills/source-of-truth/scripts/sot.py`; discovery and invocation have not yet passed end-to-end testing. For another installation, resolve the script under this skill's actual installed directory; never assume `scripts/sot.py` is at the user's repository root. Do not pass shell angle-bracket placeholders literally; substitute the two confirmed paths.
5. Report the target path, profile, every literal finding exactly as printed with its `document:line`, and the missing-fact count. Recommend that the operator review each finding. Do not infer what to edit.
6. State that the command only checks selected literal facts. It does not prove semantic correctness, completeness, configuration behavior, or current runtime/UI state. Note any requested observed source the checker could not inspect.
7. Confirm that neither selected input changed. The CLI is read-only; do not edit files as part of this check.

If either path is invalid or the command exits `2`, report the exact path/usage error and ask for a valid input. If the output says an append-only record was skipped, do not call that a clean check; ask whether the operator explicitly wants that record checked with `--force` before retrying.

## Interpret results safely

- Exit `0`: no missing selected literal facts detected. This is not proof the document is correct or complete. If the CLI says a record was skipped, the comparison did not run.
- Exit `1`: the CLI found missing literal facts. Quote the finding kind, value, and exact `document:line`; name the confirmed target in your report. Recommend review, not automatic correction.
- Exit `2`: invalid usage, missing path, or unsupported input. Do not broaden the search automatically.
- Exit `3`: the document contains possible secret-shaped material. Report only the warning kind and `file:line`; never repeat or copy a value. A secret warning can accompany other findings, so inspect stderr regardless of exit code.
- A low-confidence suppression note means some candidates were deliberately omitted. State that limitation when it affects the requested comparison; `--all` is a diagnostic view, not a claim that suppressed items are facts.

## Ownership and preservation

“One authoritative owner per fact” does not mean one physical copy. A document may own decisions, vocabulary, navigation, historical records, human-first instructions, and operational knowledge that config cannot express. A deliberate copy must state its purpose, canonical owner, and refresh rule. Configuration describes desired state; runtime/app UI/API describes observed state; docs own knowledge those systems cannot express.

Keep break-glass recovery instructions independently readable without an agent or the system being recovered. Do not treat a literal-check result as permission to stub or delete a document. Preserve unique meaning and links before any migration. A stub may retain a useful old path. Deletion requires explicit approval and preservation/link checks.

## Optional human-reviewed change plan

Only prepare this when the operator requests broader cleanup or change guidance. Keep the selected-source check read-only. Before editing anything, present a named plan containing:

- the exact document(s) and proposed action;
- each fact's current owner and proposed authoritative owner;
- whether a repeated copy is deliberate, its purpose, canonical owner, and refresh rule;
- unique decisions, vocabulary, navigation, history, break-glass, and human-first content that must remain;
- links and references to preserve or update;
- secret findings by kind and line only, never by value;
- verification and rollback steps.

Wait for explicit approval of that named plan before applying edits or deleting anything. Show the diff and verification afterward. Never auto-commit, schedule the work, create issues, or retain a report as part of the focused check.

## First-run proof and compatibility

The human quickstart is in `README.md`; the minimal one-mismatch fixture is under `tests/fixtures/first-check/`. The selected first end-to-end test target is Claude Code `2.1.49` using the project-level location `.claude/skills/source-of-truth/`; this combination is still unverified and is not a support claim. Do not claim support for this or other client/version/install combinations until the exact discovery and invocation flow passes.

## References

- `scripts/sot.py`: deterministic, read-only comparison engine and separate Markdown inventory command.
- `references/examples.md`: generated first-run output from the synthetic one-mismatch fixture.
- `references/sources-and-secrets.md`: optional source ownership and secret-handling guidance for an explicitly requested, human-reviewed plan.
