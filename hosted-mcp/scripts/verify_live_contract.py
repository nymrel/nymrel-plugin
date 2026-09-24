#!/usr/bin/env python3
"""Post-deploy contract check against the LIVE connector.

The local suite proves the code; this proves the deployment. They diverged
once (2026-08-17): the hosted runtime degraded a TypedDict schema to a bare
object, so every local gate passed while production published an uncallable
tool. Local tests cannot see runtime skew by construction - only a probe of
the served bytes can.

Usage:
    python scripts/verify_live_contract.py [base_url]
    python scripts/verify_live_contract.py --remote-read --issuer https://issuer.example/

Default base_url is https://mcp.nymrel.com. Exits non-zero on any failure,
printing one line per check. Read-only: the only tool it invokes with valid
arguments is the golf analyser, which computes over the numbers supplied.
"""

from __future__ import annotations

import argparse
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
REMOTE_TOOLS = {
    "nymrel_remote_" + tool["name"]
    for tool in json.loads(
        (Path(__file__).resolve().parent.parent / "api" / "remote-read-tools.json").read_text()
    )
}
REMOTE_RESOURCE = "https://mcp.nymrel.com/mcp"
REMOTE_METADATA = "/.well-known/oauth-protected-resource/mcp"
REMOTE_SCOPES = {"devices:read", "tools:read"}

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


def remote_auth_probe(base: str, token: str | None = None) -> tuple[int, str, dict]:
    """Inspect the HTTP challenge as well as the MCP error; never send real tokens."""
    headers = dict(HEADERS)
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    body = {"jsonrpc": "2.0", "id": "auth-probe", "method": "tools/call",
            "params": {"name": "nymrel_remote_list_devices", "arguments": {}}}
    request = urllib.request.Request(f"{base}/mcp", data=json.dumps(body).encode(),
                                     headers=headers, method="POST")
    try:
        response = urllib.request.urlopen(request, timeout=30)
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        return response.status, response.headers.get("WWW-Authenticate", ""), json.load(response)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url", nargs="?", default="https://mcp.nymrel.com")
    parser.add_argument("--remote-read", action="store_true", help="Check the activated private read catalog and OAuth metadata")
    parser.add_argument("--issuer", help="Exact expected OAuth issuer, including its published trailing slash")
    args = parser.parse_args()
    if args.remote_read and not args.issuer:
        parser.error("--remote-read requires --issuer")
    base = args.base_url.rstrip("/")
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
    expected = EXPECTED_TOOLS | REMOTE_TOOLS if args.remote_read else EXPECTED_TOOLS
    check("tools/list returns the expected catalog", names == expected, str(sorted(names)))
    for tool in tools:
        opaque = opaque_input_nodes(tool.get("inputSchema", {}))
        check(f"{tool['name']} schema is caller-completable", not opaque, ", ".join(opaque))
        annotations = tool.get("annotations") or {}
        check(
            f"{tool['name']} carries title + readOnlyHint",
            bool(annotations.get("title")) and "readOnlyHint" in annotations,
        )
        expected_schemes = (
            [{"type": "oauth2", "scopes": sorted(REMOTE_SCOPES)}]
            if tool["name"] in REMOTE_TOOLS else [{"type": "noauth"}]
        )
        schemes = tool.get("securitySchemes") or (tool.get("_meta") or {}).get("securitySchemes")
        check(f"{tool['name']} carries exact auth policy", schemes == expected_schemes)

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

    if args.remote_read:
        request = urllib.request.Request(f"{base}{REMOTE_METADATA}", method="GET")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                metadata = json.load(response)
            check("OAuth resource is the existing Nymrel app", metadata.get("resource") == REMOTE_RESOURCE)
            check("OAuth issuer matches exactly", metadata.get("authorization_servers") == [args.issuer])
            check("OAuth scopes are only the two reads", set(metadata.get("scopes_supported", [])) == REMOTE_SCOPES)
        except (urllib.error.URLError, ValueError) as exc:
            check("OAuth metadata is available", False, str(exc))

        for token, label in ((None, "private read requires caller OAuth"),
                             ("synthetic-invalid-contract-probe", "invalid token returns HTTP OAuth challenge")):
            try:
                status, header, payload = remote_auth_probe(base, token)
                denied = payload["result"]
                challenges = (denied.get("_meta") or {}).get("mcp/www_authenticate", [])
                challenged = (status == 401 and bool(denied.get("isError"))
                              and header in challenges and REMOTE_METADATA in header
                              and all(scope in header for scope in REMOTE_SCOPES)
                              and 'error="invalid_token"' in header and 'error_description="' in header)
            except (urllib.error.URLError, ValueError, KeyError):
                challenged = False
            check(label, challenged)
    else:
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
