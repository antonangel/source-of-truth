# ADR 0001: Precision over recall in `diff`, and the CLI contract

Status: accepted, v1.4.0 (2026-10-31)

## Context

`sot.py diff` compares the facts a document states against a target. Every fact it reports is a
claim that something is missing, and a wrong claim costs more than a missing one: an operator who
sees 45 lines of which most are noise stops reading the output, and stops running the tool.

Measured on a real 30 KB infrastructure reference (`docs/SYSTEM.md` in a homelab repo) before this
change: `missing facts: 45 of 78`. The port set included `2001`, `569`, `1400`, `00` and `02`, all
fragments of the IPv6 prefix `2001:569:7e51:1400::/56`; `404` from a proxy rule written
`http_status:404`; and two-digit fragments of dates. Four `id` facts were real container IDs, absent
from the config directory being compared — true, and useless there.

In parallel, `inventory` did not finish at all: it exceeded a 180-second timeout on an 889-document
repository because it read application data as documentation and rescanned every file body once per
document.

## Decision

1. **Precision beats recall.** When a number cannot be told apart from a status code, a clock, a
   date fragment or an IPv6 octet, it is suppressed rather than guessed at.
2. **Suppression is visible, never silent.** The count goes to stderr, and `--all` reveals the
   suppressed candidates so the classifier can be audited.
3. **Facts carry provenance.** Each reported line ends with `doc:line`, captured during extraction,
   so a finding can be judged without re-reading the file.
4. **Two named profiles replace a remembered kind list.** `--profile=skill` checks all seven kinds;
   `--profile=config` checks path, host, ip, port and env, because a config directory cannot hold a
   command line or a container id and reporting them as missing is drift that does not exist.
5. **Exit codes are a contract**: `0` clean, `1` missing facts, `2` usage error, `3` the document
   holds something that looks like a secret.
6. **One entry point.** The deprecated `fact-diff.py` and `doc-inventory.py` shims are removed;
   the repository is early and a compatibility tail costs more than it returns.

## Consequences

- A prose address such as `backend:80` is now missed. `port 80`, `host:80`, `localhost:80` and a URL
  authority are still caught, and `--all` shows the suppressed candidate.
- A clean exit can coexist with suppressed candidates. The count is printed for that reason; CI
  should treat a nonzero count as a prompt to look, not as a failure.
- Container ids are reported only in the skill profile, so they cannot masquerade as drift.
- IPv6 and MAC addresses remain unextracted. This ADR does not add them; it only stops them
  manufacturing ports.

## Rejected alternatives

- **Confidence labels per fact** (high/medium/low). Three states are read as noise, and the low tier
  would still be printed.
- **Suppressing facts whose only occurrence sits in a masked region.** Applied literally this hides
  every real IPv4 and IPv6 fact, including the one the user came to find. Masking therefore applies
  to the port scanner only, and never to the extractor that owns the value.
- **Keeping the shims for another release.** Nothing in the wild depends on them; two documented
  commands are easier to follow than four.
- **`--json` in the same release.** A second output format is a second contract, and the current
  audience reads the table.
