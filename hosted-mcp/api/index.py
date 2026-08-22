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
from urllib.parse import parse_qs

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from typing import Annotated  # noqa: E402

from pydantic import Field  # noqa: E402

import nymrel_public_mcp_server as server  # noqa: E402


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


# --- ASGI plumbing ----------------------------------------------------------

_mcp_app = server.mcp.http_app(path=MCP_PATH, stateless_http=True, json_response=True)

# The session manager's task group is bound to the event loop that started it.
# Serverless adapters commonly run a fresh loop per invocation, so the state has
# to be keyed by loop rather than by process.
_lifespans: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()
_locks: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()


async def _ensure_lifespan() -> None:
    """Start the MCP session manager once per event loop, without a lifespan event."""
    loop = asyncio.get_running_loop()
    if loop in _lifespans:
        return
    lock = _locks.get(loop)
    if lock is None:
        # No await between get and set, so this stays race-free on one loop.
        lock = asyncio.Lock()
        _locks[loop] = lock
    async with lock:
        if loop in _lifespans:
            return
        context = _mcp_app.router.lifespan_context(_mcp_app)
        await context.__aenter__()
        # Held for the life of the loop; the platform reclaims it on shutdown.
        _lifespans[loop] = context


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
    "tools": [
        "nymrel_audit_website",
        "nymrel_find_domain",
        "nymrel_golf_bag_gap",
        "nymrel_social_clip_score",
    ],
    "upstream_api": server.DEFAULT_BASE_URL,
    "support": "contact@nymrel.com",
    "docs": "https://nymrel.com/mcp",
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


async def app(scope, receive, send):
    """Root ASGI entrypoint exported to the hosting platform."""
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
                await _send_json(send, 200, DISCOVERY)
                return
            # A POST to the bare domain is someone following the discovery
            # document's endpoint loosely; serve it rather than lecture them.
        elif recovered not in MCP_PATHS:
            # Everything else - /.well-known/oauth-*, /register, stray crawls -
            # is NOT this server. 404 is load-bearing: it is what tells an MCP
            # client there is no sign-in service and it should connect
            # unauthenticated.
            await _send_json(send, 404, DISCOVERY)
            return

    elif path not in PATH_ALIASES:
        # No rewrite in play (local run, tests, a future platform): the scope
        # path is the real path, so route on it directly.
        if path not in MCP_PATHS:
            await _send_json(send, 200 if path == "/" else 404, DISCOVERY)
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
            await _send_json(send, 200, DISCOVERY)
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


# Aliases some platform adapters look for.
application = app
handler = app
