"""Wire-level regression cases for the post-SDK discovery adapter."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))
import security_wire  # noqa: E402


def test_only_correlated_discovery_requests_are_adapted():
    assert security_wire.list_request(b'{"jsonrpc":"2.0","id":0,"method":"tools/list"}') == 0
    for body in (b'[]', b'{', b'{"method":"tools/list"}',
                 b'{"jsonrpc":"2.0","id":true,"method":"tools/list"}',
                 b'{"jsonrpc":"2.0","id":1,"method":"tools/call"}'):
        assert security_wire.list_request(body) is None


@pytest.mark.anyio
async def test_chunked_discovery_preserves_policy_and_recalculates_length():
    messages = []
    async def send(message):
        messages.append(message)
    wrap = security_wire.wire_sender(send, 7)
    raw = json.dumps({"jsonrpc":"2.0", "id":7, "result":{"tools":[
        {"name":"private", "_meta":{"securitySchemes":[{"type":"oauth2", "scopes":["read"]}]}}
    ], "nextCursor":"next"}}).encode()
    await wrap({"type":"http.response.start", "status":200, "headers":[(b"content-length",b"1"),(b"content-type",b"application/json")]})
    await wrap({"type":"http.response.body", "body":raw[:20], "more_body":True})
    assert messages == []
    await wrap({"type":"http.response.body", "body":raw[20:], "more_body":False})
    output = json.loads(messages[1]["body"])
    assert output["result"]["nextCursor"] == "next"
    assert output["result"]["tools"][0]["securitySchemes"] == [{"type":"oauth2", "scopes":["read"]}]
    assert (b"content-length", str(len(messages[1]["body"])).encode()) in messages[0]["headers"]


@pytest.mark.anyio
@pytest.mark.parametrize("response", [
    {"jsonrpc":"2.0","id":8,"result":{"tools":[]}},
    {"jsonrpc":"2.0","id":7,"result":{"tools":[{"name":"unknown"}]}},
    {"jsonrpc":"2.0","id":7,"result":{"tools":[{"name":"unknown","_meta":{"securitySchemes":[]}}]}},
    {"jsonrpc":"2.0","id":7,"result":{"tools":"invalid"}},
])
async def test_invalid_discovery_never_sends_a_partial_response(response):
    messages = []
    async def send(message):
        messages.append(message)
    wrap = security_wire.wire_sender(send, 7)
    await wrap({"type":"http.response.start", "status":200, "headers":[(b"content-type",b"application/json")]})
    with pytest.raises(RuntimeError):
        await wrap({"type":"http.response.body", "body":json.dumps(response).encode()})
    assert messages == []

@pytest.mark.anyio
async def test_oversized_response_fails_before_sending_headers():
    messages = []
    async def send(message):
        messages.append(message)
    wrap = security_wire.wire_sender(send, 7)
    await wrap({"type":"http.response.start", "status":200, "headers":[(b"content-type",b"application/json")]})
    with pytest.raises(RuntimeError, match="exceeds limit"):
        await wrap({"type":"http.response.body", "body":b"x" * (security_wire.MAX_RESPONSE_BYTES + 1)})
    assert messages == []


@pytest.mark.anyio
async def test_error_result_is_preserved_without_injecting_policy():
    messages = []
    async def send(message):
        messages.append(message)
    wrap = security_wire.wire_sender(send, "r")
    raw = b'{"jsonrpc":"2.0","id":"r","error":{"code":-32600,"message":"bad"}}'
    await wrap({"type":"http.response.start", "status":200, "headers":[(b"content-type",b"application/json")]})
    await wrap({"type":"http.response.body", "body":raw})
    assert messages[1]["body"] == raw
