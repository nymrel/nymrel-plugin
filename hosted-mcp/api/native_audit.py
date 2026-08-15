"""Native AI-discoverability audit.

The hosted MCP server normally forwards ``audit-website`` to the Nymrel public
tools API. While that upstream is not deployed the tool answered
UPSTREAM_NOT_DEPLOYED for every caller, which turns a public listing into a
dead end. This module performs the audit in-process instead, so the tool
returns a real, fetched result with no upstream dependency.

Everything reported here is measured from bytes actually fetched from the
target. Nothing is inferred, defaulted, or scored from a lookup table.
"""

from __future__ import annotations

import ipaddress
import json
import re
import socket
import time
from typing import Any
from urllib.parse import urljoin, urlparse

import requests

USER_AGENT = "NymrelAuditBot/1.0 (+https://nymrel.com/site-audit)"
#: (connect, read). Slow targets must not consume the whole request.
TIMEOUT = (4, 6)
MAX_BYTES = 800_000
#: Total wall-clock for all fetches. Must stay well under the platform's
#: function limit so a slow site returns a partial report rather than a 504.
#: Some origins tarpit datacenter egress, so this is the binding constraint in
#: production even though every site responds in about a second locally.
BUDGET_SECONDS = 20.0
#: Each hop costs a full connect+read, so an unbounded chain outlives the
#: budget on its own.
MAX_REDIRECTS = 3

# Crawlers that decide whether an assistant may read the site at all.
AI_CRAWLERS = [
    "GPTBot",
    "OAI-SearchBot",
    "ClaudeBot",
    "Claude-Web",
    "PerplexityBot",
    "Google-Extended",
    "CCBot",
]


class AuditInputError(ValueError):
    """The supplied URL cannot be audited."""


def _resolves_to_public_ip(hostname: str) -> bool:
    """Reject hosts that resolve into private space.

    This tool fetches an attacker-supplied URL from our infrastructure, so
    every resolved address must be public or the endpoint becomes an SSRF
    pivot into the hosting network.
    """
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise AuditInputError(f"Could not resolve host '{hostname}'.") from exc

    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_reserved
            or address.is_multicast
            or address.is_unspecified
        ):
            return False
    return True


def _normalise_url(raw: str) -> str:
    candidate = (raw or "").strip()
    if not candidate:
        raise AuditInputError("A url is required.")
    if not re.match(r"^https?://", candidate, re.IGNORECASE):
        candidate = f"https://{candidate}"

    parsed = urlparse(candidate)
    if parsed.scheme.lower() not in ("http", "https"):
        raise AuditInputError("Only http and https URLs can be audited.")
    if not parsed.hostname:
        raise AuditInputError("That URL has no hostname.")
    if not _resolves_to_public_ip(parsed.hostname):
        raise AuditInputError("Only public internet hosts can be audited.")
    return candidate


def _get(url: str, deadline: float | None = None) -> tuple[int, str]:
    """Fetch a URL and return (status, body). Never raises on transport error.

    Returns status ``-1`` when the time budget is exhausted, which the caller
    reports as unmeasured rather than as a failed check.
    """
    if deadline is not None and time.monotonic() >= deadline:
        return -1, ""
    try:
        session = requests.Session()
        session.max_redirects = MAX_REDIRECTS
        response = session.get(
            url,
            timeout=TIMEOUT,
            headers={"User-Agent": USER_AGENT},
            allow_redirects=True,
            stream=True,
        )
        # Read in chunks and re-check the clock between them. A single
        # raw.read() is not bounded by the socket timeout when the origin
        # trickles bytes, which is how a slow site consumed the whole request.
        chunks: list[bytes] = []
        total = 0
        for chunk in response.iter_content(chunk_size=32_768):
            if not chunk:
                continue
            chunks.append(chunk)
            total += len(chunk)
            if total >= MAX_BYTES:
                break
            if deadline is not None and time.monotonic() >= deadline:
                break
        response.close()
        body = b"".join(chunks)
        return response.status_code, body.decode(
            response.encoding or "utf-8", errors="replace"
        )
    except requests.RequestException:
        return 0, ""


