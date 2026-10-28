#!/usr/bin/env python3
"""Offline, rule-based triage of supplied MCP configuration and log files.

This experiment does not launch a server, invoke a tool, install a package,
make a network request, or establish runtime or security correctness.
"""

from __future__ import annotations

import argparse
import html
import json
import math
import re
import shutil
import sys
from pathlib import Path
from typing import Any


MAX_INPUT_BYTES = 2 * 1024 * 1024
MAX_SERVERS = 100
RUNTIME_NAMES = frozenset({"node", "npx", "python", "python3", "uv", "uvx"})
LIMITS = [
    "This is static triage of supplied files, not a connection or security test.",
    "No server, command, package, or MCP tool is executed; no network is used.",
    "Rules can miss problems and can match unrelated messages in combined logs.",
    "No matched rule means not verified, not readiness or safety.",
    "Local runtime checks, when requested, inspect this host's PATH only; configured paths and environments are not tested.",
    "Reports omit raw names, arguments, environment values, endpoints, paths, and log excerpts. The original inputs remain local.",
]


class InputError(ValueError):
    """An error whose fixed message is suitable for the user-facing CLI."""


def read_text(path: Path, label: str) -> str:
    try:
        if not path.is_file():
            raise InputError(f"The supplied {label} must be a regular file.")
        with path.open("rb") as source:
            raw = source.read(MAX_INPUT_BYTES + 1)
    except InputError:
        raise
    except (OSError, ValueError):
        raise InputError(f"The supplied {label} could not be read.") from None
    if len(raw) > MAX_INPUT_BYTES:
        raise InputError(f"The supplied {label} exceeds the 2 MiB limit.")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeError:
        raise InputError(f"The supplied {label} must be valid UTF-8 text.") from None


def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise InputError("Configuration contains duplicate keys; resolve the ambiguity before analysis.")
        result[key] = value
    return result


def parse_config(text: str) -> dict[str, Any]:
    def reject_constant(value: str) -> None:
        raise InputError("Configuration must not contain nonfinite JSON constants.")

    def bounded_number(value: str) -> int | float:
        if len(value) > 1000:
            raise InputError("Configuration contains an unsupported numeric literal.")
        result = float(value) if any(char in value for char in ".eE") else int(value)
        if isinstance(result, float) and not math.isfinite(result):
            raise InputError("Configuration contains an unsupported numeric literal.")
        return result

    try:
        config = json.loads(text, object_pairs_hook=unique_pairs, parse_constant=reject_constant,
                            parse_int=bounded_number, parse_float=bounded_number)
    except InputError:
        raise
    except ValueError:
        raise InputError("Configuration is not valid JSON; check it locally before analysis.") from None
    except (RecursionError, OverflowError):
        raise InputError("Configuration nesting exceeds the supported limit.") from None
    if not isinstance(config, dict):
        raise InputError("Configuration must be a JSON object.")
    present = [name for name in ("mcpServers", "servers") if name in config]
    if len(present) != 1:
        raise InputError("Configuration must contain exactly one of mcpServers or servers.")
    servers = config[present[0]]
    if not isinstance(servers, dict):
        raise InputError("The server collection must be a JSON object.")
    if len(servers) > MAX_SERVERS:
        raise InputError("Configuration exceeds the supported limit of 100 server entries.")
    for server in servers.values():
        if not isinstance(server, dict):
            raise InputError("Each server entry must be a JSON object.")
        if "args" in server and (
            not isinstance(server["args"], list)
            or not all(isinstance(arg, str) for arg in server["args"])
        ):
            raise InputError("Server arguments must be an array of strings.")
        if "env" in server and (
            not isinstance(server["env"], dict)
            or not all(isinstance(value, str) for value in server["env"].values())
        ):
            raise InputError("Server environment values must be strings in an object.")
    return servers


def finding(code: str, scope: str, title: str, detail: str, next_step: str,
            severity: str = "warning") -> dict[str, str]:
    return {"code": code, "scope": scope, "severity": severity,
            "title": title, "detail": detail, "next_step": next_step}


