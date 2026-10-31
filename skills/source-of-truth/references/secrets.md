# Secrets in docs

Runbooks collect credentials: a Pi-hole password, an API token, a Wi-Fi key, a tailnet auth key.
"Migrate verbatim" is the right rule for procedure and the wrong one for credentials. Moving a
secret into a skill copies it into a directory that gets synced, backed up, shared with an agent
session, or pushed.

## Scrub first

1. Run `fact-diff.py` on the doc. Warnings go to stderr as `file:line` plus a kind. The value is
   never printed, and a flagged line is left out of the fact checks until it is clean.
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
