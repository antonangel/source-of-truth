# Spec — Minimalize `source-of-truth` into a public, agent-readable skill

Status: ready-for-agent | Date: 2026-10-30 | Source prompt: `docs/prompts/source-of-truth-minimal-redesign.md`

## Problem Statement

`source-of-truth` v1.2.0 ships 18 tracked files (SKILL.md, 6 references, 2 scripts, tests,
fixtures, README, CHANGELOG, LICENSE, CI). That surface is larger than the documentation it
helps shrink: an agent loading the skill pays context cost for 6 references it mostly does not
need, and a self-hoster adopting it must understand the `references/` convention before getting
value. The tooling is also split across two scripts (`doc-inventory.py`, `fact-diff.py`) that
overlap in purpose. The goal is a repo a self-hoster can read in one file and run with one
command, with no leakage of the author's environment.

## Solution

Shrink the repo to: `SKILL.md` (doctrine + usage, <= 250 lines), `README.md` (install +
60-second quickstart), `LICENSE`, one script `scripts/sot.py` with `inventory` and `diff`
subcommands, two on-demand reference files, a merged test suite, and a minimal CI job. Keep
backwards compatibility for one release via thin shims named `fact-diff.py` and
`doc-inventory.py` that import `sot.py` as a module. Sanitize the worked example to generic
values while preserving its realistic structure.

## User Stories

1. As a self-hoster using a coding agent, I want to read one SKILL.md and understand the whole
   doctrine, so that I do not have to load six reference files.
2. As a self-hoster, I want one command (`sot.py`) with subcommands, so that I do not have to
   remember two script names.
3. As an existing user, I want my old `fact-diff.py` / `doc-inventory.py` invocations to keep
   working for one release, so that my scripts and cron jobs do not break.
4. As an adopter, I want the worked example to use generic values, so that no author environment
   leaks into my repo.
5. As an adopter, I want a 60-second quickstart in README, so that I can verify the tool works
   before reading the doctrine.
6. As a maintainer, I want SKILL.md under 250 lines, so that the always-on context cost stays low.
7. As a maintainer, I want on-demand references for examples and source/secrets detail, so that
   deep material does not bloat the skill file.
8. As a reviewer, I want the before/after `doc-inventory` numbers in the PR body, so that the
   shrinkage is measurable.
9. As a tester, I want a stdlib-only test runner, so that no `pytest` install is required.
10. As a CI consumer, I want a green badge, so that I can trust the repo before adopting.
11. As a security-conscious user, I want `secret_lines()` empty on every tracked file, so that no
    credential is shipped.
12. As a migration author, I want a CHANGELOG entry with the rename and deprecation window, so
    that upgrades are documented.

## Implementation Decisions

- Merge `doc-inventory.py` and `fact-diff.py` into `scripts/sot.py` exposing `inventory <repo>`
  and `diff <doc> <target> [--kinds=...] [--quiet]`, preserving all flags and exit codes.
- Shims `scripts/fact-diff.py` and `scripts/doc-inventory.py` import `sot` as a module (via
  `importlib`/`runpy`) and delegate; they print a one-line deprecation notice to stderr.
- SKILL.md stays at ~126 lines; do not fold all references into it (rejected: ~364 lines).
- Trim `references/` to two files:
  - `references/examples.md` = `before-after-homelab.md` + `consolidation-walkthrough.md`.
  - `references/sources-and-secrets.md` = `homelab-sources.md` + `secrets.md` + `break-glass.md`
    + `audit-report-template.md`.
- Remove the six original reference files after merging their content into the two above.
- Rename `tests/fixtures/homelab/` → `tests/fixtures/example-stack/` and sanitize values:
  IPs → 10.0.0.x, hosts → example.com, paths → /opt/example, generic container names.
- Merge `tests/run_tests.py` into `tests/test_sot.py` (or keep `run_tests.py` as the entry
  point calling `test_sot`); keep stdlib-only.
- Keep a minimal CI job (timeboxed, single test command).
- Keep README.md with install + 60-second quickstart.
- Backwards-compat window: one release with shims, then remove shims in the following release.
- Public-safety: no private IPs/hosts/paths except the sanitized example; `secret_lines()` empty.

## Testing Decisions

- Test external behavior only: CLI exit codes, flag parsing, extraction correctness, present/absent
  matching, secret scanning, inventory counts. Do not test internal helper refactors.
- Prior art: existing `tests/run_tests.py` (48 checks) is the baseline; all must still pass after
  the rename/move.
- Add a smoke test that `sot.py --help`, `sot.py inventory <repo>`, and `sot.py diff ...` run
  end-to-end on the sanitized fixture.
- Add a regression test that the shim names delegate correctly.

## Out of Scope

- Changing extraction logic or fact kinds (IPv6, MAC, config keys) — separate issue.
- Multi-agent/multi-profile concerns.
- New fact kinds or new secret patterns.
- Removing the doctrine; only its packaging shrinks.

## Implementation notes (from code grill, 2026-10-30)

These were found by comparing the spec against the actual repo. They must be handled in the
tickets; do not treat them as surprises mid-implementation.

1. **Test-path migration is required.** `tests/run_tests.py` hardcodes
   `SCRIPT = …/fact-diff.py`, `inventory = SCRIPT.parent / "doc-inventory.py"`, and reads
   `references/before-after-homelab.md`. The golden test also asserts 3 command blocks in that
   file. These paths must move to `sot.py` and `references/examples.md` in the same PR.
2. **SKILL.md references old names.** It cites `scripts/doc-inventory.py`, `scripts/fact-diff.py`,
   and `references/before-after-homelab.md`. Update to `scripts/sot.py` and
   `references/examples.md`.
3. **Golden example command string.** The before/after doc shows
   `$ python3 scripts/fact-diff.py …`. Decision: switch examples to `sot.py diff` and update
   the test regex to `scripts/(?:fact-diff\.py|sot\.py)` (or the new name only). Keep the
   output comparison unchanged.
4. **CI entry point.** `.github/workflows/test.yml` runs `python3 tests/run_tests.py`. Keep
   `run_tests.py` as the entry point (no CI change) and update its internal paths; do not rename
   the test file.
5. **Shim importability.** `sot.py` must be importable without side effects (guard `main`).
   Preserve module-level functions (`extract`, `present`, `skill_corpus`, `secret_lines`,
   `find_ports`, etc.) so shims can `import sot`. Move the `doc-inventory` importlib logic
   into `sot.py`.
6. **Pointer exemption.** Already matches the `skills/<name>` prefix, so
   `skills/source-of-truth/references/examples.md` stays exempt. Add a test case for it.
7. **README consistency test** (`readme_checks`) enforces: fact kinds match `fd.KINDS`, no
   restated SKILL.md lines, all relative links resolve, <= 70 lines. Any README rewrite must
   satisfy these.

## Further Notes

- Baseline `doc-inventory` numbers for the repo should be captured before the shrinkage and
  included in the PR body.
- The PR must include before/after fact counts and the migration note.
- This spec is the contract for `to-tickets`; do not start implementation without ticket approval.
