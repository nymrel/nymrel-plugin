# Disposable view input, not a new ledger

Implementation: `../scripts/evidence_workspace.py`. Python 3.10+, standard library.
The input is a minimal projection of already-retrieved connector results. It never
fetches URLs, authenticates, writes back, changes authority, or verifies signatures.
All output conclusions are scoped to supplied evidence. Do not feed the view back
as stronger evidence than its underlying sources.

## Envelope

- `format`: `nymrel-evidence-view/1`
- `title`: focused question/title, at most 220 characters
- `scope`: exact scope/coverage limitations, at most 1,600 characters
- `captured_at`: ISO timestamp with timezone for this export
- `freshness_hours`: explicit local review window, positive and at most 720;
  this is an operator-selected view policy, not a vendor freshness guarantee
- `records`: at most 100 records; full input <= 2 MiB

Each record has exactly `id`, `kind`, `audience`, `title`, `source_url`,
`observed_at`, `data`. IDs are stable lowercase identifiers. Do not renumber an
existing item to manufacture a delta. `audience` must explicitly be `private` or
`public`; no implicit public default. `observed_at` is the timestamp when source
read evidence was captured, not a claim that a provider event happened then.
A later re-fetch is not a newer merge/release/news event. Missing reliable
observation timing must be disclosed rather than invented.

Source links must be credential-free HTTPS, with no query parameters or unsafe
link delimiters. Supported provider hosts are GitHub, ChatGPT for plugin identity,
and official OpenAI domains for this initial capability adapter. This is a bounded
provider set; extending it requires explicit mapping and tests, not fake URLs.

## Adapters

**github_issue** data contains exactly:
`issue_number`, `state`, `state_reason`, `updated_at`, `closed_at`, and optional
`summary` and `next_action` (each at most 1,200 characters). Copy native state
fields from an authorized current GitHub issue read. The positive integer issue
number must match a credential-free `https://github.com/OWNER/REPO/issues/NUMBER`
source link; PR paths, mismatching IDs and comment fragments are rejected.
Do not copy the raw issue body, comments, assignees or customer records.

`state` is `open` or `closed`. An open issue has null `closed_at` and a null or
`reopened` reason. A closed issue needs `closed_at` and a null, `completed`,
`not_planned` or `duplicate` reason. Closure must not be later than `updated_at`;
source update must not be later than the observation. Re-fetching unchanged
source changes observation time, not the source update revision.

Optional summary/next action are minimized sourced text, not executable commands
or authorization. Open issues appear under Goals & issues. Closed issues appear
in History; a supplied next action is not presented as active direction after
closure. A `completed` reason becomes **Closed · reported complete**, with
execution and accepted completion still unverified. The viewer does not infer a
completion percentage, worker acknowledgment, tests or deployment from issue
state, checkboxes or a closure reason. This adapter is a presentation of the
existing goal record, not another goal store or execution system.

**github_pr** data contains:
`state`, `draft`, `merged`, `merged_at`, `head_sha`, `merge_commit_sha`, and optional
`reviews` and `checks`. Use native GitHub field meanings. `merge_commit_sha` alone
is not merge proof: GitHub can expose a test merge commit for an unmerged PR.
`reviews` is null when unqueried, otherwise a retrieved list with `reviewer`,
`state`, `commit_id`, `submitted_at`, `url`. `checks` is null when unqueried,
otherwise a list with `id` (string), `name`, `head_sha`, `status`, `conclusion`,
`url`, and optional actual `step_count`. A check list is not evidence of complete
required-check coverage. Reviewer independence remains outside the adapter.

**plugin_release** data contains:
`plugin_id`, `name`, `version`, `current_release_id`, `scope`, `discoverability`,
as returned by Plugin Creator. Private discoverability cannot be relabeled public.
Preserve current `PRIVATE`, `UNLISTED` and `LISTED` values; legacy `PUBLIC` input
remains accepted for existing snapshots. Discoverability never determines the
record's audience or grants publication authority. A private source record stays
private even when the plugin itself is listed.
Use the exact returned plugin URL, not a guessed slug. Saved metadata is not host
invocation proof. This version intentionally does not accept a made-up `installed`
or `production_ready` flag.

