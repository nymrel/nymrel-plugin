"""Packaging tests for the hosted Nymrel MCP connector.

These run the real ASGI app through httpx's ASGITransport, which never sends an
ASGI lifespan event. That is deliberate: it reproduces the serverless case and
proves the lazy lifespan shim actually starts the MCP session manager.
"""

from __future__ import annotations

import json
import os
import sys
import unittest
from unittest.mock import Mock, patch

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "api"))

import index  # noqa: E402
import nymrel_public_mcp_server as server  # noqa: E402


MCP_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}

READ_TOOLS = {
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


def _tool_payload(response: httpx.Response) -> dict:
    """Read a tool result out of an MCP response with exactly one parse."""
    body = response.json()
    content = body["result"]["content"][0]["text"]
    return json.loads(content)


class HostedEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_every_hosted_tool_carries_directory_annotations(self):
        """Annotations must hold on the hosted app, not just the module.

        index.py removes tools and re-registers two, so annotations set on the
        canonical server alone silently vanish in production. The Claude
        Connectors Directory rejects tools missing a title or read/write hint.
        """
        async with await self._client() as client:
            response = await client.post(
                "/mcp", headers=MCP_HEADERS, json=_rpc("tools/list")
            )
        tools = response.json()["result"]["tools"]
        self.assertEqual(len(tools), 4)
        for tool in tools:
            annotations = tool.get("annotations") or {}
            self.assertTrue(
                annotations.get("title"), f"{tool['name']} has no annotation title"
            )
            self.assertIn(
                "readOnlyHint", annotations, f"{tool['name']} has no readOnlyHint"
            )

    async def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=index.app),
            base_url="http://mcp.test",
        )

    async def test_tools_list_exposes_only_operational_public_tools_without_lifespan(self):
        async with await self._client() as client:
            response = await client.post("/mcp", headers=MCP_HEADERS, json=_rpc("tools/list"))

        self.assertEqual(response.status_code, 200)
        names = {tool["name"] for tool in response.json()["result"]["tools"]}
        self.assertEqual(names, READ_TOOLS)

    async def test_initialize_succeeds_over_stateless_http(self):
        async with await self._client() as client:
            response = await client.post(
                "/mcp",
                headers=MCP_HEADERS,
                json=_rpc(
                    "initialize",
                    {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {},
                        "clientInfo": {"name": "packaging-test", "version": "1.0"},
                    },
                ),
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("serverInfo", response.json()["result"])

    async def test_read_tool_needs_no_auth_and_returns_api_json_unchanged(self):
        stub = Mock()
        stub.call.return_value = {"score": 88, "grade": "A"}
        call = _rpc(
            "tools/call",
            {"name": "nymrel_audit_website", "arguments": {"url": "https://example.com"}},
        )
        with patch.object(server, "_client", return_value=stub):
            async with await self._client() as client:
                response = await client.post("/mcp", headers=MCP_HEADERS, json=call)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(_tool_payload(response), {"score": 88, "grade": "A"})

    async def test_path_aliases_all_reach_the_mcp_endpoint(self):
        async with await self._client() as client:
            for path in ("/mcp", "/api/index", "/api/mcp"):
                with self.subTest(path=path):
                    response = await client.post(
                        path, headers=MCP_HEADERS, json=_rpc("tools/list")
                    )
                    self.assertEqual(response.status_code, 200)
                    self.assertIn("tools", response.json()["result"])

    async def test_published_descriptions_carry_no_unbacked_claims(self):
        """Published descriptions must match the two heuristic/open-world tools."""
        async with await self._client() as client:
            response = await client.post("/mcp", headers=MCP_HEADERS, json=_rpc("tools/list"))

        described = {t["name"]: (t.get("description") or "") for t in response.json()["result"]["tools"]}

        for name, banned in (
            ("nymrel_social_clip_score", ("goviral", "-backed")),
            ("nymrel_find_domain", ("verified", "guaranteed")),
        ):
            text = described[name].lower()
            for phrase in banned:
                with self.subTest(tool=name, phrase=phrase):
                    self.assertNotIn(phrase, text)

        # and the honest qualifiers are actually present
        self.assertIn("does not predict", described["nymrel_social_clip_score"].lower())
        self.assertIn("not confirmed free", described["nymrel_find_domain"].lower())

    async def test_tool_result_is_single_encoded(self):
        """One parse must reach the object - no JSON quoted inside JSON."""
        stub = Mock()
        stub.call.return_value = {"score": 88, "grade": "A"}
        call = _rpc(
            "tools/call",
            {"name": "nymrel_audit_website", "arguments": {"url": "https://example.com"}},
        )
        with patch.object(server, "_client", return_value=stub):
            async with await self._client() as client:
                response = await client.post("/mcp", headers=MCP_HEADERS, json=call)

        result = response.json()["result"]
        once = json.loads(result["content"][0]["text"])
        self.assertEqual(once, {"score": 88, "grade": "A"})
        self.assertNotIsInstance(once, str, "text content still holds a JSON string")
        self.assertEqual(
            result["structuredContent"],
            {"score": 88, "grade": "A"},
            "structuredContent must be the object, not {'result': '<json string>'}",
        )

    async def test_rolling_out_upstream_surfaces_as_upstream_not_deployed(self):
        """The live state today: /api/v1/tools/* answers 404 with an HTML page."""

        class NotDeployed:
            status_code = 404
            headers = {"content-type": "text/html; charset=utf-8"}

            @staticmethod
            def json():
                raise ValueError("Expecting value")

        # audit-website is the one tool with a local fallback, so a tool
        # without one is what proves the upstream contract still holds.
        call = _rpc(
            "tools/call",
            {
                "name": "nymrel_golf_bag_gap",
                "arguments": {"clubs": [{"name": "7i", "carry_yards": 150}]},
            },
        )
        real_client = server.NymrelPublicApiClient(
            base_url="https://api.example.test/api/v1/tools",
            requester=lambda *a, **k: NotDeployed(),
        )
        with patch.object(server, "_client", return_value=real_client):
            async with await self._client() as client:
                response = await client.post("/mcp", headers=MCP_HEADERS, json=call)

        payload = _tool_payload(response)
        self.assertEqual(payload["error"]["code"], "UPSTREAM_NOT_DEPLOYED")
        self.assertFalse(payload["error"]["retryable"])
        self.assertIn("rolling out", payload["error"]["message"])

    async def test_audit_website_falls_back_to_a_measured_local_audit(self):
        """An absent upstream must not turn a listed tool into a dead end."""

        class NotDeployed:
            status_code = 404
            headers = {"content-type": "text/html; charset=utf-8"}

            @staticmethod
            def json():
                raise ValueError("Expecting value")

        call = _rpc(
            "tools/call",
            {"name": "nymrel_audit_website", "arguments": {"url": "https://example.com"}},
        )
        real_client = server.NymrelPublicApiClient(
            base_url="https://api.example.test/api/v1/tools",
            requester=lambda *a, **k: NotDeployed(),
        )
        sentinel = {"url": "https://example.com", "score": 42, "grade": "F"}
        with patch.object(server, "_client", return_value=real_client), patch.object(
            server.native_audit, "audit_website", return_value=sentinel
        ) as local:
            async with await self._client() as client:
                response = await client.post("/mcp", headers=MCP_HEADERS, json=call)

        payload = _tool_payload(response)
        local.assert_called_once_with("https://example.com")
        self.assertNotIn("error", payload)
        self.assertEqual(payload["score"], 42)

    async def test_every_published_tool_error_reads_as_a_sentence(self):
        """A caller-side mistake on any read tool comes back readable."""
        bad_arguments = {
            "nymrel_audit_website": {"url": " "},
            "nymrel_find_domain": {"keyword_or_concept": ""},
            "nymrel_golf_bag_gap": {"clubs": []},
            "nymrel_social_clip_score": {"transcript_text": ""},
        }
        async with await self._client() as client:
            for name, arguments in bad_arguments.items():
                with self.subTest(tool=name):
                    response = await client.post(
                        "/mcp",
                        headers=MCP_HEADERS,
                        json=_rpc("tools/call", {"name": name, "arguments": arguments}),
                    )
                    error = _tool_payload(response)["error"]
                    self.assertEqual(error["code"], "INVALID_INPUT")
                    self.assertFalse(error["retryable"])
                    self.assertTrue(error["message"].endswith("."))
                    self.assertGreater(len(error["message"].split()), 6)

    async def test_find_domain_description_states_honest_v1_semantics(self):
        async with await self._client() as client:
            response = await client.post("/mcp", headers=MCP_HEADERS, json=_rpc("tools/list"))

        description = {
            t["name"]: (t.get("description") or "") for t in response.json()["result"]["tools"]
        }["nymrel_find_domain"]

        self.assertNotIn("verified", description.lower())
        self.assertIn("not confirmed free", description.lower())

    async def test_root_serves_discovery_document(self):
        async with await self._client() as client:
            response = await client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["endpoint"], "https://mcp.nymrel.com/mcp")


class NoServerCredentialTests(unittest.TestCase):
    def test_read_path_forwards_no_authorization_header(self):
        """A public read must not carry the studio's own credential upstream."""
        seen = {}

        def requester(method, url, **kwargs):
            seen.update(kwargs)

            class Response:
                status_code = 200

                @staticmethod
                def json():
                    return {"ok": True}

            return Response()

        with patch.dict(os.environ, {}, clear=True):
            client = server.NymrelPublicApiClient(
                base_url="https://api.example.test/api/v1/tools",
                requester=requester,
            )
            client.call("audit-website", {"url": "https://example.com"})

        self.assertNotIn("Authorization", seen["headers"])

if __name__ == "__main__":
    unittest.main(verbosity=2)
