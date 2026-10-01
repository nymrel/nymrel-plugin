# Official MCP Registry release packet

Target server: `io.github.nymrel/nymrel`

Source of truth for the published remote is the hosted MCP package in this repository. The broader `nymrel/nymrel-mcp-hub` remains a separate source package and is not represented by this Registry entry.

## Preconditions

- `https://mcp.nymrel.com/mcp` responds with the reviewed public MCP contract.
- Public tool catalog and authentication policy match the repository release being represented.
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

Preferred CI path when a reviewed publication workflow is later adopted:

```bash
mcp-publisher login github-oidc
```

This requires GitHub Actions `id-token: write` and grants publication only within the authenticated GitHub namespace. Interactive `mcp-publisher login github` is an alternative operator path.

Do not create or embed a registry token in source. Do not use DNS/domain private keys unless a separate domain-namespace decision requires them.

## Publication

Protected action — execute only under the current Nymrel release/publication gate:

```bash
mcp-publisher publish server.json
```

After publication, query the official Registry for the exact name/version and retain the returned public listing plus registry metadata as the publication receipt.

## Post-publication acceptance

- Registry resolves `io.github.nymrel/nymrel` version `1.2.0`.
- Listed remote URL is exactly `https://mcp.nymrel.com/mcp`.
- A clean external MCP client can initialize, list the expected public tools, and complete one safe read-only call.
- Tool results, errors, auth challenges, privacy/support links, and Nymrel identity match the released contract.
- Rollback/deprecation uses `mcp-publisher status`; registry visibility does not replace hosted-endpoint rollback.

## Boundary

This packet prepares publication metadata only. It does not authenticate to the Registry, publish the server, change DNS, create keys, change production MCP behavior, or imply that the source-only MCP Hub is hosted.
