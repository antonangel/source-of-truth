# Changelog

## 1.6.0

Three verbs and a contract that stays installed (ADR 0002).

- **`init`** installs the document contract: `docs/doc-classes.md`, `docs/templates/{adr,runbook}.md`
  and `.sotignore`, written only when absent. It prints the `AGENTS.md` block and a CI snippet and
  writes neither. `--print` writes nothing, `--force` overwrites only files it owns, and an existing
  `AGENTS.md` is never touched. The script resolves its own path at run time — relative to the git
  root when it lives inside the repository, absolute when it does not — so no printed command carries
  a hardcoded install path.
- **`init --hook`** installs a pre-commit check over staged Markdown only. A dirty sibling file is
  never in the index, so the failure that banned doc linting from pre-push cannot recur. An unmanaged
  hook is refused by name; a managed one is skipped; a moved script skips the check rather than
  blocking every commit.
- **`check`** enforces five of seven classes — `derived` provably generated, one `authority`, one
  `vocabulary`, `navigational` links and `canonical:` targets resolving — and reports the rest at info
  tier. Tiers, not a softened exit: `0` means clean at the threshold, `--strict` lowers the threshold,
  and info-tier findings always print.
- **`audit`** emits one row per document — class, facts, inbound references, a candidate target, the
  exact `diff` command — ranked and never judged. It exits `0` whenever it produced a plan. Records
  and stubs are skipped and listed last.
- Classes own facts; directories own storage. `vendor` and `template` are directory attributes with
  no rule. Class comes from frontmatter, then an optional `.sotclasses` map; there is no name map.
- `diff` and `inventory` are unchanged, including their output and exit codes.
- The honest claim is **five enforced classes, not seven**: no machine can tell a good runbook from a
  bad one, so `procedural` is declarable and unjudged, and `decided` is advisory.
- Measured on a real 890-document homelab: `audit` completes in 9.1 s, pairs 380 documents and skips
  204 records. The first eleven of twelve ranked rows were vendored third-party skills until
  `external/` was listed in `.sotignore` — the vendor exclusion is load-bearing, and `init` ships it.

## 1.5.0

- Narrow the first-run promise to a read-only comparison of one operator-selected document against one confirmed config or skill target. Findings are literal, with exact document lines; the CLI does not claim semantic or live-state validation.
- Add a minimal one-mismatch fixture and matched control; verify the README command's exact output, exit code, and unchanged inputs. Regenerate the example from the real CLI.
- Rewrite the README and agent workflow around the selected-source check, operator authority, safe secret handling, and approval-gated broader guidance. Remove unsupported prevalence claims and update the obsolete `fact-diff.py` reference.
- Claude Code 2.1.49 with project-level `.claude/skills/source-of-truth/` remains the first end-to-end test target, not a support claim; that client/version/path combination is still unverified.

## 1.4.0

First-run credibility: the tool now finishes on a real repository, and stops reporting facts that
are not facts.

- `inventory` censuses markdown only and prunes data and build directories at the walk, so it no
  longer reads `docker/data` volumes. On a real 889-document homelab it completes in about 7
  seconds, where 1.3.0 exceeded a 180-second timeout.
- Inbound references are computed in one linear pass over the census, instead of scanning every
  file body once per document.
- New `.sotignore` at the repo root: one glob per line, `#` comments, matching a path, a basename or
  a path segment.
- New `--top=N` limits the inventory table.
- Port extraction no longer invents facts: IPv6 literals, clock values and `http_status`-style
  key/value pairs are excluded, and a bare `host:N` is accepted only when the left side is an
  address, `localhost`, a URL authority, or a name with a port number of 1024 or more. On a real
  system reference this removed `2001`, `569`, `1400`, `00`, `02` (an IPv6 prefix), `404` (a proxy
  rule) and two-digit date fragments.
- Suppressed candidates are counted on stderr, so a clean run cannot hide a finding; `--all`
  reveals them.
- A URL fragment or a backticked endpoint such as `/reconcile` is no longer read as a filesystem
  path.
- Every reported fact carries the `doc:line` it came from, captured during extraction.
- A pointer to the target skill is exempt however it is written: `skills/<name>`, or an absolute or
  `~` path that resolves to it.
- New profiles: `--profile=skill` (all kinds) and `--profile=config` (path, host, ip, port, env).
  `--kinds` still overrides either.
- Exit codes are unchanged and now documented as a contract: 0 clean, 1 missing facts, 2 usage,
  3 possible secret.
- Tests: a real-world noise fixture asserting the exact fact set in both directions, a masking-safety
  test, profile and pointer coverage, a 600-document inventory speed budget, and a version-agreement
  check between this file and the skill.
- `tests/regenerate_examples.py` generates `references/examples.md` from real output, so the
  examples cannot drift from what the script prints.

**Breaking:** the deprecated `scripts/fact-diff.py` and `scripts/doc-inventory.py` shims are
removed. Use `sot.py diff` and `sot.py inventory`.

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