def _tag(pattern: str, html: str) -> str | None:
    """Search with DOTALL off.

    Every capture below is bounded to characters that cannot appear inside the
    attribute it is reading. Unbounded `.*?` with DOTALL backtracks across the
    whole document and hangs on large pages.
    """
    match = re.search(pattern, html, re.IGNORECASE)
    return match.group(1).strip() if match else None


def _meta(name: str, html: str) -> str | None:
    """Read a meta tag by name or property, attribute order independent."""
    escaped = re.escape(name)
    for attr in ("name", "property"):
        for pattern in (
            rf'<meta[^>]*\b{attr}=["\']{escaped}["\'][^>]*\bcontent=["\']([^"\']*)["\']',
            rf'<meta[^>]*\bcontent=["\']([^"\']*)["\'][^>]*\b{attr}=["\']{escaped}["\']',
        ):
            found = _tag(pattern, html)
            if found:
                return found
    return None


def _json_ld_types(html: str) -> list[str]:
    """Collect @type values from every JSON-LD block that parses."""
    types: list[str] = []
    blocks = re.findall(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html,
        re.IGNORECASE | re.DOTALL,
    )

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            value = node.get("@type")
            if isinstance(value, str):
                types.append(value)
            elif isinstance(value, list):
                types.extend(item for item in value if isinstance(item, str))
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    for block in blocks:
        try:
            walk(json.loads(block.strip()))
        except (json.JSONDecodeError, ValueError):
            # A malformed block is itself a finding, surfaced by the caller.
            types.append("__unparseable__")
    return list(dict.fromkeys(types))


