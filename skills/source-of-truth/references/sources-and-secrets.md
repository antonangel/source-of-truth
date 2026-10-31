# Homelab sources of truth

Infrastructure facts have different authorities. Configuration can describe desired state; a runtime or application UI/API can describe observed state; documents can own decisions, history, navigation and operational knowledge that other sources cannot express. Name one authoritative owner for each fact. A repeated copy may be deliberate, but state its purpose, canonical owner and refresh rule so it does not quietly become a competing authority.

| Fact | Where the truth lives | Print it with |
|---|---|---|
| Desired services, ports and image refs | Compose files | `docker compose config`, `docker compose config --images` |
| What is actually running | The Docker daemon | `docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Ports}}'` |
| Container networks and IPs | Docker | `docker network inspect <network>` |
| NixOS settings | The flake or `configuration.nix` | `nix eval .#nixosConfigurations.<host>.config.<option>` |
| Hosts and variables | Ansible inventory | `ansible-inventory --list` |
| Cloud or VM resources | Terraform / OpenTofu state | `terraform output`, `terraform state list` |
| VMs and containers on Proxmox | The hypervisor | `qm list`, `pct list` |
| Running units, timers | systemd | `systemctl list-units --type=service --state=running`, `systemctl list-timers` |
| Mounts and disks | The kernel | `findmnt`, `lsblk` |
| Local DNS records, proxy routes | The resolver's and proxy's own config files | link to the file |

## Rules of thumb

- A fact in prose is derived only when it restates desired or observed state owned by another source. Point to that owner, or label a deliberate copy with its purpose, canonical owner and refresh rule.
- A list of current services in `AGENTS.md` usually restates configuration. Keep navigation there, and identify the config owner instead of treating the list as authoritative.
- Rationale, decisions, historical records and operational knowledge may belong in documents when no other source expresses them. Preserve that unique knowledge.
- Keep a generator next to a table that is meant to be derived. When no generator exists, identify whether the table is a decision, observation or manually maintained record and name its owner; do not delete it just because it is not generated.


# Secrets in docs

Runbooks collect credentials: a Pi-hole password, an API token, a Wi-Fi key, a tailnet auth key.
"Migrate verbatim" is the right rule for procedure and the wrong one for credentials. Moving a
secret into a skill copies it into a directory that gets synced, backed up, shared with an agent
session, or pushed.

## Scrub first

1. Run the bundled `scripts/sot.py diff` on the selected doc and operator-confirmed target, using the config or skill profile as appropriate. It reports literal facts absent from the target with `doc:line`; it does not decide which source is authoritative or validate semantic/live-state correctness. Warnings go to stderr as `file:line` plus a kind. The value is never printed, and a flagged line is left out of the fact checks until it is clean.
2. Replace each value with a placeholder that names where the real one lives:
   `WEBPASSWORD=<from the password manager, entry "pihole">`.
3. **Treat the old value as exposed** if the doc was ever committed, synced or pasted into an agent
   session. Git history keeps it. Rotate it.
4. Only then migrate the doc.

## Where the value should live

An untracked `.env` outside the repo, `sops` or `age`, or a password manager. The doc names the
location, never the value.

## What the scanner catches

Private-key headers, common provider token prefixes, JWTs, credentials embedded in URLs, and
assignments such as `password=`, `token:`, `api_key=` or `psk=` with a non-placeholder value.

## What it does not

A bare random string with no keyword, a secret split across lines, secrets inside images, and
anything already in git history. It is a tripwire for docs, not a replacement for a history
scanner such as gitleaks or trufflehog in CI.


# Break-glass: recovery docs that outlive the host

The optional, human-reviewed consolidation guidance in this skill is not a rule that every procedure must move or every document must become a stub. The procedure for bringing a failed system back must remain readable when that system is down. A stub that points into a skill on the dead host is a trap.

## The test

If the machine that holds this doc, or the agent that reads it, is offline, can I still read it?
If not, it is not break-glass.

## What a break-glass copy holds

- How to reach the hypervisor or console when DNS is down.
- The DNS and DHCP fallback: what to set by hand, and where.
- Where backups and keys live (the location, never the value) and the restore order.
- Who or what to call when the first three steps fail.

Plain text, one page, no agent needed to follow it.

## Where it lives

Somewhere independent of the failure: printed, a note in the password manager, a second machine,
or a git remote hosted off the lab. Not on the NAS it restores.

## A deliberate copy with a named refresh rule

The break-glass page deliberately repeats critical recovery facts so they remain usable when the primary system or its agent is offline. State the copy's purpose, canonical owner, and refresh or review rule. Keep the independent copy readable without an agent; preserve it during consolidation and do not stub or delete it unless a human approves a replacement and preservation/link checks pass.


# Audit plan template (step 6)

Present this and wait for approval of the named plan. The table describes proposals only: do not edit or delete anything first. Preserve unique meaning and links, and record the purpose, canonical owner, and refresh rule for any intentional duplicate. Never include a secret's value.

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
