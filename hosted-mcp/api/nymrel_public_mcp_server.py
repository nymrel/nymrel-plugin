#!/usr/bin/env python3
"""Public FastMCP facade for Nymrel's seven HTTP tool contracts.

This process is a transport adapter, not a second implementation of the tools.
It forwards validated inputs to the canonical Nymrel API and returns the API's
JSON unchanged. Provider failures fail closed; this module never fabricates
domain availability, player values, permit authorities, or scoring results.

v1.1 adds an honest failure contract on top of that: each failure carries its
own code, one plain sentence, and a ``retryable`` flag that is true only when a
retry can actually change the outcome.

v1.2 makes one deliberate exception to "transport only": ``audit-website``
falls back to a local audit (``native_audit``) when the upstream is absent, so
a publicly listed tool returns a real measured result instead of an error. The
fallback is measurement, not fabrication, and the upstream reclaims the call as
soon as it is deployed. No other tool has a local path.
"""

from __future__ import annotations

import math
import os
import re
from collections.abc import Callable, Mapping
from typing import Any, TypedDict
from urllib.parse import urljoin, urlparse

import requests
from fastmcp import FastMCP

try:  # packaged as api/ on Vercel, imported as a module in tests
    from . import native_audit
except ImportError:  # pragma: no cover - flat import path
    import native_audit


class _GolfClubRequired(TypedDict):
    """The keys the golf-bag-gap upstream requires for every club."""

    name: str
    carry_distance_yards: int


class GolfClub(_GolfClubRequired, total=False):
    """One club. ``loft_degrees`` is the only optional key the upstream allows.

    Declared as a type rather than a bare dict so the published tool schema
    names these keys. The upstream validates strictly and rejects any other
    key, so a caller that cannot see the contract cannot guess it.
    """

    loft_degrees: float


DEFAULT_BASE_URL = "https://nymrel.com/api/v1/tools/"
DEFAULT_TIMEOUT_SECONDS = 20.0
OPERATIONS = frozenset(
    {
        "audit-website",
        "find-domain",
        "evaluate-fantasy-trade",
        "golf-bag-gap",
        "local-permit-lookup",
        "social-clip-score",
        "submit-studio-brief",
    }
)
SAFE_ERROR_CODE = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")
HTTP_TRANSPORTS = frozenset({"http", "streamable-http"})

# --- error taxonomy ---------------------------------------------------------
#
# Every failure gets its own code and one plain sentence a non-developer can
# read, and `retryable` says what is actually true of that case. A deterministic
# failure marked retryable burns a caller's retry budget for nothing, so
# "retry will not help" cases are marked false even when they look transient.

MESSAGE_NOT_DEPLOYED = (
    "This Nymrel tool is still rolling out and is not answering yet, so nothing was returned - "
    "your request was fine, please check back soon."
)
MESSAGE_TIMEOUT = (
    "Nymrel did not answer in time, so no result came back - waiting a moment and asking again "
    "usually works."
)
MESSAGE_UNAVAILABLE = (
    "Nymrel could not be reached just now, so no result came back - try again in a minute."
)
MESSAGE_SERVER_ERROR = (
    "Nymrel ran into a problem on its own side and could not produce a result."
)
MESSAGE_MALFORMED = (
    "Nymrel sent back something this connector could not read, so nothing is being shown rather "
    "than a guess."
)
MESSAGE_RATE_LIMITED = (
    "Too many requests have gone to Nymrel in a short time - wait a moment and try again."
)
MESSAGE_REJECTED = (
    "Nymrel turned down this request - check the values you sent, and email contact@nymrel.com if "
    "it keeps happening."
)
MESSAGE_BAD_INPUT = (
    "Nymrel could not use the values in this request - check them and try again."
)
MESSAGE_UNKNOWN_TOOL = (
    "That tool is not part of the Nymrel tool suite, so there was nothing to call."
)
MESSAGE_INTAKE_NOT_CONFIGURED = (
    "Sending a studio brief is switched off on this server, so the brief was not delivered."
)

RETRYABLE_STATUS = frozenset({502, 503, 504})
NOT_DEPLOYED_STATUS = frozenset({404, 405})


