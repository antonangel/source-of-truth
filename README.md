# Source of Truth

A read-only literal-fact check for self-hosters who keep infrastructure docs and text config in a local Git repo and use agents to maintain them.

Requires Python 3.10+ and the standard library only.

Choose one document and one config or skill target. The check reports facts it can extract from the document that are absent from that target, with the exact document line. It does not decide which source is authoritative: you choose. It does not validate meaning, completeness, runtime state, or UI-managed settings, and it does not edit files.

## First check

Run from this repository's root. This synthetic example has one deliberately missing IP:

```text
$ python3 skills/source-of-truth/scripts/sot.py diff tests/fixtures/first-check/docs/dns-runbook.md tests/fixtures/first-check/config --profile=config
ip       203.0.113.10  tests/fixtures/first-check/docs/dns-runbook.md:3
missing facts: 1 of 1 checked
```

Expected exit code: `1` (a missing literal fact). The check leaves both inputs unchanged. Exit `0` means only that no selected literal facts were missing; it is not proof that the document is correct or current.

## Use with your repo

After installing the skill using the setup below, run the bundled check from your repository root:

```bash
python3 .claude/skills/source-of-truth/scripts/sot.py diff path/to/runbook.md path/to/config --profile=config
```

Use `--profile=skill` for a skill target. Config checks `path`, `host`, `ip`, `port`, and `env`; skill checks those plus `id` and `command`. Replace the example paths with the pair you chose. If an agent suggests a target, confirm it before the check.

## Claude Code

First end-to-end test target: Claude Code `2.1.49` with the project-level path `.claude/skills/source-of-truth/`. This client/version/path combination has not yet passed end-to-end validation and is not a support claim. From the repository you want the skill available in, the proposed installation is:

```bash
git clone https://github.com/antonangel/source-of-truth /tmp/source-of-truth
mkdir -p .claude/skills
cp -R /tmp/source-of-truth/skills/source-of-truth .claude/skills/
```

Then invoke `/source-of-truth` and identify both the document and target. Other agent clients and install locations have not been end-to-end verified.

## Boundaries

- Exit `0`: no missing selected literal facts detected. Exit `1`: findings. Exit `2`: usage, path, or input error. Exit `3`: possible secret-shaped content. Read warnings even when findings are also reported; never repeat a secret value.
- The checker compares literal text, not semantics. It cannot inspect runtime state or application UI/API sources.
- The operator chooses the authority. Config can describe desired state; a runtime or app UI/API can describe observed state; documents can own decisions, history, navigation, and knowledge other sources cannot express.
- One authoritative owner per fact does not mean one physical copy. A deliberate copy must state its purpose, canonical owner, and refresh rule. Preserve human-first and break-glass instructions.
- The focused workflow is on-demand and read-only. Broader documentation changes require a named plan, explicit approval, and preservation/link checks before edits or deletion.

Optional Markdown inventory, separate from the first check:

```bash
python3 skills/source-of-truth/scripts/sot.py inventory .
```

Fact kinds: `path`, `host`, `ip`, `port`, `env`, `id`, `command`. See the [agent workflow](skills/source-of-truth/SKILL.md) and [secret-handling guidance](skills/source-of-truth/references/sources-and-secrets.md).

MIT licensed.
