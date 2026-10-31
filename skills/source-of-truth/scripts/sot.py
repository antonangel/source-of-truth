#!/usr/bin/env python3
"""Compare the environment-specific facts a document holds against a target.

    sot.py diff <doc.md> <skill-dir | SKILL.md | config-dir> [--profile=skill|config]
                [--kinds=path,host,ip,port,env,id] [--all] [--quiet] [--force]
    sot.py inventory [repo] [--top=N]

The target of `diff` is either a skill (is the doc redundant?) or a config directory (has the doc
drifted?). Every text file under it is searched.

Fact kinds: path, host, ip, port, env, id, command.

Output: one fact per line on stdout, `kind`, then the value, then the `doc:line` it came from.
A summary line follows. Secret warnings, suppressed-candidate counts and notes go to stderr.

Exit codes:
    0  no missing facts detected
    1  facts are missing: migrate them into the skill's references/ before stubbing
    2  usage error
    3  the document holds something that looks like a secret

**Exit 0 is necessary, not sufficient.** It proves the target contains every fact the doc states.
It cannot tell you the target arranges them into a usable procedure, that the commands still work,
or that the doc's prose carried no meaning. Read the pair first.

Precision beats recall. A candidate that cannot be told apart from a status code, a clock, a date
fragment or an IPv6 octet is suppressed rather than reported, because one wrong line costs more
trust than one missing line. The count of suppressed candidates is printed, and `--all` shows them.

Secrets: a doc line that looks like a secret is reported by line and kind, its value is never
printed, and the line is left out of the fact checks. Scrub it, then run again. This is a tripwire
for docs, not a history scanner.

Known limitations:
- Config keys, parameters, image names and volume mappings are not extracted; env vars only in the
  form NAME=value. IPv6 and MAC addresses are not extracted, and an IPv6 literal is never read as
  a port list.
- A bare `host:N` is reported only when the host is an address, `localhost`, a URL authority, or a
  name with N >= 1024, so `backend:80` in prose is missed and `http_status:404` is not invented.
- An `N:M` pair is a port mapping only inside a fence, a quote or a backtick, or next to a mapping
  keyword; `90:10` in prose is a ratio, not a port.
- Inline backtick prose is filtered with a stopword list; a phrase whose first word is not a
  stopword (for example "run tests") can be mistaken for a command. Fenced blocks are unaffected.
- A doc command that is a prefix of a longer target command counts as present when the next
  character is whitespace.

Python 3.10+, standard library only.
"""


import subprocess
import sys
import time
from pathlib import Path

# Dual-use: run as a script (sys.path[0] is this directory) or loaded by importlib in the test
# harness (sys.path[0] is not). Both must find the engine.
_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from sotassets import OWNED, agents_block, ci_snippet
from sotlib import (
    EXIT_CLEAN, EXIT_MISSING, EXIT_SECRET, EXIT_USAGE, KINDS, PROFILES,
    census, check_docs, check_scope, extract, find_ports, inbound_counts, is_pointer,
    is_record, load_ignore, pointer_needles, present, secret_lines, skill_corpus,
)


# --------------------------------------------------------------------------- CLI

def parse_diff_args(argv: list[str]):
    paths: list[str] = []
    quiet, force, show_all, kinds, profile = False, False, False, None, "skill"
    for arg in argv[1:]:
        if arg == "--quiet":
            quiet = True
        elif arg == "--force":
            force = True
        elif arg == "--all":
            show_all = True
        elif arg.startswith("--kinds="):
            kinds = [k.strip() for k in arg.split("=", 1)[1].split(",") if k.strip()]
            if not kinds or any(k not in KINDS for k in kinds):
                return None
        elif arg.startswith("--profile="):
            profile = arg.split("=", 1)[1].strip()
            if profile not in PROFILES:
                return None
        elif arg.startswith("--"):
            return None
        else:
            paths.append(arg)
    if len(paths) != 2:
        return None
    return (paths, quiet, kinds if kinds is not None else list(PROFILES[profile]), show_all, force)


DIFF_USAGE = (
    "usage: sot.py diff <doc> <skill-dir | SKILL.md | config-dir>\n"
    "       [--profile=skill|config] [--kinds=a,b] [--all] [--quiet] [--force]\n"
    f"kinds: {', '.join(KINDS)}\n"
    "profiles: skill, config"
)


