"""Public hosted entrypoint for the Nymrel MCP connector.

The public catalog exposes only tools that return useful production results
without private credentials or an unconfigured provider. The vendored module
keeps the broader HTTP contracts available for future releases, while this
entrypoint publishes the four currently operational read tools.

The ASGI wrapper also supplies a lazy lifespan shim because serverless adapters
do not reliably emit lifespan events for FastMCP's streamable-HTTP manager.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import weakref
from typing import Any
from urllib.parse import parse_qs, parse_qsl, urlencode

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from typing import Annotated  # noqa: E402

from pydantic import Field  # noqa: E402
from mcp.types import ListToolsRequest  # noqa: E402

import nymrel_public_mcp_server as server  # noqa: E402
import nymrel_private_handoff as private_handoff  # noqa: E402

from starlette.applications import Starlette  # noqa: E402


MCP_PATH = "/mcp"

# Vercel routes a rewritten request to the function under its own path; accept
# every alias the platform may present so the endpoint is path-stable.
PATH_ALIASES = frozenset({"/mcp", "/api/index", "/api/index/mcp", "/api/mcp", "/api"})

# Paths that ARE the MCP endpoint once the original path is known. /server and
# /sse are public URLs - printed on nymrel.com/mcp and used by connector setup
# docs - that only ever worked because the rewrite hid the path. Once the
# rewrite forwards it (vercel.json: destination /api/index?__path=/$1), they
# must be named here or this fix would break every published setup snippet.
MCP_PATHS = PATH_ALIASES | frozenset({"/server", "/sse"})

MAX_BODY_BYTES = 1_048_576
PUBLIC_TOOL_NAMES = (
    "nymrel_audit_website",
    "nymrel_find_domain",
    "nymrel_golf_bag_gap",
    "nymrel_social_clip_score",
)

#: A TLD as the upstream actually accepts it: leading dot, 2-24 letters.
#: The published schema said only "array of string" until 2026-08-18, so a model
#: holding the schema would send ["com"] and get INVALID_REQUEST with nothing to
#: tell it why. The pattern is the upstream's own regex, so the advertised
#: contract and the enforced one are the same contract.
Tld = Annotated[str, Field(pattern=r"^\.[a-z]{2,24}$", examples=[".com", ".ai", ".app", ".dev"])]

_provider = getattr(server.mcp, "local_provider", server.mcp)


# Hide contracts that are not ready for a public no-auth catalog, and replace
# two over-broad descriptions with wording that matches the live implementation.

_provider.remove_tool("nymrel_evaluate_fantasy_trade")
_provider.remove_tool("nymrel_social_clip_score")
_provider.remove_tool("nymrel_local_permit_lookup")
_provider.remove_tool("nymrel_find_domain")
_provider.remove_tool("nymrel_submit_studio_brief")


@server.mcp.tool(
    name="nymrel_find_domain",
    annotations={
        "title": "Find domain names",
        "readOnlyHint": True,
        "openWorldHint": True,
        "destructiveHint": False,
    },
)
def nymrel_find_domain(
    keyword_or_concept: str,
    tlds: Annotated[
        list[Tld] | None,
        Field(
            default=None,
            max_length=6,
            description=(
                'Up to 6 TLDs, each written with its leading dot - ".com", not "com". '
                "The upstream enforces this with a regex and rejects the request "
                "otherwise. Defaults to .com, .ai, .app and .dev."
            ),
        ),
    ] = None,
) -> dict[str, Any]:
    """Suggest domain names and check each one against public registry records.

    A name is only reported available when the registry clearly says it is free.
    When the lookup is inconclusive `availability_checked` is false and
    `available` is false, so read that as "not confirmed free" rather than
    "already taken" - some TLDs have no registry service to ask. Confirm at a
    registrar before buying.

    `brandability_score` is an opinion about the string, not a claim about how
    the name will perform; `brandability_factors` reports what it was computed
    from so you can weigh it yourself.
    """
    payload: dict[str, Any] = {"keyword_or_concept": keyword_or_concept}
    if tlds is not None:
        payload["tlds"] = tlds
    return server._call_tool("find-domain", payload)


@server.mcp.tool(
    name="nymrel_social_clip_score",
    annotations={
        "title": "Measure a short-video hook",
        "readOnlyHint": True,
        "openWorldHint": False,
        "destructiveHint": False,
    },
)
def nymrel_social_clip_score(transcript_text: str, target_platform: str = "tiktok") -> dict[str, Any]:
    """Measure what the opening of a short-video transcript actually does.

    Returns each measured signal - opening word count, whether it opens on a
    hook pattern, whether it addresses the viewer, curiosity signals, whether
    the total word count sits in the platform's range - plus `hook_score`, a
    0-100 rollup of exactly those signals, and suggested edits.

    Every figure describes the text the caller supplied. This does not estimate
    reach, views, retention or virality; those are outcomes in the world that
    this tool never observes. Read `signals` to see what moved the score.
    """
    return server._call_tool(
        "social-clip-score",
        {"transcript_text": transcript_text, "target_platform": target_platform},
    )


# These tools are present in the hosted registry but feature-hidden unless the
# private flag is explicit. Their handlers still require a provider-verified
# token and the operation's exact scope. The public app below injects no auth
# provider, so its live/default contract remains exactly four anonymous tools.
private_handoff.register_private_handoff_tools(server.mcp)


def _tool_security_schemes(tool: Any) -> list[dict[str, Any]]:
    """Return one explicit per-tool auth policy for every published tool."""
    if tool.name in private_handoff.PRIVATE_TOOL_NAMES:
        metadata = tool.meta or {}
        schemes = metadata.get("securitySchemes")
        if not isinstance(schemes, list) or not schemes:
            raise RuntimeError(f"Private tool {tool.name} is missing its OAuth policy.")
        return schemes
    if tool.name in PUBLIC_TOOL_NAMES:
        return [{"type": "noauth"}]
    raise RuntimeError(f"Tool {tool.name} has no reviewed authentication policy.")


async def _list_tools_with_explicit_security(request: ListToolsRequest):
    """Publish OpenAI's top-level auth field plus the legacy `_meta` mirror.

    MCP SDK 1.27 accepts extension fields but FastMCP 3.2.3 does not populate
    ``securitySchemes`` itself. Registering this bounded list-tools adapter
    keeps the real wire descriptor compliant without rewriting response bytes.
    """
    result = await server.mcp._list_tools_mcp(request)
    for tool in result.tools:
        schemes = _tool_security_schemes(tool)
        tool.meta = {**(tool.meta or {}), "securitySchemes": schemes}
        setattr(tool, "securitySchemes", schemes)
    return result


# Replace FastMCP's registered low-level list handler before the HTTP app is
# built. The SDK's Tool model explicitly allows extension fields, so the field
# survives normal typed serialization and cache refreshes.
server.mcp._mcp_server.list_tools()(_list_tools_with_explicit_security)


# --- ASGI plumbing ----------------------------------------------------------

_mcp_app = server.mcp.http_app(path=MCP_PATH, stateless_http=True, json_response=True)

# The session manager's task group is bound to both the event loop and the task
# that started it. A dedicated owner task therefore enters and exits each
# loop's lifespan; request tasks only wait for readiness.
_lifespans: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()
_locks: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()


async def _own_lifespan(ready: asyncio.Event, stop: asyncio.Event) -> None:
    """Enter and exit FastMCP's task group from one owning task."""
    try:
        async with _mcp_app.router.lifespan_context(_mcp_app):
            ready.set()
            await stop.wait()
    finally:
        # Unblock startup if the lifespan failed before it could become ready.
        ready.set()


