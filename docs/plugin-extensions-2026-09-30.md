# Public plugin extensions — September 30, 2026

The tool workbench lets users run each of Nymrel's four public tools from a
single view opened through navigation or inside a thread. It extends the
existing PR 37 source at `85cc3dd`; it preserves the plugin, registered app,
MCP endpoint, public data contracts, and OAuth boundaries.

The source package is version 1.4.0 with portable Agent Plugins 1.0
`plugin.json`/`mcp.json` and synchronized Codex/Claude compatibility versions.
The existing app binding and all three starter prompts are preserved. This is
a source release candidate; public directory approval is a separate outcome.

## Implemented experience

`nymrel_open_tools` accepts `{}` and returns the public catalog without an
external call. The resource `ui://nymrel/tools-v1.html` consumes that launch
result. The four forms invoke the existing website, domain, golf, and clip
tools through the MCP Apps host bridge only after submission. Results preserve
their evidence and error state, with a separate user action to add a result
to conversation context. Untrusted result strings are rendered as text.

The app supports fullscreen only, uses host theme/context updates, and asks
once for fullscreen if a host starts inline and advertises that mode. A host
may decline that request. Deep links select `/website`, `/domains`, `/golf`,
or `/clip`; selecting a view does not run a tool or discard form input.

Browser preferences contain only display choices. Inputs and results are not
stored. These preferences are distinct from native plugin-details settings:
the anonymous public service has no per-user settings storage contract.

## Source and SDK evidence

- Server: existing Python/FastMCP 3.4.7; real wire tests cover the extension
  descriptors, independently gated resources, empty launch, and public results.
- Browser: locked `@modelcontextprotocol/ext-apps` 1.7.5 `App` bridge; bundled
  through the existing locked esbuild dependency into a self-contained asset.
  No external browser assets or network domains are allowed by resource CSP.
  Full license notices for the actual bundled package inputs are embedded in
  the resource; builds fail when a dependency has no usable notice.
- Extension metadata follows the [official specification at source commit
  e314720](https://github.com/openai/mcp-extensions/blob/e314720a0daac326217d1f123fcf51647868fa9f/docs/spec.md):
  tool `openai/ui.entrypoints`; resource `openai/ui.preferredDisplayMode` and
  `availableDisplayModes`. FastMCP preserves those fields on the real MCP wire.

## Plugin family boundaries

| Existing component | This batch | Remaining proof or source boundary |
| --- | --- | --- |
| Public website/domain/golf/clip tools | Shared workbench, global/thread entrypoints, deep links, in-app preferences, explicit result context | Actual target-host rendering and release activation |
| Completed website audit view | Explicit fullscreen metadata and one bounded placement request | Actual host placement |
| Nymrel Remote | Reuse existing separate OAuth-protected read tools unchanged | An interactive file surface needs host-granted resource access and authenticated owner binding; a local path is not a grant |
| Nymrel Publisher | Preserve the existing source and content-version approval invariant | Current Publisher source implements history reads; the private service and OAuth integration need deployment/configuration proof before connection activation |
| Private studio companions | Separate owned releases connect the existing hosted MCP service and preserve original skills/prompts | Account-package saving and fresh-conversation activation are distinct; cached files are not an owning editable source |

No anonymous workbench button dispatches Remote, private handoff, or Publisher
actions. No native file handler or account settings capability is advertised
by this batch without its supporting resource/identity contract.

Website forms and the hosted audit entrypoint reject embedded URL credentials
before forwarding a request. The form explains that submitting sends its
inputs to Nymrel. Only benign display preferences are persisted in the browser.

## Activation and acceptance

`NYMREL_TOOLS_UI_ENABLED` is off by default and is independent of
`NYMREL_AUDIT_UI_ENABLED`. Both apps can be inspected on a local/review server;
default catalog behavior remains covered by the existing tests. Production
activation, directory publication, and authenticated file acceptance are
separate outcomes.

Run `npm run verify`, `npm run test:ui`, and the complete hosted Python gate
in CONTRIBUTING. `npm run verify:ui` checks source/asset reproducibility.
Playwright uses the shipped HTML with an isolated synthetic MCP host. Those
tests prove local browser behavior, not a ChatGPT or mobile-client entitlement.

For an enabled review deployment use
`hosted-mcp/scripts/verify_live_contract.py <base> --tools-ui --audit-ui`;
include `--remote-read --issuer <exact-issuer>` only when that existing feature
is enabled. Disable either flag independently to hide and deny that view.

Before enabling the workbench in production, record the exact deployed commit,
host, timestamp, and observed results for this matrix:

1. Open from global navigation and from a thread; verify placement and no call
   on launch. Open each supported deep link.
2. Submit a public URL, a domain concept with dotted TLDs, measured golf clubs,
   and a transcript. Check form payloads and result evidence against the data
   tools, including registry uncertainty and measured-text scope.
3. Exercise loading, a failed call, unsupported host capabilities, narrow
   sizing, keyboard labels, and theme changes. Preserve edited form input.
4. Share one result through the explicit conversation-context action; verify
   no chat message or external send is triggered automatically.
5. Verify rollback hides the opener/resource and denies direct calls while
   the four existing public data tools still work.
