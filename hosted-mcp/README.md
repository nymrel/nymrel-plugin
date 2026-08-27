# Nymrel hosted MCP

Production source for `https://mcp.nymrel.com/mcp`.

The public server intentionally exposes four credential-free read tools:

- `nymrel_audit_website`
- `nymrel_find_domain`
- `nymrel_golf_bag_gap`
- `nymrel_social_clip_score`

The vendored client contains additional Nymrel API contracts, but the hosted entrypoint removes them from `tools/list` until their provider or authorization boundaries are production-ready.

## Dormant private handoff adapter

This source also contains a disabled-by-default adapter for two future,
authenticated tools behind the same `@Nymrel` MCP tag:

- `nymrel_submit_private_handoff`
- `nymrel_get_private_handoff_status`

The public and private contracts stay separate. The four production tools
remain anonymous reads. Private submit/status calls use a caller token verified
by an injected FastMCP `AuthProvider`, then proxy the accepted
`/api/agent/v1/handoffs` REST contract. The MCP layer does not accept bearer
tokens as tool arguments, hold a shared server credential, choose projects, or
grant execution authority.

Setting `NYMREL_PRIVATE_HANDOFF_MCP_ENABLED=true` alone does **not** activate
the bridge. Production also needs an explicitly injected OAuth 2.1 provider
that publishes protected-resource metadata and verifies issuer, audience,
expiry, revocation, and the exact `handoff:create` / `handoff:read_own` scopes.
Its verified access token must also map to the same principal, revocation,
scope, and project-allowlist authority enforced by the Nymrel REST endpoint;
an unrelated provider token fails closed with `401` and is not an activation.
No provider, client secret, production token, or real customer content is part
of this branch.

FastMCP 3.2.3's bundled MCP model emits per-tool `securitySchemes` under the
documented `_meta` compatibility mirror rather than as a top-level tool field.
The adapter also returns `_meta["mcp/www_authenticate"]` when a private call
lacks a valid token or scope. Reconfirm both shapes against the target ChatGPT
client before production activation.

## Verify

```powershell
python -m unittest discover -s tests -v
```

The private adapter's synthetic-only gate is:

```powershell
python -m unittest tests.test_private_handoff -v
```

## Deploy

Link this directory to the existing `nymrel-mcp` Vercel project, run the tests, then deploy from this exact clean commit. Verify `tools/list` and one successful call per advertised tool after the production alias is ready.

Do not deploy the private feature until its separate consent, retention,
provider, secret, project-allowlist, and synthetic production gates are
approved. Until then, production proof remains exactly four public tools.
