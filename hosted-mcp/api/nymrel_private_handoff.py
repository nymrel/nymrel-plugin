"""Private handoff tools for the hosted ``@Nymrel`` MCP surface.

This module is a transport adapter for the accepted Nymrel private-handoff
REST contract.  It never owns credentials, project policy, content custody, or
execution authority.  An injected FastMCP ``AuthProvider`` verifies the
caller's bearer token; the verified token is then forwarded to the REST API,
which remains authoritative for scopes and project allowlists.

The tools are dormant unless ``NYMREL_PRIVATE_HANDOFF_MCP_ENABLED`` is true.
They intentionally do not reuse ``NYMREL_PUBLIC_TOOLS_TOKEN`` and never accept
a bearer credential as a model-visible tool argument.
"""

from __future__ import annotations

import os
import re
from contextvars import ContextVar, Token
from collections.abc import Callable, Mapping
from typing import Annotated, Any, Literal
from urllib.parse import urlparse

import requests
from fastmcp.server.auth import JWTVerifier, RemoteAuthProvider
from fastmcp.server.dependencies import get_access_token
from fastmcp.tools.base import ToolResult
from mcp.types import CallToolResult
from pydantic import AnyHttpUrl, Field


FEATURE_ENV = "NYMREL_PRIVATE_HANDOFF_MCP_ENABLED"
API_URL_ENV = "NYMREL_PRIVATE_HANDOFF_API_URL"
TIMEOUT_ENV = "NYMREL_PRIVATE_HANDOFF_TIMEOUT_SECONDS"
OAUTH_ISSUER_ENV = "NYMREL_PRIVATE_HANDOFF_OAUTH_ISSUER"

DEFAULT_API_URL = "https://nymrel.com/api/agent/v1/handoffs"
DEFAULT_TIMEOUT_SECONDS = 20.0
CONTRACT_VERSION = "nymrel.private-handoff.v1"
MCP_BASE_URL = "https://mcp.nymrel.com"
MCP_RESOURCE_URL = f"{MCP_BASE_URL}/mcp"
RESOURCE_METADATA_URL = (
    "https://mcp.nymrel.com/.well-known/oauth-protected-resource/mcp"
)

CREATE_SCOPE = "handoff:create"
READ_SCOPE = "handoff:read_own"

PRIVATE_TOOL_NAMES = frozenset(
    {
        "nymrel_submit_private_handoff",
        "nymrel_get_private_handoff_status",
    }
)

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{15,127}$")
_HANDOFF_ID = re.compile(r"^nymh_[A-Za-z0-9_-]{24}$")
_SAFE_ERROR_CODE = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")
_PRIVATE_AUTH_AVAILABLE: ContextVar[bool] = ContextVar(
    "nymrel_private_auth_available",
    default=False,
)

Intent = Literal[
    "project_handoff",
    "clarification_request",
    "bug_report",
    "partner_request",
]
Urgency = Literal["urgent", "high", "normal", "low"]
RequestedAssignee = Literal["auto", "codex", "claude", "operator"]


def private_handoff_enabled() -> bool:
    """Return the explicit feature state; unknown values stay disabled."""
    return os.environ.get(FEATURE_ENV, "").strip().lower() in _TRUE_VALUES


def _normalise_oauth_issuer(value: str) -> str:
    issuer = value.strip().rstrip("/")
    parsed = urlparse(issuer)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port is not None
        or parsed.path
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        raise RuntimeError("The Nymrel private handoff OAuth issuer is invalid.")
    return issuer


def configured_private_auth_provider() -> RemoteAuthProvider:
    """Build direct JWT verification for a spec-compatible OAuth issuer.

    AuthKit owns login, consent, PKCE, CIMD/DCR, and token issuance. The MCP
    edge only advertises that issuer and verifies its RS256 JWTs for the exact
    MCP resource. Each private tool then enforces its own exact operation
    scope. No upstream client secret or shared service bearer token is used.
    """
    if not private_handoff_enabled():
        raise RuntimeError(f"Set {FEATURE_ENV}=true before configuring private auth.")
    raw_issuer = os.environ.get(OAUTH_ISSUER_ENV, "")
    if not raw_issuer.strip():
        raise RuntimeError(f"Set {OAUTH_ISSUER_ENV} before configuring private auth.")
    issuer = _normalise_oauth_issuer(raw_issuer)
    verifier = JWTVerifier(
        jwks_uri=f"{issuer}/oauth2/jwks",
        issuer=issuer,
        audience=MCP_RESOURCE_URL,
        algorithm="RS256",
        # Scope enforcement is per tool below. Requiring both scopes here
        # would reject a legitimate least-privilege token before its one tool
        # could inspect it, causing an authorization loop.
        required_scopes=None,
        ssrf_safe=True,
    )
    return RemoteAuthProvider(
        token_verifier=verifier,
        authorization_servers=[AnyHttpUrl(issuer)],
        base_url=MCP_BASE_URL,
        scopes_supported=[CREATE_SCOPE, READ_SCOPE],
        resource_name="Nymrel private handoff",
        resource_documentation=AnyHttpUrl("https://nymrel.com/mcp"),
    )


