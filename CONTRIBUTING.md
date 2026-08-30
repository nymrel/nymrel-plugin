# Contributing to the Nymrel universal plugin

Keep changes small, contract-first, and explicit about which surface they
affect: the TypeScript development harness, the hosted Python MCP service, or
the host manifests. Do not turn a local test into a claim about deployment,
directory publication, provider activation, or customer access.

## Toolchains

- Node 24.20.0 is the declared development line; CI also proves Node 22.22.0.
- npm 11.19.1 is required exactly. Plain `npm ci` enforces the reviewed
  install-script allowlist.
- The hosted service requires Python 3.13 and exact direct dependency pins.

## Required gate

From the repository root:

```powershell
fnm use (Get-Content .node-version)
corepack npm@11.19.1 ci
corepack npm@11.19.1 run verify
corepack npm@11.19.1 audit --audit-level=high
corepack npm@11.19.1 audit --omit=dev --audit-level=high
```

From `hosted-mcp`, use a clean Python 3.13 virtual environment and run every
command in the Verify section of `hosted-mcp/README.md`.

Before opening or updating a pull request, also run `git diff --check`, inspect
the scoped diff, and confirm that generated `dist/` output is committed when
TypeScript source changed. Never add credentials, private handoff content,
provider tokens, or real customer fixtures.

Hosted CI and CodeQL remain required evidence when GitHub Actions is available.
If the account or repository cannot execute Actions, leave the pull request
open and record that external gate instead of describing local checks as hosted
proof.
