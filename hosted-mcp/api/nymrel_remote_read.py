"""Dormant same-app Remote reader. No shared credential or arbitrary proxy."""
from __future__ import annotations

import json
import os
from contextvars import ContextVar
from pathlib import Path
from typing import Annotated
from urllib.parse import urlparse

import httpx
from jsonschema import validate
from pydantic import AnyHttpUrl, PrivateAttr, TypeAdapter, UrlConstraints
from fastmcp.server.auth import RemoteAuthProvider
from fastmcp.server.auth.providers.jwt import JWTVerifier
from fastmcp.server.dependencies import get_access_token
from fastmcp.tools import Tool
from fastmcp.tools.tool import ToolResult
from mcp.types import CallToolResult, TextContent

import nymrel_private_handoff as handoff

FEATURE_ENV = "NYMREL_REMOTE_READ_MCP_ENABLED"
ISSUER_ENV = "NYMREL_REMOTE_READ_OAUTH_ISSUER"
JWKS_ENV = "NYMREL_REMOTE_READ_OAUTH_JWKS_URL"
RESOURCE = "https://mcp.nymrel.com/mcp"
METADATA = "https://mcp.nymrel.com/.well-known/oauth-protected-resource/mcp"
BACKEND = "https://nymrel-remote-production.up.railway.app/nymrel/plugin/readonly/mcp"
SCOPES = ["devices:read", "tools:read"]
CATALOG = json.loads(Path(__file__).with_name("remote-read-tools.json").read_text())
SCHEMAS = {tool["name"]: tool["inputSchema"] for tool in CATALOG}
TOOL_NAMES = tuple("nymrel_remote_" + name for name in SCHEMAS)
_AUTH_AVAILABLE = ContextVar("remote_read_auth_available", default=False)


def enabled():
    return os.environ.get(FEATURE_ENV, "").strip().lower() in {"true", "1", "yes", "on"}


def validate_activation():
    if enabled() and handoff.private_handoff_enabled():
        raise RuntimeError("Remote read and private handoff OAuth cannot be enabled together.")


def _https_setting(name):
    value = os.environ.get(name, "")
    parsed = urlparse(value)
    if (not value or value != value.strip() or parsed.scheme != "https" or
            not parsed.hostname or parsed.username or parsed.password or
            parsed.fragment or parsed.query):
        raise RuntimeError(f"Set {name} to its exact HTTPS provider value.")
    return value


def configured_auth_provider():
    validate_activation()
    if not enabled():
        raise RuntimeError("Remote read feature must be enabled before configuring auth.")
    issuer = _https_setting(ISSUER_ENV)
    jwks = _https_setting(JWKS_ENV)
    # OAuth issuer identifiers are exact strings. Ordinary AnyHttpUrl adds a
    # slash to origin-only values, including when metadata is serialized.
    issuer_url = TypeAdapter(
        Annotated[AnyHttpUrl, UrlConstraints(preserve_empty_path=True)]
    ).validate_python(issuer)
    if str(issuer_url) != issuer:
        raise RuntimeError(f"Set {ISSUER_ENV} to its exact canonical HTTPS provider value.")
    # Preserve issuer trailing slash and provider-specific JWKS path exactly.
    return RemoteAuthProvider(
        token_verifier=JWTVerifier(jwks_uri=jwks, issuer=issuer,
                                  audience=RESOURCE, algorithm="RS256",
                                  required_scopes=None, ssrf_safe=True),
        authorization_servers=[issuer_url],
        base_url="https://mcp.nymrel.com", scopes_supported=SCOPES,
        resource_name="Nymrel Remote read access",
    )


def visible(_context):
    return enabled() and not handoff.private_handoff_enabled() and _AUTH_AVAILABLE.get()


def auth_failure(error="insufficient_scope"):
    return CallToolResult(isError=True, content=[{"type": "text", "text": "Connect an approved Nymrel account to inspect its paired files."}],
        _meta={"mcp/www_authenticate": [
            f'Bearer resource_metadata="{METADATA}", error="{error}", '
            'error_description="Connect with both Remote read permissions", '
            'scope="devices:read tools:read"']})


def failure():
    return CallToolResult(isError=True, content=[{"type": "text", "text": "Nymrel Remote could not complete this read. Retry later; do not broaden access."}])


async def proxy_read(name, arguments, bearer):
    # Validate before opening a connection; no caller-controlled URLs or names.
    if name not in SCHEMAS:
        raise ValueError("Remote write and unknown tools are unavailable.")
    validate(arguments, SCHEMAS[name])
    request_id = "nymrel-remote-read"
    headers = {"Authorization": f"Bearer {bearer}",
               "Content-Type": "application/json", "Accept": "application/json, text/event-stream",
               "MCP-Protocol-Version": "2026-07-28", "MCP-Method": "tools/call", "MCP-Name": name}
    body = {"jsonrpc": "2.0", "id": request_id, "method": "tools/call",
            "params": {"name": name, "arguments": arguments, "_meta": {
                "io.modelcontextprotocol/protocolVersion": "2026-07-28",
                "io.modelcontextprotocol/clientCapabilities": {},
                "io.modelcontextprotocol/clientInfo": {"name": "nymrel-hosted-mcp", "version": "1.0.0"}}}}
    try:
        async with httpx.AsyncClient(timeout=35, follow_redirects=False, trust_env=False) as client:
            async with client.stream("POST", BACKEND, headers=headers, json=body) as response:
                if response.status_code in {401, 403}:
                    return auth_failure()
                if response.status_code != 200:
                    return failure()
                chunks = bytearray()
                async for chunk in response.aiter_bytes():
                    chunks.extend(chunk)
                    if len(chunks) > 2_097_152:
                        return failure()
        payload = json.loads(chunks)
        if not isinstance(payload, dict) or payload.get("jsonrpc") != "2.0" or payload.get("id") != request_id or "error" in payload:
            return failure()
        result = payload["result"]
        # Never let an upstream error reflect the request credential.
        if bearer and bearer in json.dumps(result):
            return failure()
        parsed = CallToolResult.model_validate(result)
        # Auth challenges always belong to this public resource, not Railway.
        if parsed.meta and "mcp/www_authenticate" in parsed.meta:
            return auth_failure()
        if parsed.structuredContent and parsed.structuredContent.get("pending") is True:
            parsed.content.append(TextContent(type="text", text="Retrieve this pending read with nymrel_remote_get_read_result and the returned call ID; do not resubmit the original read."))
        return parsed
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return failure()


class ForwardedResult(ToolResult):
    _result: CallToolResult = PrivateAttr()

    def __init__(self, result):
        super().__init__(content=result.content, structured_content=result.structuredContent, meta=result.meta)
        self._result = result

    def to_mcp_result(self):
        return self._result


class RemoteReadTool(Tool):
    backend_name: str

    async def run(self, arguments):
        if not visible(None):
            return ForwardedResult(failure())
        token = get_access_token()
        if token is None or not set(SCOPES).issubset(token.scopes):
            return ForwardedResult(auth_failure())
        return ForwardedResult(await proxy_read(self.backend_name, arguments, token.token))


def register_tools(mcp):
    for descriptor in CATALOG:
        name = descriptor["name"]
        mcp.add_tool(RemoteReadTool(
            name="nymrel_remote_" + name, backend_name=name,
            description=descriptor["description"].replace("get_read_result", "nymrel_remote_get_read_result"),
            parameters=descriptor["inputSchema"], annotations=descriptor["annotations"],
            meta={"securitySchemes": [{"type": "oauth2", "scopes": SCOPES}]},
            auth=visible,
        ))
