# Before and after: one DNS runbook

An invented example: one doc, one skill, no real hosts. The files are in
`tests/fixtures/homelab/` and the output below is checked against them by the test suite.

## Before

`docs/dns-runbook.md` describes the Pi-hole restart, the published ports and the admin address. The
`network-ops` skill covers the same job in different words. Run the fact-diff:

```text
$ python3 scripts/fact-diff.py docs/dns-runbook.md skills/network-ops
host     pihole.lan
ip       192.168.1.1
port     443
port     53
port     80
port     8080
command  cd /srv/stack/dns
command  docker compose pull
command  docker compose up -d pihole
missing facts: 9 of 13 checked
```

On stderr, one more line:

```text
warning: possible secret (credential assignment) at docs/dns-runbook.md:24
```

The doc is not redundant. Nine facts exist only in the doc, and line 24 holds a password.

## Scrub, then migrate

Replace the password with a placeholder, rotate the old one, copy the doc into
`skills/network-ops/references/dns-runbook.md` unchanged, and turn `docs/dns-runbook.md` into a
pointer:

```markdown
# DNS and proxy runbook (moved)

Canonical home: the `network-ops` skill.
Full original text: `skills/network-ops/references/dns-runbook.md`.
Holds: DNS restart procedure, published ports, admin UI address.
Do not add procedure to this file.
```

## After

```text
$ python3 scripts/fact-diff.py docs/dns-runbook.md skills/network-ops
no missing facts detected (14 checked)
```

(Run it on the original text, before it becomes the pointer.)

The doc is still at its path, so nothing that linked to it broke. The procedure has one home.

## And the drift check

The same doc against the compose directory:

```text
$ python3 scripts/fact-diff.py docs/dns-runbook.md config --kinds=path,host,ip,port,env,id
path     /srv/stack/dns
host     pihole.lan
ip       192.168.1.1
port     8080
missing facts: 4 of 9 checked
```

Port `8080` is the useful line. The runbook says the admin UI is on 8080; the compose file maps
`8081:80`. The doc was stale, and an agent following it would have been wrong.
