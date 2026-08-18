#!/usr/bin/env python3
"""Post-deploy contract check against the LIVE connector.

The local suite proves the code; this proves the deployment. They diverged
once (2026-08-17): the hosted runtime degraded a TypedDict schema to a bare
object, so every local gate passed while production published an uncallable
tool. Local tests cannot see runtime skew by construction - only a probe of
the served bytes can.

Usage:
    python scripts/verify_live_contract.py [base_url]

Default base_url is https://mcp.nymrel.com. Exits non-zero on any failure,
printing one line per check. Read-only: the only tool it invokes with valid
arguments is the golf analyser, which computes over the numbers supplied.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "api"))

from schema_contract import opaque_input_nodes  # noqa: E402

EXPECTED_TOOLS = {
    "nymrel_audit_website",
    "nymrel_find_domain",
    "nymrel_golf_bag_gap",
    "nymrel_social_clip_score",
}

HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}


def rpc(base: str, method: str, params: dict) -> dict:
    body = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    ).encode()
    request = urllib.request.Request(
        f"{base}/mcp", data=body, headers=HEADERS, method="POST"
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read().decode()
    # Streamable HTTP may frame the JSON as an SSE event; take the JSON line.
    for line in raw.splitlines():
        line = line.removeprefix("data:").strip()
        if line.startswith("{"):
            return json.loads(line)
    return json.loads(raw)


def main() -> int:
    base = (sys.argv[1] if len(sys.argv) > 1 else "https://mcp.nymrel.com").rstrip("/")
    failures: list[str] = []

    def check(label: str, ok: bool, detail: str = "") -> None:
        print(f"  {'ok  ' if ok else 'FAIL'} {label}" + (f" - {detail}" if detail else ""))
        if not ok:
            failures.append(label)

    print(f"verify-live-contract against {base}")

    # 1. GET / serves the discovery document (proves the current wrapper is
    #    what is serving - the pre-2026-08-17 build answers 405 here).
    request = urllib.request.Request(f"{base}/", method="GET")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            discovery_ok = response.status == 200 and b"endpoint" in response.read()
    except Exception as exc:  # noqa: BLE001
        discovery_ok, exc_detail = False, str(exc)
    else:
        exc_detail = ""
    check("GET / serves discovery document", discovery_ok, exc_detail)

    # 2. tools/list: exactly the expected tools, every input schema
    #    caller-completable.
    tools = rpc(base, "tools/list", {})["result"]["tools"]
    names = {tool["name"] for tool in tools}
    check("tools/list returns the expected four", names == EXPECTED_TOOLS, str(sorted(names)))
    for tool in tools:
        opaque = opaque_input_nodes(tool.get("inputSchema", {}))
        check(f"{tool['name']} schema is caller-completable", not opaque, ", ".join(opaque))
        annotations = tool.get("annotations") or {}
        check(
            f"{tool['name']} carries title + readOnlyHint",
            bool(annotations.get("title")) and "readOnlyHint" in annotations,
        )

    # 3. The golf contract round-trips: the documented shape is accepted and
    #    a wrong key is rejected by the schema layer, naming the field.
    good = rpc(base, "tools/call", {
        "name": "nymrel_golf_bag_gap",
        "arguments": {"clubs": [
            {"name": "7 iron", "carry_distance_yards": 150},
            {"name": "9 iron", "carry_distance_yards": 128},
        ]},
    })["result"]
    good_text = good.get("content", [{}])[0].get("text", "")
    check(
        "golf accepts the documented shape",
        not good.get("isError") and "average_gap_yards" in good_text,
        good_text[:120],
    )

    bad = rpc(base, "tools/call", {
        "name": "nymrel_golf_bag_gap",
        "arguments": {"clubs": [{"name": "7 iron", "carry_yards": 150}]},
    })["result"]
    bad_text = bad.get("content", [{}])[0].get("text", "")
    check(
        "golf rejects a wrong key naming the field",
        bool(bad.get("isError")) and "carry_distance_yards" in bad_text,
        bad_text[:120],
    )

    # 4. OAuth discovery probes answer 404. A 200 here made Claude.ai read
    #    this authless server as a broken OAuth provider and refuse to connect
    #    ("Couldn't register with Nymrel Tools's sign-in service", 2026-08-18).
    #    The 404 is what tells an MCP client to proceed unauthenticated.
    for probe in (
        "/.well-known/oauth-protected-resource",
        "/.well-known/oauth-authorization-server",
        "/.well-known/openid-configuration",
        "/register",
    ):
        request = urllib.request.Request(f"{base}{probe}", method="GET")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                status = response.status
        except urllib.error.HTTPError as exc:
            status = exc.code
        except Exception as exc:  # noqa: BLE001
            status = f"error: {exc}"
        check(f"GET {probe} answers 404", status == 404, f"got {status}")

    if failures:
        print(f"LIVE CONTRACT: {len(failures)} FAILURE(S)")
        return 1
    print("LIVE CONTRACT: all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
