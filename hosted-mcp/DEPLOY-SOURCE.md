# This directory is the deploy source for mcp.nymrel.com

Verified 2026-08-18 against the live server. Reconciled 2026-11-08 against
current provider state and the reviewed `main`.

## Current release-route status (2026-11-08)

This section supersedes every older release-route section below.

- The Vercel project is `nymrel-mcp` (`prj_QwLEjytbPHmQiUM2crObafkzosoZ`) in
  `jalens-projects-0ade4450` / `team_MkEJAArMiAM6dAEnF96D5GLE`; the canonical
  alias is `mcp.nymrel.com`.
- The alias currently serves `dpl_5bY3CxAFQwAvHjYuZh2ptcvFUNNB`: READY, target
  `production`, created 2026-10-11T21:44:13Z. Aliases are `mcp.nymrel.com`,
  `nymrel-mcp.vercel.app`, and
  `nymrel-mcp-jalens-projects-0ade4450.vercel.app`.
- Provider deployment metadata reports `githubCommitSha`
  `408a34e7f8f2495c3ce9bf1e30f98fd98de1f420` on `nymrel/nymrel-plugin` `main`
  (merge of PR #48), with `studioSourceManifestSha256`
  `ff9a1b7c4c578df22bec7684f5316988a6959a15d9701cbd6eeac6e446758439` and
  previous deployment `dpl_8wbAQrW9UHNNyZTnf9MWqjsxKkNA`. **`gitSource` and
  `source` are both null**, so Vercel does not attest an immutable build
  source; the commit SHA is provider-reported metadata, not provenance.
- Reviewed `main` at reconciliation is `2069dda7d6c585fa4f77f18d742d805cacef37b6`
  (merge of PR #75). `408a34e` is an ancestor of it
  (`git merge-base --is-ancestor` exits 0), so the provider-reported commit is
  **behind** reviewed `main`; deployed source identity remains unverified.
- `hosted-mcp/` between `408a34e` and `2069dda` differs by 15 files,
  +827/-66: `README.md`, the generated `api/assets/workbench.html`,
  `api/index.py`, `api/nymrel_public_mcp_server.py`,
  `api/nymrel_remote_read.py`, `api/public_results.py`, `api/public_scope.py`,
  the new `api/security_wire.py`, `pyproject.toml`, `requirements*.txt`, and
  four test modules. Whether production contains this delta is unverified.
- The 2026-10-03 rail run produced a PASS receipt for
  `dpl_AZDphk2nkXEUFbmBpkpmRjoHrL53` at source
  `014267c140f8ebdfbcdea5078b4f3e4e27bf3224`: alias promotion PASS,
  provider source-tree attestation `true` by `api-file-content` over 33 files
  (`payloadManifestSha256`
  `5685a7e0a92f8b87ee2e12291909fd9801d4f6ee5b0b8ac669368f016f974e90`),
  `gitSource` null, `lambdaSourceVerified` false, and the live contract PASS.
  An earlier attempt at 09:42 failed pre-stage with
  `ProviderSourceError: matching .vercel project binding is missing or unreadable`.
  Receipts: `portfolio-control/studio-comm/receipts/deployments/nymrel-mcp/`
  (`latest.json`, `20261003T095617746346Z-dpl_AZDphk2nkXEUFbmBpkpmRjoHrL53.json`,
  `prestage/20261003T094210895735Z.json`).
- On 2026-11-08 a fresh read-only live-contract check passed against
  `https://mcp.nymrel.com` with
  `--public-results --remote-read --issuer https://nymrel-remote-production.up.railway.app`:
  four public tools, seven OAuth-protected remote-read tools, exact output
  schemas, OAuth resource/issuer/scopes, and "private read requires caller
  OAuth". This proves the **served contract only**, not source identity.
- The two private-handoff tools remain hidden and are not in the production
  catalog; both Workbench UI feature flags remain off.

**What is attested and what is not.** The alias serves a READY production
deployment whose provider-reported commit is an ancestor of reviewed `main`;
the served contract passes. What is **not** attested is an immutable
provider-to-source binding (`gitSource` is null on both the 2026-10-03 and
2026-10-11 deployments), and whether production contains the reviewed `main`
delta is unverified. Closing that gap requires a clean-checkout run of the
sanctioned rail
(`python portfolio-control/tools/studio-deploy.py nymrel-mcp --yes`) that
records an attested source deployment; do not hand-run `vercel --prod`.

## Historical release-route status (2026-10-01) — superseded above

This section recorded the 2026-10-01 rollback. It is kept for history and is
superseded by the 2026-11-08 section; it does not describe current production.

- The Vercel project is `nymrel-mcp` (`prj_QwLEjytbPHmQiUM2crObafkzosoZ`) in
  `jalens-projects-0ade4450`; its production alias is `mcp.nymrel.com`.
- Immediately before the 2026-10-01 release, production was READY at
  `dpl_86j9zWEggbpQDj7R1tfRvWFVk7FA`, source commit
  `4a70be6e9c6eab8ee160c97061959c851c243588`. PR #40 is merged to `main` at
  `46e71d6e949c9f290a739157f571edc8fb14628e`, and `origin/main` matches.
- The authorized source-only release created
  `dpl_9RvC5DhkdCVjt8VHEb1ByJgRb3PX`; Vercel inspection reports READY, target
  `production`, with `mcp.nymrel.com` among its aliases. Its provider
  `gitSource` is null, so the rail cannot attest the deployed SHA from Vercel.
  The rail's provider-mutation receipt is FAIL and its configured post-deploy
  command is NOT_RUN. The previous production deployment above remains the
  rollback target.
- A separate read-only contract diagnostic against `https://mcp.nymrel.com`
  passed for the four public tools, seven OAuth-protected remote-read tools,
  schemas, auth metadata, and validation cases. This diagnostic does not
  supply immutable provider `gitSource` SHA provenance. Its receipt is in
  `portfolio-control/studio-comm/receipts/deployments/nymrel-mcp/`.
- A later read-only comparison of the temporary deployment's provider `src`
  tree found the same 33 paths as `git ls-files` in the clean Windows checkout
  at `46e71d6`; provider SHA-256 hashes matched those checkout bytes. An
  independent raw Git-blob comparison then found **0/33 exact blob matches**;
  all 33 matched only after applying LF-to-CRLF checkout conversion. This is
  checkout-byte equivalence only, not proof of exact commit blob bytes or
  immutable `gitSource` provenance. The post-hoc line-ending transform is not
  accepted as release proof. See
  `portfolio-control/studio-comm/receipts/deployments/nymrel-mcp/provider-byte-diagnostic-20261001.json`
  and its correction receipt.
- On 2026-10-01 the authorized Vercel rollback restored
  `dpl_86j9zWEggbpQDj7R1tfRvWFVk7FA` as the production target and returned
  `mcp.nymrel.com` to that deployment. A second contract verification after
  rollback passed the same four-public/seven-Remote catalog, schema, read-only,
  and OAuth checks. The rollback result is recorded separately from the failed
  source-only release and its standalone diagnostic.
- A read-only `GET /v9/projects/prj_QwLEjytbPHmQiUM2crObafkzosoZ` returned no
  project `link` (null/absent). Historical production metadata proves the
  project previously received GitHub deployments from `nymrel/nymrel-plugin`,
  but the current project response does not establish a usable provider Git
  binding for an exact-SHA deployment. The CLI offers `vercel git connect` and
  `disconnect`, not a read-only binding command. Do not create or alter a Git
  integration, identity, or OAuth permission as part of this source-only lane.
- The exact-commit preview `dpl_5AcC1uSUgXbyePPfpwiY3XrhdohS` is READY at
  `46e71d6e949c9f290a739157f571edc8fb14628e`, but has no production target or
  production aliases. Preview acceptance does not establish production.
- The current production MCP catalog has four public tools and seven
  OAuth-protected remote-read tools. The remote-read issuer is
  `https://nymrel-remote-production.up.railway.app`; the two Workbench UI
  feature flags remain off. This lane did not change OAuth or either flag.
- The control-plane manifest now has a local `nymrel-mcp` entry binding this
  checkout to the verified project ID and team slug; that control-plane change
  remains local and uncommitted. The sanctioned rail now
  passes `--scope jalens-projects-0ade4450` to deploy and inspection commands;
  its unit tests cover both paths. These edits are not integrated yet.
- The manifest's pre-deploy checks use the CI-pinned `corepack npm@11.19.1`
  for repository verification and Workbench UI smoke tests; its post-deploy
  command checks public output schemas plus the existing remote-read catalog
  and OAuth metadata using the production issuer. UI activation checks are
  omitted because both UI flags remain off. The configured command passed as
  an independent read-only diagnostic after the rail stopped at provider
  source attestation; it did not turn the rail transaction green.

**As of 2026-10-01, the production alias was restored to the previous READY
deployment.** That rollback state is historical; later deployments replaced
it (see the 2026-11-08 section). The source-only CLI deployment for `46e71d6`
was rolled back because Vercel supplied
no immutable provider `gitSource` SHA and the sanctioned rail correctly failed
closed. The separate live diagnostic passed on that temporary deployment; it
does not make the rail transaction green. The current Git binding is not
verified, so an existing provider route to build exact `46e71d6` without a
connection change has not been established. No OAuth, identity, Git
integration, DNS, or UI-flag setting changed; both UI flags remain off.

## Historical public catalog snapshot (2026-08-18)

At this snapshot, `api/index.py` removed five vendored tools and re-registered
two, so the server published **four public tools**:

    nymrel_audit_website · nymrel_golf_bag_gap · nymrel_find_domain · nymrel_social_clip_score

That was exactly what `tools/list` returned in production at the time. The
current production catalog is four public tools plus seven OAuth-protected
remote-read tools, as recorded above.

## Private handoff code is activation-held

`api/nymrel_private_handoff.py` and the generic builder in `api/index.py`
prepare two separate private-handoff tools behind the same `@Nymrel` tag.
Those two tools remain hidden and are not part of the current production
catalog. This does not describe the seven active remote-read tools above. The
legacy `nymrel_submit_studio_brief` tool remains removed and must never be used
as a substitute.

Do not turn on `NYMREL_PRIVATE_HANDOFF_MCP_ENABLED`, configure private-handoff
OAuth, or accept customer content as part of an ordinary MCP deploy. The
private-handoff issuer is separate from the already-active remote-read issuer.
Activation is a
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

## Historical rail invocation (2026-08-17)

The following command and verification recipe records the original rail
adoption. It is superseded by the scoped, exact-SHA route in the current
release-status section above; do not copy this older invocation.

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

## Historical Git-integration behavior (verified 2026-08-18)

The next deployment-history notes describe the state observed on 2026-08-18,
not the current sanctioned release path. The current route is the explicit
scoped rail documented at the top of this file.

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
