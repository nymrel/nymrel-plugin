# Same-app Remote reader (disabled)

The existing `https://mcp.nymrel.com/mcp` app can expose seven additional
`nymrel_remote_` tools while retaining its four anonymous public tools.
This source change is not an activation, deployment, or ChatGPT acceptance.

The gateway and dedicated Remote backend implement one OAuth resource:
`https://mcp.nymrel.com/mcp`. The caller's verified bearer is forwarded only to
`https://nymrel-remote-production.up.railway.app/nymrel/plugin/readonly/mcp`.
The backend must independently verify that exact audience, issuer, subject,
scopes and dedicated tenant mapping. Existing direct Remote endpoints keep
their original audiences. No shared service token or token tool argument exists.

## Configuration for a later reviewed activation

- `NYMREL_REMOTE_READ_MCP_ENABLED=true` explicitly enables the adapter.
- `NYMREL_REMOTE_READ_OAUTH_ISSUER` is the exact published HTTPS issuer,
  preserving any trailing slash.
- `NYMREL_REMOTE_READ_OAUTH_JWKS_URL` is the provider's exact HTTPS JWKS URL.
- Tokens must carry both `devices:read` and `tools:read`, with RS256 signatures
  and audience `https://mcp.nymrel.com/mcp`.
- The existing private-handoff feature must remain disabled. Simultaneous
  activation fails at startup; its provider and tools are not reused.

The gateway never selects a tenant or grants a device permission. Before
activation, deploy the separately reviewed backend profile, configure its
restricted subject mapping, and configure the provider for the plugin resource.
The previously staged Auth0 API for the Railway read-only URL has a different
audience and cannot supply a usable plugin token.

`api/remote-read-tools.json` freezes the seven read schemas from Remote's
`chatgpt-readonly-profile.js` as inspected on September 23, 2026. Only those
names are routable. Additional arguments, write tools, redirects and custom
destinations are rejected. Responses are bounded to 2 MiB; reads that return
pending retain their call ID and use `nymrel_remote_get_read_result`.

## Verification

Run `python -m unittest discover -s tests -v` from `hosted-mcp`.
Synthetic tests cover public catalog preservation, seven explicit OAuth
policies, missing scopes, fixed upstream routing, result preservation, denied
writes, issuer/audience rejection, and incompatible feature flags.

Production acceptance still requires refreshing this existing app's tools,
anonymous public-tool calls, real login and refresh, one approved local read,
denial of parent/credential paths, and retrieval of a pending read. Do not
claim ChatGPT local-file access from the synthetic tests alone.