**handoff** data contains:
`comment_id` (positive integer), `created_at`, `target`, `summary`.
Use an exact GitHub issue-comment URL with a matching ID. This adapter proves only
that the supplied source records a handoff, never owner acceptance. Retrieve later
owner responses separately and explain them in the sourced brief until an explicit
acknowledgment adapter has been designed and tested.

**capability** data contains:
`summary`, `existing_owner`, `next_test`, `limitations` (list).
These are carefully sourced summaries and clearly proposed adoption steps, not
operational status. The source is an official OpenAI document. Do not include
unsupported plan prices, guarantees, dates, or model benchmarks.

## Privacy and failure behavior

Unknown fields are rejected, so raw body text, tokens, or accidental customer data
cannot silently enter the view through extra fields. Known credential-like strings
are rejected as defense in depth; this is not a comprehensive DLP detector.
The caller must minimize data and classify visibility correctly. A GitHub path's
appearance does not establish its repository visibility.

Public exports remove private cards and private envelope title/scope before
serialization, rendering, totals, and source hashing. They do not include a hidden
private payload or private-record count. Public export is not public publication.
Do not upload a private report or its source JSON to a public host.

The renderer escapes untrusted text and embeds no remote fonts, images, scripts,
telemetry, storage, or automatic refresh. Hash-based CSP permits its fixed UI
script and style; `connect-src 'none'` prevents network reads. Source navigation
requires a user click. The export includes all cards of the view audience, not
only the filtered results, which the interface states explicitly.

`build` writes a new directory with `index.html`, `brief.md`, and `view.json`.
`compare` additionally writes `delta.json`. Existing output paths are refused.
Exit 0 means local rendering completed; exit 2 means input or write validation
failed. Neither exit code certifies source authenticity or product readiness.


## Coordination updates

Use `coordination_update` for a minimized source-reported state of an existing
lane. This is a derived display record; it neither creates work nor authenticates
owner custody. The source must be an exact credential-free GitHub issue or PR
comment URL (`/OWNER/REPO/issues/NUMBER#issuecomment-ID` or `/pull/NUMBER`).

Data contains exactly these nine keys:

| Field | Contract |
| --- | --- |
| `lane_id` | Original stable lowercase lane ID; 1–96 characters using record-ID syntax. Preserve it across updates. |
| `project` | Nonempty sourced project name, at most 220 characters. |
| `owner` | Sourced owner label, at most 220 characters, or null when unverified. A reported name is not a current live claim. |
| `source_date` | Explicit checkpoint date in the source body as YYYY-MM-DD, no later than observation UTC date; null when absent. Never substitute issue-update or retrieval time. |
| `state` | `needs_acceptance`, `next_action`, `blocked`, `reported_complete`, `superseded`, or `research`. These are presentation categories. |
| `summary` | Minimized sourced account of the material change, at most 1,200 characters. |
| `next_action` | Sourced next step, at most 1,200 characters, or null. No commands or implied execution authority. |
| `checkpoint_at` | Actual stated checkpoint ISO timestamp with timezone, or null. Future planned checkpoints are permitted. |
| `supersedes` | Up to 100 distinct stable record IDs explicitly replaced by this source; empty when none. |

Supersession must point to an included coordination update in the same lane and
audience. Self references, missing targets, cycles, cross-lane and cross-audience
relationships are rejected. Caller-supplied replacement links must be grounded
in the original source; validation checks consistency, not authenticity. Timestamps
alone never supersede an update. A standalone `superseded` source state may
remain historical when its replacement is unavailable; disclose that limitation.

Replaced records remain in History, with their former next action retained only
as historical data. Current action prompts are suppressed. Reported completion
has its own category and never supplies completion or acceptance proof.
Missing owners and checkpoints remain explicit. All coordination evidence grids
retain unverified custody and outcome boundaries.

Coordination snapshots default to Current updates, with History available.
Owner and project controls filter the view. Search, source disclosure and download
retain existing behavior. JSON export and no-JavaScript HTML include history.
Public projection removes private records before derived output and counts.
Use the pack's [material-change digest](../../../resources/material-change-digest.md)
for a short sourced update accompanying the snapshot.
