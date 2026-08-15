# QA inventory

## User-visible claims and checks

| Claim or control | Functional check | Visual state | Evidence target |
| --- | --- | --- | --- |
| A public page produces a real technical report | Unit fixture plus optional live `example.com` call | Populated report | Test output and desktop screenshot |
| The top three fixes are obvious to a non-developer | Verify priority order and plain-language copy | Initial populated report | 390px and desktop screenshots |
| Developers receive stable structured data | MCP tool has explicit input/output schemas and digest | MCP tool result | MCP smoke output |
| Private/reserved targets are blocked before fetch | Unit and MCP calls against loopback | Error response, no widget | Test output |
| All / Needs work / Passed filters work | Click each filter and count visible findings | Each filter state | Browser assertions/screenshots |
| Finding evidence expands in place | Click one failed finding | Expanded finding | Browser assertion/screenshot |
| Follow-up action remains clear | Click in standalone preview | Local explanatory status | Browser assertion |
| Mobile layout works at 375/390px | Inspect initial and dense states; assert no x-overflow | Mobile populated report | Mobile screenshot and bounds |

## Exploratory cases

- Long page titles and URLs should wrap or truncate without horizontal overflow.
- A perfect report with no priorities should show the calm no-urgent-fixes state.
- A filter with no matching checks should show an explicit empty state.
- Reduced-motion mode should remain legible and fully interactive.

## Acceptance run — 2026-08-14

- `npm run verify`: passed.
- Plugin package validator: passed.
- Live public audit of `https://example.com`: passed with a real bounded fetch and structured report.
- MCP client smoke: discovered both tools and the UI resource; private-target rejection passed.
- Desktop `1440x1000`: no console/page errors, no horizontal overflow, all filters passed, failed finding disclosure exposed observed and recommended text, and standalone follow-up status passed.
- Mobile `390x844` and `375x812`: no console/page errors or horizontal overflow, score and first priority visible in the initial viewport, and minimum interactive target height was 44px.
- Browser contexts and the headless browser were closed after acceptance.

## Hosted integration status

- The permanent production endpoint is `https://mcp.nymrel.com/mcp`; no development tunnel is used.
- The operator's ChatGPT account connected the Nymrel app and discovered the original seven-tool catalog on 2026-08-14. Version 1.2.0 narrows the public catalog to four tools with passing production calls; hosts must refresh the app after deployment.
- Codex and Claude Code both have the Nymrel plugin installed from the repo-local marketplaces.
- This proves private/operator-host activation, not public directory approval. Refresh the ChatGPT app and rerun the eight review cases after any production tool metadata or behavior change.
