# One bounded adoption packet

Published by Nymrel. Copy this template into an existing project note, issue,
pull request, or local report. It creates no registry, schedule, or authorization.
Leave unavailable observations unknown; use null when a structured value is
needed. Mark proposed actions clearly.

**Outcome:** What useful task should improve? What is difficult about the current
approach? State the scope and the person's intended result.

**Existing component:** Identify the repository, package, or workflow being
reused, its exact version or revision, relevant project instructions, and any
known overlapping work. Keep the existing review and release process.

**Verified capability:** Link current primary documentation and record when it
was checked. State the documented API, host/version, account requirements,
rollout, relevant cost boundary, and unresolved availability gaps. Documentation
and actual account access are separate evidence.

**Smallest test:** Specify the exact task and permitted inputs, including their
rights and privacy classification. Define the baseline, candidate, expected
output, and pass/fail criterion before running it. Label synthetic examples.

**Execution boundary:** Record the user's authorized scope and the supported
source, tool, or runtime. What may the test read, write, or cost? Which required
access is available? Do not include secrets. A no-additional-spend constraint is
not a measured cost result.

**Observed result:** Link exact artifacts and versions. List tests actually run,
user-visible output inspected, host/version exercised, errors, and limitations.
State whether independent review occurred. Preserve unknown measurements.

**Decision and reuse:** Recommend adopt, defer, or reject for this task, with the
reason and strongest verified status. Identify any reusable component. Separate
proposed reuse from applied integration and real use. One synthetic result does
not establish general reliability or business value.

**Next proof or stop:** Name one concrete next action and its required evidence.
If blocked, identify the exact unavailable capability, conflicting change,
failed check, missing access, or decision outside the authorized scope. Continue
independent authorized work; preserve a useful artifact rather than repeatedly
attempting an unchanged failure.

## Synthetic example

**Outcome:** Produce a consistent release summary from a small set of public
commit messages.

**Smallest test:** Give the current approach and candidate the same five
synthetic messages. Pass only if both identify all three supplied user-visible
changes, omit the two maintenance-only changes, and add no unsupported claims.

**Execution boundary:** Local files only; no external service calls or additional
provider spend authorized.

**Observed result:** Not run. Runtime cost, time saved, and model identity are
unknown. This example demonstrates a test definition, not a capability result.
