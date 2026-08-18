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

## How to release (2026-08-17: this surface is on the studio rail now)

The project link lives in this directory, but do not run `vercel --prod` by
hand — this connector has a manifest entry (`nymrel-mcp` in
`portfolio-control/config/studio-deploy-manifest.json`) and releases through
the front door like every other production surface:

    python portfolio-control/tools/studio-deploy.py nymrel-mcp --yes

The rail enforces clean tree, on-`main`, HEAD-pushed, and descent from live
production before deploying. Its post-deploy `GET /` verify may report a 405
FAIL in the first seconds after the deploy — that is alias propagation lag,
not a bad deploy; re-probe before rolling back.

Then prove the served contract, not just the routes:

    python hosted-mcp/scripts/verify_live_contract.py

This asserts on the LIVE server: exactly four tools, no opaque input schema,
title + readOnlyHint on every tool, and the golf round-trip (documented shape
accepted; a wrong key rejected naming the field). It exists because the local
suite passed while production published a degraded schema (2026-08-17): the
hosted runtime flattened a `typing.TypedDict` to a bare object, and the
platform rewrite hid the discovery route. Local tests cannot see runtime skew;
only a probe of served bytes can.
