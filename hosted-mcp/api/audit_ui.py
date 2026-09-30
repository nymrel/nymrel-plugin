"""A separately activated, read-only MCP App for completed public audits."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

from pydantic import Field

from public_results import AuditSummary, EvidenceModel

FEATURE_ENV = "NYMREL_AUDIT_UI_ENABLED"
TOOL_NAME = "nymrel_render_website_audit"
RESOURCE_URI = "ui://nymrel/website-audit-v1.html"
MIME_TYPE = "text/html;profile=mcp-app"


def enabled(_context=None):
    return os.environ.get(FEATURE_ENV, "").strip().lower() in {"true", "1", "yes", "on"}


def register(mcp):
    @mcp.resource(
        RESOURCE_URI, name="Nymrel website audit", mime_type=MIME_TYPE,
        auth=enabled,
        meta={"ui": {"prefersBorder": True, "csp": {"connectDomains": [], "resourceDomains": []}}},
    )
    def audit_widget() -> str:
        return Path(__file__).with_name("assets").joinpath("audit-widget.html").read_text(encoding="utf-8")

    @mcp.tool(
        name=TOOL_NAME, auth=enabled,
        annotations={"title": "Show website audit", "readOnlyHint": True,
                     "openWorldHint": False, "destructiveHint": False},
        meta={"ui": {"resourceUri": RESOURCE_URI, "visibility": ["model", "app"]}},
    )
    def render_website_audit(
        report: AuditSummary,
        requested_url: Annotated[str, Field(pattern=r"^https?://[^\s]+$", max_length=2048)],
    ) -> AuditView:
        """Show a completed nymrel_audit_website result as an interactive report.

        Call the audit data tool first, then pass its successful result unchanged
        and the URL requested by the user. This displays supplied evidence; it
        does not fetch, refresh, or independently verify its page identity.
        The view labels caller-supplied and returned URLs separately. If the host cannot
        display an app, summarize the same structured result in plain text.
        """
        return AuditView(report=report, requested_url=requested_url)


class AuditView(EvidenceModel):
    report: AuditSummary
    requested_url: str
