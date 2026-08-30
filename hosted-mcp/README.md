# Nymrel hosted MCP

Production source for `https://mcp.nymrel.com/mcp`.

The public server intentionally exposes four credential-free read tools:

- `nymrel_audit_website`
- `nymrel_find_domain`
- `nymrel_golf_bag_gap`
- `nymrel_social_clip_score`

The vendored client contains additional Nymrel API contracts, but the hosted entrypoint removes them from `tools/list` until their provider or authorization boundaries are production-ready.

## Activation-held private handoff adapter

This source also contains a disabled-by-default adapter for two future,
authenticated tools behind the same `@Nymrel` MCP tag:

- `nymrel_submit_private_handoff`
- `nymrel_get_private_handoff_status`

The public and private contracts stay separate. The four production tools
remain anonymous reads. Private submit/status calls use a caller token verified
by a direct FastMCP `RemoteAuthProvider`, then proxy the accepted
`/api/agent/v1/handoffs` REST contract. The MCP layer does not accept bearer
tokens as tool arguments, hold a shared server credential, choose projects, or
grant execution authority.

Setting `NYMREL_PRIVATE_HANDOFF_MCP_ENABLED=true` alone does **not** activate
the bridge. `NYMREL_PRIVATE_HANDOFF_OAUTH_ISSUER` must identify a Nymrel-owned,
root-level HTTPS OAuth issuer whose JWKS lives at `/oauth2/jwks`. The edge
accepts only RS256 JWTs for `https://mcp.nymrel.com/mcp`, then enforces the
single exact scope declared by the private tool being called. The Nymrel REST
API independently verifies the same claims and maps the
stable provider `sub` to its revocation and project-allowlist policy. An
unrelated provider token fails closed with `401` and is not an activation. No
provider secret, production token, tester identity, or real customer content
is part of source control.

FastMCP 3.2.3 does not populate the OpenAI-required top-level
`securitySchemes` field itself. The hosted list-tools adapter publishes that
field explicitly and retains the same value under `_meta` for older clients.
Contract tests require `noauth` on every public tool and the exact OAuth scope
on each private tool. The adapter also returns a complete
`_meta["mcp/www_authenticate"]` challenge when a private call lacks a valid
token or scope. A target-client OAuth canary remains mandatory before
production activation.

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
AuthKit tenant, tester-subject, dedicated-storage, project-allowlist, and
synthetic production gates are approved. Until then, production proof remains
exactly four public tools.