async def _ensure_lifespan() -> None:
    """Start one owner task per event loop when the host omits lifespan events."""
    loop = asyncio.get_running_loop()
    state = _lifespans.get(loop)
    if state is not None and not state[0].done():
        return
    lock = _locks.get(loop)
    if lock is None:
        # No await between get and set, so this stays race-free on one loop.
        lock = asyncio.Lock()
        _locks[loop] = lock
    async with lock:
        state = _lifespans.get(loop)
        if state is not None and not state[0].done():
            return
        ready = asyncio.Event()
        stop = asyncio.Event()
        task = loop.create_task(_own_lifespan(ready, stop))
        _lifespans[loop] = (task, stop)
        await ready.wait()
        if task.done():
            await task


async def _close_lifespan_for_current_loop() -> None:
    """Signal the owner task and await deterministic same-task cleanup."""
    loop = asyncio.get_running_loop()
    state = _lifespans.pop(loop, None)
    _locks.pop(loop, None)
    if state is not None:
        task, stop = state
        stop.set()
        await task


async def _send_json(send, status: int, body: dict[str, Any]) -> None:
    raw = json.dumps(body, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(raw)).encode("ascii")),
                (b"cache-control", b"no-store"),
            ],
        }
    )
    await send({"type": "http.response.body", "body": raw})


