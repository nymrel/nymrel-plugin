---
name: evidence-workspace
description: Build or compare an offline evidence snapshot from selected GitHub issues, pull requests, handoffs, saved plugin metadata, or official OpenAI capability records. Use for a source-linked status view, implementation-versus-adoption check, or a brief explaining material changes.
---

# Evidence Workspace

Turn one question into an HTML view, Markdown brief, and normalized JSON snapshot.
We use this workflow to see what changed, which claims have source evidence,
and what remains unknown. It works from a small supplied export and makes no
network calls. Python 3.10+ and the standard library are sufficient.

Example requests:

- “Show what is implemented, reviewed, and still unverified for this PR.”
- “Compare these two checkpoints and explain material changes.”
- “Prepare a public snapshot from these classified source records.”

## Select the question and retrieve evidence

Use the exact issue, PR, plugin, or initiative the user named. Read only the
sources needed to answer the question through the user's authorized tools.
Keep the user on their chosen conversation surface; agent execution does not
require the user to open a terminal.

Retrieve actual source state before concluding. For GitHub, preserve native
issue/PR state and exact revision; retrieve review and check results separately
when needed. For plugins, preserve the returned release ID and scope. For a
capability, use current official documentation. Source prose records a claim;
it does not establish that a test ran or a deployment happened.

## Prepare minimal input

Read the [input contract](references/input-contract.md). The supported adapters
are GitHub issue, PR, handoff and coordination update; ChatGPT plugin release;
and official OpenAI capability documentation. These are the current provider
boundaries. Do not invent source URLs to fit another provider into this schema.

Each record needs a stable ID, source URL, observation timestamp, and explicit
public/private classification. Use only allowlisted fields and short sourced
summaries. Exclude credentials, raw messages, full issue bodies, customer records,
and private correspondence. Keep event time separate from retrieval time.

Missing reviews or checks remain null unless actually retrieved. An unchanged
re-fetch does not count as product progress. Validation checks consistency,
not source authenticity, permissions, or completeness.

## Generate the snapshot

Commands below are relative to this skill directory:

```sh
python scripts/evidence_workspace.py validate --input references/synthetic-example.json --json-errors
python scripts/evidence_workspace.py build --input references/synthetic-example.json --output /tmp/evidence-example
python scripts/evidence_workspace.py compare --input CURRENT.json --previous PRIOR.json --output NEW_OUTPUT_DIR
```

Use a new output directory each time. Build writes `index.html`, `brief.md`,
and `view.json`; compare also writes `delta.json`. The included example is
synthetic and its placeholder source URL is not a real project result.

Default output is private. Add `--audience public` to remove private records
and private envelope text before rendering, serialization, counts, and hashing.
Review classification and remaining public content before sharing. The flag
does not authorize publication or comprehensively detect confidential data.

The renderer reads no credentials, executes no source commands, and includes no
remote assets, telemetry, automatic refresh, or network requests. Clickable
source links navigate only when a person selects them. Output is a snapshot;
it is not a live dashboard or an authoritative task system.

## Verify and interpret

After changing executable resources, run:

```sh
python -m unittest discover -s tests -p 'test_*.py'
```

Inspect rendered output at desktop and narrow mobile widths when a browser is
available. Check filtering, multiword search, clear/Escape controls, source
details, light/dark appearance, keyboard focus, overflow, and download. Downloads
include all audience-visible records, even cards hidden by current filters.
If browser execution is unavailable, say so.

Preserve the limits of the evidence:

- Saved plugin metadata does not prove installation, invocation, or host acceptance.
- A merge does not establish deployment or real use.
- Missing checks do not mean successful tests; an old-head review does not clear a new head.
- A posted handoff does not establish acknowledgment or current ownership.
- Official documentation does not establish account access or measured value.
- A record absent from a bounded snapshot is not necessarily deleted.
- A digest identifies local content; it does not authenticate the source.

## Deliver

Lead with the finding and link the actual HTML, brief, or JSON snapshot. State
scope, observation time, source revision, checks actually run, and the smallest
remaining uncertainty. Use the [material-change digest](../../resources/material-change-digest.md)
when a short update is more useful than another full report.

If no execution surface exists, deliver the same sourced table in chat and label
the HTML artifact unbuilt. Do not claim that installing the skill creates an
execution environment, grants access, or schedules a refresh.

