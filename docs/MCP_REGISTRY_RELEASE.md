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

## Authentication

The operator can use the interactive publisher flow:

```bash
mcp-publisher login github
```

Organization namespace publication requires the authenticated user to be an owner
of `nymrel`. On 2026-10-01 UTC the current GitHub account's membership was active
with role `admin`; this proves the organization role, not a Registry publisher
login. GitHub authentication needs organization-role read access and no repository
scopes. Complete the specific publisher authorization under the applicable
operator grant. No CI workflow or `id-token: write` change is included.

Do not create or embed a registry token in source. Do not use DNS/domain private keys unless a separate domain-namespace decision requires them.

## Publication

Protected action — execute only under the current Nymrel release/publication gate:

```bash
mcp-publisher publish server.json
```

After publication, query the official Registry for the exact name/version and retain the returned public listing plus registry metadata as the publication receipt.

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

This packet prepares publication metadata only. It does not authenticate to the Registry, publish the server, change DNS, create keys, change production MCP behavior, or imply that the source-only MCP Hub is hosted.
