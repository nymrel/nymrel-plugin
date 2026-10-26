# A bounded test before building a flagship

Decision date: October 26, 2026 (Pacific time).

## Candidate

An offline MCP configuration/log diagnostic report for developers and support
staff. The job is: "Explain why this setup failed and give me the next evidence
to collect, without making me execute more unknown code or share credentials."

This is a product hypothesis. The primary source reports establish examples of
pain; they do not establish that a standalone diagnostic tool is needed.

## Baseline

The first human comparison is supplied-file diagnosis using current MCP
Inspector documentation and the package's current README, versus the same
supplied files plus the prototype. Record exact documentation/source revisions
and observation dates. Do not use an obsolete release or withhold a documented
feature that applies to the task.

Inspector's live/runtime diagnostics are not executed or evaluated in this first
comparison. Its result cannot establish superiority over Inspector as a whole.
If participants normally use live inspection, a separate, appropriately scoped
comparison of that actual workflow is needed before making a replacement claim.

## Participants and cases

Recruit five consenting developers or support staff who have configured at
least one MCP server. No outreach has been performed. A GitHub commenter is not
automatically a participant, a customer, or a nondeveloper.

Use rights-cleared synthetic configurations/logs with three predefined failures:

1. A missing launcher/runtime signal and an opaque timeout.
2. Installer output appearing in a combined log with a protocol parse failure.
3. A certificate or registry-egress problem in a restricted environment.

Include two deliberately ambiguous cases:

4. An installed, pinned Python launcher whose package has a hidden Node/npm
   dependency, with only a generic client timeout in the supplied log. The
   report must preserve an unverified cause and request stage-specific evidence;
   it cannot infer that hidden dependency from the launcher configuration.
5. No useful diagnostic signal. The result must remain not verified.

Correct behavior in both cases is to preserve uncertainty and request narrower
evidence. These harder cases prevent an apparent win on synthetic examples
designed only to match the prototype's existing rules.
Do not run upstream packages or contact a held service for these tasks.

Give each participant both approaches in a varied order. Record the diagnosis,
next action, elapsed task time, wrong conclusions, assistance, and whether they
would use the result again. Keep personal data and real credentials out of the
published evidence. Missing measurements remain unknown.

## Predefined continuation criteria

- At least four of five participants identify a defensible next action for
  each concrete failure, and nobody interprets an ambiguous case as verified.
- Median diagnosis time is at least 30% lower than the incumbent baseline on
  these tasks, with raw paired observations retained. This small sample is
  directional usability evidence, not a population estimate.
- Report outputs contain none of the seeded secret values, raw arguments,
  endpoints, paths, or log text.
- At least two participants voluntarily bring a second relevant case or reuse
  the prototype within a week. Do not count a star, download, or polite interest
  as repeat use.

Do not claim these criteria passed before observations exist. Current status:
**not run**; elapsed times, participant outcomes, repeat use, and value are unknown.

## Stop or change direction

Stop the standalone product if Inspector already explains the cases equally
well, false diagnoses create extra work, or upstream fixes remove the recurring
job. An issue reproduction, documentation improvement, fixture contribution, or
integration into an existing project may be the better result. Follow the
receiving project's current contribution policy; no external contact or PR has
been sent.

If the gap is real, expand only the most frequently repeated failure class.
Support deterministic rules and evidence before adding model-based diagnosis.
Keep a developer CLI and a readable report over the same small core; consider
a nondeveloper interface only when actual nondeveloper tasks are validated.

## A route to a recognizable open-source provider

1. Choose one plain-language promise and one initial user group.
2. Publish a complete, tested workflow with an honest license and a five-minute
   example; maintain the issue/release/security instructions in its owning repo.
3. Turn consented, reproducible failures into regression fixtures and fixes.
4. Contribute useful documentation and fixes to upstream projects that accept
   them, with attribution and review.
5. Report actual successful tasks, repeat use, outside contributions, response
   time, and compatibility maintenance. Downloads and stars are distribution
   indicators, not proof of solved pain.

The initial two weeks are for the comparison and one narrow usable release if
the gate passes. The following two weeks are for onboarding/support and repeat
use, with dates adjusted to actual participant availability. These are proposed
work windows, not scheduled jobs or guaranteed outcomes.
