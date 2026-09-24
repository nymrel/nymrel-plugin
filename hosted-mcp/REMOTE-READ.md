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

### Bounded CLI acceptance probe

After the issuer, backend profile, subject mapping, and gateway activation are
configured, `scripts/accept_remote_file_read.py` can check the exact published
issuer/resource metadata, exactly one named `ChatGPTStudio` device, one
user-approved file path with its expected SHA-256, and one parent or credential
path. It asks for a short-lived access token through hidden terminal input.
The entire visible `list_devices` result must contain exactly one device, named
`ChatGPTStudio`, with a nonempty immutable device ID; any additional visible
device (including a broad workstation such as `JalenPC`) stops the probe. This
is an exclusive tenant visibility check for the isolated ChatGPTStudio device.
The token is sent only as the bearer header to the fixed MCP endpoint; it is
not accepted as a command-line argument, written to disk, or printed. The
probe requires an interactive terminal and aborts if hidden-input handling
would fall back to echoing input. It reports only pass/fail labels and
suppresses paths, response details,
and file contents. It refuses authenticated calls unless the exact issuer
(including a trailing slash when published) and resource metadata match.
Completed reads must return the exact structured path and content matching the
provided SHA-256. Pending reads are retrieved by call ID without resubmitting
the original read; a still-pending result is reported as not validated. A path
denial counts only when the structured result names that exact path and its
reason is the exact outside-allowed-directory error code or an anchored
boundary-denial message.

Example (choose paths appropriate to the paired device and keep the approved
file limited to content the user has authorized):

```powershell
python hosted-mcp/scripts/accept_remote_file_read.py `
  --issuer 'https://your-exact-issuer/' `
  --device-name 'ChatGPTStudio' `
  --approved-path 'C:\Users\you\ChatGPTStudio\reports\automation\chatgptstudio-share-20260922\INDEX.md' `
  --expected-sha256 '<sha256-of-approved-file>' `
  --denied-path 'C:\Users\you\ChatGPTStudio\reports\automation\credentials'
```

From `hosted-mcp/`, run the fixture-only tests with
`python -m unittest tests.test_remote_file_acceptance -v`.
This CLI checks a bounded HTTP/MCP result contract only. It is not a substitute
for a regular ChatGPT conversation: after the CLI passes, refresh the existing
app connection and perform the approved read and denied-path check in ChatGPT
itself before claiming host acceptance. A CLI or fixture result cannot prove
that ChatGPT offered OAuth or completed the read in conversation.

After activation, run `python hosted-mcp/scripts/verify_live_contract.py
--remote-read --issuer <exact-published-issuer>` from the repository root.
This checks the served eleven-tool catalog, per-tool OAuth policies, exact
resource metadata and the unauthenticated private-tool challenge without
transmitting a credential. The default invocation remains the four-tool
pre-activation check. A passing public check still does not replace the
authenticated ChatGPT conversation test.
