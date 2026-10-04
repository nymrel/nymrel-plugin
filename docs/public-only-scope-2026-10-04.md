# Public-only diagnostic route

The existing hosted service exposes an additional `/public/mcp` endpoint with an
independent FastMCP registry containing exactly these four read-only utilities:

- `nymrel_audit_website`
- `nymrel_find_domain`
- `nymrel_golf_bag_gap`
- `nymrel_social_clip_score`

The original `/mcp` registry, optional OAuth/device operations, app bindings,
plugin identity and compatibility manifests are unchanged. This source change
creates no registered App, account, OAuth grant, credential or production setting.
The existing catch-all rewrite covers the additional path.

This is a serving boundary: private tools/providers, prompts and resources are
not copied. Calls to excluded names fail even with a valid developer token.
Incoming authorization and cookies do not reach the anonymous public MCP app.
The route rejects ambiguous rewrite markers and request bodies above 1 MiB.

The public audit retains validated diagnostic fields and errors, but removes
`full_report_url` from text, structured output and schema. Its existing destination
offers paid digital services. This scope supplies diagnostics in the conversation
without digital-service upgrades, subscriptions, checkout or sales handoffs.
The developer route keeps its current response contract.

Public tools preserve their input schemas and read-only/destructive/open-world
annotations. The public route has its own lazy, per-event-loop HTTP lifecycle;
optional developer UI metadata is omitted because no UI resources are inherited.

## Verification and release

`hosted-mcp/tests/test_public_scope.py` covers direct/rewrite paths, valid/invalid/
absent tokens, all excluded private names, original authenticated synthetic device
operation, public schemas/results, errors/retry information and request bounds.
The full hosted test suite and lint remain the normal repository gates.

Source integration does not prove deployment or public directory availability.
After the existing source release process deploys this change, verify exactly
four tools at `https://mcp.nymrel.com/public/mcp`, reject forged excluded calls,
and confirm the original catalog/auth behavior. Do not redirect the developer
plugin's current `/mcp` binding to this route.

The public upload candidate remains separate review material until live endpoint
verification, existing publisher/App identity, countries, accurate commerce/policy
declarations, actual recorded demo and saved-version host review are complete.
No legal/policy attestation or public marketplace submission is included here.

Rollback: revert this source change through the ordinary reviewed source process;
the original registry, manifests and OAuth configuration require no restoration.
