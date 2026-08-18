# This directory is the deploy source for mcp.nymrel.com

Verified 2026-08-18 against the live server.

`api/index.py` here removes five vendored tools and re-registers two, so the
server publishes **four** tools:

    nymrel_audit_website · nymrel_golf_bag_gap · nymrel_find_domain · nymrel_social_clip_score

That is exactly what `tools/list` returns in production.

## Do not deploy from `Desktop/mcp-connector-lane`

That directory held the Vercel project link and still carries an older
`api/index.py` that re-registers **all seven** tools. Deploying it would put
three tools back on the public connector that cannot serve a request:

| Tool | What the upstream actually answers |
|---|---|
| `nymrel_evaluate_fantasy_trade` | `503 NOT_CONFIGURED` - no player value source |
| `nymrel_local_permit_lookup` | `503 NOT_CONFIGURED` - no permit directory |
| `nymrel_submit_studio_brief` | write tool, needs a caller bearer token |

Its `proof-tools-list.json` is a receipt from when the server did publish seven
— it is history, not the current contract.

The project link now lives here as well, so `vercel --prod` from this directory
is the correct release. Confirm afterwards that `tools/list` still returns four.
