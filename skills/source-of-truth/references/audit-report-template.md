# Audit plan template (step 6)

Present this and wait for a yes. Nothing moves before then. Never include a secret's value.

```markdown
# Docs audit plan: <repo>  (<date>)

Surveyed N docs. M to migrate, K with possible secrets, D drift findings, 0 deletions.

## Plan
| # | Doc | Class | Proper home | Action | Blocker |
|---|-----|-------|-------------|--------|---------|
| 1 | docs/dns-runbook.md | Procedural | skill `network-ops` | migrate verbatim, stub | secret on line 24 |

## Secrets (file:line and kind only)
| Doc:line | Kind | Rotate? |
|---|---|---|

## Drift (doc vs config)
| Doc | Fact the doc states | What config says | Resolution |
|---|---|---|---|

## Break-glass
Which recovery docs stay readable off-host, and where the copy lives.

## Left alone
Records and anything not touched, with one line on why.

## Open questions
```

Close with: "Reply `go` to execute items 1 to N, or tell me which to drop."
