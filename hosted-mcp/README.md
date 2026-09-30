# Nymrel hosted MCP

Production source for `https://mcp.nymrel.com/mcp`.

The public server intentionally exposes four credential-free read tools:

- `nymrel_audit_website`
- `nymrel_find_domain`
- `nymrel_golf_bag_gap`
- `nymrel_social_clip_score`

The vendored client contains additional Nymrel API contracts, but the hosted entrypoint removes them from `tools/list` until their provider or authorization boundaries are production-ready.

## Result contracts and audit app

The four public data tools publish explicit success/error output schemas.
Valid upstream payloads retain their original fields and evidence. Missing or
invalid measurements produce `INVALID_RESULT` with `isError: true`; safe
upstream errors also carry the MCP error bit. Text and structured results agree.

`NYMREL_AUDIT_UI_ENABLED=true` adds the fifth anonymous, read-only tool
`nymrel_render_website_audit` and `ui://nymrel/website-audit-v1.html`. This flag is
off by default. First call the audit tool, then pass its successful result and
the requested URL to the renderer. Rendering makes no network request and does
not authenticate the provenance of caller-supplied data. The data tools remain
useful without a UI. The view labels missing measurements as unknown and uses
text nodes for all report content.

The hosted asset is `api/assets/audit-widget.html`; it is independent of the
older TypeScript harness's richer signed-report format. Test the hosted asset
with `node scripts/audit-ui-smoke.mjs` from the repository root after installing
the locked Node dependencies and Playwright Chromium. CI runs this synthetic
host check on Linux/Node 24. It is not a substitute for ChatGPT acceptance.

After deployment, run `scripts/verify_live_contract.py --public-results` to
require the new output schemas. After activating the view in a review
deployment, add `--audit-ui`; that checks the exact catalog, resource metadata,
and a synthetic render. For a deployment with Remote reads active, also supply
`--remote-read --issuer https://nymrel-remote-production.up.railway.app` (the
issuer has no trailing slash). The verifier's default remains compatible with
the earlier live catalog for release comparisons.

Before production UI activation, refresh the ChatGPT tool catalog and run
`evals/workflow-adoption-cases.json`: data-to-view flow, text fallback, mobile,
theme changes, errors, and untrusted page content. Record the deployed commit,
host, timestamp, and evidence. Roll back the view by setting the flag false;
roll back the full contract change by redeploying the preceding release.

Remote reads preserve their backend payloads. A pending result must contain one
unambiguous, non-empty `call.id` or `callId`; malformed pending results fail
closed. `_meta["nymrel/readState"]` supplies the resume tool and forbids
resubmitting the original operation. The plugin skill bounds status checks to
three per turn; the proxy itself makes one backend call and never auto-replays.

See `../docs/chatgpt-workflow-adoption-2026-09-29.md` for source-backed decisions,
validation, and the remaining target-host gates.

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

The pinned FastMCP 3.4.7 integration does not leave the OpenAI-required
top-level `securitySchemes` field to implicit framework behavior. The hosted
list-tools adapter publishes that field explicitly and retains the same value
under `_meta` for older clients.
Contract tests require `noauth` on every public tool and the exact OAuth scope
on each private tool. The adapter also returns a complete
`_meta["mcp/www_authenticate"]` challenge when a private call lacks a valid
token or scope. A target-client OAuth canary remains mandatory before
production activation.

## Verify

The deployable runtime is pinned to Python 3.13. Create a clean environment and
install the reviewed runtime plus test tools:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip==26.2.1
.\.venv\Scripts\python.exe -m pip install -r requirements-test.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m ruff check --config pyproject.toml api tests
.\.venv\Scripts\python.exe -m compileall -q api
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe -m pip_audit --strict --progress-spinner off -r requirements.txt
```

The private adapter's synthetic-only gate is:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_private_handoff.py -q
```

## Deploy

Link this directory to the existing `nymrel-mcp` Vercel project, run the tests,
then deploy from this exact clean commit through the existing protected release
rail. Verify `tools/list` and one successful call per advertised tool after the
production alias is ready. A source, PR, or local-test result is not a
deployment receipt.

Do not deploy the private feature until its separate consent, retention,
AuthKit tenant, tester-subject, dedicated-storage, project-allowlist, and
synthetic production gates are approved. Until then, production proof remains
exactly four public tools.
