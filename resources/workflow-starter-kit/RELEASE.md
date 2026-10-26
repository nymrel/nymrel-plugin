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

The containing repository's Node verification passed 14 tests plus its local
MCP smoke test. Its existing hosted Python code passed 169 tests and 248
subtests, lint, compilation, and dependency-consistency checks. These are local
results, not hosted-service verification.

Whole-plugin release remains pending: existing npm dependency audits report
three high and two moderate findings; the pinned Playwright browser download
is denied by this environment's network policy; the default UI test therefore
cannot start; and the strict Python dependency audit cannot create its temporary
environment because Python 3.13's `ensurepip` is unavailable. The offline kit
uses Python's standard library and contains none of those plugin dependencies.
The preview does not waive any repository integration gate or change the plugin.

The public pull request records the exact source and hosted-check state.
Automated checks validate file behavior; they do not establish model routing,
host installation, or actual user adoption.

## Release boundaries

Only the source kit is offered in this release. It makes no service deployment,
directory approval, npm/PyPI publication, provider compatibility, or current
hosted-service availability claim. No hosted MCP or app configuration is
included in the kit, and no production service is changed.
