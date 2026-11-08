#!/usr/bin/env python3
"""Cold-start ASGI smoke using only the declared runtime dependencies.

Runs in a fresh process with no test dependencies installed. Proves the
serverless import path and the public/auth boundary the rail relies on.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "api"))

# Register the OAuth-protected Remote tools so the auth boundary is exercised.
# The challenge is produced before any JWKS fetch, so this stays offline.
os.environ.setdefault("NYMREL_REMOTE_READ_MCP_ENABLED", "true")
os.environ.setdefault(
    "NYMREL_REMOTE_READ_OAUTH_ISSUER", "https://issuer.runtime-only.test"
)
os.environ.setdefault(
    "NYMREL_REMOTE_READ_OAUTH_JWKS_URL", "https://issuer.runtime-only.test/jwks"
)

import httpx  # noqa: E402

from index import app  # noqa: E402

BASE = "http://runtime-only.test"
HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}
PRIVATE_CALL = {
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/call",
    "params": {"name": "nymrel_remote_list_devices", "arguments": {}},
}


async def main() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE) as client:
        discovery = await client.get("/")
        assert discovery.status_code == 200, f"GET / -> {discovery.status_code}"
        body = discovery.json()
        assert len(body.get("tools", [])) == 4, "expected four public tools"
        assert len(body.get("private_tools", [])) == 7, "expected seven Remote tools"

        initialize = await client.post(
            "/mcp",
            headers=HEADERS,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "runtime-smoke", "version": "1"},
                },
            },
        )
        assert initialize.status_code == 200, f"initialize -> {initialize.status_code}"

        missing = await client.post("/mcp", headers=HEADERS, json=PRIVATE_CALL)
        assert missing.status_code == 401, f"private without token -> {missing.status_code}"

        invalid = await client.post(
            "/mcp",
            headers={**HEADERS, "Authorization": "Bearer invalid-token"},
            json=PRIVATE_CALL,
        )
        assert invalid.status_code == 401, f"private invalid token -> {invalid.status_code}"

    print(
        "runtime-only smoke passed: GET / 200, initialize 200, "
        "private missing/invalid token 401"
    )


if __name__ == "__main__":
    asyncio.run(main())