def direct_package_pin(args: list[str], runner: str) -> bool:
    """Recognize only a deliberately small, direct runner syntax."""
    remaining = list(args)
    if runner in {"npm", "pipx"}:
        if not remaining or remaining.pop(0) not in {"exec", "run"}:
            return False
    if runner == "uv":
        if remaining[:2] != ["tool", "run"]:
            return False
        remaining = remaining[2:]
    while remaining and remaining[0] in {"-y", "--yes", "--"}:
        remaining.pop(0)
    if not remaining or remaining[0].startswith("-"):
        return False
    package = remaining[0]
    if runner in {"npx", "npm"}:
        return re.fullmatch(r"(?:@[\w.-]+/)?[\w.-]+@\d+\.\d+\.\d+", package) is not None
    return re.fullmatch(r"[\w.-]+==\d+\.\d+\.\d+", package) is not None


def analyze(servers: dict[str, Any], log: str = "", check_local_runtimes: bool = False) -> dict[str, Any]:
    findings: list[dict[str, str]] = []
    summaries: list[dict[str, str]] = []
    for index, server in enumerate(servers.values(), start=1):
        scope = f"server-{index}"
        command = server.get("command")
        endpoint = server.get("url")
        args = server.get("args", [])
        launch_kind = "unrecognized"
        runtime_state = "not-requested" if not check_local_runtimes else "not-checked"
        if command is not None and endpoint is not None:
            findings.append(finding("ambiguous-launch", scope, "Two launch forms are present",
                "This entry supplies both a command and an endpoint; this limited reader does not choose one.",
                "Confirm the intended transport using the host's current configuration documentation."))
        elif isinstance(command, str) and command.strip():
            launch_kind = "local-command"
            name = command.replace("\\", "/").rsplit("/", 1)[-1].lower().removesuffix(".exe")
            is_runner = name in {"npx", "uvx"} or (name == "npm" and args[:1] == ["exec"]) or (name == "pipx" and args[:1] == ["run"]) or (name == "uv" and args[:2] == ["tool", "run"])
            if is_runner:
                launch_kind = "package-runner"
                findings.append(finding("package-resolution", scope, "Package resolution may require setup and network access",
                    "The launch uses a package runner, which can resolve or install code depending on its cache and options. Server-internal installs are not determined by this scan.",
                    "Check the runner's cache, package source, exact version, and documented setup/egress requirements in the target environment."))
                if not direct_package_pin(args, name):
                    findings.append(finding("package-pin-unconfirmed", scope, "An exact package pin was not confirmed",
                        "The limited direct-runner syntax check did not recognize an exact version. This is not proof that the package is unpinned.",
                        "Review the launch syntax and lock/install procedure against the runner's documentation."))
            if check_local_runtimes and command in RUNTIME_NAMES:
                try:
                    present = shutil.which(command) is not None
                except OSError:
                    raise InputError("Local runtime lookup was unavailable.") from None
                runtime_state = "found-on-this-path" if present else "not-found-on-this-path"
                if not present:
                    findings.append(finding("local-runtime-not-found", scope, "A requested runtime name was not found on this host's PATH",
                        "The optional name lookup found no allowlisted executable. It did not inspect another machine, a configured executable path, or server-specific environment.",
                        "Check the intended host and documented runtime setup. This tool will not install or launch it."))
        elif isinstance(endpoint, str) and endpoint.strip():
            launch_kind = "remote-endpoint"
        else:
            findings.append(finding("unrecognized-launch", scope, "The launch form was not recognized",
                "This entry does not contain a supported nonempty command or endpoint. Host-specific fields may require a different reader.",
                "Compare the entry with the exact host's current schema; do not treat this report as a validation pass."))
        env = server.get("env", {})
        if env.get("NODE_TLS_REJECT_UNAUTHORIZED") == "0" or env.get("PYTHONHTTPSVERIFY") == "0":
            findings.append(finding("certificate-verification-config", scope, "Configuration requests disabled certificate verification",
                "A known environment flag that can disable verification is present. Its actual runtime effect is not tested.",
                "Have the responsible owner review the trusted certificate/proxy setup; this tool changes no configuration."))
        summaries.append({"id": scope, "launch_kind": launch_kind, "local_runtime_lookup": runtime_state})

    log_rules = [
        ("runtime-log-signal", r"(?:\b(?:node|npx|python3?|uvx)\b[^\n]{0,160}(?:ENOENT|not found|not recognized)|(?:ENOENT|not found|not recognized)[^\n]{0,160}\b(?:node|npx|python3?|uvx)\b)",
         "Log mentions a missing runtime", "The supplied text contains a missing-executable signal. It may describe a nested subprocess rather than the main server.",
         "Check which stage requested the executable and verify that stage's runtime requirements on the intended host."),
        ("certificate-log-signal", r"certificate verify failed|CERT_HAS_EXPIRED|SELF_SIGNED_CERT_IN_CHAIN|UNABLE_TO_VERIFY_LEAF_SIGNATURE|unable to get local issuer",
         "Log contains a certificate-verification failure", "A known certificate error string appears in the supplied text; its origin and current status are not verified.",
         "Ask the responsible owner to check the approved proxy and trusted CA chain. Do not bypass verification based on this report."),
        ("proxy-log-signal", r"proxy[^\n]{0,100}(?:denied|forbidden|407|blocked)|407[^\n]{0,60}proxy",
         "Log contains a proxy-denial signal", "The supplied text includes a possible proxy denial. Combined logs can contain unrelated events.",
         "Check the intended destination and the existing network policy through the authorized owner; no policy change is implied."),
        ("timeout-stage-unknown", r"\btimed?\s*out\b|\bETIMEDOUT\b|\btimeout\b",
         "A timeout does not locate the failing stage", "The supplied text mentions a timeout; it does not establish whether transport, HTTP, parsing, installation, or a subprocess stalled.",
         "Collect a minimized timeline for startup, network request, parsing/subprocess, and tool response before changing the timeout."),
    ]
    for code, pattern, title, detail, next_step in log_rules:
        if re.search(pattern, log, re.IGNORECASE):
            findings.append(finding(code, "supplied-log", title, detail, next_step))
    installer = re.search(r"added\s+\d+\s+packages|npm\s+(?:notice|warn)|Successfully installed", log, re.IGNORECASE)
    protocol = re.search(r"JSON-RPC|invalid JSON|unexpected token|parse error", log, re.IGNORECASE)
    if installer and protocol:
        findings.append(finding("installer-protocol-log-signal", "supplied-log", "Installer and protocol-error signals occur together",
            "The supplied text contains both installer messages and protocol/JSON errors. This is a hypothesis: combined stdout/stderr logs do not prove stream contamination.",
            "Verify which stream carried installer output and whether dependency installation occurred during startup or the tool call."))
    if re.search(r"registry\.npmjs\.org|pypi\.org", log, re.IGNORECASE) and re.search(r"ECONNREFUSED|ENETUNREACH|403|forbidden|network is unreachable|blocked", log, re.IGNORECASE):
        findings.append(finding("registry-egress-log-signal", "supplied-log", "Registry and network-denial signals occur together",
            "A package-registry reference and a denial signal appear in supplied text. Their causal relationship and current reachability are not verified.",
            "Check whether documented setup or a nested tool step needs registry access; confirm the existing policy with its owner."))
    return {"schema": "nymrel-mcp-preflight/0.1", "mode": "offline-static-triage",
            "assessment": "needs-investigation" if findings else "not-verified",
            "servers": summaries, "findings": findings, "limits": LIMITS,
            "exit_zero_means": "Analysis completed; it is not a readiness, safety, or connection result."}