class NymrelPublicApiError(RuntimeError):
    """Safe, public-facing failure from the HTTP transport boundary."""

    def __init__(self, code: str, message: str, *, status: int = 503, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.retryable = retryable

    def payload(self) -> dict[str, Any]:
        return {
            "status": "error",
            "error": {
                "code": self.code,
                "message": self.message,
                "retryable": self.retryable,
            },
        }


# --- input rules ------------------------------------------------------------
#
# Checked before the network call so a caller with a bad value gets INVALID_INPUT
# naming the field, instead of an upstream error that hides their own mistake.
# Kept on the client so the hosted wrappers in api/index.py inherit it too.

INPUT_RULES: dict[str, tuple[tuple[str, str, str], ...]] = {
    "audit-website": (
        ("url", "url", "Pass the full web address of the page, starting with https://."),
    ),
    "find-domain": (
        ("keyword_or_concept", "text", "Pass a word or short idea to build names from."),
        ("tlds", "optional_text_list", "Pass endings like .com or .io, or leave it out."),
    ),
    "evaluate-fantasy-trade": (
        ("side_a_players", "text_list", "Pass at least one player name for side A."),
        ("side_b_players", "text_list", "Pass at least one player name for side B."),
        ("league_format", "text", "Pass a league format such as dynasty or redraft."),
    ),
    "golf-bag-gap": (
        ("clubs", "record_list", "Pass at least one club, each with its name and carry distance."),
    ),
    "local-permit-lookup": (
        ("city_or_zip", "text", "Pass a city name or ZIP code."),
        ("trade_type", "text", "Pass a trade such as electrical or plumbing."),
    ),
    "social-clip-score": (
        ("transcript_text", "text", "Pass the words spoken in the clip."),
        ("target_platform", "text", "Pass a platform such as tiktok or reels."),
    ),
    "submit-studio-brief": (
        ("sender_name", "text", "Pass the name to show as the sender."),
        ("target_project", "text", "Pass the project the brief is for."),
        ("title", "text", "Pass a short title for the brief."),
        ("content_markdown", "text", "Pass the body of the brief."),
    ),
}


def _bad_input(field: str, problem: str, hint: str) -> NymrelPublicApiError:
    return NymrelPublicApiError(
        "INVALID_INPUT",
        f"The {field} value {problem}. {hint}",
        status=400,
    )


def _validate_payload(operation: str, payload: Mapping[str, Any]) -> None:
    for field, kind, hint in INPUT_RULES.get(operation, ()):
        value = payload.get(field)

        if kind == "optional_text_list" and value is None:
            continue

        if kind in {"text", "url"}:
            if not isinstance(value, str) or not value.strip():
                raise _bad_input(field, "is empty", hint)
            if kind == "url" and urlparse(value.strip()).scheme not in {"http", "https"}:
                raise _bad_input(field, "is not a web address", hint)
            continue

        if kind in {"text_list", "optional_text_list"}:
            if not isinstance(value, list) or not value:
                raise _bad_input(field, "is empty", hint)
            if any(not isinstance(item, str) or not item.strip() for item in value):
                raise _bad_input(field, "has a blank entry in it", hint)
            continue

        if kind == "record_list":
            if not isinstance(value, list) or not value:
                raise _bad_input(field, "is empty", hint)
            if any(not isinstance(item, Mapping) or not item for item in value):
                raise _bad_input(field, "has an entry with no details in it", hint)


def _normalise_base_url(value: str) -> str:
    candidate = value.strip().rstrip("/") + "/"
    parsed = urlparse(candidate)
    local_http = parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
    if parsed.scheme != "https" and not local_http:
        raise NymrelPublicApiError(
            "INVALID_API_BASE_URL",
            "The Nymrel API base URL must use HTTPS (localhost HTTP is allowed for tests).",
            status=500,
        )
    if not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise NymrelPublicApiError(
            "INVALID_API_BASE_URL",
            "The Nymrel API base URL is invalid.",
            status=500,
        )
    return candidate


def _safe_upstream_code(payload: object, default: str = "UPSTREAM_REJECTED") -> str:
    if not isinstance(payload, Mapping):
        return default
    error = payload.get("error")
    if not isinstance(error, Mapping):
        return default
    code = error.get("code")
    return str(code) if isinstance(code, str) and SAFE_ERROR_CODE.fullmatch(code) else default


def _looks_like_html(response: Any) -> bool:
    headers = getattr(response, "headers", None) or {}
    try:
        content_type = str(headers.get("content-type", ""))
    except AttributeError:
        content_type = ""
    return "text/html" in content_type.lower()


def _upstream_failure(status_code: int, body: object, parsed: bool) -> NymrelPublicApiError:
    """Map one upstream response onto the taxonomy, with retryable set honestly."""
    upstream_code = _safe_upstream_code(body, default="") if parsed else ""

    if status_code in NOT_DEPLOYED_STATUS and not upstream_code:
        # The route itself is missing, not the thing being asked about. Retrying
        # cannot deploy it, so this is deliberately not retryable.
        return NymrelPublicApiError(
            "UPSTREAM_NOT_DEPLOYED", MESSAGE_NOT_DEPLOYED, status=502, retryable=False
        )
    if status_code == 429:
        return NymrelPublicApiError(
            "UPSTREAM_RATE_LIMITED", MESSAGE_RATE_LIMITED, status=429, retryable=True
        )
    if 500 <= status_code < 600:
        return NymrelPublicApiError(
            upstream_code or "UPSTREAM_5XX",
            MESSAGE_SERVER_ERROR,
            status=status_code,
            retryable=status_code in RETRYABLE_STATUS,
        )
    if status_code in {400, 422}:
        return NymrelPublicApiError(
            upstream_code or "INVALID_INPUT",
            MESSAGE_BAD_INPUT,
            status=status_code,
            retryable=False,
        )
    return NymrelPublicApiError(
        upstream_code or "UPSTREAM_REJECTED",
        MESSAGE_REJECTED,
        status=status_code,
        retryable=False,
    )


def _normalise_timeout(value: float | str) -> float:
    try:
        timeout = float(value)
    except (TypeError, ValueError) as exc:
        raise NymrelPublicApiError(
            "INVALID_API_TIMEOUT",
            "The Nymrel API timeout is invalid.",
            status=500,
        ) from exc
    if not math.isfinite(timeout) or not 0 < timeout <= 120:
        raise NymrelPublicApiError(
            "INVALID_API_TIMEOUT",
            "The Nymrel API timeout must be between 0 and 120 seconds.",
            status=500,
        )
    return timeout


def _normalise_port(value: int | str) -> int:
    try:
        port = int(value)
    except (TypeError, ValueError) as exc:
        raise NymrelPublicApiError(
            "INVALID_MCP_PORT",
            "The Nymrel MCP port is invalid.",
            status=500,
        ) from exc
    if not 1 <= port <= 65_535:
        raise NymrelPublicApiError(
            "INVALID_MCP_PORT",
            "The Nymrel MCP port must be between 1 and 65535.",
            status=500,
        )
    return port


def _normalise_http_path(value: str) -> str:
    path = value.strip()
    if not path.startswith("/") or path.startswith("//") or "?" in path or "#" in path:
        raise NymrelPublicApiError(
            "INVALID_MCP_PATH",
            "The Nymrel MCP HTTP path is invalid.",
            status=500,
        )
    return path


class NymrelPublicApiClient:
    """Small injectable client used by both FastMCP tools and unit tests."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        bearer_token: str | None = None,
        timeout_seconds: float | None = None,
        requester: Callable[..., Any] = requests.request,
    ) -> None:
        self.base_url = _normalise_base_url(
            base_url or os.environ.get("NYMREL_PUBLIC_TOOLS_BASE_URL", DEFAULT_BASE_URL)
        )
        self.bearer_token = bearer_token if bearer_token is not None else os.environ.get("NYMREL_PUBLIC_TOOLS_TOKEN", "")
        self.timeout_seconds = _normalise_timeout(
            timeout_seconds
            if timeout_seconds is not None
            else os.environ.get("NYMREL_PUBLIC_TOOLS_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS)
        )
        self.requester = requester

    def call(self, operation: str, payload: Mapping[str, Any], *, require_auth: bool = False) -> dict[str, Any]:
        if operation not in OPERATIONS:
            raise NymrelPublicApiError("UNKNOWN_OPERATION", MESSAGE_UNKNOWN_TOOL, status=404)
        if require_auth and not self.bearer_token:
            raise NymrelPublicApiError(
                "INTAKE_AUTH_NOT_CONFIGURED",
                MESSAGE_INTAKE_NOT_CONFIGURED,
                status=503,
            )
        _validate_payload(operation, payload)

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "nymrel-public-fastmcp/1.0",
        }
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"

        try:
            response = self.requester(
                "POST",
                urljoin(self.base_url, operation),
                json=dict(payload),
                headers=headers,
                timeout=self.timeout_seconds,
            )
        except requests.Timeout as exc:
            raise NymrelPublicApiError(
                "UPSTREAM_TIMEOUT", MESSAGE_TIMEOUT, status=504, retryable=True
            ) from exc
        except requests.RequestException as exc:
            raise NymrelPublicApiError(
                "UPSTREAM_UNAVAILABLE", MESSAGE_UNAVAILABLE, status=503, retryable=True
            ) from exc

        status_code = int(response.status_code)

        # Parsed before the status check so an upstream error code survives, but
        # a parse failure is never fatal on its own - the status decides first.
        try:
            body: object = response.json()
            parsed = True
        except (TypeError, ValueError):
            body, parsed = None, False

        if not 200 <= status_code < 300:
            raise _upstream_failure(status_code, body, parsed)

        if not parsed or not isinstance(body, dict):
            # A 200 carrying an app shell instead of JSON is the same rolling-out
            # state as a 404, so say that rather than blaming the response shape.
            if _looks_like_html(response):
                raise NymrelPublicApiError(
                    "UPSTREAM_NOT_DEPLOYED", MESSAGE_NOT_DEPLOYED, status=502, retryable=False
                )
            raise NymrelPublicApiError(
                "UPSTREAM_MALFORMED", MESSAGE_MALFORMED, status=502, retryable=False
            )
        return body


def _client() -> NymrelPublicApiClient:
    return NymrelPublicApiClient()


def _call_tool(operation: str, payload: Mapping[str, Any], *, require_auth: bool = False) -> dict[str, Any]:
    """Return the API object itself.

    Returning a dict rather than a JSON string is what keeps the MCP result
    single-encoded: the client gets a real object in ``structuredContent`` and
    readable JSON in the text block, instead of JSON quoted inside JSON.
    """
    try:
        return _client().call(operation, payload, require_auth=require_auth)
    except NymrelPublicApiError as exc:
        return exc.payload()


mcp = FastMCP("Nymrel Public Tool Suite")


#: Upstream states that mean "nobody answered", as opposed to "the upstream
#: answered and said no". Only the former may fall back to the local audit.
_UPSTREAM_ABSENT = {
    "UPSTREAM_NOT_DEPLOYED",
    "UPSTREAM_UNAVAILABLE",
    "UPSTREAM_TIMEOUT",
    "UPSTREAM_5XX",
}


@mcp.tool(annotations={"title": "Audit website discoverability", "readOnlyHint": True, "openWorldHint": True})
def nymrel_audit_website(url: str) -> dict[str, Any]:
    """Audit one public website for SEO, schema, and AI discoverability.

    Fetches the page, its robots.txt, sitemap.xml and llms.txt, then reports a
    scored breakdown: which AI crawlers are named in robots, which JSON-LD
    types are present, and what to fix. Every field is measured from the
    response bytes.
    """
    result = _call_tool("audit-website", {"url": url})

    # While the upstream API is undeployed this tool answered with an error for
    # every caller, which makes a public listing a dead end. Serve the audit
    # locally instead; when the upstream lands it silently takes over again.
    if result.get("status") == "error":
        if str(result.get("error", {}).get("code")) in _UPSTREAM_ABSENT:
            try:
                return native_audit.audit_website(url)
            except native_audit.AuditInputError as exc:
                return NymrelPublicApiError(
                    "INVALID_INPUT", str(exc), status=400, retryable=False
                ).payload()
    return result


@mcp.tool(annotations={"title": "Find domain names", "readOnlyHint": True, "openWorldHint": True})
def nymrel_find_domain(keyword_or_concept: str, tlds: list[str] | None = None) -> dict[str, Any]:
    """Request verified domain suggestions from Nymrel DomainPilot.

    Each ``tlds`` entry must include the leading dot -- ".com", ".app" -- and at
    most six may be passed. An entry without the dot ("com") is rejected. Omit
    ``tlds`` entirely to search the default .com/.ai/.app/.io set.
    """
    payload: dict[str, Any] = {"keyword_or_concept": keyword_or_concept}
    if tlds is not None:
        payload["tlds"] = tlds
    return _call_tool("find-domain", payload)


@mcp.tool(annotations={"title": "Evaluate fantasy trade", "readOnlyHint": True, "openWorldHint": True})
def nymrel_evaluate_fantasy_trade(
    side_a_players: list[str],
    side_b_players: list[str],
    league_format: str = "dynasty",
) -> dict[str, Any]:
    """Evaluate a fantasy trade through the DraftADynasty-backed API."""
    return _call_tool(
        "evaluate-fantasy-trade",
        {
            "side_a_players": side_a_players,
            "side_b_players": side_b_players,
            "league_format": league_format,
        },
    )


@mcp.tool(annotations={"title": "Analyse golf bag gaps", "readOnlyHint": True, "openWorldHint": True})
def nymrel_golf_bag_gap(clubs: list[GolfClub]) -> dict[str, Any]:
    """Analyse carry-distance gaps for a structured list of golf clubs.

    Every club needs a ``name`` and its measured ``carry_distance_yards``;
    ``loft_degrees`` is optional. Pass 1 to 14 clubs with unique names. The
    upstream rejects any other key, so send only these three.
    """
    return _call_tool("golf-bag-gap", {"clubs": [dict(club) for club in clubs]})


@mcp.tool(annotations={"title": "Look up local permit authority", "readOnlyHint": True, "openWorldHint": True})
def nymrel_local_permit_lookup(city_or_zip: str, trade_type: str = "electrical") -> dict[str, Any]:
    """Look up a verified PNW permitting jurisdiction and portal."""
    return _call_tool(
        "local-permit-lookup",
        {"city_or_zip": city_or_zip, "trade_type": trade_type},
    )


@mcp.tool(annotations={"title": "Score a short-video hook", "readOnlyHint": True, "openWorldHint": True})
def nymrel_social_clip_score(transcript_text: str, target_platform: str = "tiktok") -> dict[str, Any]:
    """Score a social-video hook through the GoViral-backed API."""
    return _call_tool(
        "social-clip-score",
        {"transcript_text": transcript_text, "target_platform": target_platform},
    )


@mcp.tool(annotations={"title": "Submit a studio brief", "readOnlyHint": False, "destructiveHint": False, "openWorldHint": False})
def nymrel_submit_studio_brief(
    sender_name: str,
    target_project: str,
    title: str,
    content_markdown: str,
) -> dict[str, Any]:
    """Submit an authenticated collaboration brief to Nymrel Studio."""
    return _call_tool(
        "submit-studio-brief",
        {
            "sender_name": sender_name,
            "target_project": target_project,
            "title": title,
            "content_markdown": content_markdown,
        },
        require_auth=True,
    )


def run_server() -> None:
    """Run locally over stdio or as a stateless cloud HTTP service.

    ``NYMREL_MCP_TRANSPORT=http`` enables the remote endpoint used by the
    public installation guide. The default remains stdio for local clients.
    """
    transport = os.environ.get("NYMREL_MCP_TRANSPORT", "stdio").strip().lower()
    if transport == "stdio":
        mcp.run(transport="stdio")
        return
    if transport not in HTTP_TRANSPORTS:
        raise NymrelPublicApiError(
            "INVALID_MCP_TRANSPORT",
            "The Nymrel MCP transport must be stdio or HTTP.",
            status=500,
        )
    host = os.environ.get("NYMREL_MCP_HOST", "0.0.0.0").strip() or "0.0.0.0"
    port = _normalise_port(
        os.environ.get("NYMREL_MCP_PORT")
        or os.environ.get("PORT")
        or "8000"
    )
    path = _normalise_http_path(os.environ.get("NYMREL_MCP_PATH", "/mcp"))
    mcp.run(
        transport=transport,
        host=host,
        port=port,
        path=path,
        stateless_http=True,
        json_response=True,
    )


if __name__ == "__main__":
    run_server()
