# Local candidate verification

October 26, 2026. This receipt covers a local experiment, not a public release,
production service, demand study, or security clearance.

## Executable source reviewed

- `mcp-preflight/preflight.py` SHA-256:
  `20fefde36fd9a8d19314ce9f2d87e301cf98d622be537d801be42291178384e0`
- `mcp-preflight/tests/test_preflight.py` SHA-256:
  `449cc8dba4efff17bef1faae0b12c7be8f8f42923c6df2f992bbf2764de79c5e`

An independent Codex reviewer approved these exact executable/test sources after
the fixes below. The root agent also ran the final 37-test suite on Python
3.12.14. The implementation agent and independent reviewer each reported all
37 tests passing on Python 3.12.14 and 3.13.5. Python 3.10 is the source syntax
minimum; a local Python 3.10 run was not performed.

## Meaningful checks

- Supported and ambiguous configuration shapes, unknown transport, empty input,
  and no-match output; none produces a ready/safe/verified result.
- No subprocess/network invocation in analysis; local PATH lookup is optional
  and limited to known bare runtime names.
- Seeded names, paths, arguments, environment values, endpoints, header values,
  and log text do not appear in reports or CLI output.
- HTML/log-injection inputs and private-safe CLI/JSON/file errors.
- Existing-output preservation, unchanged input bytes, and failed-write cleanup.
- Duplicate keys, nonfinite/oversized numeric literals, excessive nesting,
  invalid UTF-8, oversized files, and the 100-server boundary.
- Conservative package-pin recognition and whitespace-only endpoints.

Review found and corrected malformed-version recognition, whitespace endpoint
handling, numeric-limit/error behavior, embedded-NUL path errors, and oversized
server collections. No blocking finding remained in the final source review.

## Browser inspection

Chromium 151.0.7922.173 through Playwright inspected the synthetic diagnostic
and unmatched-input reports at 1280, 390, and 320 pixels. All widths fit without
horizontal overflow. The page had no scripts, HTTP requests, CSP errors, or
console errors; a seeded input value was absent. The narrow-screen screenshot
was visually inspected. HTML was loaded via `setContent`, since the environment's
browser policy blocks direct file navigation.

Final-source example HTML is byte-identical to the inspected report HTML.
These checks establish the supplied report behavior, not every browser/host or
accessibility condition.

## Limits of the result

- No real upstream failure was reproduced, no actual MCP connection was made,
  and no protected service or configuration was changed.
- Rules provide possible explanations, not a causal diagnosis or a fix.
- The two motivating MCP reports share one dependency path. They do not
  establish a large cross-server market.
- No task comparison against Inspector, participant study, repeat use, measured
  savings, registry publication, hosted CI, or outside adoption has occurred.
- No new public repository, upstream submission, outbound customer contact,
  credential/access change, paid trial, or scheduled job was created.

The executable candidate is ready for the bounded comparison in
[VALIDATION.md](VALIDATION.md). That experiment's result remains unknown.

## Implementation-plan execution supplement

The original diagnostic core and original 37 tests are unchanged. The pilot
preparation adds a scenario runner, neutral participant cases/task cards, blank
observations, and 23 tests. All **60 tests** passed locally on Python 3.12.14
and 3.13.5, and the candidate worktree passed the 60-test suite again.

- Scenario runner SHA-256:
  `ab4dd11a15c26d87cfb3ccd900750c6da952c6d71b2b9e4507c7f6fb69715eff`
- Pilot tests SHA-256:
  `3c8789a4792e8a44d6a878eca8baef251b99004f0e8decbfab641ff3affada4d`

All five synthetic scenarios passed their declared contracts. The hidden
dependency case emitted only the generic timeout/evidence-collection finding,
with no invented Node/npm diagnosis. All human counts, accuracy, task time,
repeat use, and actual baseline-version observations remain null/not-run.
The first planned human baseline is a supplied-file/documentation comparison;
it does not evaluate Inspector's live/runtime capabilities.

The included [result](../mcp-preflight/validation/example-results/result.json)
records the actual evaluator/core hashes and each declared check. Its pass is
automated fixture evidence only. A new bounded CI workflow runs tests and the
five cases on Python 3.10 and 3.13; the pull request records actual hosted
results separately. No containing-repository integration gate is waived.

The evaluator review also found a phrase-matching false positive for uncertainty
words and explicit negations. Word boundaries and bounded negation handling,
with regression cases, corrected it. This remains a declared fixture contract,
not a general semantic truth classifier. The included results were regenerated
with the final evaluator.
