# Nymrel universal plugin submission packet

## Listing

- Name: Nymrel
- Publisher: Nymrel
- Category: Productivity
- One-line value: Bring an idea, website, or client need to Nymrel without leaving ChatGPT or Codex.
- MCP endpoint: `https://mcp.nymrel.com/mcp`
- Authentication: none for the four public tools or the bundled skills.

## Release notes

Version 1.3.0 adds the `nymrel-studio` skill for client discovery, service
matching, and build-brief preparation; updates the listing around direct
`@Nymrel` use in ChatGPT and Codex; and leaves the reviewed four-tool MCP
contract and authentication boundary unchanged.

## Supported installed-plugin workflows

- Turn an idea or existing problem into a Nymrel-ready build brief.
- Match the user to a Nymrel service without claiming a booking or sale.
- Audit one public page, find domain candidates, analyze golf-club gaps, or
  measure short-video hook signals through the production MCP endpoint.

The first two workflows are skill-guided and do not transmit the brief. The
four MCP tools are anonymous and read-only. Authenticated client handoff remains
activation-held and is not part of this public submission.

## Review claims

- Read-only and non-mutating: tools fetch public data or calculate from caller-supplied inputs without changing public or third-party state.
- External reach is explicit: website and domain discovery interact with dynamic public resources; golf-gap and clip-signal calculations stay within a closed service domain.
- No private data: no account, login, cookie, file upload, contact field, or persistent user profile is accepted.
- No commerce: the plugin does not initiate checkout, subscriptions, upgrades, or payment.
- Bounded output: one page, three same-origin discovery probes, one report, and no background monitoring.

## Starter prompts

1. Turn my idea into a Nymrel-ready build brief.
2. Audit my website and prioritize the fixes.
3. Help me choose the right Nymrel service.

## Test cases

The provider import file `chatgpt-app-submission.json` contains exactly five
positive and three negative cases. The broader regression set remains in
`evals/review-cases.json`; every expectation records the live response it was
checked against, and `hosted-mcp/tests/test_review_cases.py` fails the build if
a case names a tool this server does not publish.

## Current provider state

- The hosted MCP endpoint is live and lists four credential-free read tools.
- The Nymrel custom app is connected in the operator's ChatGPT account, and
  direct `@Nymrel` invocation works there.
- The same MCP endpoint is connected in the operator's Claude Code user scope.
- Website Audit, domain suggestions, golf bag gaps, and social clip scoring return production results.
- Trade evaluation, permit lookup, and studio intake are intentionally not advertised until their provider or authorization contracts are production-ready.

## External gates before public directory submission

- Verify Nymrel publisher identity and Apps Management write access in the OpenAI Platform.
- Support URL is live at https://nymrel.com/support (added 2026-08-18).
- Refresh the registered Nymrel app before the provider scan. The installed
  ChatGPT snapshot still exposes seven tools, while the live MCP endpoint lists
  the reviewed four-tool public contract.
- Add the production MCP URL, complete the domain-verification challenge, and
  run a fresh tool scan in the OpenAI submission portal.
- Review every imported schema, security scheme, annotation, and justification.
- Upload or import both bundled skills and verify the three starter prompts.
- Provide a public demo-recording URL, exactly five positive cases, exactly
  three negative cases, release notes, country availability, and policy
  attestations.
- Submit and publish through OpenAI after approval. Submit separately to
  Anthropic; local installation is not directory approval.
