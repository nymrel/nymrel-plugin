"""Published public result contracts; validate without rewriting measured data."""
from __future__ import annotations

import json
from functools import wraps
from typing import Annotated, Literal

from fastmcp.tools.tool import ToolResult
from mcp.types import CallToolResult
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, TypeAdapter, ValidationError


class EvidenceModel(BaseModel):
    # Preserve forward-compatible evidence, but never coerce a string into a
    # measurement or a truthy value into an availability assertion.
    model_config = ConfigDict(extra="allow", strict=True, allow_inf_nan=False)


Score = Annotated[float, Field(ge=0, le=100)]


class AuditSummary(EvidenceModel):
    score: Score
    grade: str
    ai_discoverability_status: str
    schema_detected: list[str]
    recommendations: list[str]
    full_report_url: str


class BrandabilityFactors(EvidenceModel):
    label_length: int
    contains_digit: bool
    contains_hyphen: bool
    contains_vowel: bool


class DomainSuggestion(EvidenceModel):
    domain: str
    available: bool
    availability_checked: bool
    brandability_score: Score
    brandability_factors: BrandabilityFactors


class DomainResult(EvidenceModel):
    suggestions: list[DomainSuggestion]


class GolfResult(EvidenceModel):
    average_gap_yards: Annotated[float, Field(ge=0)]
    problem_gaps: list[str]
    recommendations: list[str]


class ClipSignals(EvidenceModel):
    opening_word_count: Annotated[int, Field(ge=0)]
    opens_with_hook_pattern: bool
    addresses_viewer: bool
    has_curiosity_signal: bool
    opening_contains_number: bool
    total_word_count: Annotated[int, Field(ge=0)]
    platform_word_range: Annotated[list[int], Field(min_length=2, max_length=2)]
    total_word_count_in_platform_range: bool


class ClipResult(EvidenceModel):
    target_platform: Literal["tiktok", "instagram_reels", "youtube_shorts", "x"]
    hook_score: Score
    hook_strength: str
    signals: ClipSignals
    suggested_edits: list[str]


class ErrorDetail(EvidenceModel):
    code: str
    message: str
    retryable: bool


class ErrorResult(EvidenceModel):
    status: Literal["error"]
    error: ErrorDetail


class PublicToolResult(ToolResult):
    """Keep the wire error bit alongside text and structured error content."""
    _result: CallToolResult = PrivateAttr()

    def __init__(self, payload: dict, *, is_error: bool = False):
        result = CallToolResult(
            content=[{"type": "text", "text": json.dumps(payload, allow_nan=False)}],
            structuredContent=payload, isError=is_error,
        )
        super().__init__(content=result.content, structured_content=payload)
        self._result = result

    def to_mcp_result(self):
        return self._result


def output_schema(model: type[BaseModel]) -> dict:
    # MCP requires an object at the root, even for success/error alternatives.
    schema = TypeAdapter(model | ErrorResult).json_schema()
    definitions = schema.pop("$defs", {})

    def inline(node):
        if isinstance(node, list):
            return [inline(item) for item in node]
        if isinstance(node, dict):
            if "$ref" in node:
                # Our finite models use only local, non-recursive definitions.
                return inline(definitions[node["$ref"].removeprefix("#/$defs/")])
            return {key: inline(value) for key, value in node.items()}
        return node

    # FastMCP inlines these references on the wire. Publish that same reviewed
    # representation so the local and deployed schema checks compare like-for-like.
    return {"type": "object", **inline(schema)}


def validate_result(model: type[BaseModel], payload: object) -> PublicToolResult:
    is_error = isinstance(payload, dict) and payload.get("status") == "error"
    try:
        (ErrorResult if is_error else model).model_validate(payload)
        # Reject non-JSON extras as well. Never expose invalid upstream data or
        # Pydantic validation details (which can contain the original payload).
        json.dumps(payload, allow_nan=False)
    except (ValidationError, ValueError, TypeError):
        return PublicToolResult({"status": "error", "error": {
            "code": "INVALID_RESULT", "message": "Nymrel returned an incomplete or invalid result.",
            "retryable": False,
        }}, is_error=True)
    return PublicToolResult(payload, is_error=is_error)


def contract(model: type[BaseModel]):
    def decorate(function):
        @wraps(function)
        def validated(*args, **kwargs):
            return validate_result(model, function(*args, **kwargs))
        return validated
    return decorate
