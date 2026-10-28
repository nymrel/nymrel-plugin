# Version 0.1.0 — October 26, 2026

Public source preview of two skills and one companion template:

- Evidence Workspace: offline renderer, input contract, synthetic fixture,
  HTML template, and regression tests.
- Capability Adoption: standalone guide and experiment packet.
- Material Change Digest: reusable reporting template.

The executable renderer and its regression suite are reused from Nymrel's
Evidence Workspace. Public instructions remove internal operating-ledger,
personal, and private companion dependencies. The input format remains
`nymrel-evidence-view/1` so existing minimized exports can be reused.

## Verification

- 120 renderer/CLI/coordination regression tests passed on Python 3.12.14.
- The synthetic fixture validated and generated public HTML, Markdown, and JSON.
- Private identifier and relative-reference checks passed for the public kit.
- `git diff --check` passed.
- Independent Codex source review found no blocking bugs, privacy leaks, or
  broken relative references in the public kit.
- Chromium 151.0.7922.173 passed a synthetic browser exercise at desktop,
  390-pixel, and 320-pixel widths: filters, multiword search, empty state,
  Escape/reset, source details, keyboard navigation, light/dark appearance,
  and JSON download while a filter hides records. No HTTP requests, CSP errors,
  or console errors occurred. The local HTML was loaded with Playwright's
  `setContent`; the browser's file-navigation policy blocks direct `file:`
  navigation in this environment.

At the original preview, the containing repository passed 14 Node tests and
its local MCP smoke test, plus 169 Python tests and 248 subtests. Its npm audit
then reported three high and two moderate findings. The original Python test
environment later reported PyJWT 2.13.0 advisories.

On the reconciled integration candidate, Node verification and both npm audits
pass; the hosted Python suite passes 177 tests and 248 subtests, lint, compilation,
and dependency consistency. The installed Python test environment audit reports
no known vulnerabilities with PyJWT 2.15.1. The Playwright-pinned browser
download is blocked by this environment's network policy, so the repository UI
smoke uses locally installed Chromium. Python 3.10, other matrix platforms and
hosted CI require their own runs. These local results do not establish hosted
service behavior or authorize a plugin release. The offline kit uses Python's
standard library and contains none of those plugin dependencies.

The public pull request records the exact source and hosted-check state.
Automated checks validate file behavior; they do not establish model routing,
host installation, or actual user adoption.

## Release boundaries

Only the source kit is offered in this release. It makes no service deployment,
directory approval, npm/PyPI publication, provider compatibility, or current
hosted-service availability claim. No hosted MCP or app configuration is
included in the kit, and no production service is changed.
