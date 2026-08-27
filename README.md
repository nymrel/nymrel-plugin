# Nymrel universal plugin

One package for the live Nymrel ChatGPT app, Codex plugin, Claude plugin, and hosted MCP service.

## Live bindings

- ChatGPT app: the `.app.json` file binds the installed plugin to the registered Nymrel app.
- Codex plugin: the `.codex-plugin/plugin.json` manifest discovers the skill, app, and remote MCP configuration.
- Claude plugin: the `.claude-plugin/plugin.json` manifest discovers the same skill and remote MCP configuration.
- MCP: every host connects to `https://mcp.nymrel.com/mcp` through the root `.mcp.json` file.

The hosted service is the source of truth for production tools. The TypeScript server in this folder remains a local development harness for the polished Website Audit widget; it is not the production MCP endpoint.

## Product boundary

- Audits one public HTTP(S) page plus conventional discovery files on the same origin.
- Performs read-only technical checks. It does not log in, crawl private pages, change the target site, or claim legal/compliance certification.
- Blocks local, private, link-local, reserved, credential-bearing, and non-web targets before fetching.
- Returns useful structured data and text even when the host does not render the widget.

## Local widget development

```powershell
$env:npm_config_cache = "$PWD\.npm-cache"
npm.cmd install
npm.cmd run verify
npm.cmd start
```

The HTTP MCP endpoint is `http://127.0.0.1:8787/mcp`. A standalone widget preview is available at `http://127.0.0.1:8787/preview`.

For stdio-only development hosts, build first and launch `node dist/server.js --stdio` directly. The packaged `.mcp.json` intentionally points at the live HTTPS endpoint.

## Production tools

- `nymrel_audit_website`
- `nymrel_find_domain`
- `nymrel_golf_bag_gap`
- `nymrel_social_clip_score`

All four tools are live, credential-free, read-only, and backed by the production Nymrel API. Trade evaluation, permit lookup, and studio intake remain outside the public catalog until their provider or authorization contracts are production-ready.

The hosted source now includes a dormant private-handoff adapter for future
approved clients. It keeps `@Nymrel` as the invocation surface while requiring
per-client OAuth and server-side project allowlists for submit/status calls.
It is disabled, has no selected production auth provider, and is not evidence
that Nymrel can receive real client content through the app today. See
`hosted-mcp/README.md` for the activation boundary.

The deployable source for `https://mcp.nymrel.com/mcp` lives in `hosted-mcp/`. The broader vendored API contracts stay private to that deployment package; `hosted-mcp/api/index.py` explicitly publishes only the four production-ready tools.

## Validation levels

- Static contract: plugin manifest, exact tool metadata, MCP Apps resource metadata, and eight review evals.
- Compile/unit: `npm run check` and `npm test`.
- Runtime: `npm run build && npm run test:mcp` starts the real HTTP server, connects an MCP client, and verifies tool/resource discovery.
- Live public fetch: `npm run test:live` audits `https://example.com`; use only when outbound network proof is wanted.
- Host: connect the deployed HTTPS `/mcp` endpoint in ChatGPT Developer Mode, invoke `@Nymrel`, and run the prompts in `evals/review-cases.json` (six positive, four negative, one per published tool).

## Publication boundary

Local installation and the private ChatGPT/Claude connections do not prove public directory publication. OpenAI and Anthropic review their own listings independently.
