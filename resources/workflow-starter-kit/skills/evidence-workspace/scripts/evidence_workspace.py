"""Offline presentation adapter for source-backed Nymrel evidence snapshots.

No network, credentials, scheduler, provider calls, or source-of-truth mutation.
Validation checks input consistency, NOT source authenticity or authorization.
Python 3.10+; standard library only.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

FORMAT = "nymrel-evidence-view/1"
MAX_BYTES = 2 * 1024 * 1024
MAX_RECORDS = 100
KINDS = {"github_issue", "github_pr", "plugin_release", "handoff", "capability", "coordination_update"}
UPDATE_STATES = {"needs_acceptance", "next_action", "blocked", "reported_complete", "superseded", "research"}
ID_RE = re.compile(r"[a-z0-9][a-z0-9._-]{0,95}\Z")
SHA_RE = re.compile(r"[0-9a-f]{40}\Z")
GITHUB_COMMENT_RE = re.compile(r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/(?:issues|pull)/[1-9][0-9]*#issuecomment-[1-9][0-9]*")
SECRET_RE = re.compile(r"(?:sk-(?:proj-)?[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|Bearer\s+[A-Za-z0-9._-]{20,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)")
EVIDENCE_GRIDS = {
    "github_issue": (("ISSUE STATE", "Recorded"), ("EXECUTION", "Unverified"), ("COMPLETION PROOF", "Unverified")),
    "plugin_release": (("ACCOUNT SAVE", "Recorded"), ("HOST INVOCATION", "Unverified"), ("PRODUCTION", "Unverified")),
    "capability": (("DOCUMENTATION", "Retrieved"), ("ACCOUNT ACCESS", "Unverified"), ("ADOPTION", "Unverified")),
    "handoff": (("RECEIPT", "Recorded"), ("ACKNOWLEDGMENT", "Unverified"), ("EXECUTION", "Unverified")),
    "coordination_update": (("SOURCE REPORT", "Recorded"), ("OWNER ACCEPTANCE", "Unverified"), ("COMPLETION PROOF", "Unverified")),
}

class EvidenceError(ValueError):
    """Input cannot safely or truthfully be rendered under this view contract."""

def text(value: Any, name: str, limit: int = 1000) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise EvidenceError(f"{name}: expected a nonempty string <= {limit} characters")
    if any(ord(c) < 32 and c not in "\n\t" for c in value):
        raise EvidenceError(f"{name}: control characters are not permitted")
    return value

def stamp(value: Any, name: str) -> datetime:
    try:
        result = datetime.fromisoformat(text(value, name, 64).replace("Z", "+00:00"))
    except (ValueError, TypeError) as exc:
        raise EvidenceError(f"{name}: expected an ISO timestamp with timezone") from exc
    if result.tzinfo is None:
        raise EvidenceError(f"{name}: timezone is required")
    try:
        return result.astimezone(timezone.utc)
    except OverflowError as exc:
        raise EvidenceError(f"{name}: timestamp is outside the supported UTC range") from exc

def url(value: Any, name: str, hosts: set[str] | None = None) -> str:
    value = text(value, name, 1800)
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise EvidenceError(f"{name}: invalid URL") from exc
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or
        parsed.password or port not in (None, 443) or parsed.query or
        any(c.isspace() for c in value) or re.search(r'[<>"\'`\[\]{}()]', value) or "\\" in value or
        re.search(r"%0[ad]", value, re.I)):
        raise EvidenceError(f"{name}: use a credential-free HTTPS URL without query parameters")
    host = parsed.hostname.lower()
    if hosts is not None and host not in hosts:
        raise EvidenceError(f"{name}: unexpected provider host")
    if host in {"localhost", "127.0.0.1", "::1"} or host.endswith((".local", ".internal")):
        raise EvidenceError(f"{name}: local destinations are not allowed")
    return value

def exact_keys(obj: Any, allowed: set[str], required: set[str] | None = None, name: str = "object") -> dict:
    """Require every allowed key unless an explicit required subset is supplied."""
    if not isinstance(obj, dict):
        raise EvidenceError(f"{name}: expected an object")
    required = allowed if required is None else required
    extra, missing = set(obj) - allowed, required - set(obj)
    if extra or missing:
        raise EvidenceError(f"{name}: unexpected keys {sorted(extra)}; missing keys {sorted(missing)}")
    return obj

def boolean(value: Any, name: str) -> bool:
    if type(value) is not bool:
        raise EvidenceError(f"{name}: expected true or false, not a coerced value")
    return value

def sha(value: Any, name: str) -> str:
    if not isinstance(value, str) or not SHA_RE.fullmatch(value):
        raise EvidenceError(f"{name}: expected a 40-character lowercase Git commit SHA")
    return value

def sequence(value: Any, name: str, maximum: int = 200) -> list:
    if not isinstance(value, list) or len(value) > maximum:
        raise EvidenceError(f"{name}: expected a bounded list")
    return value

def update_data(data: Any, source: str, observed: datetime) -> dict:
    """Validate a minimized comment report; timestamps never establish acceptance."""
    exact_keys(data, {"lane_id", "project", "owner", "source_date", "state", "summary",
                      "next_action", "checkpoint_at", "supersedes"}, name="coordination data")
    if not GITHUB_COMMENT_RE.fullmatch(source):
        raise EvidenceError("Coordination source must be an exact GitHub issue or pull comment URL")
    lane = text(data["lane_id"], "coordination.lane_id", 96)
    if not ID_RE.fullmatch(lane):
        raise EvidenceError("coordination.lane_id must be a stable lowercase identifier")
    text(data["project"], "coordination.project", 220)
    for field, limit in (("owner", 220), ("next_action", 1200)):
        if data[field] is not None:
            text(data[field], f"coordination.{field}", limit)
    text(data["summary"], "coordination.summary", 1200)
    if not isinstance(data["state"], str) or data["state"] not in UPDATE_STATES:
        raise EvidenceError("Unknown coordination state")
    if data["source_date"] is not None:
        value = text(data["source_date"], "coordination.source_date", 10)
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
            raise EvidenceError("coordination.source_date must be a body-reported YYYY-MM-DD date or null")
        try:
            reported = date.fromisoformat(value)
        except ValueError as exc:
            raise EvidenceError("coordination.source_date is not a valid calendar date") from exc
        if reported > observed.date():
            raise EvidenceError("Body-reported source date is after its source observation")
    if data["checkpoint_at"] is not None:
        # A planned checkpoint may lie after observation; it is not an event receipt.
        stamp(data["checkpoint_at"], "coordination.checkpoint_at")
    references = sequence(data["supersedes"], "coordination.supersedes", MAX_RECORDS)
    seen = set()
    for rid in references:
        text(rid, "coordination.supersedes ID", 96)
        if not ID_RE.fullmatch(rid) or rid in seen:
            raise EvidenceError("coordination.supersedes requires distinct stable record IDs")
        seen.add(rid)
    return data

def archive_update(card: dict) -> None:
    """Keep source assertions available without exposing old direction as current."""
    card.update(status="Superseded · historical report", category="History", tone="neutral", attention=False)
    card["next_action"] = "Historical report. Its supplied next action is inactive; consult the current source and owner lane."
    card["limits"].append("A superseded report and its former next action are retained as history, not active direction.")

def resolve_updates(cards: list[dict]) -> None:
    """Only explicit, same-lane and same-audience edges can retire an update."""
    by_id = {card["id"]: card for card in cards}
    updates = {cid: card for cid, card in by_id.items() if card["kind"] == "coordination_update"}
    for cid, card in updates.items():
        for previous in card["supersedes"]:
            target = by_id.get(previous)
            if previous == cid:
                raise EvidenceError("Coordination update cannot supersede itself")
            if target is None:
                raise EvidenceError("Coordination supersedes references a missing record")
            if target["kind"] != "coordination_update" or target["lane_id"] != card["lane_id"]:
                raise EvidenceError("Coordination supersession must stay in the same coordination lane")
            if target["audience"] != card["audience"]:
                raise EvidenceError("Coordination supersession must stay in the same audience")
    visited, visiting = set(), set()
    def visit(cid: str) -> None:
        if cid in visiting:
            raise EvidenceError("Cyclic coordination supersession")
        if cid in visited:
            return
        visiting.add(cid)
        for previous in updates[cid]["supersedes"]:
            visit(previous)
        visiting.remove(cid)
        visited.add(cid)
    for cid in updates:
        visit(cid)
    for cid, card in updates.items():
        for previous in card["supersedes"]:
            updates[previous]["superseded_by"].append(cid)
    for card in updates.values():
        card["superseded_by"].sort()
        if card["superseded_by"]:
            if card["category"] != "History":
                archive_update(card)
            card["limits"].append("Explicitly superseded by supplied record IDs: " + ", ".join(card["superseded_by"]) + ".")
        elif card["state"] == "superseded":
            card["limits"].append("The source reports this update superseded; a replacement record was not supplied.")
        if card["category"] == "History":
            card["attention"] = False

def pairs_unique(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, val in pairs:
        if key in result:
            raise EvidenceError(f"Duplicate JSON key: {key}")
        result[key] = val
    return result

def load(path: Path) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise EvidenceError("Input must be a regular, nonsymlink UTF-8 JSON file <= 2 MiB")
    try:
        raw = path.read_text(encoding="utf-8")
        return json.loads(raw, object_pairs_hook=pairs_unique,
                          parse_constant=lambda x: (_ for _ in ()).throw(EvidenceError(f"Invalid JSON constant: {x}")))
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise EvidenceError("Input is not valid bounded UTF-8 JSON") from exc

def review_summary(reviews: Any, head: str, observed: datetime) -> tuple[str, list[str]]:
    if reviews is None:
        return "Unverified", ["Review results were not supplied."]
    sequence(reviews, "reviews")
    latest: dict[str, tuple[datetime, dict]] = {}
    notes = []
    for review in reviews:
        exact_keys(review, {"reviewer", "state", "commit_id", "submitted_at", "url"}, name="review")
        reviewer = text(review["reviewer"], "reviewer", 100)
        when = stamp(review["submitted_at"], "submitted_at")
        if when > observed:
            raise EvidenceError("Review timestamp is later than its source observation")
        sha(review["commit_id"], "review.commit_id")
        url(review["url"], "review.url", {"github.com"})
        if not isinstance(review["state"], str) or review["state"] not in {"APPROVED", "CHANGES_REQUESTED", "COMMENTED", "DISMISSED", "PENDING"}:
            raise EvidenceError("Unknown review state")
        # Pending/comment-only reviews do not supersede an explicit verdict.
        if review["state"] in {"PENDING", "COMMENTED"}:
            continue
        prev = latest.get(reviewer)
        if prev and prev[0] == when and prev[1] != review:
            raise EvidenceError("Ambiguous simultaneous review verdicts")
        if prev is None or when > prev[0]:
            latest[reviewer] = (when, review)
    current = [r for _, r in latest.values() if r["commit_id"] == head]
    outdated = [r for _, r in latest.values() if r["commit_id"] != head and r["state"] != "DISMISSED"]
    if outdated:
        notes.append("Supplied prior-head verdicts are not current-head clearance.")
    if any(r["state"] == "CHANGES_REQUESTED" for r in current):
        return "Changes requested", notes
    if any(r["state"] == "APPROVED" for r in current):
        notes.append("A supplied approval does not establish reviewer independence or all repository merge gates.")
        return "Approval on exact head", notes
    if outdated:
        return "Prior-head verdict only", notes
    return "No current verdict in supplied results", notes

def check_summary(checks: Any, head: str) -> tuple[str, list[str]]:
    if checks is None:
        return "Unverified", ["Check results were not supplied."]
    sequence(checks, "checks")
    current = []
    notes = []
    ids = set()
    for check in checks:
        exact_keys(check, {"id", "name", "head_sha", "status", "conclusion", "url", "step_count"},
                   {"id", "name", "head_sha", "status", "conclusion", "url"}, "check")
        cid = text(check["id"], "check.id", 100)
        if cid in ids:
            raise EvidenceError("Duplicate check ID")
        ids.add(cid)
        text(check["name"], "check.name", 200)
        sha(check["head_sha"], "check.head_sha")
        url(check["url"], "check.url", {"github.com"})
        if not isinstance(check["status"], str) or check["status"] not in {"queued", "in_progress", "completed"}:
            raise EvidenceError("Unknown check status")
        if check["conclusion"] is not None and (not isinstance(check["conclusion"], str) or check["conclusion"] not in {"success", "failure", "cancelled", "timed_out", "neutral", "skipped", "action_required", "stale"}):
            raise EvidenceError("Unknown check conclusion")
        if check["status"] != "completed" and check["conclusion"] is not None:
            raise EvidenceError("Incomplete check cannot have a conclusion")
        if "step_count" in check and (type(check["step_count"]) is not int or check["step_count"] < 0):
            raise EvidenceError("step_count must be a nonnegative integer")
        if check["head_sha"] == head:
            current.append(check)
    if not current:
        return "No exact-head checks supplied", ["Missing checks are not passing checks."]
    bad = [c for c in current if c["conclusion"] in {"failure", "cancelled", "timed_out", "action_required", "stale"}]
    if bad:
        if any(c["conclusion"] == "failure" and c.get("step_count") == 0 for c in bad):
            notes.append("A supplied failed job has zero executed steps; this alone does not establish a code defect.")
        return "Attention in supplied checks", notes
    if any(c["status"] != "completed" for c in current):
        return "Checks in progress", notes
    if all(c["conclusion"] == "success" for c in current):
        return "Supplied checks passed", ["Required-check completeness was not established by this snapshot."]
    return "Checks not all successful", ["Skipped, neutral, or missing conclusions are not all-success proof."]

def normalize(record: dict, as_of: datetime, ttl: float) -> dict:
    exact_keys(record, {"id", "kind", "audience", "title", "source_url", "observed_at", "data"}, name="record")
    rid = text(record["id"], "record.id", 96)
    if not ID_RE.fullmatch(rid):
        raise EvidenceError("record.id must be a stable lowercase identifier")
    kind = record["kind"]
    if not isinstance(kind, str) or kind not in KINDS or not isinstance(record["audience"], str) or record["audience"] not in {"private", "public"}:
        raise EvidenceError("Unknown record kind or explicit audience missing")
    title = text(record["title"], "record.title", 220)
    observed = stamp(record["observed_at"], "observed_at")
    if observed > as_of:
        raise EvidenceError("Source observation is in the future relative to as_of")
    expected_hosts = {"github.com"} if kind in {"github_issue", "github_pr", "handoff", "coordination_update"} else ({"chatgpt.com"} if kind == "plugin_release" else {"developers.openai.com", "help.openai.com", "openai.com"})
    source = url(record["source_url"], "source_url", expected_hosts)
    data = record["data"]
    stale = as_of - observed > timedelta(hours=ttl)
    out = {"id": rid, "kind": kind, "audience": record["audience"], "title": title,
           "source_url": source, "observed_at": record["observed_at"],
           "freshness": "Recheck source" if stale else "Within snapshot window",
           "revision": None, "facts": [], "limits": [], "review": "Unverified",
           "checks": "Unverified", "production": "Unverified", "attention": True}
    if kind == "coordination_update":
        update_data(data, source, observed)
        state = data["state"]
        labels = {"needs_acceptance": "Needs acceptance · reported", "next_action": "Next action · reported",
                  "blocked": "Blocked · reported", "reported_complete": "Reported complete · unverified",
                  "superseded": "Superseded · historical report", "research": "Research · not adopted"}
        category = {"reported_complete": "Completion", "superseded": "History", "research": "Research"}.get(state, "Action")
        out.update({key: data[key] for key in ("lane_id", "project", "owner", "source_date", "state", "checkpoint_at")})
        out.update(status=labels[state], category=category, tone="warning" if category == "Action" else "neutral",
                   revision=urlsplit(source).fragment, supersedes=list(data["supersedes"]), superseded_by=[],
                   reported_next_action=data["next_action"], attention=state != "superseded")
        out["facts"] = [data["summary"]]
        out["next_action"] = data["next_action"] or "No next action was supplied in this source report."
        out["limits"] = ["Owner, state, summary and next action are source reports. Owner acceptance, execution, tests, deployment and accepted completion remain unverified.",
                         "The body-reported date is distinct from observation time. A planned checkpoint is not an acknowledgment or execution receipt."]
        if state == "research":
            out["limits"].append("Research is separate from active work; a proposal does not establish account access, adoption or execution authority.")
        if state == "superseded":
            archive_update(out)
    elif kind == "github_issue":
        required = {"issue_number", "state", "state_reason", "updated_at", "closed_at"}
        exact_keys(data, required | {"summary", "next_action"}, required, "issue data")
        number = data["issue_number"]
        if type(number) is not int or number < 1:
            raise EvidenceError("issue_number must be a positive integer")
        parsed = urlsplit(source)
        if (not re.fullmatch(r"/[^/]+/[^/]+/issues/" + str(number), parsed.path)
                or parsed.fragment):
            raise EvidenceError("Issue source must bind to the exact GitHub issue number, not a PR or comment")
        state, reason = data["state"], data["state_reason"]
        if not isinstance(state, str) or state not in {"open", "closed"}:
            raise EvidenceError("Issue state must be open or closed")
        if reason is not None and (not isinstance(reason, str) or reason not in
                                   {"completed", "not_planned", "reopened", "duplicate"}):
            raise EvidenceError("Unknown issue state_reason")
        updated = stamp(data["updated_at"], "issue.updated_at")
        if updated > observed:
            raise EvidenceError("Issue update is after its source observation")
        out["revision"] = data["updated_at"]
        out["facts"] = [f"Issue #{number}; source updated {data['updated_at']}"]
        if "summary" in data:
            out["facts"].insert(0, text(data["summary"], "issue.summary", 1200))
        if "next_action" in data:
            text(data["next_action"], "issue.next_action", 1200)
        if state == "open":
            if data["closed_at"] is not None or reason not in {None, "reopened"}:
                raise EvidenceError("Open issue cannot have a closure timestamp or a closed-state reason")
            out.update(status="Reopened" if reason == "reopened" else "Open", category="Work", tone="warning")
            out["next_action"] = data.get("next_action", "Read the current issue and owner lane, then carry out the next authorized action.")
        else:
            if reason == "reopened" or data["closed_at"] is None:
                raise EvidenceError("Closed issue needs closed_at and cannot have a reopened reason")
            closed = stamp(data["closed_at"], "issue.closed_at")
            if closed > updated:
                raise EvidenceError("Issue closure is after its last source update")
            labels = {"completed": "Closed · reported complete", "not_planned": "Closed · not planned",
                      "duplicate": "Closed · duplicate", None: "Closed · reason unavailable"}
            out.update(status=labels[reason], category="History", tone="neutral", attention=reason in {None, "completed"})
            out["facts"].append(f"Closure recorded {data['closed_at']}")
            out["next_action"] = "Read the closure evidence before treating the outcome as complete. Do not resume a closed goal without current owner direction."
            if "next_action" in data:
                out["limits"].append("A supplied next action is not active direction while the issue is closed.")
        out["limits"].append("Issue state and any supplied summary are source assertions; they do not prove execution, worker pickup, tests, deployment, or accepted completion.")
    elif kind == "github_pr":
        exact_keys(data, {"state", "draft", "merged", "merged_at", "head_sha", "merge_commit_sha", "reviews", "checks"},
                   {"state", "draft", "merged", "merged_at", "head_sha", "merge_commit_sha"}, "PR data")
        if not isinstance(data["state"], str) or data["state"] not in {"open", "closed"}:
            raise EvidenceError("PR state must be open or closed")
        draft, merged = boolean(data["draft"], "draft"), boolean(data["merged"], "merged")
        head = sha(data["head_sha"], "head_sha")
        out["revision"] = head
        if data["merge_commit_sha"] is not None:
            sha(data["merge_commit_sha"], "merge_commit_sha")
        if merged:
            if draft or data["state"] != "closed" or not data["merged_at"] or not data["merge_commit_sha"]:
                raise EvidenceError("Contradictory merged PR fields")
            if stamp(data["merged_at"], "merged_at") > observed:
                raise EvidenceError("Merge is after the observation")
            out.update(status="Merged", category="Build", tone="success")
            out["facts"].append(f"Merge recorded {data['merged_at']}")
            out["facts"].append(f"Merge commit {data['merge_commit_sha']}")
            out["next_action"] = "Verify deployment and user-visible behavior independently before calling this live."
        else:
            if data["merged_at"] is not None:
                raise EvidenceError("Unmerged PR cannot have merged_at")
            if data["state"] == "closed":
                out.update(status="Closed · not merged", category="History", tone="neutral", attention=False)
                out["next_action"] = "Retain as historical evidence; do not revive or treat this proposal as adopted."
            else:
                out.update(status="Draft" if draft else "Open", category="Build", tone="warning")
                out["next_action"] = "Re-read current ownership, exact-head review, and required checks before changes."
        out["review"], notes = review_summary(data.get("reviews"), head, observed)
        out["limits"].extend(notes)
        out["checks"], notes = check_summary(data.get("checks"), head)
        out["limits"].extend(notes)
        out["limits"].append("Source state does not establish deployment, public listing, or customer use.")
    elif kind == "plugin_release":
        exact_keys(data, {"plugin_id", "name", "version", "current_release_id", "scope", "discoverability"}, name="plugin data")
        for k in ("plugin_id", "name", "version", "current_release_id", "scope", "discoverability"):
            text(data[k], k, 200)
        if data["scope"] not in {"USER", "WORKSPACE"} or data["discoverability"] not in {"PRIVATE", "UNLISTED", "LISTED", "PUBLIC"}:
            raise EvidenceError("Unknown plugin scope/discoverability")
        if data["discoverability"] == "PRIVATE" and record["audience"] != "private":
            raise EvidenceError("Private plugin cannot be marked as public evidence")
        if urlsplit(source).path.rstrip("/").split("/")[-1] != data["plugin_id"]:
            raise EvidenceError("Plugin source URL does not match plugin ID")
        out.update(status=f"Saved · v{data['version']}", category="Build", tone="success", revision=data["current_release_id"])
        out["facts"] = [f"Scope: {data['scope']}; visibility: {data['discoverability']}"]
        out["next_action"] = "Verify this exact saved release in a fresh host conversation."
        out["limits"] = ["Account save is verified by the supplied source; installation, automatic routing, and host behavior remain unverified."]
    elif kind == "handoff":
        exact_keys(data, {"comment_id", "created_at", "target", "summary"}, name="handoff data")
        if type(data["comment_id"]) is not int or data["comment_id"] < 1:
            raise EvidenceError("comment_id must be a positive integer")
        if stamp(data["created_at"], "created_at") > observed:
            raise EvidenceError("Handoff is after the observation")
        if not GITHUB_COMMENT_RE.fullmatch(source):
            raise EvidenceError("Handoff source must be an exact GitHub issue or pull comment URL")
        if urlsplit(source).fragment != f"issuecomment-{data['comment_id']}":
            raise EvidenceError("Handoff link must bind to the exact comment ID")
        text(data["target"], "target", 300)
        text(data["summary"], "summary", 1200)
        out.update(status="Recorded · pickup unverified", category="Handoffs", tone="warning", revision=str(data["comment_id"]))
        out["facts"] = [data["summary"], f"Existing destination: {data['target']}"]
        out["next_action"] = "Obtain a current owner acknowledgment with scope, revision, and next action in the existing lane."
        out["limits"] = ["A recorded comment is not worker pickup, implementation, review, or permission to execute."]
    elif kind == "capability":
        exact_keys(data, {"summary", "existing_owner", "next_test", "limitations"}, name="capability data")
        for k in ("summary", "existing_owner", "next_test"):
            text(data[k], k, 1200)
        sequence(data["limitations"], "limitations", 10)
        for limitation in data["limitations"]:
            text(limitation, "limitation", 1000)
        out.update(status="Documented · not adopted", category="Research", tone="neutral")
        out["facts"] = [data["summary"], f"Proposed integration target: {data['existing_owner']}"]
        out["next_action"] = data["next_test"]
        out["limits"] = data["limitations"] + ["Vendor documentation does not prove account availability or Nymrel adoption."]
    if stale:
        out["attention"] = True
        out["limits"].insert(0, "Source observation is outside this snapshot's declared freshness window.")
    return out

def build(snapshot: dict, audience: str = "private", as_of: str | None = None) -> dict:
    exact_keys(snapshot, {"format", "title", "scope", "captured_at", "freshness_hours", "records"}, name="snapshot")
    if snapshot["format"] != FORMAT or audience not in {"private", "public"}:
        raise EvidenceError("Unsupported format or audience")
    text(snapshot["title"], "title", 220)
    text(snapshot["scope"], "scope", 1600)
    clock = stamp(as_of or snapshot["captured_at"], "as_of" if as_of else "captured_at")
    if stamp(snapshot["captured_at"], "captured_at") > clock:
        raise EvidenceError("Snapshot capture is later than as_of")
    ttl = snapshot["freshness_hours"]
    if type(ttl) not in (int, float) or not 0 < ttl <= 720 or not math.isfinite(ttl):
        raise EvidenceError("freshness_hours must be finite, positive and <= 720")
    records = sequence(snapshot["records"], "records", MAX_RECORDS)
    raw = json.dumps(snapshot, ensure_ascii=False, allow_nan=False)
    if len(raw.encode("utf-8")) > MAX_BYTES or SECRET_RE.search(raw):
        raise EvidenceError("Oversized input or credential-like content: do not place secrets in evidence views")
    ids, cards = set(), []
    for record in records:
        card = normalize(record, clock, float(ttl))
        if card["id"] in ids:
            raise EvidenceError("Duplicate stable record ID")
        ids.add(card["id"])
        cards.append(card)
    # Validate the complete graph before projection. Cross-audience edges are never
    # permitted to change public state or leak a private source through metadata.
    resolve_updates(cards)
    cards = [card for card in cards if audience == "private" or card["audience"] == "public"]
    order = {"Work": 0, "Build": 1, "Research": 2, "Handoffs": 3, "History": 4}
    if any(card["kind"] == "coordination_update" for card in cards):
        order = {"Action": 0, "Work": 1, "Build": 2, "Handoffs": 3, "Completion": 4, "Research": 5, "History": 6}
    state_order = {"needs_acceptance": 0, "next_action": 1, "blocked": 2}
    cards.sort(key=lambda c: (order[c["category"]], state_order.get(c.get("state"), 3), c["title"].casefold(), c["id"]))
    visible = [r for r in records if audience == "private" or r["audience"] == "public"]
    digest = hashlib.sha256(json.dumps(visible, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    return {"format": FORMAT, "title": snapshot["title"] if audience == "private" else "Nymrel public evidence",
            "scope": snapshot["scope"] if audience == "private" else "Explicitly public records only. This export is a bounded snapshot, not a complete inventory.",
            "audience": audience, "captured_at": snapshot["captured_at"], "as_of": clock.isoformat(),
            "freshness_hours": ttl, "visible_source_sha256": digest, "cards": cards,
            "boundary": "Presentation only. No network refresh, authorization, source mutation, or automated execution."}

def semantic(card: dict) -> dict:
    result = {k: v for k, v in card.items() if k not in {"observed_at", "freshness", "attention", "limits"}}
    result["limits"] = [x for x in card["limits"] if x != "Source observation is outside this snapshot\'s declared freshness window."]
    return result

def compare(before: dict, after: dict) -> dict:
    if before["audience"] != after["audience"]:
        raise EvidenceError("Compare views with the same audience")
    if stamp(after["captured_at"], "after.captured_at") < stamp(before["captured_at"], "before.captured_at"):
        raise EvidenceError("After snapshot must not precede before snapshot")
    old, new = ({c["id"]: c for c in v["cards"]} for v in (before, after))
    changes = []
    for cid in sorted(set(old) | set(new)):
        if cid not in old:
            changes.append({"id": cid, "change": "newly_observed", "title": new[cid]["title"]})
        elif cid not in new:
            changes.append({"id": cid, "change": "not_observed_in_new_snapshot", "title": old[cid]["title"]})
        else:
            previous, current = semantic(old[cid]), semantic(new[cid])
            if previous != current:
                fields = sorted(k for k, value in current.items() if value != previous.get(k))
                changes.append({"id": cid, "change": "material_change", "fields": fields, "title": new[cid]["title"]})
    return {"changes": changes, "note": "Retrieval-time-only changes are ignored. Missing observations never prove deletion. No state is written back."}

def markdown(view: dict) -> str:
    def safe(s: Any) -> str:
        return str(s).replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]").replace("<", "&lt;").replace(">", "&gt;")
    lines = [f"# {safe(view['title'])}", "", f"{view['audience'].upper()} SNAPSHOT — {view['captured_at']}", "", safe(view["scope"]), "", view["boundary"], ""]
    for c in view["cards"]:
        lines.extend([f"## {safe(c['title'])}", f"**{safe(c['status'])}**", "",
                      f"Source: [{safe(c['kind'])}]({c['source_url']}) · observed {c['observed_at']}",
                      f"Revision: {safe(c['revision'] or 'Not applicable')}",
                      f"Review: {safe(c['review'])}; checks: {safe(c['checks'])}; production: {safe(c['production'])}.", ""])
        lines.extend(safe(x) for x in c["facts"])
        if c["kind"] == "coordination_update":
            lines.extend([f"Project: {safe(c['project'])}; lane: {safe(c['lane_id'])}.",
                          f"Reported owner: {safe(c['owner'] or 'Unverified · not supplied')}; owner acceptance: Unverified.",
                          f"Body-reported date: {safe(c['source_date'] or 'Not supplied')}.",
                          f"Planned checkpoint: {safe(c['checkpoint_at'] or 'Not supplied')}."])
            if c["category"] == "History" and c["reported_next_action"]:
                lines.append(f"Historical next action (inactive): {safe(c['reported_next_action'])}")
            if c["supersedes"]:
                lines.append("Explicitly supersedes: " + safe(", ".join(c["supersedes"])) + ".")
            if c["superseded_by"]:
                lines.append("Explicitly superseded by: " + safe(", ".join(c["superseded_by"])) + ".")
        label = "Reported next step" if c["kind"] == "coordination_update" else "Next step"
        lines.extend(["", f"{label}: {safe(c['next_action'])}", ""] + [f"Limitation: {safe(x)}" for x in c["limits"]] + [""])
    if not view["cards"]:
        lines.append("No records in this bounded view. This is not evidence that no work exists.")
    return "\n".join(lines)

def render(view: dict) -> str:
    template = (Path(__file__).resolve().parent.parent / "assets" / "workspace.html").read_text(encoding="utf-8")
    esc = lambda x: html.escape(str(x), quote=True)
    updates = [c for c in view["cards"] if c["kind"] == "coordination_update"]
    coordination = bool(updates)
    cards = []
    for c in view["cards"]:
        facts = "".join(f"<p>{esc(t)}</p>" for t in c["facts"])
        limits = "".join(f"<li>{esc(t)}</li>" for t in c["limits"])
        metadata, source_details, update_search, attributes = "", "", [], ""
        next_label = "Next evidence step"
        if c["kind"] == "coordination_update":
            owner = c["owner"] or "Unverified · not supplied"
            checkpoint = c["checkpoint_at"] or "Not supplied"
            metadata = f'<dl class="coordination-meta"><div><dt>Project</dt><dd>{esc(c["project"])}</dd></div><div><dt>Reported owner</dt><dd>{esc(owner)}</dd></div><div><dt>Planned checkpoint</dt><dd>{esc(checkpoint)}</dd></div></dl>'
            source_details = f'<dt>Lane</dt><dd>{esc(c["lane_id"])}</dd><dt>Body-reported date</dt><dd>{esc(c["source_date"] or "Not supplied")}</dd><dt>Source-reported state</dt><dd>{esc(c["state"])}</dd>'
            if c["supersedes"]:
                source_details += f'<dt>Explicitly supersedes</dt><dd>{esc(", ".join(c["supersedes"]))}</dd>'
            if c["superseded_by"]:
                source_details += f'<dt>Explicitly superseded by</dt><dd>{esc(", ".join(c["superseded_by"]))}</dd>'
            if c["category"] == "History" and c["reported_next_action"]:
                source_details += f'<dt>Historical next action · inactive</dt><dd>{esc(c["reported_next_action"])}</dd>'
            next_label = "Historical direction · inactive" if c["category"] == "History" else "Reported next step"
            state = "superseded" if c["category"] == "History" else c["state"]
            attributes = f' data-state="{esc(state)}" data-owner="{esc(json.dumps(c["owner"], ensure_ascii=False))}" data-project="{esc(c["project"])}"'
            update_search = [c["lane_id"], c["project"], owner, checkpoint, c["source_date"] or "",
                             c["reported_next_action"] or ""]
        search = esc(" ".join([c["title"], c["status"], c["category"], c["kind"], c["next_action"],
                               c["source_url"], c["revision"] or "", c["observed_at"], c["freshness"],
                               c["review"], c["checks"], c["production"]] + c["facts"] + c["limits"] + update_search).lower())
        grid = EVIDENCE_GRIDS.get(c["kind"], [("REVIEW", c["review"]), ("CHECKS", c["checks"]), ("PRODUCTION", c["production"])])
        grid_html = "".join(f"<div><span>{esc(label)}</span><strong>{esc(value)}</strong></div>" for label, value in grid)
        cards.append(f'''<article class="card" data-category="{esc(c['category'])}" data-search="{search}" data-attention="{str(c['attention']).lower()}"{attributes}>
<div class="card-top"><span class="eyebrow">{esc(c['category'])}</span><span class="status {esc(c['tone'])}">{esc(c['status'])}</span></div>
<h2>{esc(c['title'])}</h2>{metadata}<div class="facts">{facts}</div>
<div class="evidence-grid">{grid_html}</div>
<div class="next"><span>{next_label}</span><p>{esc(c['next_action'])}</p></div>
<details><summary>Source and what is still unknown</summary><dl>{source_details}<dt>Revision</dt><dd class="mono">{esc(c['revision'] or 'Not applicable')}</dd><dt>Observed</dt><dd>{esc(c['observed_at'])}</dd><dt>Freshness at build</dt><dd>{esc(c['freshness'])}</dd></dl><ul>{limits}</ul><a href="{esc(c['source_url'])}" target="_blank" rel="noopener noreferrer" referrerpolicy="no-referrer">Open original source<span class="sr-only"> for {esc(c['title'])}; opens in a new tab</span> ↗</a></details></article>''')
    filters = [("All", "All work"), ("Work", "Goals & issues"), ("Build", "Changes & plugins"),
               ("Research", "Research"), ("Handoffs", "Handoffs"), ("History", "History"), ("Attention", "Needs evidence")]
    selectors, legend = "", ""
    if coordination:
        filters = [("Current", "Current updates"), ("Action", "Needs action"), ("Completion", "Reported complete"),
                   ("Research", "Research"), ("History", "History"), ("All", "All records"), ("Attention", "Needs evidence")]
        categories = {c["category"] for c in view["cards"]}
        filters += [(key, label) for key, label in (("Work", "Goals & issues"), ("Build", "Changes & plugins"), ("Handoffs", "Handoffs")) if key in categories]
        owners = sorted({c["owner"] for c in updates if c["owner"] is not None}, key=str.casefold)
        owner_options = ''.join(f'<option value="{esc(json.dumps(owner, ensure_ascii=False))}">{esc(owner)}</option>' for owner in owners)
        if any(c["owner"] is None for c in updates):
            owner_options += '<option value="null">Unverified · owner not supplied</option>'
        project_options = ''.join(f'<option value="{esc(project)}">{esc(project)}</option>' for project in sorted({c["project"] for c in updates}, key=str.casefold))
        state_options = ''.join(f'<option value="{state}">{label}</option>' for state, label in
                                (("needs_acceptance", "Needs acceptance"), ("next_action", "Next action"), ("blocked", "Blocked"),
                                 ("reported_complete", "Reported complete"), ("research", "Research"), ("superseded", "Superseded")))
        selectors = f'<div class="selectors"><label for="owner-filter">Reported owner<select id="owner-filter"><option value="">All owners</option>{owner_options}</select></label><label for="project-filter">Project<select id="project-filter"><option value="">All projects</option>{project_options}</select></label><label for="state-filter">Reported status<select id="state-filter"><option value="">All statuses</option>{state_options}</select></label></div>'
        legend = '<p><strong>Coordination updates</strong> are source reports. A named owner does not establish acceptance. A missing owner or checkpoint stays explicit. <strong>Current updates</strong> hides History; only an explicit supersession report or link moves an update there. A later date alone does not retire an earlier report. <strong>Reported complete</strong> and <strong>Research</strong> remain separate from active next actions. All records, downloads and the no-JavaScript view retain History.</p>'
    filter_html = ''.join(f'<button type="button" aria-pressed="{str(i == 0).lower()}" data-filter="{key}">{esc(label)}</button>' for i, (key, label) in enumerate(filters))
    data = json.dumps(view, ensure_ascii=False, sort_keys=True).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    slots = {"TITLE": esc(view["title"]), "SCOPE": esc(view["scope"]), "AUDIENCE": esc(view["audience"].upper()),
             "CAPTURED": esc(stamp(view["captured_at"], "captured_at").strftime("%b %d, %Y · %H:%M UTC")), "ASOF": esc(view["as_of"]), "COUNT": str(len(view["cards"])),
             "ATTENTION": str(sum(c["attention"] for c in view["cards"])), "CARDS": "\n".join(cards),
             "DATA": data, "HASH": esc(view["visible_source_sha256"]), "FILTERS": filter_html,
             "SELECTORS": selectors, "COORDINATIONLEGEND": legend, "DEFAULTFILTER": "Current" if coordination else "All"}
    template = re.sub(r"@@([A-Z]+)@@", lambda m: slots.get(m.group(1), m.group(0)), template)
    # Hash-based CSP permits only this generated file's known inline script/style.
    import base64
    hashes = {}
    for tag, directive in (("script", "SCRIPT_HASHES"), ("style", "STYLE_HASHES")):
        chunks = re.findall(fr"<{tag}(?:\s[^>]*)?>(.*?)</{tag}>", template, re.S)
        hashes[directive] = " ".join("'sha256-" + base64.b64encode(hashlib.sha256(s.encode()).digest()).decode() + "'" for s in chunks)
    for key, value in hashes.items():
        template = template.replace("@@" + key + "@@", value)
    return template

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["validate", "build", "compare"],
                        help="validate checks input without writing files; build renders a snapshot; compare also reports changes")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--previous", type=Path)
    parser.add_argument("--output", type=Path, help="Required for build/compare: a new output directory")
    parser.add_argument("--audience", choices=["private", "public"], default="private")
    parser.add_argument("--as-of", help="ISO timestamp; default is the input capture time")
    parser.add_argument("--json-errors", action="store_true", help="Report validation/file errors as JSON on stderr (exit 2)")
    args = parser.parse_args(argv)
    new_output_created = False
    artifact_path = args.output

    def read_view(path: Path, label: str, as_of: str | None = None) -> dict:
        try:
            return build(load(path), args.audience, as_of)
        except (OSError, ValueError, RecursionError) as exc:
            raise EvidenceError(f"{label} {path}: {exc}") from exc

    try:
        if args.command == "validate" and (args.output is not None or args.previous is not None):
            raise EvidenceError("validate does not use --output or --previous; it checks input without writing files")
        if args.command != "validate" and args.output is None:
            raise EvidenceError("build/compare requires --output NEW_DIRECTORY; previous output is never overwritten")
        if args.command == "build" and args.previous is not None:
            raise EvidenceError("Use compare with --previous, or remove --previous for a standalone build")
        view = read_view(args.input, "Current input", args.as_of)
        if args.command == "validate":
            print(json.dumps({"status": "valid", "records": len(view["cards"]),
                              "attention": sum(c["attention"] for c in view["cards"]),
                              "audience": view["audience"], "network_calls": 0,
                              "boundary": "Input consistency checked; source authenticity and authorization are not verified."}))
            return 0
        delta = None
        if args.command == "compare":
            if args.previous is None:
                raise EvidenceError("compare requires --previous")
            prev = read_view(args.previous, "Previous input")
            delta = compare(prev, view)
        if args.output.exists() or args.output.is_symlink():
            raise EvidenceError("Output directory already exists; choose a new path to preserve prior evidence")
        args.output.mkdir(parents=True, exist_ok=False)
        new_output_created = True
        outputs = {"index.html": render(view), "brief.md": markdown(view), "view.json": json.dumps(view, indent=2, ensure_ascii=False)}
        if delta is not None:
            outputs["delta.json"] = json.dumps(delta, indent=2)
        for name, body in outputs.items():
            artifact_path = args.output / name
            artifact_path.write_text(body, encoding="utf-8")
        print(json.dumps({"status": "rendered", "records": len(view["cards"]), "audience": view["audience"], "output": str(args.output),
                          "artifacts": {name: str(args.output / name) for name in outputs}, "network_calls": 0}))
        return 0
    except (OSError, ValueError, RecursionError) as exc:
        error = str(exc)
        if isinstance(exc, OSError) and args.output is not None:
            if new_output_created:
                error = (f"Could not finish new output at {artifact_path}: {exc}. "
                         f"Files in {args.output} may be partial; fix the cause and choose a fresh --output directory. "
                         "Prior output was not overwritten.")
            else:
                error = (f"Could not create output directory {args.output}: {exc}. "
                         "Fix the cause and choose a new --output directory.")
        if args.json_errors:
            print(json.dumps({"status": "error", "error": error, "network_calls": 0}), file=sys.stderr)
        else:
            print(f"Evidence build stopped: {error}", file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
