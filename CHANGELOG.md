# Changelog

## 1.3.0

Shrunk the repo into a minimal, public, agent-readable skill.

- Merged six references into two: `references/examples.md` and
  `references/sources-and-secrets.md`.
- Merged `doc-inventory.py` + `fact-diff.py` into `scripts/sot.py` with `inventory` and `diff`
  subcommands; the old script names remain as thin (deprecated) shims for one release.
- Renamed the fixture to `tests/fixtures/example-stack/` with sanitized values (no env leakage).
- README rewritten as a 60-second quickstart; SKILL.md stays under 250 lines.
- 48 tests still green; CI unchanged.

Migration: replace `python3 scripts/fact-diff.py` with `python3 scripts/sot.py diff` and
`python3 scripts/doc-inventory.py` with `python3 scripts/sot.py inventory`. The shims keep
working for one release.

## 1.2.0

Rewritten for homelabs and the agents that read their docs.

- SKILL.md: ground rules (dry-run first, never delete, secrets before moves, break-glass),
  layer map, audit workflow ending in an approved plan, drift check against config.
- New references: homelab sources of truth, secrets, break-glass, audit plan template, and a
  before/after example whose output the test suite verifies.
- `fact-diff.py`: fixed a false pass when a skill's name appeared inside a fact; IPs now found in
  URLs, in CIDR form and before a sentence-final period; port mappings such as `80:80` no longer
  read as clock times; trailing comments and continued commands handled; `--kinds` filter;
  secret warnings by line, never with the value.
- New `doc-inventory.py`; tests for every fact kind, a homelab golden fixture, and CI.
- README derived from the skill, with a test that it does not drift from it.

## 1.1.0

Per-kind tests, IP extraction, port context, inline-command heuristic.

## 1.0.0

Initial release.