def _feature_enabled_for_request(_context: Any) -> bool:
    """FastMCP visibility guard used independently of caller authentication."""
    return private_handoff_enabled() and _PRIVATE_AUTH_AVAILABLE.get()


def enter_private_auth_context() -> Token[bool]:
    """Mark one request as running behind injected provider middleware."""
    return _PRIVATE_AUTH_AVAILABLE.set(True)


def exit_private_auth_context(token: Token[bool]) -> None:
    _PRIVATE_AUTH_AVAILABLE.reset(token)


class NymrelPrivateHandoffError(RuntimeError):
    """Body-safe failure at the private handoff transport boundary."""

    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
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


class OAuthChallengeResult(ToolResult):
    """Tool error that preserves FastMCP serialization plus OAuth metadata."""

    def to_mcp_result(self) -> CallToolResult:
        return CallToolResult(
            content=self.content,
            structuredContent=self.structured_content,
            isError=True,
            _meta=self.meta,
        )


def _normalise_api_url(value: str) -> str:
    url = value.strip().rstrip("/")
    parsed = urlparse(url)
    if (
        url != DEFAULT_API_URL
        or parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port is not None
        or parsed.query
        or parsed.fragment
        or parsed.path != "/api/agent/v1/handoffs"
    ):
        raise NymrelPrivateHandoffError(
            "INVALID_PRIVATE_HANDOFF_API_URL",
            "The Nymrel private handoff API URL is invalid.",
        )
    return url


def _normalise_timeout(value: float | str) -> float:
    try:
        timeout = float(value)
    except (TypeError, ValueError) as exc:
        raise NymrelPrivateHandoffError(
            "INVALID_PRIVATE_HANDOFF_TIMEOUT",
            "The Nymrel private handoff timeout is invalid.",
        ) from exc
    if not 0 < timeout <= 120:
        raise NymrelPrivateHandoffError(
            "INVALID_PRIVATE_HANDOFF_TIMEOUT",
            "The Nymrel private handoff timeout must be between 0 and 120 seconds.",
        )
    return timeout


def _error_from_status(status: int, body: object) -> NymrelPrivateHandoffError:
    upstream_code = ""
    if isinstance(body, Mapping):
        error = body.get("error")
        if isinstance(error, Mapping):
            candidate = error.get("code")
            if isinstance(candidate, str) and _SAFE_ERROR_CODE.fullmatch(candidate):
                upstream_code = candidate

    defaults: dict[int, tuple[str, str, bool]] = {
        400: (
            "INVALID_HANDOFF_REQUEST",
            "Nymrel rejected the handoff request; check the named fields and try again.",
            False,
        ),
        401: (
            "HANDOFF_AUTH_REQUIRED",
            "The connected Nymrel account is not authorized for private handoffs.",
            False,
        ),
        403: (
            "HANDOFF_SCOPE_DENIED",
            "The connected Nymrel account cannot use that project or operation.",
            False,
        ),
        404: (
            "HANDOFF_NOT_FOUND",
            "No owned private handoff receipt was found for that identifier.",
            False,
        ),
        409: (
            "IDEMPOTENCY_CONFLICT",
            "That idempotency key is already bound to a different handoff.",
            False,
        ),
        413: (
            "HANDOFF_TOO_LARGE",
            "The private handoff text is too large to accept.",
            False,
        ),
        415: (
            "UNSUPPORTED_MEDIA_TYPE",
            "Nymrel accepts private handoffs as JSON text only.",
            False,
        ),
        422: (
            "INVALID_HANDOFF_REQUEST",
            "Nymrel could not use one or more handoff fields.",
            False,
        ),
        429: (
            "HANDOFF_RATE_LIMITED",
            "Too many private handoff requests were received; wait before retrying.",
            True,
        ),
    }
    if status in defaults:
        default_code, message, retryable = defaults[status]
        return NymrelPrivateHandoffError(
            upstream_code or default_code,
            message,
            retryable=retryable,
        )
    if status >= 500:
        return NymrelPrivateHandoffError(
            upstream_code or "PRIVATE_HANDOFF_UNAVAILABLE",
            "Nymrel could not accept or read the private handoff just now.",
            retryable=True,
        )
    return NymrelPrivateHandoffError(
        upstream_code or "PRIVATE_HANDOFF_REJECTED",
        "Nymrel rejected the private handoff request.",
    )


