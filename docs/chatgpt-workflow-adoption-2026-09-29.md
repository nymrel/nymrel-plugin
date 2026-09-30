# ChatGPT workflow adoption — September 29, 2026

This implementation keeps Nymrel's existing registered app, plugin identity,
MCP endpoint, and OAuth audience. It adds useful contracts to the current
service and stages the hosted audit view for target-host acceptance.

## Decisions and implementation

| Verified guidance | Nymrel implementation | Evidence / limit |
| --- | --- | --- |
| Separate data retrieval and rendering tools; attach the UI resource only to the render tool. [OpenAI MCP server guide](https://developers.openai.com/plugins/build/mcp-server) | Four data tools publish explicit result schemas; a fifth optional tool displays the completed audit without refetching. | Hosted ASGI tests and local HTTP release verifier. |
| Use the MCP Apps bridge and host context, with a useful text path. [OpenAI UI guide](https://developers.openai.com/plugins/build/chatgpt-ui), [MCP Apps](https://modelcontextprotocol.io/extensions/apps/overview) | HTML resource, initialize/result/context notifications, host theme variables, resize messages, evidence disclosure, no external assets or network access. | Playwright synthetic-host test. Real ChatGPT acceptance remains outstanding. |
| Model-facing contracts should expose actionable structure. [MCP server guide](https://developers.openai.com/plugins/build/mcp-server) | Strict success/error validation, preserved payloads, matching text/structured data, explicit `isError`. Malformed upstream payloads never become fabricated measurements. | Positive and negative wire/unit tests across all four data tools. |
| Resume long-running work from durable identifiers. | Reuse existing Remote call IDs and `nymrel_remote_get_read_result`; reject conflicting/missing IDs; bound skill polling; no automatic replay. | Synthetic backend transport tests. This does not introduce a new MCP task implementation or claim authenticated user-file acceptance. |
| Bound parallel work and verify its outputs. [Responses multi-agent guide](https://developers.openai.com/api/docs/guides/responses-multi-agent) | Host-native workflow guidance: one writer per path, bounded delegated work, independent read-only review, parent acceptance. Applied to dependency remediation and review in this change. | No paid Responses multi-agent runtime is enabled, and no model default changes. |
| Browser actions are appropriate when the task requires a UI. [Computer-use guide](https://developers.openai.com/api/docs/guides/agents-api/tools/computer-use) | Prefer existing MCP reads; use browser verification for the actual app boundary. | Browser test executes the shipped hosted HTML. No general browsing agent was added. |

The release review also identified newer model and speed options, including
[GPT-6.1 Sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol) and
[ultrafast mode](https://developers.openai.com/api/docs/guides/ultrafast-mode).
These remain benchmark candidates: documentation does not prove this account's
entitlement, cost, or benefit on Nymrel's workloads. Do not infer access from a
model name, add an API credential, or switch defaults as part of plugin setup.
The dated release source is the [OpenAI plugin changelog](https://developers.openai.com/plugins/changelog);
these architecture guides are current guidance, not claims that every concept
was released on September 29.

## Scope and release controls

- Default public catalog stays at four tools. The audit app activates only
  with `NYMREL_AUDIT_UI_ENABLED=true`; disable it to roll back the view.
- The renderer validates structure but does not sign or authenticate the
  caller-supplied report. It says so and never treats the requested URL as a
  verified final URL. It does not invent HTTP status, response timings, passed
  checks, or issue counts when the upstream omits them.
- Remote OAuth, scopes, audience, and account connection remain unchanged.
  Remote output payloads are not assigned speculative schemas without evidence
  from the authenticated backend's actual success variants.
- Compatible lockfile-only patches resolve Hono, ip-address, and Undici
  advisories. Direct dependency pins and framework major versions are unchanged.
- No deployment, directory submission, paid API activation, or real-user
  authenticated canary is implied by local success.

## Validation and release checklist

Run the repository's complete CONTRIBUTING gate, plus
`node scripts/audit-ui-smoke.mjs`. The hosted tests cover the activated and
disabled app, strict result types, evidence preservation, safe errors, and
unambiguous resume IDs. CI also runs the browser test on Linux/Node 24.

The live verifier can compare the prior production release with the new
candidate: `--public-results` requires the new schemas, and `--audit-ui`
requires the additional tool/resource. Both flags compose with `--remote-read`
and the exact issuer. This avoids describing an unshipped view as live.

Before UI activation, record a successful ChatGPT Developer Mode run using the
prompts in `evals/workflow-adoption-cases.json`. Confirm useful text fallback,
mobile sizing, host themes, evidence integrity, and pending-read continuation.
Conversational eval cases are review prompts; passing the deterministic tests
does not prove that every model follows them. Directory publication remains a
separate external outcome.
