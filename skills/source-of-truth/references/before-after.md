# Before and after

An invented example — one doc, one skill, no real hosts or paths.

## Before

`docs/queue-rotation.md` described how to rotate the queue, in prose, and the skill
`queue-ops` described the same job in different words. A text comparison scored them as
unrelated. The fact-diff found three facts the skill had never seen:

```text
host     edge.example.net
path     /srv/backups
command  qc-verify --strict
missing facts: 3 of 9 checked
```

## The migration

The three facts went into the skill verbatim, as a new reference file — not paraphrased,
not summarised. The doc became a ten-line pointer naming that reference.

## After

```text
no missing facts detected (9 checked)
```

The doc still exists at its original path, so nothing that linked to it broke. What moved
was the content: the procedure now has one home, and the pointer cannot disagree with it.
