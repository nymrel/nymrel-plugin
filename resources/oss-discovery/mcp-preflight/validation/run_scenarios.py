#!/usr/bin/env python3
"""Run rights-cleared offline diagnostic scenarios; do not measure human value."""

from __future__ import annotations

import argparse
import hashlib
import html
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
CORE_PATH = HERE.parent / "preflight.py"
SPEC = importlib.util.spec_from_file_location("nymrel_preflight_validation_core", CORE_PATH)
assert SPEC is not None and SPEC.loader is not None
core = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(core)

SCHEMA = "nymrel-preflight-scenarios/0.1"
CASE_IDS = (
    "missing-runtime", "installer-streams", "certificate-egress",
    "hidden-dependency-unknown", "no-signal",
)
CODE_NAMES = frozenset({
    "ambiguous-launch", "package-resolution", "package-pin-unconfirmed",
    "local-runtime-not-found", "unrecognized-launch", "certificate-verification-config",
    "runtime-log-signal", "certificate-log-signal", "proxy-log-signal",
    "timeout-stage-unknown", "installer-protocol-log-signal", "registry-egress-log-signal",
})
ASSESSMENTS = frozenset({"needs-investigation", "not-verified"})
UNCERTAINTY_PHRASES = {
    "installer-streams": "combined stdout/stderr logs do not prove stream contamination",
    "hidden-dependency-unknown": "does not establish whether",
    "no-signal": "not a readiness, safety, or connection result",
}
SEED_MARKERS = (
    "PILOT_NAME_SENTINEL", "PILOT_ARG_SENTINEL", "PILOT_ENV_SENTINEL",
    "PILOT_URL_SENTINEL", "PILOT_LOG_SENTINEL", "PILOT_HEADER_SENTINEL",
)


class ScenarioError(ValueError):
    """A fixed, private-safe validation failure."""


def manifest_file(root: Path, value: Any) -> Path:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ScenarioError("Case file references must be relative paths inside the case pack.")
    relative = Path(value)
    if relative.is_absolute() or any(part in {"..", "."} for part in relative.parts):
        raise ScenarioError("Case file references must be relative paths inside the case pack.")
    path = root / relative
    try:
        if any((root.joinpath(*relative.parts[:index])).is_symlink()
               for index in range(1, len(relative.parts) + 1)):
            raise ScenarioError("Symlinked case files are not supported.")
        path.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        raise ScenarioError("Case file references must stay inside the case pack.") from None
    return path


def load_cases(path: Path) -> list[dict[str, Any]]:
    def reject_number(value: str) -> None:
        raise ScenarioError("The case manifest does not support numeric values.")

    try:
        document = json.loads(core.read_text(path, "case manifest"), object_pairs_hook=core.unique_pairs,
                              parse_int=reject_number, parse_float=reject_number,
                              parse_constant=reject_number)
    except (core.InputError, ValueError, RecursionError, OverflowError):
        raise ScenarioError("The case manifest is invalid or unavailable.") from None
    if not isinstance(document, dict) or set(document) != {"schema", "cases"} or document["schema"] != SCHEMA:
        raise ScenarioError("The case manifest has an unsupported schema.")
    cases = document["cases"]
    if not isinstance(cases, list) or len(cases) != len(CASE_IDS):
        raise ScenarioError("The case pack must contain the five defined scenarios.")
    ids: list[str] = []
    for case in cases:
        if not isinstance(case, dict) or set(case) != {"id", "config", "log", "expected"}:
            raise ScenarioError("A scenario contains unsupported fields.")
        if case["id"] not in CASE_IDS or case["id"] in ids:
            raise ScenarioError("Scenario identifiers must be the five unique defined identifiers.")
        ids.append(case["id"])
        expected = case["expected"]
        if not isinstance(expected, dict) or set(expected) != {"assessment", "required_codes", "allowed_codes", "forbidden_codes"}:
            raise ScenarioError("A scenario expectation has an unsupported shape.")
        if not isinstance(expected["assessment"], str) or expected["assessment"] not in ASSESSMENTS:
            raise ScenarioError("Scenario expectations cannot declare readiness or security.")
        groups = []
        for key in ("required_codes", "allowed_codes", "forbidden_codes"):
            values = expected[key]
            if not isinstance(values, list) or not all(isinstance(item, str) and item in CODE_NAMES for item in values):
                raise ScenarioError("Scenario expectations must use known diagnostic categories.")
            if len(values) != len(set(values)):
                raise ScenarioError("Scenario expectation categories must be unique.")
            groups.append(set(values))
        required, allowed, forbidden = groups
        if not required <= allowed or allowed & forbidden:
            raise ScenarioError("Scenario expectations are inconsistent.")
        manifest_file(path.parent, case["config"])
        if case["log"] is not None:
            manifest_file(path.parent, case["log"])
    return cases


