---
name: capability-adoption
description: Evaluate a new AI feature, plugin, MCP connection, developer tool, or agent capability with primary sources and one bounded comparison before deciding whether to adopt it. Use for a concrete adoption question or an authorized experiment, not a general news roundup.
---

# Capability Adoption

Published by Nymrel. This workflow turns a promising capability into a small,
checkable decision: what it improves, what actually worked, and what remains
unknown. It needs no Nymrel account or private studio connection.

Try prompts such as:

- "Is this new tool useful for reviewing our pull requests? Compare it with our current approach using one synthetic example."
- "Evaluate this SDK feature for our mobile workflow. Check the current docs and propose the smallest useful test."
- "Run the comparison we agreed on, retain the results, and recommend whether to adopt it."

## Start with the outcome and authority

Identify one task the person wants to perform more reliably, quickly, or easily.
Record the current approach and the specific gap. A vendor announcement is a
candidate for evaluation, not a requirement to rebuild a working system.

Use the user's current authorization and the existing project workflow. This
skill grants no access, budget, or permission by itself. A research request
authorizes research; an explicitly requested experiment or implementation can
continue within its agreed scope and existing checks. Do not ask for the same
authorization again. If a necessary action exceeds that scope, complete the
independent preparation and identify the exact missing decision or access.

Use available authorized sources to resolve context before asking the person to
gather it. Preserve their chosen conversation or device while work runs through
an available authorized runtime. Do not introduce another account, subscription,
schedule, model default, or service as a side effect.

## Check the decisive unknowns

Read current primary documentation for the capability. Keep its source URL,
retrieval date, relevant version, documented API shape, supported host, account
requirements, rollout limits, cost boundary, and data handling where relevant.
Separate a documented feature from the current account's actual access.

When account availability matters, use the supported authorized read tool if
available. Documentation or an installed package alone does not establish that
the intended action works. Preserve unavailable reads and missing values.

Review the existing implementation and relevant project instructions before
building. Prefer reusing a component or adding a narrow adapter to replacing a
working workflow. Respect concurrent work and preserve other writers' changes.

## Define one useful comparison

Fill out the [adoption packet](references/adoption-packet.md) in the existing
project note, issue, pull request, or local report. It is a template, not a new
task database.

Choose a small real task that the user has authorized, preferably read-only.
Otherwise use rights-cleared synthetic inputs and label them. Record:

- The exact task, inputs, versions, baseline, and candidate.
- The output expected by the user and a pass/fail criterion chosen before execution.
- The permitted reads, writes, data, runtime, and spending boundary.
- A stop condition and the evidence required for the next decision.

Do not put credentials, private prompts, customer records, or restricted source
material into a test when synthetic or minimized inputs suffice. A constraint
such as "no additional provider spend" is not a measured runtime-cost result.

## Execute and inspect the result

For an authorized experiment, run the comparison and retain the actual outputs,
errors, commands or tool calls, and exact code/package versions. For a requested
build, carry the scoped candidate through the relevant project checks and
permitted delivery. If a required runtime or connection is unavailable, preserve
a runnable artifact where possible and identify that specific limitation.

Use deterministic checks for code and data contracts. Inspect the output the
person will actually see. Test the intended human workflow and agent execution
separately when both matter. A mobile app listing does not prove the task works
on a phone; a portable manifest does not prove every host or provider works.
Name the actual host and version tested.

Keep vendor claims separate from observations. File checks are not a model
benchmark. A synthetic success does not establish broad reliability, production
impact, customer value, or an independent review. Unknown cost, model identity,
intervention count, and business impact remain unknown; use null in structured
results rather than a fabricated zero.

## Make a bounded decision

Lead with the practical finding, then the evidence and its limits. Use the
strongest status actually supported: documented only, blocked by availability,
candidate built, locally validated, host verified, or adopted through the
existing release process. Distinguish a recommendation to adopt from a completed
integration or real use.

Retain a short learning note in the existing project location: observation,
experiment, result, limitation, reusable component, and one next action. Link the
actual artifacts and sources. If no test ran, say so. Do not invent a readiness
score, guarantee, background monitoring promise, or success metric.