async def _read_body(receive) -> bytes:
    chunks: list[bytes] = []
    size = 0
    while True:
        message = await receive()
        if message["type"] != "http.request":
            break
        chunk = message.get("body", b"")
        size += len(chunk)
        if size > MAX_BODY_BYTES:
            raise ValueError("body too large")
        chunks.append(chunk)
        if not message.get("more_body", False):
            break
    return b"".join(chunks)


def _replay(body: bytes):
    """Rebuild a receive() callable after the body has been consumed."""
    sent = False

    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}

    return receive


DISCOVERY = {
    "name": "Nymrel Public Tool Suite",
    "endpoint": "https://mcp.nymrel.com/mcp",
    "transport": "streamable-http",
    "authentication": "none",
    "tools": list(PUBLIC_TOOL_NAMES),
    "upstream_api": server.DEFAULT_BASE_URL,
    "support": "contact@nymrel.com",
    "docs": "https://nymrel.com/mcp",
}


def _discovery(private_auth_available: bool) -> dict[str, Any]:
    if not private_auth_available:
        return DISCOVERY
    return {
        **DISCOVERY,
        "name": "Nymrel Tool Suite",
        "authentication": "optional-oauth2",
        "private_tools": sorted(private_handoff.PRIVATE_TOOL_NAMES),
    }


def _original_path(scope) -> str | None:
    """Recover the pre-rewrite path the platform forwards as ?__path=.

    The vercel.json rewrite sends every request to /api/index, which erased the
    original path entirely. That blindness is not cosmetic: answering a plain
    GET on /.well-known/oauth-authorization-server with 200 JSON made Claude.ai
    read this authless server as a broken OAuth provider and fail registration
    ("Couldn't register with Nymrel Tools's sign-in service", proven live
    2026-08-18). OAuth discovery probes must 404 here, and that requires
    knowing the path again.
    """
    qs = scope.get("query_string", b"") or b""
    if not qs:
        return None
    try:
        params = parse_qs(qs.decode("latin-1"), keep_blank_values=True)
    except (UnicodeDecodeError, ValueError):
        return None
    values = params.get("__path")
    if not values or not values[0]:
        return None
    recovered = values[0]
    if not recovered.startswith("/"):
        recovered = "/" + recovered
    return recovered.rstrip("/") or "/"


def _provider_query_string(scope) -> bytes:
    """Preserve OAuth query parameters while removing the Vercel path shim."""
    raw = scope.get("query_string", b"") or b""
    if not raw:
        return b""
    try:
        pairs = parse_qsl(raw.decode("latin-1"), keep_blank_values=True)
    except (UnicodeDecodeError, ValueError):
        return b""
    return urlencode(
        [(name, value) for name, value in pairs if name != "__path"],
        doseq=True,
    ).encode("ascii")


