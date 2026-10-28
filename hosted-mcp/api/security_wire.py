"""Preserve reviewed discovery auth metadata after the SDK's schema sieve."""
from __future__ import annotations

import json

MAX_RESPONSE_BYTES = 2_097_152


def list_request(body: bytes):
    try:
        request = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return None
    if (not isinstance(request, dict) or request.get("jsonrpc") != "2.0"
            or request.get("method") != "tools/list"
            or type(request.get("id")) not in (str, int)):
        return None
    return request["id"]


def wire_sender(send, request_id):
    start = None
    chunks = []
    size = 0

    async def send_wrapped(message):
        nonlocal start, size
        if message["type"] == "http.response.start":
            start = message
            return
        if message["type"] != "http.response.body" or start is None:
            raise RuntimeError("Unexpected discovery response stream")
        chunk = message.get("body", b"")
        size += len(chunk)
        if size > MAX_RESPONSE_BYTES:
            raise RuntimeError("Discovery response exceeds limit")
        chunks.append(chunk)
        if message.get("more_body", False):
            return
        body = b"".join(chunks)
        if start["status"] == 200:
            headers = {k.lower(): v.lower() for k, v in start.get("headers", [])}
            if (not headers.get(b"content-type", b"").startswith(b"application/json")
                    or headers.get(b"content-encoding", b"identity") != b"identity"):
                raise RuntimeError("Unsupported discovery response encoding")
            response = json.loads(body)
            if (not isinstance(response, dict) or response.get("jsonrpc") != "2.0"
                    or type(response.get("id")) is not type(request_id)
                    or response.get("id") != request_id
                    or ("result" in response) == ("error" in response)):
                raise RuntimeError("Unexpected discovery response")
            if "result" in response:
                result = response["result"]
                if not isinstance(result, dict) or not isinstance(result.get("tools"), list):
                    raise RuntimeError("Invalid discovery result")
                for tool in result["tools"]:
                    if not isinstance(tool, dict):
                        raise RuntimeError("Invalid discovery tool")
                    metadata = tool.get("_meta")
                    schemes = metadata.get("securitySchemes") if isinstance(metadata, dict) else None
                    if not isinstance(schemes, list) or not schemes:
                        raise RuntimeError("Missing discovery security policy")
                    tool["securitySchemes"] = schemes
                body = json.dumps(response, separators=(",", ":"), ensure_ascii=True).encode("ascii")
        headers = [(k, v) for k, v in start.get("headers", []) if k.lower() != b"content-length"]
        headers.append((b"content-length", str(len(body)).encode("ascii")))
        await send({**start, "headers": headers})
        await send({"type": "http.response.body", "body": body, "more_body": False})

    return send_wrapped
