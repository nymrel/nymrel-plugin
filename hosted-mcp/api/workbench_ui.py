"""Optional public tool workbench; launch never performs a data-tool call."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Literal
from urllib.parse import quote

from mcp.types import Icon
from pydantic import BaseModel, ConfigDict

FEATURE_ENV = "NYMREL_TOOLS_UI_ENABLED"
TOOL_NAME = "nymrel_open_tools"
RESOURCE_URI = "ui://nymrel/tools-v1.html"
MIME_TYPE = "text/html;profile=mcp-app"
DISPLAY_META = {"preferredDisplayMode": "fullscreen", "availableDisplayModes": ["fullscreen"]}


class PublicTool(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: Literal["website", "domains", "golf", "clip"]
    name: str
    title: str
    description: str


class Workbench(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    version: Literal["1.0"] = "1.0"
    tools: list[PublicTool]
    default_tool: Literal["website"] = "website"


CATALOG = (
    PublicTool(id="website", name="nymrel_audit_website", title="Website audit",
               description="Check one public page for SEO, structured data, and AI discoverability."),
    PublicTool(id="domains", name="nymrel_find_domain", title="Domain names",
               description="Suggest names and inspect public registry availability; confirm before buying."),
    PublicTool(id="golf", name="nymrel_golf_bag_gap", title="Golf bag gaps",
               description="Compare the measured carry distances of up to fourteen clubs."),
    PublicTool(id="clip", name="nymrel_social_clip_score", title="Clip hook",
               description="Measure transcript signals and suggest edits; reach and views are not estimated."),
)


def enabled(_context=None):
    return os.environ.get(FEATURE_ENV, "").strip().lower() in {"true", "1", "yes", "on"}


def register(mcp):
    @mcp.resource(
        RESOURCE_URI, name="Nymrel tool workbench", mime_type=MIME_TYPE, auth=enabled,
        meta={"ui": {"prefersBorder": True, "csp": {"connectDomains": [], "resourceDomains": []}},
              "openai/ui": DISPLAY_META},
    )
    def workbench_widget() -> str:
        return Path(__file__).with_name("assets").joinpath("workbench.html").read_text(encoding="utf-8")

    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="none" '
           'stroke="currentColor" stroke-width="1.33"><rect x="3" y="3" width="14" '
           'height="14" rx="2"/><path d="M3 8h14M8 8v9"/></svg>')
    @mcp.tool(
        name=TOOL_NAME, title="Tool workbench", auth=enabled,
        icons=[Icon(src="data:image/svg+xml," + quote(svg), mimeType="image/svg+xml", sizes=["20x20"])],
        annotations={"title": "Tool workbench", "readOnlyHint": True,
                     "openWorldHint": False, "destructiveHint": False},
        meta={"ui": {"resourceUri": RESOURCE_URI, "visibility": ["model", "app"]},
              "openai/ui": {"entrypoints": [{"type": "global"}, {"type": "thread"}]}},
    )
    def open_tools() -> Workbench:
        """Open the public Nymrel tool workbench without running an audit or analysis.

        The user can choose website audits, domain suggestions, golf bag gaps,
        or transcript hook checks. Data tools remain available in conversation
        when this host cannot display an app. Opening makes no external call;
        each form runs only when the user submits it. Preferences affect the
        view in this browser only. This view contains no private Remote or
        publishing actions.
        """
        return Workbench(tools=list(CATALOG))
