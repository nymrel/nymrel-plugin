# Official MCP Registry release packet

Target server: `io.github.nymrel/nymrel`, version `1.4.0`.

Source of truth for the published remote is the hosted MCP package in this repository. The broader `nymrel/nymrel-mcp-hub` remains a separate source package and is not represented by this Registry entry.

## Current source and live scope

Canonical source PR #37 merged into main at
`4a70be6e9c6eab8ee160c97061959c851c243588`. Plugin version is 1.4.0.
On 2026-10-01 UTC the live endpoint advertised four anonymous public utilities
plus seven OAuth-protected Nymrel Remote read tools. A public connection can
discover the private tools, but cannot read private devices without authorization.
The metadata describes both parts of that catalog.

Fresh direct protocol calls succeeded for all four public tools using public or
synthetic inputs. The canonical live verifier passed the input/output schemas,
auth annotations, exact issuer, two read scopes, and missing/invalid-token denial
checks. These calls do not prove a host's model behavior or UI rendering.

## Preconditions

- `https://mcp.nymrel.com/mcp` responds with the reviewed public MCP contract.
- The mixed public/OAuth catalog and authentication policy match the represented release.
- Repository head and live deployment are reconciled.
- `server.json` validates with the current official `mcp-publisher validate` command.
- Namespace authentication uses the Nymrel GitHub organization or another separately approved official method.
- No package publication is implied; this entry uses the hosted Streamable HTTP remote.

## Validation

```bash
mcp-publisher validate server.json
```

Validation must be rerun after any version, endpoint, repository, or metadata change. A local JSON-schema pass is supporting evidence only; the official publisher's schema + semantic validation is the release gate.

## Authentication and controlled workflow

The interactive `mcp-publisher login github` flow can fail to establish an
organization namespace when the Registry cannot read the user's organization
role. The Registry's response may require an approved GitHub Actions OIDC flow or
a classic personal access token with `read:org`. This release route uses GitHub
Actions OIDC and does not store or pass a personal token.

The manual-only workflow is `.github/workflows/publish-mcp-registry.yml`, named
**Publish Nymrel MCP Registry listing**. Its only input is `expected_main_sha`,
the full 40-character SHA of the reviewed `main` commit. It refuses publication
unless the run is manually dispatched in `nymrel/nymrel-plugin` from `main`, the
input equals the dispatched SHA, and fetched current `main` still equals that
SHA. The read-only verification job runs first. The publication job alone gets
`id-token: write`; repository-wide permissions remain `contents: read`.
Read-only verification also runs for scoped pull requests and main pushes;
those events cannot reach the publication job.

Registry OIDC grants authority across the GitHub owner's namespace rather than
binding that authority to one repository, ref, or workflow. Preserve protected
main and source review of this workflow. Its fixed listing guards restrict this
publication path; they do not narrow the Registry token's owner-level authority.

The workflow is pinned to MCP publisher `v1.8.6`. It verifies the official Linux
amd64 release archive against its published SHA-256 and Sigstore identity, runs
official `mcp-publisher validate`, obtains GitHub Actions OIDC via
`mcp-publisher login github-oidc`, then rechecks the pinned metadata before
publishing and reading back the exact Registry version. It accepts no arbitrary
name, version, digest, URL, or artifact input. A future listing version requires
a reviewed source change and updated guard/tests.

Do not create or embed a Registry token in source. Do not use DNS/domain private
keys unless a separate domain-namespace decision requires them.

## Publication

Protected action — execute only under the current Nymrel release/publication gate:

The workflow validates the exact `server.json`, publishes it, queries the exact
Registry name/version, and records the public listing identity and endpoint in
the run summary and public JSON artifact as the publication receipt. Dispatch is intentionally not
performed by this change.

## Post-publication acceptance

- Registry resolves `io.github.nymrel/nymrel` version `1.4.0`.
- Listed remote URL is exactly `https://mcp.nymrel.com/mcp`.
- A clean external MCP client can list all eleven tools, call a public utility,
  and confirm that unauthenticated private reads are denied.
- Tool results, errors, auth challenges, privacy/support links, and Nymrel identity match the released contract.
- Registry visibility does not establish a downstream host gallery listing,
  endorsement, or security certification.
- Endpoint rollback and Registry lifecycle actions are separate; check current
  official publisher help before performing either.

## Boundary

This packet and workflow do not imply that publication has occurred. They do not
change DNS, create keys, change production MCP behavior, or imply that the
source-only MCP Hub is hosted.