def _require_string(body: Mapping[str, Any], field: str) -> str:
    value = body.get(field)
    if not isinstance(value, str) or not value:
        raise NymrelPrivateHandoffError(
            "PRIVATE_HANDOFF_MALFORMED",
            "Nymrel returned a malformed private handoff receipt.",
        )
    return value


def _require_nonnegative_int(body: Mapping[str, Any], field: str) -> int:
    value = body.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise NymrelPrivateHandoffError(
            "PRIVATE_HANDOFF_MALFORMED",
            "Nymrel returned a malformed private handoff receipt.",
        )
    return value


def _sanitise_receipt(body: object) -> dict[str, Any]:
    """Allow only body-free receipt metadata across the MCP boundary."""
    if not isinstance(body, Mapping):
        raise NymrelPrivateHandoffError(
            "PRIVATE_HANDOFF_MALFORMED",
            "Nymrel returned a malformed private handoff receipt.",
        )

    redactions = body.get("redactions")
    if not isinstance(redactions, Mapping):
        raise NymrelPrivateHandoffError(
            "PRIVATE_HANDOFF_MALFORMED",
            "Nymrel returned a malformed private handoff receipt.",
        )
    safe_redactions = {
        field: _require_nonnegative_int(redactions, field)
        for field in ("api_keys", "emails", "phone_numbers", "private_keys")
    }

    reason_codes = body.get("reason_codes")
    if not isinstance(reason_codes, list) or not all(
        isinstance(code, str) for code in reason_codes
    ):
        raise NymrelPrivateHandoffError(
            "PRIVATE_HANDOFF_MALFORMED",
            "Nymrel returned a malformed private handoff receipt.",
        )

    if body.get("content_storage") != "application-encrypted":
        raise NymrelPrivateHandoffError(
            "PRIVATE_HANDOFF_MALFORMED",
            "Nymrel returned a malformed private handoff receipt.",
        )

    return {
        "content_bytes": _require_nonnegative_int(body, "content_bytes"),
        "redactions": safe_redactions,
        "attempts": _require_nonnegative_int(body, "attempts"),
        "reason_codes": list(reason_codes),
        "content_storage": "application-encrypted",
    }


def _sanitise_status(body: object, *, submission: bool) -> dict[str, Any]:
    """Strip every field outside the accepted body-free status contract."""
    if not isinstance(body, Mapping):
        raise NymrelPrivateHandoffError(
            "PRIVATE_HANDOFF_MALFORMED",
            "Nymrel returned a malformed private handoff receipt.",
        )
    if body.get("contract_version") != CONTRACT_VERSION:
        raise NymrelPrivateHandoffError(
            "PRIVATE_HANDOFF_MALFORMED",
            "Nymrel returned a malformed private handoff receipt.",
        )

    handoff_id = _require_string(body, "handoff_id")
    if not _HANDOFF_ID.fullmatch(handoff_id):
        raise NymrelPrivateHandoffError(
            "PRIVATE_HANDOFF_MALFORMED",
            "Nymrel returned a malformed private handoff receipt.",
        )
    status = _require_string(body, "status")
    if status not in {"queued", "retrying", "delivered", "rejected"}:
        raise NymrelPrivateHandoffError(
            "PRIVATE_HANDOFF_MALFORMED",
            "Nymrel returned a malformed private handoff receipt.",
        )

    safe: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION,
        "handoff_id": handoff_id,
        "status": status,
        "target_project": _require_string(body, "target_project"),
        "received_at": _require_string(body, "received_at"),
        "updated_at": _require_string(body, "updated_at"),
        "receipt": _sanitise_receipt(body.get("receipt")),
    }
    delivered_at = body.get("delivered_at")
    if delivered_at is not None:
        if not isinstance(delivered_at, str) or not delivered_at:
            raise NymrelPrivateHandoffError(
                "PRIVATE_HANDOFF_MALFORMED",
                "Nymrel returned a malformed private handoff receipt.",
            )
        safe["delivered_at"] = delivered_at

    replay = body.get("idempotent_replay")
    if submission and not isinstance(replay, bool):
        raise NymrelPrivateHandoffError(
            "PRIVATE_HANDOFF_MALFORMED",
            "Nymrel returned a malformed private handoff receipt.",
        )
    if isinstance(replay, bool):
        safe["idempotent_replay"] = replay

    status_path = body.get("status_path")
    if submission and (not isinstance(status_path, str) or not status_path):
        raise NymrelPrivateHandoffError(
            "PRIVATE_HANDOFF_MALFORMED",
            "Nymrel returned a malformed private handoff receipt.",
        )
    if isinstance(status_path, str) and status_path:
        safe["status_path"] = status_path
    return safe


