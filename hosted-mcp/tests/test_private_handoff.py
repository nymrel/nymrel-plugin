"""Synthetic contract tests for the dormant private ``@Nymrel`` bridge."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import httpx
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastmcp.server.auth.providers.jwt import StaticTokenVerifier
from mcp.server.auth.routes import build_resource_metadata_url
from pydantic import AnyHttpUrl
from starlette.responses import JSONResponse
from starlette.routing import Route

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

import index  # noqa: E402
import nymrel_private_handoff as private  # noqa: E402


MCP_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}
PUBLIC_TOOLS = {
    "nymrel_audit_website",
    "nymrel_find_domain",
    "nymrel_golf_bag_gap",
    "nymrel_social_clip_score",
}


def _rpc(method: str, params: dict | None = None, ident: int = 1) -> dict:
    body = {"jsonrpc": "2.0", "id": ident, "method": method}
    if params is not None:
        body["params"] = params
    return body


def _receipt(*, replay: bool = False) -> dict:
    return {
        "contract_version": private.CONTRACT_VERSION,
        "handoff_id": "nymh_AbCdEfGhIjKlMnOpQrStUvWx",
        "status": "queued",
        "target_project": "Synthetic Project",
        "received_at": "2026-08-26T12:00:00.000Z",
        "updated_at": "2026-08-26T12:00:00.000Z",
        "receipt": {
            "content_bytes": 42,
            "redactions": {
                "api_keys": 0,
                "emails": 0,
                "phone_numbers": 0,
                "private_keys": 0,
            },
            "attempts": 0,
            "reason_codes": ["QUEUED_FOR_REVIEW"],
            "content_storage": "application-encrypted",
        },
        "idempotent_replay": replay,
        "status_path": "/api/agent/v1/handoffs/nymh_AbCdEfGhIjKlMnOpQrStUvWx",
    }


def _tool_payload(response: httpx.Response) -> dict:
    result = response.json()["result"]
    return json.loads(result["content"][0]["text"])


class PrivateClientTests(unittest.TestCase):
    def test_submit_forwards_verified_token_and_stable_idempotency_key(self):
        seen = {}

        def requester(method, url, **kwargs):
            seen.update({"method": method, "url": url, **kwargs})
            response = Mock(status_code=202)
            # A hypothetical upstream regression must not leak submitted text
            # through the receipt returned to the model.
            response.json.return_value = {
                **_receipt(),
                "content_markdown": "must never cross back through MCP",
            }
            return response

        client = private.NymrelPrivateHandoffClient(
            api_url=private.DEFAULT_API_URL,
            requester=requester,
        )
        payload = {
            "contract_version": private.CONTRACT_VERSION,
            "target_project": "Synthetic Project",
            "intent": "project_handoff",
            "title": "Synthetic handoff",
            "content_markdown": "Fixture-only text",
        }
        result = client.submit(
            bearer_token="synthetic-private-token",
            idempotency_key="synthetic-handoff-0001",
            payload=payload,
        )

        self.assertEqual(seen["method"], "POST")
        self.assertEqual(seen["headers"]["Authorization"], "Bearer synthetic-private-token")
        self.assertEqual(seen["headers"]["Idempotency-Key"], "synthetic-handoff-0001")
        self.assertFalse(seen["allow_redirects"])
        self.assertEqual(seen["json"], payload)
        self.assertNotIn("content_markdown", result)
        self.assertNotIn("synthetic-private-token", json.dumps(result))

    def test_status_is_get_and_returns_body_free_allowlist(self):
        seen = {}

        def requester(method, url, **kwargs):
            seen.update({"method": method, "url": url, **kwargs})
            response = Mock(status_code=200)
            response.json.return_value = {
                **_receipt(),
                "title": "not returned",
                "summary": "not returned",
                "ciphertext": "not returned",
            }
            return response

        client = private.NymrelPrivateHandoffClient(
            api_url=private.DEFAULT_API_URL,
            requester=requester,
        )
        result = client.status(
            bearer_token="synthetic-private-token",
            handoff_id="nymh_AbCdEfGhIjKlMnOpQrStUvWx",
        )

        self.assertEqual(seen["method"], "GET")
        self.assertNotIn("json", seen)
        self.assertNotIn("title", result)
        self.assertNotIn("summary", result)
        self.assertNotIn("ciphertext", result)

    def test_upstream_error_body_cannot_echo_private_text(self):
        def requester(*args, **kwargs):
            response = Mock(status_code=422)
            response.json.return_value = {
                "error": {
                    "code": "INVALID_HANDOFF_REQUEST",
                    "message": "echoed private text: fixture-only body",
                }
            }
            return response

        client = private.NymrelPrivateHandoffClient(
            api_url=private.DEFAULT_API_URL,
            requester=requester,
        )
        with self.assertRaises(private.NymrelPrivateHandoffError) as caught:
            client.submit(
                bearer_token="synthetic-private-token",
                idempotency_key="synthetic-handoff-0001",
                payload={"content_markdown": "fixture-only body"},
            )
        self.assertEqual(caught.exception.code, "INVALID_HANDOFF_REQUEST")
        self.assertNotIn("fixture-only body", caught.exception.message)

    def test_api_url_is_pinned_and_redirects_are_rejected(self):
        for url in (
            "https://attacker.example/api/agent/v1/handoffs",
            "https://127.0.0.1:9443/api/agent/v1/handoffs",
            "https://nymrel.com:443/api/agent/v1/handoffs",
            "https://nymrel.com/api/agent/v1/handoffs/extra",
        ):
            with self.subTest(url=url):
                with self.assertRaises(private.NymrelPrivateHandoffError):
                    private.NymrelPrivateHandoffClient(api_url=url)

        def requester(*args, **kwargs):
            response = Mock(status_code=307)
            response.json.return_value = {}
            return response

        client = private.NymrelPrivateHandoffClient(requester=requester)
        with self.assertRaises(private.NymrelPrivateHandoffError) as caught:
            client.submit(
                bearer_token="synthetic-private-token",
                idempotency_key="synthetic-handoff-0001",
                payload={"content_markdown": "fixture-only body"},
            )
        self.assertEqual(caught.exception.code, "PRIVATE_HANDOFF_REJECTED")


class ConfiguredPrivateAuthProviderTests(unittest.TestCase):
    def test_direct_provider_pins_issuer_resource_algorithm_and_scopes(self):
        issuer = "https://login.nymrel.test"
        with patch.dict(
            os.environ,
            {
                private.FEATURE_ENV: "true",
                private.OAUTH_ISSUER_ENV: issuer,
            },
            clear=False,
        ):
            provider = private.configured_private_auth_provider()

        verifier = provider.token_verifier
        self.assertEqual(str(provider.authorization_servers[0]).rstrip("/"), issuer)
        self.assertEqual(str(provider.base_url).rstrip("/"), private.MCP_BASE_URL)
        self.assertEqual(verifier.issuer, issuer)
        self.assertEqual(verifier.audience, private.MCP_RESOURCE_URL)
        self.assertEqual(verifier.jwks_uri, f"{issuer}/oauth2/jwks")
        self.assertEqual(verifier.algorithm, "RS256")
        self.assertTrue(verifier.ssrf_safe)
        self.assertEqual(verifier.required_scopes, [])

    def test_configured_verifier_accepts_each_least_privilege_scope(self):
        issuer = "https://login.nymrel.test"
        with patch.dict(
            os.environ,
            {
                private.FEATURE_ENV: "true",
                private.OAUTH_ISSUER_ENV: issuer,
            },
            clear=False,
        ):
            verifier = private.configured_private_auth_provider().token_verifier

        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        public_pem = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        now = int(time.time())
        for scope in (private.CREATE_SCOPE, private.READ_SCOPE):
            token = jwt.encode(
                {
                    "iss": issuer,
                    "aud": private.MCP_RESOURCE_URL,
                    "sub": "user_synthetic_123",
                    "scope": scope,
                    "iat": now,
                    "exp": now + 300,
                },
                private_pem,
                algorithm="RS256",
                headers={"kid": "synthetic-key"},
            )
            with patch.object(
                verifier,
                "_get_verification_key",
                AsyncMock(return_value=public_pem),
            ):
                access = asyncio.run(verifier.verify_token(token))
            self.assertIsNotNone(access)
            self.assertEqual(access.scopes, [scope])

    def test_direct_provider_fails_closed_on_missing_or_unsafe_issuer(self):
        with patch.dict(os.environ, {private.FEATURE_ENV: "true"}, clear=False):
            os.environ.pop(private.OAUTH_ISSUER_ENV, None)
            with self.assertRaises(RuntimeError):
                private.configured_private_auth_provider()
        for issuer in (
            "http://login.nymrel.test",
            "https://login.nymrel.test/path",
            "https://user@login.nymrel.test",
            "https://login.nymrel.test:443",
        ):
            with self.subTest(issuer=issuer), patch.dict(
                os.environ,
                {
                    private.FEATURE_ENV: "true",
                    private.OAUTH_ISSUER_ENV: issuer,
                },
                clear=False,
            ):
                with self.assertRaises(RuntimeError):
                    private.configured_private_auth_provider()


class HostedPrivateHandoffTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.feature = patch.dict(
            os.environ,
            {private.FEATURE_ENV: "true"},
            clear=False,
        )
        self.feature.start()
        self.addCleanup(self.feature.stop)
        self.provider = StaticTokenVerifier(
            tokens={
                "both-scopes-token": {
                    "client_id": "synthetic-client",
                    "scopes": [private.CREATE_SCOPE, private.READ_SCOPE],
                },
                "read-scope-token": {
                    "client_id": "synthetic-reader",
                    "scopes": [private.READ_SCOPE],
                },
            }
        )
        self.app = index.build_private_handoff_app(self.provider)

    async def asyncTearDown(self) -> None:
        await index._close_lifespan_for_current_loop()

    async def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),
            base_url="http://mcp.test",
        )

    async def test_enabled_catalog_adds_exactly_two_oauth_tools(self):
        async with await self._client() as client:
            response = await client.post(
                "/mcp", headers=MCP_HEADERS, json=_rpc("tools/list")
            )
        self.assertEqual(response.status_code, 200)
        tools = {tool["name"]: tool for tool in response.json()["result"]["tools"]}
        self.assertEqual(set(tools), PUBLIC_TOOLS | private.PRIVATE_TOOL_NAMES)
        for name in PUBLIC_TOOLS:
            self.assertEqual(tools[name]["securitySchemes"], [{"type": "noauth"}])
            self.assertEqual(
                tools[name]["_meta"]["securitySchemes"],
                [{"type": "noauth"}],
            )
        for name, scope in (
            ("nymrel_submit_private_handoff", private.CREATE_SCOPE),
            ("nymrel_get_private_handoff_status", private.READ_SCOPE),
        ):
            self.assertEqual(
                tools[name]["securitySchemes"],
                [{"type": "oauth2", "scopes": [scope]}],
            )
            self.assertEqual(
                tools[name]["_meta"]["securitySchemes"],
                [{"type": "oauth2", "scopes": [scope]}],
            )

    async def test_missing_auth_fails_closed_with_oauth_challenge(self):
        call = _rpc(
            "tools/call",
            {
                "name": "nymrel_get_private_handoff_status",
                "arguments": {"handoff_id": "nymh_AbCdEfGhIjKlMnOpQrStUvWx"},
            },
        )
        async with await self._client() as client:
            response = await client.post("/mcp", headers=MCP_HEADERS, json=call)

        result = response.json()["result"]
        self.assertTrue(result["isError"])
        self.assertEqual(_tool_payload(response)["error"]["code"], "HANDOFF_AUTH_REQUIRED")
        challenge = result["_meta"]["mcp/www_authenticate"][0]
        self.assertIn(private.RESOURCE_METADATA_URL, challenge)
        self.assertIn(private.READ_SCOPE, challenge)
        self.assertIn('error="insufficient_scope"', challenge)
        self.assertIn("error_description=", challenge)

    async def test_wrong_scope_fails_before_the_rest_client(self):
        stub = Mock()
        call = _rpc(
            "tools/call",
            {
                "name": "nymrel_submit_private_handoff",
                "arguments": {
                    "idempotency_key": "synthetic-handoff-0001",
                    "target_project": "Synthetic Project",
                    "intent": "project_handoff",
                    "title": "Synthetic handoff",
                    "content_markdown": "Fixture-only text",
                },
            },
        )
        headers = {**MCP_HEADERS, "Authorization": "Bearer read-scope-token"}
        with patch.object(private, "_client", return_value=stub):
            async with await self._client() as client:
                response = await client.post("/mcp", headers=headers, json=call)

        stub.submit.assert_not_called()
        result = response.json()["result"]
        self.assertTrue(result["isError"])
        self.assertEqual(_tool_payload(response)["error"]["code"], "HANDOFF_AUTH_REQUIRED")
        self.assertIn(private.CREATE_SCOPE, result["_meta"]["mcp/www_authenticate"][0])
        self.assertIn(
            'error="insufficient_scope"',
            result["_meta"]["mcp/www_authenticate"][0],
        )

    async def test_submit_uses_verified_context_token_and_rest_contract(self):
        stub = Mock()
        stub.submit.return_value = _receipt()
        call = _rpc(
            "tools/call",
            {
                "name": "nymrel_submit_private_handoff",
                "arguments": {
                    "idempotency_key": "synthetic-handoff-0001",
                    "target_project": "Synthetic Project",
                    "intent": "project_handoff",
                    "title": "Synthetic handoff",
                    "content_markdown": "Fixture-only text",
                    "summary": "Synthetic summary",
                },
            },
        )
        headers = {**MCP_HEADERS, "Authorization": "Bearer both-scopes-token"}
        with patch.object(private, "_client", return_value=stub):
            async with await self._client() as client:
                response = await client.post("/mcp", headers=headers, json=call)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(_tool_payload(response)["handoff_id"], _receipt()["handoff_id"])
        kwargs = stub.submit.call_args.kwargs
        self.assertEqual(kwargs["bearer_token"], "both-scopes-token")
        self.assertEqual(kwargs["idempotency_key"], "synthetic-handoff-0001")
        self.assertEqual(kwargs["payload"]["contract_version"], private.CONTRACT_VERSION)
        self.assertEqual(kwargs["payload"]["content_markdown"], "Fixture-only text")
        self.assertNotIn("bearer_token", kwargs["payload"])

    async def test_public_tools_remain_available_without_auth_when_enabled(self):
        stub = Mock()
        stub.call.return_value = {"score": 88, "grade": "A"}
        call = _rpc(
            "tools/call",
            {"name": "nymrel_audit_website", "arguments": {"url": "https://example.com"}},
        )
        import nymrel_public_mcp_server as public_server

        with patch.object(public_server, "_client", return_value=stub):
            async with await self._client() as client:
                response = await client.post("/mcp", headers=MCP_HEADERS, json=call)
        self.assertEqual(_tool_payload(response), {"score": 88, "grade": "A"})

    async def test_challenge_path_matches_and_delegates_to_provider_metadata(self):
        expected = str(
            build_resource_metadata_url(AnyHttpUrl("https://mcp.nymrel.com/mcp"))
        )
        self.assertEqual(private.RESOURCE_METADATA_URL, expected)

        async def metadata(request):
            return JSONResponse(
                {
                    "resource": "https://mcp.nymrel.com/mcp",
                    "client_id": request.query_params.get("client_id"),
                    "state": request.query_params.get("state"),
                    "path_shim": request.query_params.get("__path"),
                }
            )

        provider = StaticTokenVerifier(tokens={})
        provider.get_routes = Mock(
            return_value=[
                Route(
                    "/.well-known/oauth-protected-resource/mcp",
                    endpoint=metadata,
                    methods=["GET"],
                )
            ]
        )
        app = index.build_private_handoff_app(provider)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://mcp.test",
        ) as client:
            response = await client.get(
                "/.well-known/oauth-protected-resource/mcp"
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["resource"], "https://mcp.nymrel.com/mcp")

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://mcp.test",
        ) as client:
            rewritten = await client.get(
                "/api/index",
                params={
                    "__path": "/.well-known/oauth-protected-resource/mcp",
                    "client_id": "synthetic-client",
                    "state": "state-123",
                },
            )
        self.assertEqual(rewritten.status_code, 200)
        self.assertEqual(rewritten.json()["client_id"], "synthetic-client")
        self.assertEqual(rewritten.json()["state"], "state-123")
        self.assertIsNone(rewritten.json()["path_shim"])

    async def test_direct_provider_publishes_exact_resource_metadata(self):
        issuer = "https://login.nymrel.test"
        with patch.dict(os.environ, {private.OAUTH_ISSUER_ENV: issuer}, clear=False):
            app = index.build_private_handoff_app(
                private.configured_private_auth_provider()
            )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://mcp.test",
        ) as client:
            response = await client.get(
                "/.well-known/oauth-protected-resource/mcp"
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "resource": private.MCP_RESOURCE_URL,
                "authorization_servers": [f"{issuer}/"],
                "bearer_methods_supported": ["header"],
                "scopes_supported": [private.CREATE_SCOPE, private.READ_SCOPE],
                "resource_name": "Nymrel private handoff",
                "resource_documentation": "https://nymrel.com/mcp",
            },
        )


class DisabledPrivateHandoffTests(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self) -> None:
        await index._close_lifespan_for_current_loop()

    async def test_default_catalog_remains_exactly_four_public_tools(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop(private.FEATURE_ENV, None)
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=index.app),
                base_url="http://mcp.test",
            ) as client:
                response = await client.post(
                    "/mcp", headers=MCP_HEADERS, json=_rpc("tools/list")
                )
        tools = response.json()["result"]["tools"]
        names = {tool["name"] for tool in tools}
        self.assertEqual(names, PUBLIC_TOOLS)
        for tool in tools:
            self.assertEqual(tool["securitySchemes"], [{"type": "noauth"}])
            self.assertEqual(
                tool["_meta"]["securitySchemes"],
                [{"type": "noauth"}],
            )

    def test_unreviewed_future_tool_has_no_implicit_noauth_policy(self):
        with self.assertRaises(RuntimeError):
            index._tool_security_schemes(
                SimpleNamespace(name="nymrel_future_write", meta=None)
            )

    async def test_feature_flag_without_provider_still_exposes_only_public_tools(self):
        with patch.dict(os.environ, {private.FEATURE_ENV: "true"}, clear=False):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=index.app),
                base_url="http://mcp.test",
            ) as client:
                response = await client.post(
                    "/mcp", headers=MCP_HEADERS, json=_rpc("tools/list")
                )
        names = {tool["name"] for tool in response.json()["result"]["tools"]}
        self.assertEqual(names, PUBLIC_TOOLS)

    def test_builder_requires_both_feature_flag_and_provider(self):
        with patch.dict(os.environ, {private.FEATURE_ENV: "false"}, clear=False):
            with self.assertRaises(RuntimeError):
                index.build_private_handoff_app(StaticTokenVerifier(tokens={}))
        with patch.dict(os.environ, {private.FEATURE_ENV: "true"}, clear=False):
            with self.assertRaises(RuntimeError):
                index.build_private_handoff_app(None)


if __name__ == "__main__":
    unittest.main(verbosity=2)
