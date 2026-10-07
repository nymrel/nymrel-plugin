"""Synthetic ASGI tests for public isolation; no issuer or device is contacted."""
import asyncio
import json
import os
import sys
import unittest
from pathlib import Path
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
from fastmcp.server.auth.providers.jwt import StaticTokenVerifier
from result_fixtures import AUDIT, CLIP

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))
import index
import public_scope
import nymrel_remote_read as remote

HEADERS = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}


class PublicScopeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {remote.FEATURE_ENV: "true", index.private_handoff.FEATURE_ENV: "false"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.provider = StaticTokenVerifier(tokens={
            "fixture-read": {"client_id": "fixture", "scopes": remote.SCOPES},
        })
        self.app = index.build_remote_read_app(self.provider)

    async def asyncTearDown(self):
        await index._close_lifespan_for_current_loop()

    async def request(self, method, params=None, path="/public/mcp", token=None):
        headers = dict(HEADERS)
        if token:
            headers["Authorization"] = "Bearer " + token
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="https://test") as client:
            return await client.post(path, headers=headers, json={
                "jsonrpc": "2.0", "id": 1, "method": method, "params": params or {},
            })

    async def test_four_tools_only_on_direct_and_rewritten_paths_with_or_without_token(self):
        for path in ("/public/mcp", "/public/mcp/", "/api/index?__path=%2Fpublic%2Fmcp"):
            for token in (None, "fixture-read", "invalid"):
                with self.subTest(path=path, token=token):
                    response = await self.request("tools/list", path=path, token=token)
                    self.assertEqual(response.status_code, 200)
                    tools = response.json()["result"]["tools"]
                    self.assertEqual({tool["name"] for tool in tools}, public_scope.PUBLIC_NAMES)
                    for tool in tools:
                        self.assertEqual(tool["securitySchemes"], [{"type": "noauth"}])
                        self.assertEqual(tool["_meta"]["securitySchemes"], [{"type": "noauth"}])
                        self.assertTrue(tool["annotations"]["readOnlyHint"])
                        self.assertFalse(tool["annotations"]["destructiveHint"])
                        self.assertNotIn("ui", tool.get("_meta", {}))
                        self.assertNotIn("openai/outputTemplate", tool.get("_meta", {}))

    async def test_forged_private_and_write_calls_never_proxy_even_with_valid_developer_token(self):
        with patch.object(remote, "proxy_read", new_callable=AsyncMock) as proxy:
            for name in (*remote.TOOL_NAMES, *index.private_handoff.PRIVATE_TOOL_NAMES, "nymrel_remote_write_file"):
                for token in (None, "fixture-read"):
                    with self.subTest(name=name, token=token):
                        response = await self.request("tools/call", {"name": name, "arguments": {}}, token=token)
                        data = response.json()
                        self.assertTrue("error" in data or data["result"]["isError"])
                        self.assertNotIn("structuredContent", data.get("result", {}))
            proxy.assert_not_called()

    async def test_original_eleven_tool_catalog_and_authenticated_device_handler_stay_intact(self):
        await self.request("tools/list")  # Construct the public copy first.
        response = await self.request("tools/list", path="/mcp")
        tools = {tool["name"]: tool for tool in response.json()["result"]["tools"]}
        self.assertEqual(set(tools), public_scope.PUBLIC_NAMES | set(remote.TOOL_NAMES))
        self.assertIn("full_report_url", json.dumps(tools["nymrel_audit_website"]["outputSchema"]))
        expected = remote.CallToolResult(content=[{"type": "text", "text": "synthetic"}],
                                        structuredContent={"fixture": True}, isError=False)
        with patch.object(remote, "proxy_read", AsyncMock(return_value=expected)) as proxy:
            response = await self.request("tools/call", {"name": "nymrel_remote_list_devices", "arguments": {}},
                                          path="/mcp", token="fixture-read")
        self.assertEqual(response.json()["result"]["structuredContent"], {"fixture": True})
        proxy.assert_awaited_once_with("list_devices", {}, "fixture-read")

    async def test_public_audit_retains_diagnostics_and_omits_paid_destination_in_text_and_schema(self):
        with patch.object(index.server, "nymrel_audit_website", return_value=dict(AUDIT)):
            response = await self.request("tools/call", {"name": "nymrel_audit_website", "arguments": {"url": "https://example.com"}})
            original = await self.request("tools/call", {"name": "nymrel_audit_website", "arguments": {"url": "https://example.com"}}, path="/mcp")
        payload = response.json()["result"]["structuredContent"]
        self.assertEqual(payload, {key: value for key, value in AUDIT.items() if key != "full_report_url"})
        self.assertNotIn("full_report_url", response.text)
        self.assertNotIn("nymrel.com/site-audit", response.text)
        self.assertEqual(original.json()["result"]["structuredContent"], AUDIT)
        catalog = (await self.request("tools/list")).json()["result"]["tools"]
        audit = next(tool for tool in catalog if tool["name"] == "nymrel_audit_website")
        self.assertNotIn("full_report_url", json.dumps(audit["outputSchema"]))

    async def test_other_public_schemas_and_results_match_developer_tools(self):
        public = {tool["name"]: tool for tool in (await self.request("tools/list")).json()["result"]["tools"]}
        original = {tool["name"]: tool for tool in (await self.request("tools/list", path="/mcp")).json()["result"]["tools"]}
        for name in public_scope.PUBLIC_NAMES:
            self.assertEqual(public[name]["inputSchema"], original[name]["inputSchema"])
            if name != "nymrel_audit_website":
                self.assertEqual(public[name]["outputSchema"], original[name]["outputSchema"])
        with patch.object(index.server, "_call_tool", return_value=dict(CLIP)):
            response = await self.request("tools/call", {"name": "nymrel_social_clip_score", "arguments": {"transcript_text": "test"}})
        self.assertEqual(response.json()["result"]["structuredContent"], CLIP)

    async def test_clip_platform_aliases_normalize_and_echo_canonical_platform(self):
        aliases = {
            "reels": "instagram_reels",
            "shorts": "youtube_shorts",
            "instagram_reels": "instagram_reels",
            "youtube_shorts": "youtube_shorts",
            "tiktok": "tiktok",
            "x": "x",
        }
        for supplied, normalized in aliases.items():
            with self.subTest(platform=supplied), patch.object(
                index.server, "_call_tool", return_value=dict(CLIP),
            ) as call:
                response = await self.request("tools/call", {
                    "name": "nymrel_social_clip_score",
                    "arguments": {"transcript_text": "Fixture transcript", "target_platform": supplied},
                })
            self.assertEqual(call.call_args.args[1], {
                "transcript_text": "Fixture transcript", "target_platform": normalized,
            })
            self.assertEqual(
                response.json()["result"]["structuredContent"],
                {**CLIP, "target_platform": normalized},
            )

        catalog = {tool["name"]: tool for tool in (await self.request("tools/list")).json()["result"]["tools"]}
        clip = catalog["nymrel_social_clip_score"]
        self.assertEqual(set(clip["inputSchema"]["properties"]["target_platform"]["enum"]), set(aliases))
        clip_success_schema = next(
            schema for schema in clip["outputSchema"]["anyOf"]
            if "target_platform" in schema.get("properties", {})
        )
        self.assertEqual(
            set(clip_success_schema["properties"]["target_platform"]["enum"]),
            {"tiktok", "instagram_reels", "youtube_shorts", "x"},
        )

    async def test_error_and_retry_information_survive_audit_adapter(self):
        error = {"status": "error", "error": {"code": "RATE_LIMITED", "message": "Try later.", "retryable": True},
                 "retry_after_seconds": 17}
        with patch.object(index.server, "nymrel_audit_website", return_value=error):
            response = await self.request("tools/call", {"name": "nymrel_audit_website", "arguments": {"url": "https://example.com"}})
        self.assertTrue(response.json()["result"]["isError"])
        self.assertEqual(response.json()["result"]["structuredContent"], error)

    async def test_public_registry_has_no_resources_prompts_or_oauth_challenge(self):
        initialize = await self.request("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                                      "clientInfo": {"name": "fixture", "version": "1"}})
        self.assertEqual(initialize.status_code, 200)
        self.assertNotIn("www-authenticate", initialize.headers)
        for method, key in (("resources/list", "resources"), ("prompts/list", "prompts")):
            response = await self.request(method)
            self.assertEqual(response.json()["result"][key], [])

    async def test_ambiguous_rewrite_and_oversized_body_fail_without_device_proxy(self):
        with patch.object(remote, "proxy_read", new_callable=AsyncMock) as proxy:
            for path in ("/api/index?__path=%2Fmcp&__path=%2Fpublic%2Fmcp", "/api/index?__path=%2Fpublic%2Fmcp&__path=%2Fmcp"):
                response = await self.request("tools/list", path=path, token="fixture-read")
                self.assertEqual(response.status_code, 400)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="https://test") as client:
                response = await client.post("/public/mcp", headers=HEADERS, content=b"x" * (public_scope.MAX_BODY_BYTES + 1))
            self.assertEqual(response.status_code, 413)
            proxy.assert_not_called()

    async def test_missing_tool_or_changed_safety_annotation_fails_closed(self):
        source = AsyncMock()
        source.name = "synthetic"
        source.get_tool.return_value = None
        with self.assertRaises(RuntimeError):
            await public_scope.build_public_registry(source)
        tool = (await index.server.mcp.get_tool("nymrel_audit_website")).model_copy(deep=True)
        tool.annotations.readOnlyHint = False
        source.get_tool.return_value = tool
        with self.assertRaises(RuntimeError):
            await public_scope.build_public_registry(source)

    async def test_concurrent_startup_waiters_cannot_obtain_an_unready_app(self):
        entered, release = asyncio.Event(), asyncio.Event()

        @asynccontextmanager
        async def lifespan(app):
            entered.set()
            await release.wait()
            yield

        fake_app = SimpleNamespace(router=SimpleNamespace(lifespan_context=lifespan))
        registry = SimpleNamespace(http_app=lambda **kwargs: fake_app)
        isolated = public_scope.PublicOnlyApp(None)
        with patch.object(public_scope, "build_public_registry", AsyncMock(return_value=registry)):
            first = asyncio.create_task(isolated.ensure())
            await entered.wait()
            second = asyncio.create_task(isolated.ensure())
            await asyncio.sleep(0)
            self.assertFalse(first.done())
            self.assertFalse(second.done())
            release.set()
            self.assertEqual(await asyncio.gather(first, second), [fake_app, fake_app])
        await isolated.close_for_current_loop()

    async def test_startup_failure_reaches_all_concurrent_waiters(self):
        entered, release = asyncio.Event(), asyncio.Event()

        @asynccontextmanager
        async def lifespan(app):
            entered.set()
            await release.wait()
            raise RuntimeError("synthetic startup failure")
            yield  # Mark this as an async context manager; never reached.

        fake_app = SimpleNamespace(router=SimpleNamespace(lifespan_context=lifespan))
        registry = SimpleNamespace(http_app=lambda **kwargs: fake_app)
        isolated = public_scope.PublicOnlyApp(None)
        with patch.object(public_scope, "build_public_registry", AsyncMock(return_value=registry)):
            first = asyncio.create_task(isolated.ensure())
            await entered.wait()
            second = asyncio.create_task(isolated.ensure())
            await asyncio.sleep(0)
            release.set()
            results = await asyncio.gather(first, second, return_exceptions=True)
        for result in results:
            self.assertIsInstance(result, RuntimeError)
            self.assertEqual(str(result), "synthetic startup failure")
        with self.assertRaisesRegex(RuntimeError, "synthetic startup failure"):
            await isolated.close_for_current_loop()
        self.assertEqual(len(isolated.states), 0)

    async def test_real_asgi_shutdown_closes_public_owner_before_completion(self):
        incoming, outgoing = asyncio.Queue(), asyncio.Queue()
        lifespan = asyncio.create_task(self.app({"type": "lifespan", "asgi": {"version": "3.0"}},
                                               incoming.get, outgoing.put))
        await incoming.put({"type": "lifespan.startup"})
        self.assertEqual((await outgoing.get())["type"], "lifespan.startup.complete")
        self.assertEqual((await self.request("tools/list")).status_code, 200)
        loop = asyncio.get_running_loop()
        owner = index._public_only_app.states[loop][1]
        await incoming.put({"type": "lifespan.shutdown"})
        self.assertEqual((await outgoing.get())["type"], "lifespan.shutdown.complete")
        self.assertTrue(owner.done())
        self.assertNotIn(loop, index._public_only_app.states)
        await lifespan

    async def test_public_routes_bypass_both_developer_verifiers_before_authentication(self):
        for private in (False, True):
            with self.subTest(private_handoff=private), patch.dict(os.environ, {
                    remote.FEATURE_ENV: "false" if private else "true",
                    index.private_handoff.FEATURE_ENV: "true" if private else "false"}):
                self.app = (index.build_private_handoff_app(self.provider) if private
                            else index.build_remote_read_app(self.provider))
                with patch.object(self.provider, "verify_token", AsyncMock(wraps=self.provider.verify_token)) as verify:
                    for path in ("/public/mcp", "/api/index?__path=%2Fpublic%2Fmcp"):
                        response = await self.request("tools/list", path=path, token="fixture-read")
                        self.assertEqual(response.status_code, 200)
                    verify.assert_not_called()
                    response = await self.request("tools/list", path="/mcp", token="fixture-read")
                    self.assertEqual(response.status_code, 200)
                    verify.assert_awaited_once_with("fixture-read")
if __name__ == "__main__":
    unittest.main()
