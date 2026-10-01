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
    parser.add_argument("--public-results", action="store_true", help="Require the new explicit public output contracts")
    parser.add_argument("--audit-ui", action="store_true", help="Require the activated audit app and its resource (implies --public-results)")
    parser.add_argument("--tools-ui", action="store_true", help="Require global/thread public workbench and its bundled resource (implies --public-results)")
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
    if args.audit_ui:
        expected = expected | {"nymrel_render_website_audit"}
    if args.tools_ui:
        expected = expected | {"nymrel_open_tools"}
    check("tools/list returns the expected catalog", names == expected and len(tools) == len(expected), str(sorted(names)))
    for tool in tools:
        opaque = opaque_input_nodes(tool.get("inputSchema", {}))
        check(f"{tool['name']} schema is caller-completable", not opaque, ", ".join(opaque))
        annotations = tool.get("annotations") or {}
        check(
            f"{tool['name']} carries exact read-only annotations",
            bool(annotations.get("title"))
            and annotations.get("readOnlyHint") is True
            and annotations.get("destructiveHint") is False
            and annotations.get("openWorldHint") is (
                tool["name"] in {"nymrel_audit_website", "nymrel_find_domain"}
            ),
        )
        expected_schemes = (
            [{"type": "oauth2", "scopes": sorted(REMOTE_SCOPES)}]
            if tool["name"] in REMOTE_TOOLS else [{"type": "noauth"}]
        )
        # Both published fields are part of Nymrel's host compatibility contract.
        # A fallback would conceal a missing top-level field or a stale mirror.
        schemes = tool.get("securitySchemes")
        mirror = (tool.get("_meta") or {}).get("securitySchemes")
        check(f"{tool['name']} carries exact auth policy", schemes == expected_schemes and mirror == expected_schemes)

    if args.public_results or args.audit_ui or args.tools_ui:
        import public_results
        models = {
            "nymrel_audit_website": public_results.AuditSummary,
            "nymrel_find_domain": public_results.DomainResult,
            "nymrel_golf_bag_gap": public_results.GolfResult,
            "nymrel_social_clip_score": public_results.ClipResult,
        }
        for tool in tools:
            if tool["name"] in models:
                check(f"{tool['name']} publishes the reviewed output schema",
                      tool.get("outputSchema") == public_results.output_schema(models[tool["name"]]))
                check(f"{tool['name']} stays separate from presentation", "ui" not in (tool.get("_meta") or {}))

    if args.audit_ui:
        import audit_ui
        render = next((tool for tool in tools if tool["name"] == audit_ui.TOOL_NAME), {})
        check("audit render tool links the MCP App", (render.get("_meta") or {}).get("ui", {}).get("resourceUri") == audit_ui.RESOURCE_URI)
        contents = rpc(base, "resources/read", {"uri": audit_ui.RESOURCE_URI}).get("result", {}).get("contents", [])
        resource = contents[0] if contents else {}
        check("audit resource serves the app without external network access",
              resource.get("mimeType") == audit_ui.MIME_TYPE
              and "ui/initialize" in resource.get("text", "")
              and (resource.get("_meta") or {}).get("ui", {}).get("csp") == {"connectDomains": [], "resourceDomains": []})
        fixture = {"score": 72, "grade": "C", "ai_discoverability_status": "PARTIAL",
                   "schema_detected": [], "recommendations": ["Synthetic release check."],
                   "full_report_url": "https://nymrel.com/site-audit"}
        rendered = rpc(base, "tools/call", {"name": audit_ui.TOOL_NAME, "arguments": {
            "requested_url": "https://example.com", "report": fixture}}).get("result", {})
        check("audit render preserves synthetic evidence", not rendered.get("isError")
              and rendered.get("structuredContent") == {"requested_url": "https://example.com", "report": fixture})

    if args.tools_ui:
        import workbench_ui
        opener = next((tool for tool in tools if tool["name"] == workbench_ui.TOOL_NAME), {})
        meta = opener.get("_meta") or {}
        check("workbench advertises global and thread entrypoints",
              meta.get("openai/ui", {}).get("entrypoints") == [{"type": "global"}, {"type": "thread"}]
              and meta.get("ui", {}).get("resourceUri") == workbench_ui.RESOURCE_URI
              and bool(opener.get("icons")))
        opened = rpc(base, "tools/call", {"name": workbench_ui.TOOL_NAME, "arguments": {}}).get("result", {})
        catalog = opened.get("structuredContent") or {}
        check("empty-argument launch returns only the public workbench",
              not opened.get("isError") and catalog.get("version") == "1.0"
              and catalog.get("default_tool") == "website"
              and {tool.get("name") for tool in catalog.get("tools", [])} == EXPECTED_TOOLS)
        contents = rpc(base, "resources/read", {"uri": workbench_ui.RESOURCE_URI}).get("result", {}).get("contents", [])
        resource = contents[0] if contents else {}
        resource_meta = resource.get("_meta") or {}
        check("workbench resource is fullscreen and contains the bundled app",
              resource.get("mimeType") == workbench_ui.MIME_TYPE
              and "Nymrel tool workbench" in resource.get("text", "")
              and resource_meta.get("openai/ui") == workbench_ui.DISPLAY_META
              and resource_meta.get("ui", {}).get("csp") == {"connectDomains": [], "resourceDomains": []})

    # 3. The golf contract round-trips: the documented shape is accepted and
    #    a wrong key is rejected by the schema layer, naming the field.
    good = rpc(base, "tools/call", {
        "name": "nymrel_golf_bag_gap",
        "arguments": {"clubs": [
            {"name": "7 iron", "carry_distance_yards": 150},
            {"name": "9 iron", "carry_distance_yards": 128},
        ]},
    })["result"]
    good_text = next((item.get("text", "") for item in good.get("content", [])
                      if item.get("type") == "text"), "")
    try:
        good_payload = json.loads(good_text)
    except (TypeError, ValueError):
        good_payload = None
    structured = good.get("structuredContent")
    # This fixed fixture has an exact answer. A field name in an error message
    # or a contradictory structured result is not successful execution.
    good_result = (
        isinstance(good_payload, dict)
        and type(good_payload.get("average_gap_yards")) in (int, float)
        and good_payload["average_gap_yards"] == 22
        and isinstance(good_payload.get("problem_gaps"), list)
        and isinstance(good_payload.get("recommendations"), list)
        and (structured is None or structured == good_payload)
    )
    check(
        "golf accepts the documented shape",
        not good.get("isError") and good_result,
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
