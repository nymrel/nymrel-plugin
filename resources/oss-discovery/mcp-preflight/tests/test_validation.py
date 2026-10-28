"""Offline scenario contracts, uncertainty, privacy, and input preservation."""

from __future__ import annotations

import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import shutil
import socket
import subprocess
import tempfile
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "validation"
SPEC = importlib.util.spec_from_file_location("preflight_scenarios_test", PACK / "run_scenarios.py")
assert SPEC is not None and SPEC.loader is not None
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


class ScenarioTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.output = self.root / "results"

    def copy_pack(self):
        target = self.root / "pack"
        shutil.copytree(PACK, target, ignore=shutil.ignore_patterns("__pycache__"))
        return target / "cases.json"

    def invoke(self, manifest=None):
        args = ["--output", str(self.output)]
        if manifest is not None:
            args += ["--cases", str(manifest)]
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = runner.main(args)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_all_five_cases_execute_but_human_metrics_remain_unknown(self):
        status, stdout, stderr = self.invoke()
        self.assertEqual((status, stderr), (0, ""))
        self.assertIn("Human comparison", stdout)
        result = json.loads((self.output / "result.json").read_text())
        self.assertEqual(result["automated_fixture_results"], {"cases": 5, "passed": 5, "failed": 0})
        self.assertEqual(result["human_comparison"]["status"], "not-run")
        for key, value in result["human_comparison"].items():
            if key != "status":
                self.assertIsNone(value, key)
        self.assertIsNone(result["incumbent_baseline"]["version"])
        self.assertEqual(result["incumbent_baseline"]["status"], "not-run")
        self.assertEqual(result["core_sha256"], hashlib.sha256((ROOT / "preflight.py").read_bytes()).hexdigest())

    def test_hidden_dependency_is_not_invented_from_python_launcher(self):
        result, reports = runner.run_cases(PACK / "cases.json")
        report = reports["hidden-dependency-unknown"]
        self.assertEqual([item["code"] for item in report["findings"]], ["timeout-stage-unknown"])
        self.assertIn("does not establish whether", report["findings"][0]["detail"])
        self.assertEqual(report["servers"][0]["launch_kind"], "local-command")
        case_result = next(item for item in result["scenarios"] if item["id"] == "hidden-dependency-unknown")
        self.assertTrue(case_result["checks"]["required_uncertainty_preserved"])
        self.assertTrue(case_result["checks"]["forbidden_categories_absent"])

    def test_stronger_runtime_log_changes_evidence_and_fails_hidden_case_contract(self):
        manifest = self.copy_pack()
        (manifest.parent / "cases" / "hidden-dependency-unknown.log").write_text("node ENOENT\nClientRequest timeout\n")
        status, _, _ = self.invoke(manifest)
        self.assertEqual(status, 1)
        result = json.loads((self.output / "result.json").read_text())
        hidden = next(item for item in result["scenarios"] if item["id"] == "hidden-dependency-unknown")
        self.assertEqual(hidden["status"], "failed")
        self.assertFalse(hidden["checks"]["forbidden_categories_absent"])
        self.assertEqual(result["automated_fixture_results"]["failed"], 1)
        self.assertEqual(result["human_comparison"]["status"], "not-run")

    def test_combined_log_stays_a_stream_hypothesis(self):
        _, reports = runner.run_cases(PACK / "cases.json")
        finding = reports["installer-streams"]["findings"][0]
        self.assertIn("hypothesis", finding["detail"])
        self.assertIn("do not prove stream contamination", finding["detail"])

    def test_false_readiness_regression_is_detected(self):
        cases = runner.load_cases(PACK / "cases.json")
        case = next(item for item in cases if item["id"] == "no-signal")
        report = runner.core.analyze({})
        report["assessment"] = "ready"
        result = runner.score_report(case, report)
        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["checks"]["no_readiness_or_security_assessment"])

    def test_unsupported_causal_claim_cannot_pass_by_preserving_old_category(self):
        case = next(item for item in runner.load_cases(PACK / "cases.json") if item["id"] == "hidden-dependency-unknown")
        _, reports = runner.run_cases(PACK / "cases.json")
        report = copy.deepcopy(reports["hidden-dependency-unknown"])
        report["findings"][0]["detail"] += " Node is the root cause."
        result = runner.score_report(case, report)
        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["checks"]["no_unsupported_causal_claim"])

    def test_uncertainty_words_do_not_match_affirmative_cause_substrings(self):
        case = next(item for item in runner.load_cases(PACK / "cases.json") if item["id"] == "hidden-dependency-unknown")
        _, reports = runner.run_cases(PACK / "cases.json")
        for phrase in ("unverified cause", "unconfirmed cause", "indefinite cause"):
            with self.subTest(phrase=phrase):
                report = copy.deepcopy(reports["hidden-dependency-unknown"])
                report["findings"][0]["detail"] += " This remains an " + phrase + "."
                result = runner.score_report(case, report)
                self.assertEqual(result["status"], "passed")
                self.assertTrue(result["checks"]["no_unsupported_causal_claim"])

    def test_simple_explicit_negations_do_not_become_affirmative_claims(self):
        case = next(item for item in runner.load_cases(PACK / "cases.json") if item["id"] == "hidden-dependency-unknown")
        _, reports = runner.run_cases(PACK / "cases.json")
        phrases = (
            "This is not a confirmed cause.",
            "There is no verified cause.",
            "This is never the definite root cause.",
            "It is not an established result and not the confirmed root cause.",
        )
        for phrase in phrases:
            with self.subTest(phrase=phrase):
                report = copy.deepcopy(reports["hidden-dependency-unknown"])
                report["findings"][0]["detail"] += " " + phrase
                result = runner.score_report(case, report)
                self.assertEqual(result["status"], "passed")
                self.assertTrue(result["checks"]["no_unsupported_causal_claim"])

    def test_affirmative_cause_claims_still_fail_after_negation_scrubbing(self):
        case = next(item for item in runner.load_cases(PACK / "cases.json") if item["id"] == "hidden-dependency-unknown")
        _, reports = runner.run_cases(PACK / "cases.json")
        for phrase in ("This is a confirmed root cause.", "Node is the root cause.", "No verified cause exists here. npm is the root cause."):
            with self.subTest(phrase=phrase):
                report = copy.deepcopy(reports["hidden-dependency-unknown"])
                report["findings"][0]["detail"] += " " + phrase
                result = runner.score_report(case, report)
                self.assertEqual(result["status"], "failed")
                self.assertFalse(result["checks"]["no_unsupported_causal_claim"])

    def test_outputs_omit_seeded_values_raw_input_and_input_paths(self):
        status, out, err = self.invoke()
        self.assertEqual(status, 0)
        emitted = out + err + "".join(p.read_text() for p in self.output.iterdir())
        for marker in runner.SEED_MARKERS:
            self.assertNotIn(marker, emitted)
        self.assertNotIn("synthetic_pinned_fetch", emitted)
        self.assertNotIn("example.invalid", emitted)
        self.assertNotIn(str(PACK), emitted)
        self.assertNotIn("ClientRequest timed out waiting for a tool response", emitted)

    def test_no_subprocess_network_or_local_runtime_lookup(self):
        with patch.object(subprocess, "Popen", side_effect=AssertionError("no execution")), \
             patch.object(subprocess, "run", side_effect=AssertionError("no execution")), \
             patch.object(socket, "create_connection", side_effect=AssertionError("no network")), \
             patch.object(urllib.request, "urlopen", side_effect=AssertionError("no network")), \
             patch.object(runner.core.shutil, "which", side_effect=AssertionError("no runtime lookup")):
            status, _, _ = self.invoke()
        self.assertEqual(status, 0)

    def test_case_inputs_remain_byte_identical(self):
        manifest = self.copy_pack()
        before = {p.relative_to(manifest.parent): p.read_bytes() for p in manifest.parent.rglob("*") if p.is_file()}
        self.assertEqual(self.invoke(manifest)[0], 0)
        after = {p.relative_to(manifest.parent): p.read_bytes() for p in manifest.parent.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_inconsistent_expectations_rejected_before_output(self):
        manifest = self.copy_pack()
        document = json.loads(manifest.read_text())
        document["cases"][0]["expected"]["forbidden_codes"].append("runtime-log-signal")
        manifest.write_text(json.dumps(document))
        status, _, err = self.invoke(manifest)
        self.assertEqual(status, 2)
        self.assertIn("inconsistent", err)
        self.assertFalse(self.output.exists())

    def test_expectations_cannot_claim_safe_ready_or_verified(self):
        manifest = self.copy_pack()
        document = json.loads(manifest.read_text())
        for value in ("safe", "ready", "verified", ["not-verified"]):
            with self.subTest(value=value):
                document["cases"][0]["expected"]["assessment"] = value
                manifest.write_text(json.dumps(document))
                self.assertEqual(self.invoke(manifest)[0], 2)
                self.assertFalse(self.output.exists())

    def test_unknown_duplicate_and_missing_cases_rejected(self):
        manifest = self.copy_pack()
        original = json.loads(manifest.read_text())
        variants = []
        document = copy.deepcopy(original)
        document["cases"][0]["id"] = "PRIVATE_CASE_LABEL"
        variants.append(document)
        document = copy.deepcopy(original)
        document["cases"][0]["id"] = document["cases"][1]["id"]
        variants.append(document)
        document = copy.deepcopy(original)
        document["cases"].pop()
        variants.append(document)
        for document in variants:
            with self.subTest(document=document):
                manifest.write_text(json.dumps(document))
                status, out, err = self.invoke(manifest)
                self.assertEqual(status, 2)
                self.assertNotIn("PRIVATE_CASE_LABEL", out + err)
                self.assertFalse(self.output.exists())

    def test_unknown_or_duplicate_expected_categories_rejected(self):
        manifest = self.copy_pack()
        original = json.loads(manifest.read_text())
        for codes in (["PRIVATE_CATEGORY"], ["runtime-log-signal", "runtime-log-signal"]):
            document = copy.deepcopy(original)
            document["cases"][0]["expected"]["required_codes"] = codes
            manifest.write_text(json.dumps(document))
            status, out, err = self.invoke(manifest)
            self.assertEqual(status, 2)
            self.assertNotIn("PRIVATE_CATEGORY", out + err)
            self.assertFalse(self.output.exists())

    def test_case_references_cannot_escape_pack_or_follow_symlink(self):
        manifest = self.copy_pack()
        original = json.loads(manifest.read_text())
        outside = self.root / "PRIVATE_OUTSIDE.json"
        outside.write_text('{"mcpServers":{}}')
        for reference in ("../PRIVATE_OUTSIDE.json", str(outside)):
            document = copy.deepcopy(original)
            document["cases"][0]["config"] = reference
            manifest.write_text(json.dumps(document))
            status, out, err = self.invoke(manifest)
            self.assertEqual(status, 2)
            self.assertNotIn("PRIVATE_OUTSIDE", out + err)
            self.assertFalse(self.output.exists())
        link = manifest.parent / "cases" / "linked.json"
        try:
            link.symlink_to(outside)
        except (OSError, NotImplementedError):
            return
        document = copy.deepcopy(original)
        document["cases"][0]["config"] = "cases/linked.json"
        manifest.write_text(json.dumps(document))
        self.assertEqual(self.invoke(manifest)[0], 2)
        self.assertFalse(self.output.exists())

    def test_missing_or_malformed_case_inputs_do_not_echo_context(self):
        manifest = self.copy_pack()
        path = manifest.parent / "cases" / "missing-runtime.json"
        path.write_text('{"PRIVATE_BROKEN_CONFIG":')
        status, out, err = self.invoke(manifest)
        self.assertEqual(status, 2)
        self.assertNotIn("PRIVATE_BROKEN_CONFIG", out + err)
        self.assertNotIn(str(path), out + err)
        self.assertFalse(self.output.exists())

    def test_existing_output_is_untouched(self):
        self.output.mkdir()
        sentinel = self.output / "result.json"
        sentinel.write_text("DO_NOT_REPLACE")
        self.assertEqual(self.invoke()[0], 2)
        self.assertEqual(sentinel.read_text(), "DO_NOT_REPLACE")
        self.assertEqual(len(list(self.output.iterdir())), 1)

    def test_nul_output_and_bad_cli_values_are_private_safe(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            status = runner.main(["--output", "PRIVATE_BAD\x00PATH"])
        self.assertEqual(status, 2)
        self.assertNotIn("PRIVATE_BAD", out.getvalue() + err.getvalue())
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            status = runner.main(["--private-flag", "PRIVATE_VALUE"])
        self.assertEqual(status, 2)
        self.assertNotIn("PRIVATE_VALUE", out.getvalue() + err.getvalue())

    def test_blank_human_observation_templates_contain_no_fictional_outcomes(self):
        document = json.loads((PACK / "observations-template.json").read_text())
        self.assertEqual(document["status"], "not-run")
        self.assertEqual(document["paired_observations"], [])
        self.assertIsNone(document["consenting_participants"])
        self.assertIsNone(document["diagnosis_accuracy"])
        self.assertIsNone(document["median_time_improvement_percent"])
        self.assertIsNone(document["repeat_users"])
        self.assertTrue({"proposed_next_action", "confidence", "task_order", "fixture_revision"} <= set(document["observation_fields"]))
        self.assertEqual(len((PACK / "observations-template.csv").read_text().splitlines()), 1)

    def test_participant_files_are_neutral_and_match_the_facilitator_cases(self):
        cards = (PACK / "TASK_CARDS.md").read_text()
        for label, identifier in zip("ABCDE", runner.CASE_IDS):
            self.assertNotIn(identifier, cards)
            self.assertEqual((PACK / "participant-cases" / (label + ".config.json")).read_bytes(), (PACK / "cases" / (identifier + ".json")).read_bytes())
            self.assertEqual((PACK / "participant-cases" / (label + ".log")).read_bytes(), (PACK / "cases" / (identifier + ".log")).read_bytes())

    def test_results_bound_the_incumbent_comparison_to_documentation(self):
        result, _ = runner.run_cases(PACK / "cases.json")
        baseline = result["incumbent_baseline"]
        self.assertEqual(baseline["name"], "MCP Inspector documentation")
        self.assertIsNone(baseline["documentation_revision"])
        self.assertIn("live Inspector diagnostics are not evaluated", baseline["comparison_scope"])


if __name__ == "__main__":
    unittest.main()