def render_html(report: dict[str, Any]) -> str:
    esc = lambda value: html.escape(str(value), quote=True)
    cards = "".join(f"<article><p class='scope'>{esc(item['scope'])} · {esc(item['code'])}</p><h2>{esc(item['title'])}</h2><p>{esc(item['detail'])}</p><p><strong>Next:</strong> {esc(item['next_step'])}</p></article>" for item in report["findings"])
    if not cards:
        cards = "<article><h2>No configured rule matched</h2><p>This result is not verified. The tool did not test a connection, runtime behavior, package correctness, or security.</p></article>"
    limits = "".join(f"<li>{esc(item)}</li>" for item in report["limits"])
    rows = "".join(f"<tr><td>{esc(item['id'])}</td><td>{esc(item['launch_kind'])}</td><td>{esc(item['local_runtime_lookup'])}</td></tr>" for item in report["servers"])
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<meta name="referrer" content="no-referrer"><title>MCP preflight experiment — Nymrel</title>
<style>body{{max-width:850px;margin:0 auto;padding:28px 18px;background:#f3f4f1;color:#20312d;font:17px/1.6 system-ui,sans-serif}}h1{{line-height:1.2}}h2{{font-size:1.15rem}}article,aside{{background:white;border:1px solid #cbd5cf;border-radius:12px;padding:18px;margin:18px 0}}.scope{{font-size:.8rem;color:#425c50;overflow-wrap:anywhere}}table{{width:100%;border-collapse:collapse;font-size:.85rem}}td,th{{text-align:left;border-bottom:1px solid #cbd5cf;padding:8px;overflow-wrap:anywhere}}li{{margin:8px 0}}@media(max-width:420px){{body{{font-size:16px}}table{{font-size:.75rem}}td,th{{padding:5px}}}}</style></head>
<body><header><p>NYMREL · LOCAL PROTOTYPE</p><h1>Understand a possible MCP launch problem</h1><p><strong>{esc(report['assessment'])}</strong> · offline static triage</p><p>This experiment summarizes rule matches from supplied files. Findings suggest what to check next; they do not establish the cause or verify a fix.</p></header>
<main>{cards}<aside><h2>Configuration entries</h2><p>Entries use their original order. Names and values are deliberately omitted.</p><table><thead><tr><th>Entry</th><th>Launch form</th><th>Optional local lookup</th></tr></thead><tbody>{rows}</tbody></table></aside><aside><h2>What this report can establish</h2><ul>{limits}</ul><p>{esc(report['exit_zero_means'])}</p></aside></main></body></html>"""


def write_report(report: dict[str, Any], output: Path) -> None:
    created: list[Path] = []
    try:
        output.mkdir(mode=0o700, exist_ok=False)
    except (OSError, ValueError):
        raise InputError("Output must be a new directory with an existing writable parent; no existing path is overwritten.") from None
    try:
        for name, contents in (("report.json", json.dumps(report, indent=2, ensure_ascii=True) + "\n"), ("index.html", render_html(report))):
            path = output / name
            with path.open("x", encoding="utf-8") as target:
                created.append(path)
                target.write(contents)
    except OSError:
        for path in created:
            try:
                path.unlink()
            except OSError:
                pass
        try:
            output.rmdir()
        except OSError:
            pass
        raise InputError("Report creation failed; no existing output was overwritten.") from None


class PrivateArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise InputError("Invalid command-line arguments. Run --help for supported options.")


def main(argv: list[str] | None = None) -> int:
    parser = PrivateArgumentParser(prog="mcp-preflight", description=__doc__)
    parser.add_argument("--config", required=True, type=Path, help="Explicit UTF-8 MCP configuration file")
    parser.add_argument("--log", type=Path, help="Optional explicit UTF-8 log file")
    parser.add_argument("--check-local-runtimes", action="store_true", help="Look up allowlisted bare runtime names on this host's PATH; execute nothing")
    parser.add_argument("--output", required=True, type=Path, help="New output directory whose parent exists")
    try:
        args = parser.parse_args(argv)
        servers = parse_config(read_text(args.config, "configuration"))
        log = read_text(args.log, "log") if args.log is not None else ""
        report = analyze(servers, log, args.check_local_runtimes)
        write_report(report, args.output)
    except InputError as error:
        print(f"Analysis stopped: {error}", file=sys.stderr)
        return 2
    print("Analysis completed. Reports were created in the requested new directory; no connection or readiness result is implied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
