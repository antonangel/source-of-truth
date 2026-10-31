# ADR 0002: Three verbs, and a contract that stays installed

Status: accepted, v1.6.0 (2026-10-31)

## Context

v1.4 through v1.5 compare one document against one target and refuse to claim more. That is the
right unit of work, and it answers nothing for the operator who arrives with a repository: which
document, against what, and what keeps the next document honest.

The measured case is a real homelab: 180 markdown files under `docs/`, 89 with one or no inbound
reference, and **zero** that passed a strict delete test. The cost there was never volume; it was
duplicated authority — two documents stating the same fact, each able to disagree. Deleting files
fixed nothing. Classifying them did.

A census of that same repository by this tool's `inventory` counts 889 markdown files in 7.4 seconds,
**544 of them vendored third-party documentation under `external/`** — 61% of the corpus is somebody
else's docs. That is the measurement behind decision 8: `vendor` earns its place as a directory
attribute precisely because excluding it turns an 889-row audit into a 386-row one, and because no
rule can sensibly be applied to text the operator did not write.

So the answer to "what now" is not a larger inference engine. It is a contract that stays installed,
plus an invoked sweep that produces work for a human instead of a verdict.

## Decision

1. **Three subcommands, one entry point.** `init`, `check` and `audit` join `diff` and `inventory`.
   `sot.py` remains the only path anyone invokes (ADR 0001 §6); the engine moves to `sotlib.py` as
   an implementation detail, not a second command.

2. **`init` installs the contract and never rewrites what exists.** It writes, only when absent:
   `docs/doc-classes.md`, `docs/templates/adr.md`, `docs/templates/runbook.md`, `.sotignore`.
   It prints, and does not write, the `AGENTS.md` block and a CI snippet. It never edits an existing
   `AGENTS.md`. `--print` shows the whole set and writes nothing. `--force` overwrites files it owns.

3. **The trigger is installed, and scoped to the index.** `init --hook` installs a pre-commit hook
   running `check --staged --strict`. A dirty sibling file is never in the index, so the failure that
   banned doc linting from pre-push — `validate-repo.py` against a dirty working tree — cannot recur.
   `--strict` because a commit is the moment the document is being touched, which is exactly when an
   undeclared class stops being advisory (§4). The CI snippet is printed rather than written because
   `.git/hooks` is not versioned and a team needs the versioned form.

4. **`check` enforces five of seven classes, and tiers its findings instead of softening its exit.**
   Exit `0` keeps meaning clean *at the threshold*; `--strict` lowers the threshold so info-tier
   findings become failures. Info-tier findings print to stderr on every run, so a clean exit cannot
   hide one (ADR 0001 §2).

5. **`audit` produces a worklist and cannot pass.** It exits `0` whenever it produced a plan; `2` is
   usage. A non-zero exit would invite CI to run it, and an audit that can fail is a verdict — the
   claim v1.4 spent a release learning to refuse. Output is stdout by default, `--out <path>` to keep
   it; `init` does not create `docs/audits/` and `audit` does not assume it.

6. **Ranking is a two-key sort.** Inbound references descending, then fact count descending,
   bucketed by class. The same argument ADR 0001 used against per-fact confidence labels: an ordering
   nobody can reproduce by hand is an ordering nobody trusts. Ranking decides what is read first, not
   what is judged — every row already carries the exact `diff` command for that pair.

7. **A stub is a pointer, and the pointer is checked.** A stubbed document declares
   `class: navigational` and `canonical: <path>`. `check` fails when the target does not resolve;
   `audit` skips it. This is the only rule that catches a stub whose skill was later renamed, which
   is the common rot after a consolidation.

8. **Classes own facts; directories own storage.** Seven classes are declarable: derived, decided,
   authority, vocabulary, procedural, navigational, record. `vendor` and `template` are directory
   attributes a map may carry and no rule enforces. Two of the seven are declarable but unenforced —
   `procedural` has no mechanical rule, `decided` only an advisory one — and the documentation says
   so, in a table, rather than implying seven.

9. **No hardcoded install path.** `init` resolves the script at run time and writes the path relative
   to the git root when the script lives inside the target repository, absolute otherwise. v1.5
   documents `.claude/skills/source-of-truth/` as unverified; resolving removes that class of failure
   without a client-certification gate.

## Consequences

- The honest claim is **five enforced classes**, not seven. `procedural` documents are declarable and
  unjudged: no machine can tell a good runbook from a bad one.
- `check` sees only what it is pointed at. A secret committed long ago surfaces under `check --all`
  and not before, so `--all` is the adoption sweep and the hook is the standing guard.
- Nothing runs unless installed. A user who declines both `--hook` and the CI snippet has the
  contract and no trigger; that is their choice, and the README says so.
- The homelab keeps `compare_doc_classes()` through 1.6 and 1.7. New rules land here first and
  `drift-check.py` calls them, so divergence is one-directional. Replacing a 1,634-line checker with
  a two-cron-consumer severity model inside a minor public release inverts the dependency.
- The Atlas-installed copy of the skill is 507 lines against this repository's 794. That divergence
  already exists and must be synced at ship time, or the doctrine acquires its own duplicate.

## Rejected alternatives

- **Splitting the release: `init` + `check`, then `audit`.** Ships `init` writing a contract with
  nothing verifying it for a whole release — the anti-pattern of a command without its verifier.
- **`audit` exiting non-zero when candidates exist.** Turns a worklist into a verdict and invites CI
  to treat "this repository has docs worth reviewing" as a build failure.
- **A fifth exit code for advisory findings.** ADR 0001 deliberately kept four; a threshold knob on
  `--strict` achieves the same behaviour without widening the contract.
- **A weighted ranking score.** Unreproducible by hand, therefore untrusted.
- **Padding `procedural` and `decided` with weak heuristics.** Manufactures exactly the false
  confidence v1.4 removed.
- **Writing the CI workflow file.** GitHub, GitLab and Forgejo differ; a workflow is a bigger
  commitment than a template and it is the user's file to place.
- **A hook on pre-push.** Already banned in the reference deployment after it blocked every push on a
  dirty sibling.
- **A user-editable taxonomy config.** A config the code reads is a second authority that can name a
  class the code cannot enforce — one home per fact applies to the class list too.
- **Nine enforceable classes.** `vendor` and `template` own no durable fact; a class list where two
  entries mean nothing is worse than a shorter honest one.
