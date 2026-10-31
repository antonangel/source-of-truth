# First check: one literal mismatch

Run this exact command from the repository root against the synthetic fixture. The source document contains one IP that the selected config target does not contain.

```text
$ python3 skills/source-of-truth/scripts/sot.py diff tests/fixtures/first-check/docs/dns-runbook.md tests/fixtures/first-check/config --profile=config
ip       203.0.113.10  tests/fixtures/first-check/docs/dns-runbook.md:3
missing facts: 1 of 1 checked
```

Expected exit code: `1`, meaning one missing literal fact. The finding identifies the fact kind and its exact document line. This comparison does not validate meaning, semantic correctness, completeness, or live runtime state. It does not edit either input.