def diff_main(argv: list[str]) -> int:
    parsed = parse_diff_args(argv)
    if parsed is None:
        print(DIFF_USAGE, file=sys.stderr)
        return EXIT_USAGE
    (doc_arg, target_arg), quiet, kinds, show_all, force = parsed

    doc, target = Path(doc_arg), Path(target_arg)
    for p in (doc, target):
        if not p.exists():
            print(f"not found: {p}", file=sys.stderr)
            return EXIT_USAGE

    doc_text = doc.read_text(errors="ignore")
    if is_record(doc, doc_text) and not force:
        print(f"note: {doc} classified as append-only record; skipping fact-diff "
              f"(use --force to override)", file=sys.stderr)
        return EXIT_CLEAN

    secrets = secret_lines(doc_text)
    for number, kind in secrets:
        print(f"warning: possible secret ({kind}) at {doc}:{number}", file=sys.stderr)
    flagged = {number for number, _ in secrets}
    clean = "\n".join("" if i in flagged else line
                      for i, line in enumerate(doc_text.splitlines(), 1))

    _, suppressed = find_ports(clean)
    if suppressed and not quiet:
        print(f"note: {suppressed} low-confidence port candidate(s) suppressed "
              f"(rerun with --all to show them)", file=sys.stderr)

    corpus = skill_corpus(target)
    needles = pointer_needles(target)

    facts = extract(clean)
    selected = {k: v for k, v in facts.items() if k in kinds}
    total = sum(len(v) for v in selected.values())
    missing: list[tuple[str, str, int]] = []
    for kind in KINDS:
        if kind not in selected:
            continue
        for value in sorted(selected[kind]):
            if is_pointer(value, needles):
                continue
            if not present(corpus, value, kind):
                missing.append((kind, value, selected[kind][value]))

    if not quiet:
        for kind, value, line in missing:
            print(f"{kind:<8} {value}  {doc}:{line}")

    if missing:
        print(f"missing facts: {len(missing)} of {total} checked")
        return EXIT_MISSING

    if secrets:
        print(f"secret warnings: {len(secrets)} (exit 3)")
        return EXIT_SECRET

    print(f"no missing facts detected ({total} checked)")
    return EXIT_CLEAN


def parse_inventory_args(argv: list[str]):
    args, top = [], None
    for arg in argv[1:]:
        if arg.startswith("--top="):
            try:
                top = int(arg.split("=", 1)[1])
            except ValueError:
                return None
        elif arg.startswith("--"):
            return None
        else:
            args.append(arg)
    if len(args) > 1:
        return None
    return (Path(args[0]) if args else Path(".")), top


def inventory_main(argv: list[str]) -> int:
    parsed = parse_inventory_args(argv)
    if parsed is None:
        print("usage: sot.py inventory [repo-dir] [--top=N]", file=sys.stderr)
        return EXIT_USAGE
    root, top = parsed
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return EXIT_USAGE

    docs = census(root, load_ignore(root))
    counts = inbound_counts(docs)
    now = time.time()
    rows = []
    for rel, (path, text) in docs.items():
        facts = extract(text)
        try:
            age = int((now - path.stat().st_mtime) / 86400)
        except OSError:
            age = 0
        rows.append((
            len(text.splitlines()), age, counts[rel],
            len(facts["ip"]), len(facts["port"]), len(facts["command"]),
            len(secret_lines(text)), rel,
        ))
    rows.sort(key=lambda r: (-(r[3] + r[4] + r[5]), r[7]))
    shown = rows[:top] if top else rows

    print(f"{'lines':>6} {'age_d':>6} {'inbound':>8} {'ips':>4} {'ports':>6} {'cmds':>5} "
          f"{'secrets':>8}  path")
    for lines, age, inbound, ips, ports, cmds, secrets, rel in shown:
        print(f"{lines:>6} {age:>6} {inbound:>8} {ips:>4} {ports:>6} {cmds:>5} {secrets:>8}  {rel}")
    orphans = sum(1 for r in rows if r[2] == 0)
    with_secrets = sum(1 for r in rows if r[6])
    print(f"\n{len(rows)} docs, {with_secrets} with possible secrets, "
          f"{orphans} with no inbound references")
    if top and len(rows) > top:
        print(f"(showing {top} of {len(rows)}; sorted by facts stated)")
    return EXIT_CLEAN


CHECK_USAGE = "usage: sot.py check [repo-dir] [--staged] [--all] [--strict]"


def parse_check_args(argv: list[str]):
    args, mode, strict = [], "default", False
    for arg in argv[1:]:
        if arg == "--staged":
            mode = "staged"
        elif arg == "--all":
            mode = "all"
        elif arg == "--strict":
            strict = True
        elif arg.startswith("--"):
            return None
        else:
            args.append(arg)
    if len(args) > 1:
        return None
    return (Path(args[0]) if args else Path(".")), mode, strict


