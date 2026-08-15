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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import nymrel_public_mcp_server as server  # noqa: E402


MCP_PATH = "/mcp"

# Vercel routes a rewritten request to the function under its own path; accept
# every alias the platform may present so the endpoint is path-stable.
PATH_ALIASES = frozenset({"/mcp", "/api/index", "/api/index/mcp", "/api/mcp", "/api"})

MAX_BODY_BYTES = 1_048_576

_provider = getattr(server.mcp, "local_provider", server.mcp)


# Hide contracts that are not ready for a public no-auth catalog, and replace
# two over-broad descriptions with wording that matches the live implementation.

_provider.remove_tool("nymrel_evaluate_fantasy_trade")
_provider.remove_tool("nymrel_social_clip_score")
_provider.remove_tool("nymrel_local_permit_lookup")
_provider.remove_tool("nymrel_find_domain")
_provider.remove_tool("nymrel_submit_studio_brief")


@server.mcp.tool(name="nymrel_find_domain", annotations={"title": "Find domain names", "readOnlyHint": True, "openWorldHint": True})
def nymrel_find_domain(
    keyword_or_concept: str,
    tlds: list[str] | None = None,
) -> dict[str, Any]:
    """Suggest domain names and check each one against public registry records.

    A name is only reported available when the registry clearly says it is free.
    When the lookup is inconclusive the name comes back as available:false, so
    read false as "not confirmed free" rather than "already taken". Confirm at a
    registrar before buying.
    """
    payload: dict[str, Any] = {"keyword_or_concept": keyword_or_concept}
    if tlds is not None:
        payload["tlds"] = tlds
    return server._call_tool("find-domain", payload)


@server.mcp.tool(name="nymrel_social_clip_score", annotations={"title": "Score a short-video hook", "readOnlyHint": True, "openWorldHint": False})
def nymrel_social_clip_score(transcript_text: str, target_platform: str = "tiktok") -> dict[str, Any]:
    """Score a short-video hook with a text heuristic.

    Looks at opening length, hook phrasing, direct address, curiosity signals and
    word count for the platform. It does not predict reach, views or virality.
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

    if path not in PATH_ALIASES:
        await _send_json(send, 200 if path == "/" else 404, DISCOVERY)
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
