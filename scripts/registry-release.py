#!/usr/bin/env python3
"""Fail-closed checks for the fixed Nymrel MCP Registry listing release."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any


SERVER_NAME = "io.github.nymrel/nymrel"
SERVER_VERSION = "1.4.0"
SERVER_SHA256 = "f4115c767aa5ee0fb6eecbc428c4d9166538dca2a03ac9ad42e10409de7ebf6c"
SERVER_URL = "https://mcp.nymrel.com/mcp"
REPOSITORY = "nymrel/nymrel-plugin"


def verify_target(env: dict[str, str]) -> None:
    """Require an explicitly dispatched run against this repo's main branch."""
    if env.get("GITHUB_REPOSITORY") != REPOSITORY:
        raise ValueError("workflow target repository is not the approved source")
    if env.get("GITHUB_REF") != "refs/heads/main":
        raise ValueError("workflow target ref must be refs/heads/main")
    if env.get("GITHUB_EVENT_NAME") != "workflow_dispatch":
        raise ValueError("publication requires a manual workflow dispatch")
    sha = env.get("GITHUB_SHA", "")
    expected = env.get("EXPECTED_MAIN_SHA", "")
    if not re.fullmatch(r"[0-9a-f]{40}", sha) or expected != sha:
        raise ValueError("expected_main_sha must exactly match the dispatched full commit SHA")


def verify_source(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    # Normalize Windows checkout line endings to the canonical Git blob bytes.
    if b"\r" in raw.replace(b"\r\n", b""):
        raise ValueError("server.json contains noncanonical carriage returns")
    raw = raw.replace(b"\r\n", b"\n")
    digest = hashlib.sha256(raw).hexdigest()
    if digest != SERVER_SHA256:
        raise ValueError(f"server.json SHA-256 mismatch: {digest}")
    try:
        metadata = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("server.json is not valid UTF-8 JSON") from exc
    if not isinstance(metadata, dict):
        raise ValueError("server.json must contain a JSON object")
    if metadata.get("name") != SERVER_NAME or metadata.get("version") != SERVER_VERSION:
        raise ValueError("server.json name or version differs from the approved listing")
    remotes = metadata.get("remotes")
    if not isinstance(remotes, list) or not any(
        isinstance(remote, dict) and remote.get("url") == SERVER_URL for remote in remotes
    ):
        raise ValueError("server.json does not advertise the approved hosted endpoint")
    return metadata


def verify_listing(payload: Any) -> tuple[str, str, str]:
    """Validate public Registry readback, allowing the API's server envelope."""
    record = payload.get("server", payload) if isinstance(payload, dict) else None
    if not isinstance(record, dict):
        raise ValueError("Registry readback is not a server record")
    name, version = record.get("name"), record.get("version")
    if (name, version) != (SERVER_NAME, SERVER_VERSION):
        raise ValueError("Registry readback does not match the approved name and version")
    remotes = record.get("remotes")
    if not isinstance(remotes, list) or not any(
        isinstance(remote, dict) and remote.get("url") == SERVER_URL for remote in remotes
    ):
        raise ValueError("Registry readback endpoint differs from the approved hosted endpoint")
    return name, version, SERVER_URL


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("gate", help="validate the manual release target environment")
    source = sub.add_parser("source", help="validate the fixed server.json artifact")
    source.add_argument("path", type=Path)
    readback = sub.add_parser("readback", help="validate public Registry JSON")
    readback.add_argument("path", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "gate":
            verify_target(os.environ)
            print("Release target and expected main SHA verified.")
        elif args.command == "source":
            verify_source(args.path)
            print(f"Approved Registry metadata verified (SHA-256 {SERVER_SHA256}).")
        else:
            name, version, url = verify_listing(json.loads(args.path.read_text(encoding="utf-8")))
            line = f"MCP Registry listing verified: {name} {version} — {url}"
            summary = os.environ.get("GITHUB_STEP_SUMMARY")
            if summary:
                with Path(summary).open("a", encoding="utf-8") as stream:
                    stream.write(f"## MCP Registry publication receipt\n\n{line}\n")
            print(line)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"registry release check failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