def check_main(argv: list[str]) -> int:
    parsed = parse_check_args(argv)
    if parsed is None:
        print(CHECK_USAGE, file=sys.stderr)
        return EXIT_USAGE
    root, mode, strict = parsed
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return EXIT_USAGE

    paths, description, error = check_scope(root, mode)
    if error:
        print(error, file=sys.stderr)
        return EXIT_USAGE
    print(f"checking: {description}", file=sys.stderr)
    if paths is not None and not paths:
        print("no changed documents", file=sys.stderr)
        return EXIT_CLEAN

    findings, secrets = check_docs(root, paths)
    for finding in findings:
        location = f"{finding.path}:{finding.line}" if finding.line else finding.path
        print(f"{finding.tier:<5} {location}  {finding.message}")
    for rel, number, kind in secrets:
        print(f"warning: possible secret ({kind}) at {rel}:{number}", file=sys.stderr)

    fails = sum(1 for finding in findings if finding.tier == "fail")
    infos = len(findings) - fails
    if findings:
        print(f"{len(findings)} findings ({fails} fail, {infos} info)")
    else:
        print("no findings")

    if secrets:
        print(f"secret warnings: {len(secrets)} (exit 3)", file=sys.stderr)
        return EXIT_SECRET
    if fails or (strict and infos):
        return EXIT_MISSING
    return EXIT_CLEAN


INIT_USAGE = "usage: sot.py init [repo-dir] [--print] [--force]"


def parse_init_args(argv: list[str]):
    args, do_print, force = [], False, False
    for arg in argv[1:]:
        if arg == "--print":
            do_print = True
        elif arg == "--force":
            force = True
        elif arg.startswith("--"):
            return None
        else:
            args.append(arg)
    if len(args) > 1:
        return None
    return (Path(args[0]) if args else Path(".")), do_print, force


def _git(*args: str, cwd: Path) -> str | None:
    proc = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True)
    return proc.stdout.strip() if proc.returncode == 0 else None


def _script_ref(toplevel: Path) -> str:
    """How the operator should invoke this script from the repository root.

    Never a hardcoded install path (ADR 0002 §9): relative to the git root when the script lives
    inside the repository, absolute when it does not.
    """
    script = Path(__file__).resolve()
    try:
        return script.relative_to(toplevel).as_posix()
    except ValueError:
        return str(script)


def init_main(argv: list[str]) -> int:
    parsed = parse_init_args(argv)
    if parsed is None:
        print(INIT_USAGE, file=sys.stderr)
        return EXIT_USAGE
    root, do_print, force = parsed
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return EXIT_USAGE
    if _git("rev-parse", "--is-inside-work-tree", cwd=root) != "true":
        print(f"not a git work tree: {root}", file=sys.stderr)
        return EXIT_USAGE
    top = _git("rev-parse", "--show-toplevel", cwd=root)
    if not top:
        print(f"not a git work tree: {root}", file=sys.stderr)
        return EXIT_USAGE
    ref = _script_ref(Path(top))

    print(f"source-of-truth init — {root}")
    print()
    written = skipped = 0
    for rel, body in OWNED:
        path = root / rel
        if path.exists() and not force:
            print(f"{'skip (exists)':<18}{rel}")
            skipped += 1
        elif do_print:
            print(f"{'would write':<18}{rel}")
            written += 1
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body)
            print(f"{'write':<18}{rel}")
            written += 1

    print()
    if do_print:
        print(f"{written} would be written, {skipped} skipped (--print: nothing written)")
    else:
        print(f"{written} written, {skipped} skipped")
    print()
    print("paste this into AGENTS.md (this tool never edits it):")
    print()
    print(agents_block(ref))
    print("paste this into your CI workflow (this tool never writes it):")
    print()
    print(ci_snippet(ref))
    return EXIT_CLEAN


USAGE = """usage:
  sot.py init [repo-dir] [--print] [--force]
  sot.py check [repo-dir] [--staged] [--all] [--strict]
  sot.py inventory [repo-dir] [--top=N]
  sot.py diff <doc.md> <skill-dir | SKILL.md | config-dir> [--profile=skill|config]
              [--kinds=KINDS] [--all] [--quiet] [--force]

init installs the document contract and prints the two blocks it will not write.
check reports structural findings for changed documents (default), the index (--staged) or the
whole repository (--all); --strict promotes info-tier findings to a failure.
inventory censuses a repository. diff compares one document against one selected target.
Exit codes: 0 clean, 1 findings, 2 usage, 3 secret-shaped content."""


def main(argv: list[str]) -> int:
    if len(argv) > 1 and argv[1] == "init":
        return init_main([argv[0]] + argv[2:])
    if len(argv) > 1 and argv[1] == "check":
        return check_main([argv[0]] + argv[2:])
    if len(argv) > 1 and argv[1] == "inventory":
        return inventory_main([argv[0]] + argv[2:])
    if len(argv) > 1 and argv[1] == "diff":
        return diff_main([argv[0]] + argv[2:])
    print(USAGE.replace("KINDS", ",".join(KINDS)), file=sys.stderr)
    return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main(sys.argv))
