# Nymrel plugin cache-bootstrap repair

Date: 2026-08-30
Owner: Codex
Claim: `codex-nymrel-plugin-cache-bootstrap-fix-20260830`
Base: `c66fcc8a27ee56b0b20d129c1548ead2d6971dff`

## Mission

Repair the universal plugin's hosted Node CI bootstrap failure without weakening
its exact npm 11.19.1 `devEngines` contract or adopting unrelated dependency
updates.

## Evidence and root cause

Hosted runs `33285004441` and `33285110762` each failed all four Node jobs inside
`actions/setup-node`. Its `cache: npm` probe ran the hosted runner's npm before
the reviewed npm 11.19.1 bootstrap. On Node 24 the bundled npm was 11.19.0, so
the deliberate fail-closed package-manager contract returned
`EBADDEVENGINES`. Python and CodeQL lanes passed.

## Bounded change

- Disable setup-node's explicit and implicit package-manager cache bootstrap.
- Execute every Node package-manager command through pinned Corepack npm
  11.19.1, removing the global package-manager mutation while retaining all
  existing verification, audit, distribution, Python, and CodeQL gates.
- Add a deterministic regression contract for ordering and cache behavior.
- Preserve the primary checkout and existing public-submission worktree.
- Do not modify or adopt Dependabot PRs #4 or #5.

## Acceptance

- Full local Node verification and CI contract pass on the exact candidate.
- actionlint, workflow parsing, and zizmor pass.
- The exact commit receives independent read-only acceptance.
- Hosted Dependabot or provider-admitted CI proves Ubuntu/Windows Node 22/24.

## Honest gates

This lane does not merge dependency updates, deploy the hosted MCP service,
publish a plugin/package, change provider configuration, or claim adoption,
customers, or revenue.
