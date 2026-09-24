#!/usr/bin/env python3
"""Run a bounded OAuth acceptance probe for the Nymrel Remote read tools.

This CLI is a transport-level check. It does not prove that a regular ChatGPT
conversation can select or complete the same read; that must be checked in
ChatGPT after activation.
"""

from __future__ import annotations

import argparse
import hashlib
import getpass
import json
import re
import sys
import time
import warnings
import urllib.error
import urllib.request

RESOURCE = "https://mcp.nymrel.com/mcp"
BASE_URL = "https://mcp.nymrel.com"
METADATA_URL = BASE_URL + "/.well-known/oauth-protected-resource/mcp"
READ_TOOL = "nymrel_remote_read_file"
DEVICES_TOOL = "nymrel_remote_list_devices"
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
    "MCP-Protocol-Version": "2026-07-28",
}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, newurl):
        return None


def _read_limited(response) -> bytes:
    raw = response.read(MAX_RESPONSE_BYTES + 1)
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError("response limit exceeded")
    return raw


def _json_payload(raw: bytes) -> dict:
    text = raw.decode("utf-8")
    for line in text.splitlines():
        line = line.removeprefix("data:").strip()
        if line.startswith("{"):
            return json.loads(line)
    return json.loads(text)


def metadata_matches(expected_issuer: str, metadata: dict) -> bool:
    return (
        metadata.get("resource") == RESOURCE
        and metadata.get("authorization_servers") == [expected_issuer]
        and set(metadata.get("scopes_supported", [])) == {"devices:read", "tools:read"}
    )


def call_tool(opener, token: str, name: str, arguments: dict) -> dict:
    body = json.dumps({
        "jsonrpc": "2.0",
        "id": "nymrel-acceptance-probe",
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    }).encode("utf-8")
    request = urllib.request.Request(
        BASE_URL + "/mcp",
        data=body,
        headers={**HEADERS, "Authorization": f"Bearer {token}"},
        method="POST",
    )
    with opener.open(request, timeout=35) as response:
        payload = _json_payload(_read_limited(response))
    if payload.get("jsonrpc") != "2.0" or payload.get("id") != "nymrel-acceptance-probe":
        raise ValueError("unexpected response")
    result = payload.get("result")
    if not isinstance(result, dict):
        raise ValueError("missing result")
    return result


def exact_device_id(result: dict, expected_name: str) -> str | None:
    """Return the ID for one exact isolated-device match; fail closed otherwise."""
    structured = result.get("structuredContent")
    devices = structured.get("devices") if isinstance(structured, dict) else None
    if not isinstance(devices, list):
        return None
    matches = [device for device in devices if isinstance(device, dict) and device.get("name") == expected_name]
    if len(matches) != 1:
        return None
    device = matches[0]
    identifier = device.get("id")
    return identifier if isinstance(identifier, str) and identifier else expected_name


def completed_read_matches(result: dict, expected_path: str, expected_sha256: str) -> bool:
    """Require a completed structured read for this exact path and content hash."""
    if result.get("isError"):
        return False
    data = result.get("structuredContent")
    if not isinstance(data, dict) or data.get("pending") is True:
        return False
    path = data.get("path")
    content = data.get("content")
    if path != expected_path or not isinstance(content, str):
        return False
    actual = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return actual == expected_sha256


def outside_allowed_directory_error(result: dict, denied_path: str) -> bool:
    """Require an error tied to this exact path and the specific boundary reason."""
    if not result.get("isError"):
        return False
    data = result.get("structuredContent")
    if not isinstance(data, dict) or data.get("path") != denied_path:
        return False
    code = data.get("errorCode")
    if code in ("PATH_OUTSIDE_ALLOWED_DIRECTORY", "OUTSIDE_ALLOWED_DIRECTORY"):
        return True
    # Some backends expose only a human-readable message. Accept only an
    # entire, anchored boundary reason; substrings in arbitrary errors or
    # echoed paths must never count as a path-policy denial.
    reason = data.get("message") or data.get("error")
    if not isinstance(reason, str):
        return False
    normalized = re.sub(r"[^a-z]+", " ", reason.lower()).strip()
    return normalized in {
        "outside allowed directory",
        "path outside allowed directory",
        "path is outside allowed directory",
        "path is outside the allowed directory",
    }


