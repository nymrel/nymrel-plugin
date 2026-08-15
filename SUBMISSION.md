# ChatGPT plugin submission packet

## Listing

- Name: Nymrel
- Publisher: Nymrel
- Category: Productivity
- One-line value: See what helps or hurts a public webpage, then get a prioritized fix plan.
- MCP endpoint: `https://mcp.nymrel.com/mcp`
- Authentication: none for the free public audit v1.

## Review claims

- Read-only and open-world: the server fetches the public URL and conventional files on the same public origin.
- No private data: no account, login, cookie, file upload, contact field, or persistent user profile is accepted.
- No commerce: the plugin does not initiate checkout, subscriptions, upgrades, or payment.
- Bounded output: one page, three same-origin discovery probes, one report, and no background monitoring.

## Starter prompts

1. Audit my website and explain the top fixes.
2. Check this public page for AI readability.
3. Return a developer-friendly website audit.

## Test cases

The five positive and three negative cases required for review are in `evals/review-cases.json`.

## Current provider state

- The hosted MCP endpoint is live and lists four credential-free read tools.
- The Nymrel custom app is connected in the operator's ChatGPT account.
- The same MCP endpoint is connected in the operator's Claude Code user scope.
- Website Audit, domain suggestions, golf bag gaps, and social clip scoring return production results.
- Trade evaluation, permit lookup, and studio intake are intentionally not advertised until their provider or authorization contracts are production-ready.

## External gates before public directory submission

- Verify Nymrel publisher identity and Apps Management write access in the OpenAI Platform.
- Add a live public support URL; `/support` currently does not exist.
- Run the provider's tool scan, review imported annotations, execute all eight cases, and record same-version receipts.
- Submit separately to OpenAI and Anthropic. Local installation is not directory approval.
