# Break-glass: recovery docs that outlive the host

The migration advice in this skill ("procedures become skills, docs become stubs") has one
exception. The procedure for bringing a failed system back must be readable when that system is
down. A stub that points into a skill on the dead host is a trap.

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

## It is the one sanctioned duplicate

The break-glass page repeats facts that live elsewhere, on purpose. Declare it so an audit does not
"fix" it: date it, say which skill holds the executable version, and read it from the off-host copy
on a schedule. The audit never stubs it and never counts it as drift.
