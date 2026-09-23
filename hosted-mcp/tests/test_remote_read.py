"""Synthetic-only tests; never contact a device or production issuer."""
import base64
import json
import os
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from fastmcp.server.auth.providers.jwt import StaticTokenVerifier

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))
import index
import nymrel_remote_read as remote

HEADERS = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}


def _encode_jwt(claims, private_key):
    def encode(value):
        raw = json.dumps(value, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).rstrip(b"=")

    signing_input = b".".join((encode({"alg": "RS256", "typ": "JWT", "kid": "fixture"}), encode(claims)))
    signature = private_key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    return b".".join((signing_input, base64.urlsafe_b64encode(signature).rstrip(b"="))).decode("ascii")


class RemoteTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {remote.FEATURE_ENV: "true", index.private_handoff.FEATURE_ENV: "false"})
        self.env.start()
        self.addCleanup(self.env.stop)
        provider = StaticTokenVerifier(tokens={
            "fixture-read": {"client_id": "fixture", "scopes": remote.SCOPES},
            "fixture-partial": {"client_id": "fixture", "scopes": ["tools:read"]}})
        self.app = index.build_remote_read_app(provider)

    async def asyncTearDown(self):
        await index._close_lifespan_for_current_loop()

    async def request(self, method, params=None, token=None, app=None):
        headers = dict(HEADERS)
        if token:
            headers["Authorization"] = "Bearer " + token
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app or self.app), base_url="https://test") as client:
            return await client.post("/mcp", headers=headers,
                json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}})

    async def test_catalog_and_default_hidden(self):
        result = (await self.request("tools/list")).json()["result"]
        tools = {t["name"]: t for t in result["tools"]}
        self.assertEqual(set(tools), set(index.PUBLIC_TOOL_NAMES) | set(remote.TOOL_NAMES))
        for name, tool in tools.items():
            expected = [{"type": "noauth"}] if name in index.PUBLIC_TOOL_NAMES else [{"type": "oauth2", "scopes": remote.SCOPES}]
            self.assertEqual(tool["securitySchemes"], expected)
            self.assertEqual(tool["_meta"]["securitySchemes"], expected)
            self.assertNotIn("token", json.dumps(tool["inputSchema"]))
        with patch.dict(os.environ, {remote.FEATURE_ENV: "false"}):
            default = (await self.request("tools/list", app=index.app)).json()["result"]["tools"]
        self.assertEqual({t["name"] for t in default}, set(index.PUBLIC_TOOL_NAMES))

    async def test_missing_and_partial_auth_never_proxies(self):
        with patch.object(remote, "proxy_read", new_callable=AsyncMock) as proxy:
            for token in (None, "fixture-partial"):
                response = await self.request("tools/call", {"name": "nymrel_remote_list_devices", "arguments": {}}, token)
                result = response.json()["result"]
                self.assertTrue(result["isError"])
                self.assertIn(remote.METADATA, result["_meta"]["mcp/www_authenticate"][0])
            proxy.assert_not_called()

    async def test_verified_token_and_pending_result_preserved(self):
        expected = remote.CallToolResult(content=[{"type": "text", "text": "pending"}], structuredContent={"pending": True, "call": {"id": "fixture-call"}}, isError=False)
        with patch.object(remote, "proxy_read", new_callable=AsyncMock, return_value=expected) as proxy:
            response = await self.request("tools/call", {"name": "nymrel_remote_read_file", "arguments": {"path": "fixture.md"}}, "fixture-read")
        proxy.assert_awaited_once_with("read_file", {"path": "fixture.md"}, "fixture-read")
        self.assertEqual(response.json()["result"]["structuredContent"], expected.structuredContent)

    async def test_writes_not_found_and_public_still_anonymous(self):
        denied = await self.request("tools/call", {"name": "nymrel_remote_write_file", "arguments": {}}, "fixture-read")
        self.assertTrue("error" in denied.json() or denied.json()["result"]["isError"])
        with patch.object(index.server, "_call_tool", return_value={"fixture": "public"}):
            response = await self.request("tools/call", {"name": "nymrel_social_clip_score", "arguments": {"transcript_text": "test"}})
        self.assertFalse(response.json()["result"].get("isError", False))

    async def test_fixed_transport_headers_and_response(self):
        seen = []
        def handler(request):
            seen.append(request)
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": "nymrel-remote-read", "result": {"content": [{"type": "text", "text": "ok"}], "structuredContent": {"value": 1}, "isError": False}})
        real_client = httpx.AsyncClient
        with patch.object(remote.httpx, "AsyncClient", side_effect=lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs)):
            result = await remote.proxy_read("list_devices", {}, "fixture-read")
        self.assertEqual(str(seen[0].url), remote.BACKEND)
        self.assertEqual(seen[0].headers["authorization"], "Bearer fixture-read")
        self.assertEqual(seen[0].headers["mcp-name"], "list_devices")
        self.assertEqual(seen[0].headers["mcp-protocol-version"], "2026-07-28")
        self.assertEqual(result.structuredContent, {"value": 1})
        with self.assertRaises(ValueError):
            await remote.proxy_read("write_file", {}, "fixture-read")

    async def test_upstream_auth_redirect_and_token_echo_are_not_exposed(self):
        real_client = httpx.AsyncClient
        for status in (401, 403, 302, 500, 200):
            def handler(request, status=status):
                return httpx.Response(status, headers={"location": "https://untrusted.test"}, json={"jsonrpc": "2.0", "id": "nymrel-remote-read", "result": {"content": [{"type": "text", "text": "fixture-read"}]}})
            with patch.object(remote.httpx, "AsyncClient", side_effect=lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs)):
                result = await remote.proxy_read("list_devices", {}, "fixture-read")
            self.assertTrue(result.isError)
            self.assertNotIn("fixture-read", result.model_dump_json())

    async def test_exact_jwt_issuer_and_audience(self):
        issuer = "https://issuer.example/"
        with patch.dict(os.environ, {remote.ISSUER_ENV: issuer, remote.JWKS_ENV: "https://issuer.example/.well-known/jwks.json"}):
            provider = remote.configured_auth_provider()
        verifier = provider.token_verifier
        self.assertEqual(verifier.issuer, issuer)
        self.assertEqual(verifier.audience, remote.RESOURCE)
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        for audience, token_issuer, allowed in ((remote.RESOURCE, issuer, True), (remote.BACKEND, issuer, False), (remote.RESOURCE, issuer.rstrip("/"), False)):
            encoded = _encode_jwt({"iss": token_issuer, "aud": audience, "sub": "fixture", "exp": int(time.time()) + 60, "scope": " ".join(remote.SCOPES)}, key)
            with patch.object(verifier, "_get_verification_key", AsyncMock(return_value=public)):
                token = await verifier.verify_token(encoded)
            self.assertEqual(token is not None, allowed)

    def test_conflicting_auth_features_fail_closed(self):
        with patch.dict(os.environ, {index.private_handoff.FEATURE_ENV: "true"}), self.assertRaises(RuntimeError):
            remote.validate_activation()
