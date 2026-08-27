# This directory is the deploy source for mcp.nymrel.com

Verified 2026-08-18 against the live server.

`api/index.py` here removes five vendored tools and re-registers two, so the
server publishes **four** tools:

    nymrel_audit_website · nymrel_golf_bag_gap · nymrel_find_domain · nymrel_social_clip_score

That is exactly what `tools/list` returns in production.

## Private handoff code is activation-held

`api/nymrel_private_handoff.py` and the generic builder in `api/index.py`
prepare two OAuth-gated tools behind the same `@Nymrel` tag. They are hidden by
default and are not part of the current ChatGPT submission, review cases, or
production contract. The legacy `nymrel_submit_studio_brief` tool remains
removed and must never be used as a substitute.

Do not turn on `NYMREL_PRIVATE_HANDOFF_MCP_ENABLED`, configure an OAuth issuer,
or accept customer content as part of an ordinary MCP deploy. Activation is a
separate protected release requiring approved client consent and project
allowlists, retention/custody approval, a Nymrel-owned AuthKit environment,
dedicated Nymrel REST secrets and storage, exact provider-subject-to-principal
mapping, and synthetic production proof. The feature flag without
`NYMREL_PRIVATE_HANDOFF_OAUTH_ISSUER` now fails the deployment at import.

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

## What actually deploys this: a push to `main` (verified 2026-08-18)

The Vercel project has the GitHub integration wired (`githubDeployment: 1`,
`gitRootDirectory: hosted-mcp`). Pushing `main` to `nymrel/nymrel-plugin` is
what builds and promotes to production - every READY deployment in the history
came from a push, none from the CLI. Production is
`dpl_5DPVFTkjiehAGfSCjdu1CSKVidps` at `63dba83`.

**A push does not always produce a build.** `51f5a67` changed only this
markdown file and produced no deployment record at all - not BLOCKED, absent.
Runtime changes under `hosted-mcp/` build; a docs-only push may be skipped. So
"I pushed" is not "it deployed" in either direction, and the deployment record
is the only thing that settles it.

`npx vercel --prod` from here answers **`Error: Not authorized`** — the CLI has
no usable token in this environment — **and still exits 0.** Two background
deploys reported success while having deployed nothing. Never grade a deploy on
that exit code; grade it on the live server or the deployment record.

## The brand identity that ships is not the one doctrine asks for

Of the last six commits, the two authored `Nymrel <contact@nymrel.com>` were
**BLOCKED** by Vercel. The four authored `JalenTrades <johnsonjjalen@gmail.com>`
all reached READY.

| Commit | Author | Deploy |
|---|---|---|
| `63dba83` | JalenTrades | READY |
| `b824cfa` | **Nymrel** | **BLOCKED** |
| `7b11a6a` | JalenTrades | READY |
| `62a2514` | JalenTrades | READY |
| `2883bd2` | JalenTrades | READY |
| `cc94a1a` | **Nymrel** | **BLOCKED** |

Vercel refuses a deployment whose git author is not a team member, and
`contact@nymrel.com` is not one. `johnsonjjalen@gmail.com` is the account.

This collides with the studio brand rule, which names commit author identity as
a Nymrel-only position. Following that rule **in this repo** produces a deploy
that never happens: the push succeeds, git reports nothing wrong, and the change
silently does not go live. Neither blocked commit cost us anything here — a
later READY deploy at a descendant commit carried their content — but that was
luck, not design.

Until an operator adds `contact@nymrel.com` to the Vercel team (an account
change, not an agent action), **leave the author identity alone in this repo.**
There is no repo-local `user.name`/`user.email` override; the global identity is
`JalenTrades`, which deploys. Do not set a local one to satisfy the brand gate.

After any push here, confirm the deploy reached READY. A BLOCKED deploy is the
one failure mode that looks exactly like success from the terminal.