async def _dispatch_app(
    scope,
    receive,
    send,
    *,
    oauth_routes_app=None,
):
    """Serve the MCP app, optionally delegating OAuth provider routes."""
    discovery = _discovery(oauth_routes_app is not None)
    if scope["type"] == "lifespan":
        # Delegate to the real app so a full ASGI server still gets clean
        # startup/shutdown; the lazy shim covers platforms that skip this.
        await _mcp_app(scope, receive, send)
        return

    if scope["type"] != "http":
        await _mcp_app(scope, receive, send)
        return

    path = scope.get("path", "/").rstrip("/") or "/"

    recovered = _original_path(scope)
    if recovered is not None and path in PATH_ALIASES:
        # The rewrite hid the real path; the query string carries it. Route on
        # what the caller actually asked for.
        if recovered == "/":
            if scope.get("method") in {"GET", "HEAD"}:
                await _send_json(send, 200, discovery)
                return
            # A POST to the bare domain is someone following the discovery
            # document's endpoint loosely; serve it rather than lecture them.
        elif recovered not in MCP_PATHS:
            if oauth_routes_app is not None:
                delegated_scope = dict(
                    scope,
                    path=recovered,
                    raw_path=recovered.encode("ascii", errors="ignore"),
                    query_string=_provider_query_string(scope),
                )
                await oauth_routes_app(delegated_scope, receive, send)
                return
            # Everything else - /.well-known/oauth-*, /register, stray crawls -
            # is NOT this server. 404 is load-bearing: it is what tells an MCP
            # client there is no sign-in service and it should connect
            # unauthenticated.
            await _send_json(send, 404, discovery)
            return

    elif path not in PATH_ALIASES:
        # No rewrite in play (local run, tests, a future platform): the scope
        # path is the real path, so route on it directly.
        if path not in MCP_PATHS:
            if path == "/":
                await _send_json(send, 200, discovery)
                return
            if oauth_routes_app is not None:
                await oauth_routes_app(scope, receive, send)
                return
            await _send_json(send, 404, discovery)
            return
        # /server and /sse reach the MCP handling below.

    # Legacy fallback: an alias path with no __path forwarded (the rewrite
    # predating the query-forwarding config). Key the discovery document on
    # what the caller is doing instead of the path: a GET without an
    # event-stream Accept is a person or a probe, not an MCP client opening an
    # SSE stream. (Proven live 2026-08-17: GET / on prod answered 405 while the
    # local test passed, because the test bypasses the rewrite.)
    if scope.get("method") in {"GET", "HEAD"}:
        accept = b""
        for name, value in scope.get("headers", []):
            if name.lower() == b"accept":
                accept = value
                break
        if b"text/event-stream" not in accept:
            await _send_json(send, 200, discovery)
            return

    if scope.get("method") == "POST":
        try:
            body = await _read_body(receive)
        except ValueError:
            await _send_json(
                send,
                413,
                {
                    "status": "error",
                    "error": {
                        "code": "REQUEST_TOO_LARGE",
                        "message": (
                            "That request was too big to accept, so nothing was sent on. "
                            "Send a smaller one."
                        ),
                        "retryable": False,
                    },
                },
            )
            return

        receive = _replay(body)

    await _ensure_lifespan()
    scope = dict(scope, path=MCP_PATH, raw_path=MCP_PATH.encode("ascii"))
    await _mcp_app(scope, receive, send)


async def app(scope, receive, send):
    """Disabled-by-default public entrypoint exported to the host."""
    await _dispatch_app(scope, receive, send)


def build_private_handoff_app(auth_provider):
    """Build the hybrid public/private app with an injected AuthProvider.

    FastMCP's normal ``http_app(auth=...)`` wrapper makes the entire MCP
    endpoint require a bearer token, which would break Nymrel's four public
    tools. Instead, the provider's standard authentication/context middleware
    is installed without its endpoint-wide ``RequireAuthMiddleware``. Private
    handlers read only provider-verified tokens from FastMCP's request context;
    public handlers remain anonymous.

    Production activation uses the direct remote provider configured below;
    tests may still inject a synthetic provider. Both paths publish RFC 9728
    metadata and validate issuer, audience, expiry and the two handoff scopes.
    """
    if auth_provider is None:
        raise RuntimeError("Private handoff activation requires an AuthProvider.")
    if not private_handoff.private_handoff_enabled():
        raise RuntimeError(
            f"Set {private_handoff.FEATURE_ENV}=true before building the private app."
        )

    routes = auth_provider.get_routes(mcp_path=MCP_PATH)
    oauth_routes_app = Starlette(routes=routes)

    async def private_app(scope, receive, send):
        auth_context = private_handoff.enter_private_auth_context()
        try:
            await _dispatch_app(
                scope,
                receive,
                send,
                oauth_routes_app=oauth_routes_app,
            )
        finally:
            private_handoff.exit_private_auth_context(auth_context)

    wrapped = private_app
    # Starlette applies its Middleware list in reverse. Reproduce that ordering
    # so AuthenticationMiddleware populates scope.user before
    # AuthContextMiddleware snapshots the verified FastMCP access token.
    for middleware in reversed(auth_provider.get_middleware()):
        wrapped = middleware.cls(
            wrapped,
            *middleware.args,
            **middleware.kwargs,
        )
    return wrapped


# Select the production provider only when the explicit feature flag is on.
# Missing or invalid OAuth configuration then fails the deployment at import
# rather than silently publishing private tools behind a broken auth surface.
if private_handoff.private_handoff_enabled():
    app = build_private_handoff_app(
        private_handoff.configured_private_auth_provider()
    )


# Aliases some platform adapters look for.
application = app
handler = app