def read_hidden_token() -> str | None:
    """Read a bearer only when terminal echo can be reliably disabled."""
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        print("FAIL hidden token input requires an interactive terminal")
        return None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            token = getpass.getpass("Paste the short-lived OAuth access token (input hidden): ")
    except (getpass.GetPassWarning, EOFError, OSError):
        print("FAIL hidden token input unavailable; no credential was read")
        return None
    return token.strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--issuer", required=True, help="Exact published OAuth issuer, preserving trailing slash")
    parser.add_argument("--device-name", required=True, help="Exact isolated ChatGPTStudio device name from list_devices")
    parser.add_argument("--approved-path", required=True, help="Exact file path the user approved for this read")
    parser.add_argument("--denied-path", required=True, help="Parent or credential path that must be rejected")
    parser.add_argument("--expected-sha256", required=True, help="Expected SHA-256 of the approved UTF-8 file contents")
    parser.add_argument("--pending-checks", type=int, default=3, help="Maximum pending-result polls (default: 3; each waits two seconds)")
    args = parser.parse_args(argv)
    if (not args.approved_path or not args.denied_path or args.approved_path == args.denied_path
            or not args.device_name or not re.fullmatch(r"[0-9a-fA-F]{64}", args.expected_sha256)
            or args.pending_checks < 0 or args.pending_checks > 10):
        parser.error("approved and denied paths must be non-empty and distinct")

    opener = urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(urllib.request.Request(METADATA_URL, method="GET"), timeout=20) as response:
            metadata = json.loads(_read_limited(response))
    except Exception:  # Deliberately suppress request/response details.
        print("FAIL OAuth resource metadata could not be read")
        return 1
    if not metadata_matches(args.issuer, metadata):
        print("FAIL OAuth resource, exact issuer, or read scopes do not match")
        return 1
    print("ok   OAuth resource, exact issuer, and read scopes match")

    token = read_hidden_token()
    if not token:
        print("FAIL no access token supplied")
        return 1
    try:
        devices = call_tool(opener, token, DEVICES_TOOL, {})
        device_id = exact_device_id(devices, args.device_name)
        del devices
        if not device_id:
            print("FAIL one exact isolated ChatGPTStudio device was not found")
            return 1
        print("ok   exact isolated ChatGPTStudio device found")

        approved_args = {"path": args.approved_path, "device": device_id}
        approved = call_tool(opener, token, READ_TOOL, approved_args)
        data = approved.get("structuredContent") if isinstance(approved.get("structuredContent"), dict) else {}
        pending = data.get("pending") is True
        call_info = data.get("call")
        call_id = (call_info.get("id") if isinstance(call_info, dict) else None) or data.get("callId")
        if pending and isinstance(call_id, str) and call_id:
            del approved
            for _ in range(args.pending_checks):
                time.sleep(2)
                approved = call_tool(opener, token, "nymrel_remote_get_read_result", {"callId": call_id})
                data = approved.get("structuredContent") if isinstance(approved.get("structuredContent"), dict) else {}
                if data.get("pending") is not True:
                    break
        approved_ok = completed_read_matches(approved, args.approved_path, args.expected_sha256.lower())
        del approved, data, call_info, call_id, approved_args
        if pending and not approved_ok:
            print("not_validated approved read is still pending or did not match the expected result")
        else:
            print(f"{'ok  ' if approved_ok else 'FAIL'} approved read {'matched exact path and content hash' if approved_ok else 'did not match exact path and content hash'}")

        denied = call_tool(opener, token, READ_TOOL, {"path": args.denied_path, "device": device_id})
        denied_ok = outside_allowed_directory_error(denied, args.denied_path)
        del denied, device_id
        print(f"{'ok  ' if denied_ok else 'FAIL'} parent/credential path {'was rejected outside the allowed directory' if denied_ok else 'did not return the expected path-bound denial'}")
    except Exception:  # Do not expose the token, paths, file contents, or server errors.
        print("FAIL acceptance request did not complete; response details suppressed")
        return 1
    finally:
        # Python strings cannot be reliably zeroed, but drop our reference promptly.
        token = ""
    return 0 if approved_ok and denied_ok else 1


if __name__ == "__main__":
    sys.exit(main())
