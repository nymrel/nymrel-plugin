"""Result contracts and the activated app exercised over the real MCP wire."""
import copy
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from jsonschema import validate

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))
import index  # noqa: E402
import audit_ui  # noqa: E402
import public_results as contracts  # noqa: E402
import nymrel_remote_read as remote  # noqa: E402
from result_fixtures import AUDIT, CLIP  # noqa: E402


def test_public_results_preserve_evidence_and_publish_valid_schemas():
    for model, payload in (
        (contracts.AuditSummary, {**AUDIT, "checks": [{"measured": False}], "scored_out_of": 50}),
        (contracts.ClipResult, CLIP),
        (contracts.GolfResult, {"average_gap_yards": 35, "problem_gaps": ["50 yard gap"], "recommendations": []}),
        (contracts.DomainResult, {"suggestions": [{"domain": "example.com", "available": False,
            "availability_checked": False, "brandability_score": 90, "brandability_factors": {
                "label_length": 7, "contains_digit": False, "contains_hyphen": False, "contains_vowel": True}}]}),
    ):
        result = contracts.validate_result(model, payload).to_mcp_result()
        assert not result.isError
        assert result.structuredContent == payload == json.loads(result.content[0].text)
        validate(result.structuredContent, contracts.output_schema(model))
        for key in model.model_fields:
            incomplete = {k: v for k, v in payload.items() if k != key}
            rejected = contracts.validate_result(model, incomplete).to_mcp_result()
            assert rejected.isError
            assert rejected.structuredContent["error"]["code"] == "INVALID_RESULT"


@pytest.mark.parametrize("score", ["88", True, -1, 101, float("nan"), float("inf")])
def test_invalid_measurements_fail_without_echoing_payload(score):
    result = contracts.validate_result(contracts.AuditSummary, {**AUDIT, "score": score, "secret": "do-not-reflect"}).to_mcp_result()
    assert result.isError
    assert "do-not-reflect" not in result.model_dump_json()


def test_error_contract_and_strict_signal_types():
    payload = {"status": "error", "error": {"code": "INVALID_INPUT", "message": "Check input.", "retryable": False}}
    result = contracts.validate_result(contracts.GolfResult, payload).to_mcp_result()
    assert result.isError and result.structuredContent == payload
    validate(payload, contracts.output_schema(contracts.GolfResult))
    invalid = copy.deepcopy(CLIP)
    invalid["signals"]["addresses_viewer"] = "false"
    assert contracts.validate_result(contracts.ClipResult, invalid).to_mcp_result().isError


async def rpc(method, params=None):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=index.app), base_url="http://test") as client:
        response = await client.post("/mcp", headers={"Accept": "application/json, text/event-stream"},
            json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}})
    assert response.status_code == 200
    return response.json()["result"]


@pytest.mark.anyio
async def test_activated_ui_descriptor_resource_and_no_refetch():
    with patch.dict(os.environ, {audit_ui.FEATURE_ENV: "true"}):
        tools = {tool["name"]: tool for tool in (await rpc("tools/list"))["tools"]}
        render = tools[audit_ui.TOOL_NAME]
        assert render["_meta"]["ui"]["resourceUri"] == audit_ui.RESOURCE_URI
        assert render["securitySchemes"] == [{"type": "noauth"}]
        assert render["annotations"]["openWorldHint"] is False
        for name in index.PUBLIC_TOOL_NAMES:
            assert tools[name]["outputSchema"]["type"] == "object"
            assert "ui" not in tools[name]["_meta"]
        assert tools["nymrel_audit_website"]["outputSchema"] == contracts.output_schema(contracts.AuditSummary)
        resource = (await rpc("resources/read", {"uri": audit_ui.RESOURCE_URI}))["contents"][0]
        assert resource["mimeType"] == audit_ui.MIME_TYPE
        assert "ui/initialize" in resource["text"]
        assert resource["_meta"]["ui"]["csp"]["connectDomains"] == []
        with patch.object(index.server, "_call_tool", side_effect=AssertionError("render must not fetch")):
            result = await rpc("tools/call", {"name": audit_ui.TOOL_NAME,
                "arguments": {"report": AUDIT, "requested_url": "https://example.com"}})
        assert not result.get("isError", False)
        assert result["structuredContent"]["report"] == AUDIT
        validate(result["structuredContent"], render["outputSchema"])


@pytest.mark.anyio
async def test_disabled_ui_hidden_and_uncallable():
    with patch.dict(os.environ, {audit_ui.FEATURE_ENV: "false"}):
        assert audit_ui.TOOL_NAME not in {tool["name"] for tool in (await rpc("tools/list"))["tools"]}
        assert audit_ui.RESOURCE_URI not in {resource["uri"] for resource in (await rpc("resources/list"))["resources"]}
        result = await rpc("tools/call", {"name": audit_ui.TOOL_NAME,
            "arguments": {"report": AUDIT, "requested_url": "https://example.com"}})
        assert result["isError"]


@pytest.mark.anyio
@pytest.mark.parametrize("payload,code", [
    ({"score": 88, "grade": "A", "private": "do-not-reflect"}, "INVALID_RESULT"),
    ({"status": "error", "error": {"code": "INVALID_INPUT", "message": "Check input.", "retryable": False}}, "INVALID_INPUT"),
])
async def test_public_failures_preserve_mcp_error_bit_over_http(payload, code):
    with patch.object(index.server, "_call_tool", return_value=payload):
        result = await rpc("tools/call", {"name": "nymrel_audit_website", "arguments": {"url": "https://example.com"}})
    assert result["isError"] is True
    assert result["structuredContent"]["error"]["code"] == code
    assert result["structuredContent"] == json.loads(result["content"][0]["text"])
    assert "do-not-reflect" not in json.dumps(result)


@pytest.mark.anyio
@pytest.mark.parametrize("state,valid", [
    ({"pending": True, "call": {"id": "read-1"}}, True),
    ({"pending": True, "callId": "read-1"}, True),
    ({"pending": True}, False),
    ({"pending": True, "callId": " "}, False),
    ({"pending": True, "callId": 12}, False),
    ({"pending": True, "call": {"id": "read-1"}, "callId": "read-2"}, False),
])
async def test_pending_read_has_one_unambiguous_resume_id(state, valid):
    def handler(request):
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": "nymrel-remote-read", "result": {
            "content": [], "structuredContent": state, "isError": False}})
    real_client = httpx.AsyncClient
    with patch.object(remote.httpx, "AsyncClient", side_effect=lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs)):
        result = await remote.proxy_read("read_file", {"path": "fixture.md"}, "synthetic-bearer")
    assert result.isError is not valid
    if valid:
        assert result.structuredContent == state
        assert result.meta["nymrel/readState"] == {"state": "pending", "callId": "read-1",
            "resumeTool": "nymrel_remote_get_read_result", "resubmitOriginal": False}


@pytest.fixture
def anyio_backend():
    return "asyncio"
