# Issue tracker

## Tracker roles

- Forgejo Issues is the canonical tracker for maintainer-created specs, Wayfinder maps, and implementation tickets in `angel/source-of-truth`.
- GitHub Issues on the public mirror is the public intake surface for user reports and community requests.
- When a public report is accepted as work, link its GitHub issue from the corresponding Forgejo ticket. Do not duplicate internal planning tickets on GitHub.

## Forgejo access

Resolve the Forgejo API base URL and credentials from the maintainer's local Forgejo configuration or integration. Do not commit private hostnames, IP addresses, tokens, or passwords. If the configured API or credentials are unavailable, stop and ask rather than guessing.

The API is Gitea-compatible. Use the repository's live owner and name. Resolve label IDs by label name on each run. For dependency creation, include `index`, `owner`, and `repo` in the request body. Read issues, labels, and dependencies back before reporting writes as successful.

## Wayfinding operations

- Use `wayfinder:map` for the map and `wayfinder:research`, `wayfinder:prototype`, `wayfinder:grilling`, or `wayfinder:task` for child issues.
- Forgejo has no native parent/child issue relation; mark each child with `Map: #<number> — <map title>` and `<!-- wayfinder:map #<number> -->`.
- Use Forgejo's native issue dependencies for blocking edges. Create all issues before wiring dependencies, then read the graph back.
- Claim a ticket with a comment before work. Resolve it with an answer comment, close it, and update the map's Decisions so far.
- Ask before publishing a proposed map or ticket set.