class NymrelPrivateHandoffClient:
    """Injectable, token-per-call client for the authoritative REST API."""

    def __init__(
        self,
        *,
        api_url: str | None = None,
        timeout_seconds: float | None = None,
        requester: Callable[..., Any] = requests.request,
    ) -> None:
        self.api_url = _normalise_api_url(
            api_url or os.environ.get(API_URL_ENV, DEFAULT_API_URL)
        )
        self.timeout_seconds = _normalise_timeout(
            timeout_seconds
            if timeout_seconds is not None
            else os.environ.get(TIMEOUT_ENV, DEFAULT_TIMEOUT_SECONDS)
        )
        self.requester = requester

    def _request(
        self,
        method: str,
        url: str,
        *,
        bearer_token: str,
        payload: Mapping[str, Any] | None = None,
        idempotency_key: str | None = None,
        submission: bool,
    ) -> dict[str, Any]:
        if not bearer_token:
            raise NymrelPrivateHandoffError(
                "HANDOFF_AUTH_REQUIRED",
                "Connect an approved Nymrel account before using private handoffs.",
            )
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {bearer_token}",
            "User-Agent": "nymrel-private-handoff-mcp/1.0",
        }
        kwargs: dict[str, Any] = {
            "headers": headers,
            "timeout": self.timeout_seconds,
            # Never resend client content or credentials to a redirected
            # origin. A redirect is a contract failure, not navigation.
            "allow_redirects": False,
        }
        if payload is not None:
            headers["Content-Type"] = "application/json"
            kwargs["json"] = dict(payload)
        if idempotency_key is not None:
            headers["Idempotency-Key"] = idempotency_key

        try:
            response = self.requester(method, url, **kwargs)
        except requests.Timeout as exc:
            raise NymrelPrivateHandoffError(
                "PRIVATE_HANDOFF_TIMEOUT",
                "Nymrel did not answer the private handoff request in time.",
                retryable=True,
            ) from exc
        except requests.RequestException as exc:
            raise NymrelPrivateHandoffError(
                "PRIVATE_HANDOFF_UNAVAILABLE",
                "Nymrel could not be reached for the private handoff request.",
                retryable=True,
            ) from exc

        try:
            body: object = response.json()
        except (TypeError, ValueError):
            body = None
        status = int(response.status_code)
        if not 200 <= status < 300:
            raise _error_from_status(status, body)
        return _sanitise_status(body, submission=submission)

    def submit(
        self,
        *,
        bearer_token: str,
        idempotency_key: str,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        if not _IDEMPOTENCY_KEY.fullmatch(idempotency_key):
            raise NymrelPrivateHandoffError(
                "INVALID_IDEMPOTENCY_KEY",
                "Use a stable 16 to 128 character idempotency key for this handoff.",
            )
        return self._request(
            "POST",
            self.api_url,
            bearer_token=bearer_token,
            payload=payload,
            idempotency_key=idempotency_key,
            submission=True,
        )

    def status(self, *, bearer_token: str, handoff_id: str) -> dict[str, Any]:
        if not _HANDOFF_ID.fullmatch(handoff_id):
            raise NymrelPrivateHandoffError(
                "INVALID_HANDOFF_ID",
                "Use the private handoff identifier returned by Nymrel.",
            )
        return self._request(
            "GET",
            f"{self.api_url}/{handoff_id}",
            bearer_token=bearer_token,
            submission=False,
        )


def _client() -> NymrelPrivateHandoffClient:
    return NymrelPrivateHandoffClient()


def _auth_failure(required_scope: str) -> ToolResult:
    payload = NymrelPrivateHandoffError(
        "HANDOFF_AUTH_REQUIRED",
        "Connect an approved Nymrel account before using private handoffs.",
    ).payload()
    challenge = (
        f'Bearer resource_metadata="{RESOURCE_METADATA_URL}", '
        'error="insufficient_scope", '
        'error_description="Connect an approved Nymrel account with the required permission", '
        f'scope="{required_scope}"'
    )
    return OAuthChallengeResult(
        structured_content=payload,
        meta={"mcp/www_authenticate": [challenge]},
    )


def _verified_bearer(required_scope: str) -> str | None:
    token = get_access_token()
    if token is None or required_scope not in set(token.scopes):
        return None
    return token.token


def _security_meta(scope: str) -> dict[str, Any]:
    # The list-tools adapter mirrors this value to the descriptor's required
    # top-level field while retaining `_meta` for older clients.
    return {"securitySchemes": [{"type": "oauth2", "scopes": [scope]}]}


def register_private_handoff_tools(mcp: Any) -> None:
    """Register exactly two feature-gated private tools on a FastMCP server."""

    @mcp.tool(
        name="nymrel_submit_private_handoff",
        auth=_feature_enabled_for_request,
        meta=_security_meta(CREATE_SCOPE),
        annotations={
            "title": "Submit a private Nymrel handoff",
            "readOnlyHint": False,
            "destructiveHint": False,
            "openWorldHint": True,
            "idempotentHint": True,
        },
    )
    def nymrel_submit_private_handoff(
        idempotency_key: Annotated[
            str,
            Field(
                min_length=16,
                max_length=128,
                pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{15,127}$",
                description=(
                    "A caller-generated value that stays unchanged when retrying "
                    "this exact handoff."
                ),
            ),
        ],
        target_project: Annotated[
            str,
            Field(
                min_length=1,
                max_length=100,
                pattern=r"^[A-Za-z0-9][A-Za-z0-9 ._-]{0,99}$",
                description="One project approved for the connected Nymrel account.",
            ),
        ],
        intent: Intent,
        title: Annotated[str, Field(min_length=5, max_length=140)],
        content_markdown: Annotated[
            str,
            Field(
                min_length=1,
                max_length=100_000,
                description=(
                    "Text-only project context. Never include passwords, provider "
                    "credentials, API keys, or other secrets."
                ),
            ),
        ],
        summary: Annotated[str | None, Field(min_length=1, max_length=2_000)] = None,
        urgency: Urgency = "normal",
        requested_assignee: RequestedAssignee = "auto",
    ) -> dict[str, Any]:
        """Queue an approved text-only handoff for Nymrel studio review.

        Call only after the user explicitly confirms the project, content, and
        submission.  This consequential action creates a review-queue receipt;
        it does not authorize an agent, execute work, fetch URLs, or accept files.
        """
        bearer = _verified_bearer(CREATE_SCOPE)
        if bearer is None:
            return _auth_failure(CREATE_SCOPE)  # type: ignore[return-value]
        payload: dict[str, Any] = {
            "contract_version": CONTRACT_VERSION,
            "target_project": target_project,
            "intent": intent,
            "title": title,
            "content_markdown": content_markdown,
            "urgency": urgency,
            "requested_assignee": requested_assignee,
        }
        if summary is not None:
            payload["summary"] = summary
        try:
            return _client().submit(
                bearer_token=bearer,
                idempotency_key=idempotency_key,
                payload=payload,
            )
        except NymrelPrivateHandoffError as exc:
            return exc.payload()

    @mcp.tool(
        name="nymrel_get_private_handoff_status",
        auth=_feature_enabled_for_request,
        meta=_security_meta(READ_SCOPE),
        annotations={
            "title": "Read a private Nymrel handoff receipt",
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": True,
            "idempotentHint": True,
        },
    )
    def nymrel_get_private_handoff_status(
        handoff_id: Annotated[
            str,
            Field(
                pattern=r"^nymh_[A-Za-z0-9_-]{24}$",
                description="A private handoff identifier returned to this caller.",
            ),
        ],
    ) -> dict[str, Any]:
        """Read the owned, body-free receipt for one private handoff.

        The result contains status and receipt metadata only; it never returns
        the submitted project text, prompts, outputs, files, or credentials.
        """
        bearer = _verified_bearer(READ_SCOPE)
        if bearer is None:
            return _auth_failure(READ_SCOPE)  # type: ignore[return-value]
        try:
            return _client().status(bearer_token=bearer, handoff_id=handoff_id)
        except NymrelPrivateHandoffError as exc:
            return exc.payload()
