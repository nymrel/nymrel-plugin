# Platform connections

The live Streamable HTTP endpoint is `https://mcp.nymrel.com/mcp`. It advertises
four anonymous utilities and seven optional OAuth-protected Remote read tools.
All eleven are read-only; a public connection does not authorize private devices.

## Gemini CLI

This repository contains a `gemini-extension.json` manifest and `GEMINI.md`
guidance. The server uses Gemini's `httpUrl` transport and an `includeTools`
allowlist for the four public tools. Normal host confirmation rules remain in
place. No key or OAuth connection is needed for those utilities.

After this change is merged, install the public source with:

```sh
gemini extensions install https://github.com/nymrel/nymrel-plugin
```

For a local source checkout, use `gemini extensions install <checkout-path>`.
The CLI copies the extension; later source edits require an extension update.
Check `gemini extensions list` and `gemini mcp list` before claiming it is loaded.
This manifest alone does not prove tool discovery or model execution.

For gallery discovery, add the repository topic `gemini-cli-extension` only when
the publisher is ready for indexing. The gallery crawls tagged public repos
daily and validates the root manifest. A topic change is not publication proof.

## Claude Code and VS Code

Claude Code can use the existing remote directly:

```sh
claude mcp add --transport http --scope user nymrel https://mcp.nymrel.com/mcp
claude mcp get nymrel
```

VS Code accepts this remote definition in its MCP configuration:

```json
{
  "servers": {
    "nymrel": {"type": "http", "url": "https://mcp.nymrel.com/mcp"}
  }
}
```

Adding configuration does not establish host trust or grant Remote scopes.
Preserve other configured servers; enable only the tools needed by the task.

## MCP Registry metadata

The [existing registry draft](https://github.com/nymrel/nymrel-plugin/pull/38)
owns `server.json` for `io.github.nymrel/nymrel`. Its metadata must describe both
public and OAuth capabilities and must not request a shared API-key header.
Registry publication requires a publisher login and proof
that the login is an owner of the `nymrel` GitHub organization. Repository admin
access alone does not prove that organization role. Do not claim this draft is
registered, approved, or discoverable in a downstream host gallery.

## Vercel Connect

OAuth discovery succeeds for the MCP endpoint. Vercel's provider draft reported
“Manual registration required” on 2026-09-30. It requires an OAuth client with
redirect `https://connect.vercel.com/callback`, a test connector, a real token
test, and review submission. Public tools remain usable directly via MCP.
Do not put client secrets, tokens, or reviewer credentials in this repository.

## Public directories

OpenAI and Claude directory publication require separate publisher review.
Before submission, confirm policy coverage for actual hosted-tool data flows,
the intended mixed public/OAuth review scope, host-specific test results, and
reviewer access. OpenAI additionally requires a reviewer-accessible demo and
publisher declarations. Prepared archives and connected development clients do
not establish directory publication.

## Official references

- [Gemini extension format](https://github.com/google-gemini/gemini-cli/blob/main/docs/extensions/reference.md)
- [Gemini MCP transport and tool filters](https://github.com/google-gemini/gemini-cli/blob/main/docs/tools/mcp-server.md)
- [Gemini gallery releases](https://github.com/google-gemini/gemini-cli/blob/main/docs/extensions/releasing.md)
- [VS Code MCP configuration](https://code.visualstudio.com/docs/agent-customization/mcp-servers)
- [MCP remote registry metadata](https://github.com/modelcontextprotocol/registry/blob/main/docs/modelcontextprotocol-io/remote-servers.mdx)
- [MCP publisher authentication](https://github.com/modelcontextprotocol/registry/blob/main/docs/modelcontextprotocol-io/authentication.mdx)
- [Vercel provider submissions](https://vercel.com/docs/connect/providers)
- [OpenAI submission requirements](https://developers.openai.com/plugins/deploy/submission)
- [Claude connector submission](https://claude.com/docs/connectors/building/submission)
