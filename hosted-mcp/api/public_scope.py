"""Independent four-tool MCP registry; never copies private providers or tools."""
from __future__ import annotations

import asyncio
import json
import weakref
from functools import wraps
from inspect import iscoroutinefunction
from urllib.parse import parse_qs

from fastmcp import FastMCP
from fastmcp.tools.tool import ToolResult
from mcp.types import ListToolsRequest

from public_results import PublicToolResult

PUBLIC_PATH = "/public/mcp"
PUBLIC_NAMES = frozenset({
    "nymrel_audit_website", "nymrel_find_domain",
    "nymrel_golf_bag_gap", "nymrel_social_clip_score",
})
MAX_BODY_BYTES = 1_048_576


def _audit_without_commercial_link(result):
    # The existing full_report_url leads to paid digital-service offers. Retain
    # validated diagnostics, but publish no sales destination on this route.
    if not isinstance(result, ToolResult) or not isinstance(result.structured_content, dict):
        raise RuntimeError("The public audit must return validated structured diagnostics.")
    payload = dict(result.structured_content)
    payload.pop("full_report_url", None)
    return PublicToolResult(payload, is_error=bool(result.to_mcp_result().isError))


def _public_audit_function(function):
    if iscoroutinefunction(function):
        @wraps(function)
        async def call(*args, **kwargs):
            return _audit_without_commercial_link(await function(*args, **kwargs))
    else:
        @wraps(function)
        def call(*args, **kwargs):
            return _audit_without_commercial_link(function(*args, **kwargs))
    return call


def _remove_report_link_schema(node):
    if isinstance(node, list):
        return [_remove_report_link_schema(item) for item in node]
    if not isinstance(node, dict):
        return node
    output = {key: _remove_report_link_schema(value) for key, value in node.items()}
    if isinstance(output.get("properties"), dict):
        output["properties"].pop("full_report_url", None)
    if isinstance(output.get("required"), list):
        output["required"] = [name for name in output["required"] if name != "full_report_url"]
    return output


def uses_public_path(scope):
    path = scope.get("path", "").rstrip("/")
    if path == PUBLIC_PATH:
        return True
    if path not in {"/mcp", "/api/index", "/api/index/mcp", "/api/mcp", "/api"}:
        return False
    values = parse_qs(scope.get("query_string", b"").decode("latin-1")).get("__path", [])
    # A duplicated rewrite marker must never fall back to the developer app.
    return any(("/" + value.lstrip("/")).rstrip("/") == PUBLIC_PATH for value in values)


async def build_public_registry(source):
    public = FastMCP(source.name, auth=None, tasks=False, instructions=(
        "Provide public website diagnostics, domain suggestions, golf carry-gap "
        "calculations and transcript signals. No device access, purchases, "
        "digital-service upsells, subscriptions or sales handoffs."
    ))
    for name in sorted(PUBLIC_NAMES):
        tool = await source.get_tool(name)
        if tool is None or tool.annotations is None:
            raise RuntimeError(f"Public tool {name} is unavailable.")
        if (tool.annotations.readOnlyHint is not True
                or tool.annotations.destructiveHint is not False
                or not isinstance(tool.annotations.openWorldHint, bool)):
            raise RuntimeError(f"Public tool {name} has an unreviewed annotation.")
        copied = tool.model_copy(deep=True)
        copied.meta = dict(copied.meta or {})
        for key in ("ui", "openai/outputTemplate", "openai/widgetAccessible", "openai/visibility"):
            copied.meta.pop(key, None)
        copied.meta["securitySchemes"] = [{"type": "noauth"}]
        if name == "nymrel_audit_website":
            copied.fn = _public_audit_function(copied.fn)
            copied.output_schema = _remove_report_link_schema(copied.output_schema)
        public.add_tool(copied)

    @public._mcp_server.list_tools()
    async def list_public_tools(request: ListToolsRequest):
        result = await public._list_tools_mcp(request)
        if {tool.name for tool in result.tools} != PUBLIC_NAMES:
            raise RuntimeError("The public registry must contain exactly four tools.")
        for tool in result.tools:
            tool.meta = {**(tool.meta or {}), "securitySchemes": [{"type": "noauth"}]}
            setattr(tool, "securitySchemes", [{"type": "noauth"}])
        return result

    return public


class PublicOnlyApp:
    """Manage the independent registry's stateless HTTP lifecycle per loop."""

    def __init__(self, source):
        self.source = source
        self.states = weakref.WeakKeyDictionary()
        self.locks = weakref.WeakKeyDictionary()

    async def ensure(self):
        loop = asyncio.get_running_loop()
        state = self.states.get(loop)
        if state is not None:
            return await self.ready_app(state)
        lock = self.locks.setdefault(loop, asyncio.Lock())
        async with lock:
            state = self.states.get(loop)
            if state is not None:
                return await self.ready_app(state)
            public = await build_public_registry(self.source)
            app = public.http_app(path="/mcp", stateless_http=True, json_response=True)
            ready, stop = asyncio.Event(), asyncio.Event()

            async def own_lifespan():
                try:
                    async with app.router.lifespan_context(app):
                        ready.set()
                        await stop.wait()
                finally:
                    ready.set()

            task = loop.create_task(own_lifespan())
            state = (app, task, stop, ready)
            self.states[loop] = state
            return await self.ready_app(state)

    @staticmethod
    async def ready_app(state):
        await state[3].wait()
        if state[1].done():
            await state[1]  # Propagate the same startup failure to every waiter.
            raise RuntimeError("The public MCP lifespan ended before the request.")
        return state[0]

    async def close_for_current_loop(self):
        loop = asyncio.get_running_loop()
        state = self.states.pop(loop, None)
        self.locks.pop(loop, None)
        if state is not None:
            state[2].set()
            await state[1]

    async def __call__(self, scope, receive, send):
        values = parse_qs(scope.get("query_string", b"").decode("latin-1")).get("__path", [])
        if scope.get("path", "").rstrip("/") != PUBLIC_PATH and len(values) != 1:
            await self.reject(send, 400, "Ambiguous public endpoint path.")
            return
        if scope.get("method") == "POST":
            chunks, size = [], 0
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                chunk = message.get("body", b"")
                size += len(chunk)
                if size > MAX_BODY_BYTES:
                    await self.reject(send, 413, "Public request exceeds the size limit.")
                    return
                chunks.append(chunk)
                if not message.get("more_body", False):
                    break
            body = b"".join(chunks)
            delivered = False

            async def replay():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": body, "more_body": False}
                return {"type": "http.disconnect"}

            receive = replay
        # Even an authenticated developer request uses the anonymous public registry.
        public_scope = dict(scope, path="/mcp", raw_path=b"/mcp", query_string=b"",
                            headers=[(k, v) for k, v in scope.get("headers", [])
                                     if k.lower() not in {b"authorization", b"cookie"}])
        public_scope.pop("user", None)
        public_scope.pop("auth", None)
        app = await self.ensure()
        await app(public_scope, receive, send)

    @staticmethod
    async def reject(send, status, message):
        body = json.dumps({"status": "error", "message": message}).encode()
        await send({"type": "http.response.start", "status": status,
                    "headers": [(b"content-type", b"application/json"), (b"cache-control", b"no-store")]})
        await send({"type": "http.response.body", "body": body})