def audit_website(url: str) -> dict[str, Any]:
    """Audit one public site and return a measured discoverability report."""
    target = _normalise_url(url)
    deadline = time.monotonic() + BUDGET_SECONDS
    status, html = _get(target, deadline)
    if status <= 0:
        raise AuditInputError(f"Could not reach {target}.")

    origin = f"{urlparse(target).scheme}://{urlparse(target).netloc}"
    checks: list[dict[str, Any]] = []
    recommendations: list[str] = []

    def check(
        name: str,
        passed: bool,
        weight: int,
        fix: str,
        detail: str = "",
        measured: bool = True,
    ) -> None:
        """Record one check.

        An unmeasured check is excluded from the score entirely. Counting it as
        a failure would report a problem we never actually observed.
        """
        checks.append(
            {
                "check": name,
                "passed": passed if measured else None,
                "weight": weight,
                "measured": measured,
                "detail": detail if measured else "not checked (time budget)",
            }
        )
        if measured and not passed:
            recommendations.append(fix)

    # --- crawlability -----------------------------------------------------
    robots_status, robots = _get(urljoin(origin, "/robots.txt"), deadline)
    robots_measured = robots_status != -1
    robots_present = robots_status == 200 and robots.strip() != ""
    check(
        "robots.txt present",
        robots_present,
        10,
        "Add a robots.txt so crawlers get an explicit policy instead of guessing.",
        measured=robots_measured,
    )

    robots_lower = robots.lower()
    allowed = [bot for bot in AI_CRAWLERS if bot.lower() in robots_lower]
    # A named bot under an explicit Disallow: / is a block, not an allow.
    blocked = [
        bot
        for bot in allowed
        if re.search(
            rf"user-agent:\s*{re.escape(bot)}\s*\n+\s*disallow:\s*/\s*$",
            robots_lower,
            re.IGNORECASE | re.MULTILINE,
        )
    ]
    check(
        "AI crawlers addressed in robots.txt",
        robots_present and bool(allowed) and not blocked,
        20,
        "Name the AI crawlers in robots.txt ("
        + ", ".join(AI_CRAWLERS[:4])
        + ") and allow the ones you want quoting you.",
        detail=f"named={allowed or 'none'} blocked={blocked or 'none'}",
        measured=robots_measured,
    )

    sitemap_status, sitemap = _get(urljoin(origin, "/sitemap.xml"), deadline)
    check(
        "sitemap.xml present",
        sitemap_status == 200
        and ("<urlset" in sitemap.lower() or "<sitemapindex" in sitemap.lower()),
        10,
        "Publish a sitemap.xml and reference it from robots.txt.",
        measured=sitemap_status != -1,
    )

    llms_status, llms = _get(urljoin(origin, "/llms.txt"), deadline)
    check(
        "llms.txt present",
        llms_status == 200 and llms.strip().startswith("#"),
        15,
        "Add an llms.txt stating plainly what you do and linking the pages an assistant should read.",
        measured=llms_status != -1,
    )

    # --- what an assistant reads on the page ------------------------------
    title = _tag(r"<title[^>]*>([^<]*)</title>", html)
    check(
        "title tag",
        bool(title and len(title) >= 10),
        10,
        "Give the page a descriptive <title> of at least 10 characters.",
        detail=title or "",
    )

    description = _meta("description", html)
    check(
        "meta description",
        bool(description and len(description) >= 50),
        10,
        "Write a meta description of 50+ characters that answers what the page is for.",
        detail=description or "",
    )

    canonical = _tag(
        r'<link[^>]*\brel=["\']canonical["\'][^>]*\bhref=["\']([^"\']*)["\']', html
    ) or _tag(
        r'<link[^>]*\bhref=["\']([^"\']*)["\'][^>]*\brel=["\']canonical["\']', html
    )
    check(
        "canonical URL",
        bool(canonical),
        5,
        "Add a canonical link so duplicate paths consolidate onto one URL.",
        detail=canonical or "",
    )

    og_present = bool(_meta("og:title", html) and _meta("og:description", html))
    check(
        "Open Graph tags",
        og_present,
        5,
        "Add og:title and og:description so shared links render with real context.",
    )

    twitter_present = bool(_meta("twitter:card", html))
    check(
        "Twitter card",
        twitter_present,
        5,
        "Add a twitter:card meta tag.",
    )

    schema_types = _json_ld_types(html)
    malformed = "__unparseable__" in schema_types
    schema_types = [t for t in schema_types if t != "__unparseable__"]
    check(
        "JSON-LD structured data",
        bool(schema_types) and not malformed,
        10,
        "Add valid JSON-LD (Organization at minimum) so assistants can read your entity."
        if not schema_types
        else "Fix the JSON-LD block that does not parse — a malformed block is skipped entirely.",
        detail=f"types={schema_types or 'none'} malformed={malformed}",
    )

    measured_checks = [c for c in checks if c["measured"]]
    earned = sum(c["weight"] for c in measured_checks if c["passed"])
    possible = sum(c["weight"] for c in measured_checks)
    score = round(earned / possible * 100) if possible else 0
    unmeasured = [c["check"] for c in checks if not c["measured"]]

    if score >= 90:
        grade, status_label = "A", "PASS"
    elif score >= 80:
        grade, status_label = "B", "PASS"
    elif score >= 70:
        grade, status_label = "C", "PARTIAL"
    elif score >= 60:
        grade, status_label = "D", "PARTIAL"
    else:
        grade, status_label = "F", "FAIL"

    return {
        "url": target,
        "http_status": status,
        # Some sites serve a near-empty shell to non-browser agents and fill
        # the page in with client-side JavaScript. This audit reports what an
        # AI crawler actually receives, so a small byte count next to missing
        # tags means the content is not in the served HTML at all.
        "html_bytes": len(html),
        "audited": "HTML as served to a non-browser crawler",
        "score": score,
        "grade": grade,
        "ai_discoverability_status": status_label,
        "schema_detected": schema_types,
        "ai_crawlers_named_in_robots": allowed,
        "ai_crawlers_blocked_in_robots": blocked,
        "checks": checks,
        "unmeasured_checks": unmeasured,
        "scored_out_of": possible,
        "recommendations": recommendations[:10],
        "full_report_url": "https://nymrel.com/site-audit",
        "measured_by": "nymrel-native-audit/1.0",
    }
