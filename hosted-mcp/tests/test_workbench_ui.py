"""Exercise extension metadata and activation on the real hosted MCP wire."""
import json
import os
from unittest.mock import patch

import httpx
import pytest
from jsonschema import validate

import audit_ui
import index
import workbench_ui as ui
from result_fixtures import AUDIT, CLIP


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def rpc(method, params=None):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=index.app), base_url="http://test") as client:
        response = await client.post("/mcp", headers={"Accept": "application/json, text/event-stream"},
            json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}})
    assert response.status_code == 200
    return response.json()["result"]


@pytest.mark.anyio
async def test_global_and_thread_launch_accept_empty_arguments_without_network():
    with patch.dict(os.environ, {ui.FEATURE_ENV: "true", audit_ui.FEATURE_ENV: "false"}):
        tools = {tool["name"]: tool for tool in (await rpc("tools/list"))["tools"]}
        assert set(tools) == set(index.PUBLIC_TOOL_NAMES) | {ui.TOOL_NAME}
        opener = tools[ui.TOOL_NAME]
        assert opener["title"] == "Tool workbench"
        assert opener["_meta"]["openai/ui"]["entrypoints"] == [{"type": "global"}, {"type": "thread"}]
        assert opener["_meta"]["ui"]["resourceUri"] == ui.RESOURCE_URI
        assert opener["securitySchemes"] == opener["_meta"]["securitySchemes"] == [{"type": "noauth"}]
        assert opener["icons"][0]["mimeType"] == "image/svg+xml"
        assert not opener["inputSchema"].get("required")
        with patch.object(index.server, "_call_tool", side_effect=AssertionError("launch must not fetch")):
            launched = await rpc("tools/call", {"name": ui.TOOL_NAME, "arguments": {}})
        assert not launched.get("isError")
        data = launched["structuredContent"]
        validate(data, opener["outputSchema"])
        assert data == json.loads(launched["content"][0]["text"])
        assert {item["name"] for item in data["tools"]} == set(index.PUBLIC_TOOL_NAMES)
        assert {item["id"] for item in data["tools"]} == {"website", "domains", "golf", "clip"}
        resource = (await rpc("resources/read", {"uri": ui.RESOURCE_URI}))["contents"][0]
        assert resource["mimeType"] == ui.MIME_TYPE
        assert resource["_meta"]["ui"]["csp"] == {"connectDomains": [], "resourceDomains": []}
        assert resource["_meta"]["openai/ui"] == ui.DISPLAY_META
        assert "Nymrel tool workbench" in resource["text"]


@pytest.mark.anyio
async def test_disabled_workbench_hidden_and_uncallable_independently_of_audit():
    with patch.dict(os.environ, {ui.FEATURE_ENV: "false", audit_ui.FEATURE_ENV: "true"}):
        tools = {tool["name"] for tool in (await rpc("tools/list"))["tools"]}
        assert ui.TOOL_NAME not in tools and audit_ui.TOOL_NAME in tools
        resources = {resource["uri"] for resource in (await rpc("resources/list"))["resources"]}
        assert ui.RESOURCE_URI not in resources and audit_ui.RESOURCE_URI in resources
        denied = await rpc("tools/call", {"name": ui.TOOL_NAME, "arguments": {}})
        assert denied["isError"]
        audit = (await rpc("resources/read", {"uri": audit_ui.RESOURCE_URI}))["contents"][0]
        assert audit["_meta"]["openai/ui"] == ui.DISPLAY_META


@pytest.mark.anyio
@pytest.mark.parametrize("name,args,payload", [
    ("nymrel_audit_website", {"url": "https://example.com"}, AUDIT),
    ("nymrel_find_domain", {"keyword_or_concept": "fixture", "tlds": [".com"]}, {"suggestions": []}),
    ("nymrel_golf_bag_gap", {"clubs": [{"name": "7 iron", "carry_distance_yards": 150}]},
     {"average_gap_yards": 0, "problem_gaps": [], "recommendations": []}),
    ("nymrel_social_clip_score", {"transcript_text": "Fixture transcript", "target_platform": "reels"}, CLIP),
])
async def test_workbench_uses_existing_public_data_contracts(name, args, payload):
    with patch.dict(os.environ, {ui.FEATURE_ENV: "true"}), patch.object(index.server, "_call_tool", return_value=payload) as call:
        result = await rpc("tools/call", {"name": name, "arguments": args})
    assert not result.get("isError") and result["structuredContent"] == payload
    assert call.call_count == 1


@pytest.mark.anyio
async def test_data_failure_stays_an_error_with_workbench_enabled():
    error = {"status": "error", "error": {"code": "UPSTREAM_TIMEOUT", "message": "Try again later.", "retryable": True}}
    with patch.dict(os.environ, {ui.FEATURE_ENV: "true"}), patch.object(index.server, "_call_tool", return_value=error):
        result = await rpc("tools/call", {"name": "nymrel_find_domain", "arguments": {"keyword_or_concept": "fixture"}})
    assert result["isError"] and result["structuredContent"] == error