def score_report(case: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    expected = case["expected"]
    codes = {item.get("code") for item in report.get("findings", [])}
    text = json.dumps(report, sort_keys=True).lower()
    # These are checks of declared scenario contracts, not a general truth classifier.
    cause_phrase = r"\b(?:(?:confirmed|verified|definite)\s+(?:root\s+)?cause|(?:node|npm)\s+is\s+the\s+root\s+cause)\b"
    # Scrub only these explicit, bounded negations before the affirmative check.
    # This does not attempt to infer arbitrary sentence meaning.
    claim_text = re.sub(r"\b(?:no|not|never)\s+(?:(?:a|an|the)\s+)?" + cause_phrase, "", text)
    unsupported = re.search(cause_phrase, claim_text)
    checks = {
        "expected_assessment": report.get("assessment") == expected["assessment"],
        "no_readiness_or_security_assessment": report.get("assessment") in ASSESSMENTS,
        "required_categories_present": set(expected["required_codes"]) <= codes,
        "only_allowed_categories": codes <= set(expected["allowed_codes"]),
        "forbidden_categories_absent": not (codes & set(expected["forbidden_codes"])),
        "no_unsupported_causal_claim": unsupported is None,
        "seeded_values_absent": not any(marker.lower() in text for marker in SEED_MARKERS),
    }
    phrase = UNCERTAINTY_PHRASES.get(case["id"])
    if phrase is not None:
        checks["required_uncertainty_preserved"] = phrase in text
    return {"id": case["id"], "status": "passed" if all(checks.values()) else "failed",
            "checks": checks, "finding_codes": sorted(code for code in codes if isinstance(code, str))}


def run_cases(path: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    cases = load_cases(path)
    results = []
    reports = {}
    for case in cases:
        try:
            config = core.read_text(manifest_file(path.parent, case["config"]), "scenario configuration")
            log = "" if case["log"] is None else core.read_text(manifest_file(path.parent, case["log"]), "scenario log")
            report = core.analyze(core.parse_config(config), log, check_local_runtimes=False)
        except core.InputError:
            raise ScenarioError("A scenario input is invalid or unavailable; no results were written.") from None
        reports[case["id"]] = report
        results.append(score_report(case, report))
    passed = sum(item["status"] == "passed" for item in results)
    return {
        "schema": "nymrel-preflight-scenario-result/0.1",
        "evidence_mode": "rights-cleared synthetic offline fixtures",
        "status": "passed" if passed == len(results) else "failed",
        "core_sha256": hashlib.sha256(CORE_PATH.read_bytes()).hexdigest(),
        "evaluator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "automated_fixture_results": {"cases": len(results), "passed": passed, "failed": len(results) - passed},
        "scenarios": results,
        "human_comparison": {
            "status": "not-run", "consenting_participants": None,
            "paired_observations": None, "diagnosis_accuracy": None,
            "median_time_improvement_percent": None, "repeat_users": None,
        },
        "incumbent_baseline": {
            "name": "MCP Inspector documentation", "status": "not-run", "version": None,
            "documentation_revision": None,
            "comparison_scope": "Supplied-file/documentation comparison only; live Inspector diagnostics are not evaluated.",
        },
        "limits": [
            "Passing fixtures checks declared diagnostic behavior, not real-world diagnosis or a product gap.",
            "No server, package, subprocess, or network request was run by this evaluator.",
            "The hidden dependency scenario intentionally lacks enough evidence to identify Node or npm.",
            "Human outcomes, comparative usefulness, repeat use, and security clearance remain unmeasured.",
        ],
    }, reports


def result_html(result: dict[str, Any]) -> str:
    rows = []
    for item in result["scenarios"]:
        details = ", ".join(name for name, passed in item["checks"].items() if not passed) or "Declared checks passed"
        rows.append(f"<tr><td><a href='{html.escape(item['id'], quote=True)}.html'>{html.escape(item['id'])}</a></td><td>{html.escape(item['status'])}</td><td>{html.escape(details)}</td></tr>")
    return """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"><meta name="referrer" content="no-referrer"><title>Offline scenario results — Nymrel</title><style>body{max-width:880px;margin:auto;padding:24px 18px;font:17px/1.6 system-ui,sans-serif;color:#20312d;background:#f3f4f1}main{background:white;padding:20px;border:1px solid #cbd5cf;border-radius:12px}h1{line-height:1.2}table{width:100%;border-collapse:collapse;table-layout:fixed}td,th{text-align:left;vertical-align:top;border-bottom:1px solid #cbd5cf;padding:8px;overflow-wrap:anywhere}a{color:#164f3c}a:focus-visible{outline:3px solid #164f3c;outline-offset:3px}@media(max-width:420px){table{font-size:.8rem}td,th{padding:5px}}</style></head><body><main><p>NYMREL · SYNTHETIC FIXTURE EVALUATION</p><h1>Offline diagnostic scenarios</h1><p>""" + html.escape(result["status"]) + """ — these results check declared fixture behavior.</p><p><strong>Human comparison: not run.</strong> Participant outcomes, time savings, repeat use, incumbent version, and product demand remain unknown.</p><p>The prepared human comparison is limited to supplied files and documentation. Inspector's live diagnostics have not been evaluated.</p><table><thead><tr><th>Scenario</th><th>Result</th><th>Check details</th></tr></thead><tbody>""" + "".join(rows) + """</tbody></table><p>No MCP server or package was started, and no network request was made. A fixture pass is not a readiness, security, adoption, or real-issue reproduction result.</p></main></body></html>"""


def write_outputs(result: dict[str, Any], reports: dict[str, dict[str, Any]], output: Path) -> None:
    files = {"result.json": json.dumps(result, indent=2) + "\n", "index.html": result_html(result)}
    for identifier, report in reports.items():
        files[identifier + ".report.json"] = json.dumps(report, indent=2) + "\n"
        files[identifier + ".html"] = core.render_html(report)
    try:
        output.mkdir(mode=0o700, exist_ok=False)
    except (OSError, ValueError):
        raise ScenarioError("Output must be a new directory with an existing writable parent.") from None
    written = []
    try:
        for name, value in files.items():
            target = output / name
            with target.open("x", encoding="utf-8") as stream:
                written.append(target)
                stream.write(value)
    except OSError:
        for target in written:
            try:
                target.unlink()
            except OSError:
                pass
        try:
            output.rmdir()
        except OSError:
            pass
        raise ScenarioError("Scenario output could not be completed; existing output was not overwritten.") from None


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ScenarioError("Invalid arguments. Use --help for supported options.")


def main(argv: list[str] | None = None) -> int:
    parser = Parser(prog="preflight-scenarios", description=__doc__)
    parser.add_argument("--cases", type=Path, default=HERE / "cases.json", help="Explicit local scenario manifest")
    parser.add_argument("--output", type=Path, required=True, help="New output directory")
    try:
        args = parser.parse_args(argv)
        result, reports = run_cases(args.cases)
        write_outputs(result, reports, args.output)
    except ScenarioError as error:
        print(f"Evaluation stopped: {error}", file=sys.stderr)
        return 2
    print("Synthetic fixture evaluation completed. Human comparison and product usefulness remain unmeasured.")
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
