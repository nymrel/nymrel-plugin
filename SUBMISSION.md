# ChatGPT plugin submission packet

## Listing

- Name: Nymrel
- Publisher: Nymrel
- Category: Productivity
- One-line value: See what helps or hurts a public webpage, then get a prioritized fix plan.
- MCP endpoint: `https://mcp.nymrel.com/mcp`
- Authentication: none for the free public audit v1.

## Review claims

- Read-only and non-mutating: tools fetch public data or calculate from caller-supplied inputs without changing public or third-party state.
- External reach is explicit: website and domain discovery interact with dynamic public resources; golf-gap and clip-signal calculations stay within a closed service domain.
- No private data: no account, login, cookie, file upload, contact field, or persistent user profile is accepted.
- No commerce: the plugin does not initiate checkout, subscriptions, upgrades, or payment.
- Bounded output: one page, three same-origin discovery probes, one report, and no background monitoring.

## Starter prompts

1. Audit my website and explain the top fixes.
2. Check this public page for AI readability.
3. Return a developer-friendly website audit.

## Test cases

The provider import file `chatgpt-app-submission.json` contains exactly five
positive and three negative cases. The broader regression set remains in
`evals/review-cases.json`; every expectation records the live response it was
checked against, and `hosted-mcp/tests/test_review_cases.py` fails the build if
a case names a tool this server does not publish.

## Current provider state

- The hosted MCP endpoint is live and lists four credential-free read tools.
- The Nymrel custom app is connected in the operator's ChatGPT account.
- The same MCP endpoint is connected in the operator's Claude Code user scope.
- Website Audit, domain suggestions, golf bag gaps, and social clip scoring return production results.
- Trade evaluation, permit lookup, and studio intake are intentionally not advertised until their provider or authorization contracts are production-ready.

## External gates before public directory submission

- Verify Nymrel publisher identity and Apps Management write access in the OpenAI Platform.
- Support URL is live at https://nymrel.com/support (added 2026-08-18).
- Run the provider's tool scan, review imported annotations, execute all ten cases, and record same-version receipts.
- Submit separately to OpenAI and Anthropic. Local installation is not directory approval.
