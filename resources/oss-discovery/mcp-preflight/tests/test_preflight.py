"""Synthetic behavior and confidentiality checks for the local experiment."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import socket
import subprocess
import tempfile
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("preflight", ROOT / "preflight.py")
preflight = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(preflight)


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = self.root / "config.json"
        self.output = self.root / "new-output"

    def run_cli(self, config=None, log=None, arguments=None):
        if config is not None:
            self.config.write_text(config if isinstance(config, str) else json.dumps(config), encoding="utf-8")
        args = ["--config", str(self.config), "--output", str(self.output)]
        if log is not None:
            log_path = self.root / "log.txt"
            log_path.write_text(log, encoding="utf-8")
            args += ["--log", str(log_path)]
        args += arguments or []
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            status = preflight.main(args)
        return status, out.getvalue(), err.getvalue()

    def report(self):
        return json.loads((self.output / "report.json").read_text())

    def test_synthetic_demo_is_actionable_and_hypothesis_scoped(self):
        config = json.loads((ROOT / "fixtures" / "package-runner.json").read_text())
        log = (ROOT / "fixtures" / "setup.log").read_text()
        code, stdout, stderr = self.run_cli(config, log)
        self.assertEqual((code, stderr), (0, ""))
        report = self.report()
        codes = {item["code"] for item in report["findings"]}
        self.assertTrue({"package-resolution", "package-pin-unconfirmed", "runtime-log-signal", "timeout-stage-unknown", "installer-protocol-log-signal", "registry-egress-log-signal"} <= codes)
        self.assertEqual(report["assessment"], "needs-investigation")
        mixed = next(item for item in report["findings"] if item["code"] == "installer-protocol-log-signal")
        self.assertIn("hypothesis", mixed["detail"])
        self.assertIn("no connection or readiness result", stdout)

    def test_no_matches_is_never_ready(self):
        code, _, _ = self.run_cli({"mcpServers": {}})
        self.assertEqual(code, 0)
        self.assertEqual(self.report()["assessment"], "not-verified")
        self.assertEqual(self.report()["findings"], [])
        self.assertIn("No configured rule matched", (self.output / "index.html").read_text())

    def test_remote_entry_is_not_connection_verification(self):
        code, _, _ = self.run_cli({"servers": {"named": {"type": "http", "url": "https://example.invalid/token-secret"}}})
        self.assertEqual(code, 0)
        self.assertEqual(self.report()["assessment"], "not-verified")
        self.assertEqual(self.report()["servers"][0]["launch_kind"], "remote-endpoint")

    def test_unknown_launch_is_reported_not_passed(self):
        code, _, _ = self.run_cli({"servers": {"named": {"type": "future-transport"}}})
        self.assertEqual(code, 0)
        self.assertEqual(self.report()["findings"][0]["code"], "unrecognized-launch")
        self.assertEqual(self.report()["assessment"], "needs-investigation")

    def test_blank_endpoint_is_unrecognized(self):
        code, _, _ = self.run_cli({"servers": {"private": {"type": "http", "url": " \t\n "}}})
        self.assertEqual(code, 0)
        self.assertEqual(self.report()["servers"][0]["launch_kind"], "unrecognized")
        self.assertIn("unrecognized-launch", {item["code"] for item in self.report()["findings"]})

    def test_command_and_endpoint_do_not_select_transport(self):
        code, _, _ = self.run_cli({"mcpServers": {"named": {"command": "npx", "url": "https://example.invalid"}}})
        self.assertEqual(code, 0)
        self.assertEqual(self.report()["findings"][0]["code"], "ambiguous-launch")
        self.assertEqual(self.report()["servers"][0]["launch_kind"], "unrecognized")

    def test_secrets_and_injection_never_enter_reports_or_cli(self):
        secrets = ["NAME_PRIVATE_913", "ARG_PRIVATE_913", "ENV_PRIVATE_913", "URL_PRIVATE_913", "HEADER_PRIVATE_913", "LOG_PRIVATE_913", "PATH_PRIVATE_913"]
        self.config = self.root / (secrets[-1] + ".json")
        config = {"mcpServers": {
            secrets[0] + "<script>alert(1)</script>": {"command": "npx", "args": ["package@latest", secrets[1]], "env": {"TOKEN": secrets[2]}},
            "other": {"url": "https://example.invalid/" + secrets[3], "headers": {"Authorization": secrets[4]}}
        }}
        code, out, err = self.run_cli(config, secrets[5] + "<img src=x onerror=alert(1)>\x1b[31m npm warn JSON-RPC parse error")
        self.assertEqual(code, 0)
        emitted = out + err + (self.output / "report.json").read_text() + (self.output / "index.html").read_text()
        for secret in secrets:
            self.assertNotIn(secret, emitted)
        self.assertNotIn("<script>", emitted)
        self.assertNotIn("<img", emitted)
        self.assertNotIn("\x1b", emitted)
        self.assertNotIn(str(self.root), emitted)

    def test_malformed_multiline_json_has_no_raw_error_context(self):
        code, out, err = self.run_cli('{\n "mcpServers": {\n "SECRET_BAD_JSON":\n')
        self.assertEqual(code, 2)
        self.assertNotIn("SECRET_BAD_JSON", out + err)
        self.assertNotIn(str(self.config), out + err)
        self.assertFalse(self.output.exists())

    def test_duplicate_root_and_nested_keys_rejected(self):
        for data in ['{"mcpServers":{},"mcpServers":{}}', '{"mcpServers":{"private":{"command":"node","command":"other"}}}']:
            with self.subTest(data=data):
                code, _, err = self.run_cli(data)
                self.assertEqual(code, 2)
                self.assertIn("duplicate keys", err)
                self.assertNotIn("private", err)
                self.assertFalse(self.output.exists())

    def test_nonfinite_constants_rejected(self):
        for constant in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(constant=constant):
                code, _, err = self.run_cli('{"mcpServers":{},"ignored":' + constant + '}')
                self.assertEqual(code, 2)
                self.assertIn("nonfinite", err)

    def test_both_supported_roots_are_ambiguous_even_when_empty(self):
        code, _, err = self.run_cli({"mcpServers": {}, "servers": {}})
        self.assertEqual(code, 2)
        self.assertIn("exactly one", err)

    def test_large_numeric_literal_is_fixed_input_error(self):
        code, out, err = self.run_cli('{"mcpServers":{},"ignored":' + '9' * 10000 + '}')
        self.assertEqual(code, 2)
        self.assertIn("unsupported numeric literal", err)
        self.assertNotIn('9' * 50, out + err)
        self.assertFalse(self.output.exists())

    def test_float_overflow_is_rejected_consistently_across_runtimes(self):
        code, _, err = self.run_cli('{"mcpServers":{},"ignored":1e10000}')
        self.assertEqual(code, 2)
        self.assertIn("unsupported numeric literal", err)

    def test_invalid_shapes_fail_without_reporting_input(self):
        for config in [[], {}, {"mcpServers": []}, {"mcpServers": {"SECRET": []}}, {"mcpServers": {"SECRET": {"args": "SECRET"}}}, {"mcpServers": {"SECRET": {"args": [1]}}}, {"servers": {"SECRET": {"env": ["SECRET"]}}}, {"servers": {"SECRET": {"env": {"SECRET": 1}}}}]:
            with self.subTest(config=config):
                code, out, err = self.run_cli(config)
                self.assertEqual(code, 2)
                self.assertNotIn("SECRET", out + err)
                self.assertFalse(self.output.exists())

    def test_invalid_utf8_is_fixed_error(self):
        self.config.write_bytes(b"\xff\x00PRIVATE")
        code, out, err = self.run_cli()
        self.assertEqual(code, 2)
        self.assertIn("valid UTF-8", err)
        self.assertNotIn("PRIVATE", out + err)

    def test_embedded_nul_input_path_has_fixed_error(self):
        self.config = self.root / "PRIVATE_NUL\x00.json"
        code, out, err = self.run_cli()
        self.assertEqual(code, 2)
        self.assertNotIn("PRIVATE_NUL", out + err)
        self.assertNotIn("Traceback", out + err)

    def test_embedded_nul_output_path_has_fixed_error(self):
        self.output = self.root / "PRIVATE_NUL\x00"
        code, out, err = self.run_cli({"mcpServers": {}})
        self.assertEqual(code, 2)
        self.assertNotIn("PRIVATE_NUL", out + err)
        self.assertNotIn("Traceback", out + err)

    def test_server_count_limit_prevents_report_expansion(self):
        code, _, err = self.run_cli({"mcpServers": {str(i): {"command": "npx"} for i in range(preflight.MAX_SERVERS + 1)}})
        self.assertEqual(code, 2)
        self.assertIn("100 server entries", err)
        self.assertFalse(self.output.exists())

    def test_server_count_limit_boundary_is_supported(self):
        code, _, _ = self.run_cli({"mcpServers": {str(i): {"url": "https://example.invalid"} for i in range(preflight.MAX_SERVERS)}})
        self.assertEqual(code, 0)
        self.assertEqual(len(self.report()["servers"]), preflight.MAX_SERVERS)

    def test_bom_is_supported(self):
        self.config.write_bytes(b"\xef\xbb\xbf" + b'{"mcpServers":{}}')
        code, _, _ = self.run_cli()
        self.assertEqual(code, 0)

    def test_oversize_configuration_rejected(self):
        self.config.write_bytes(b" " * (preflight.MAX_INPUT_BYTES + 1))
        code, _, err = self.run_cli()
        self.assertEqual(code, 2)
        self.assertIn("2 MiB", err)

    def test_oversize_log_rejected_without_output(self):
        code, _, err = self.run_cli({"mcpServers": {}}, "x" * (preflight.MAX_INPUT_BYTES + 1))
        self.assertEqual(code, 2)
        self.assertIn("log exceeds", err)
        self.assertFalse(self.output.exists())

    def test_missing_input_does_not_disclose_path(self):
        self.config = self.root / "SECRET_MISSING_FILE.json"
        code, out, err = self.run_cli()
        self.assertEqual(code, 2)
        self.assertNotIn("SECRET_MISSING_FILE", out + err)
        self.assertNotIn(str(self.root), out + err)

    def test_unknown_cli_arguments_do_not_echo_values(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = preflight.main(["--secret-token", "SECRET_CLI"])
        self.assertEqual(code, 2)
        self.assertNotIn("SECRET_CLI", out.getvalue() + err.getvalue())

    def test_executable_and_network_functions_never_called(self):
        marker = self.root / "executed.txt"
        hostile = f"sh -c 'touch {marker}; curl https://example.invalid' $(echo SECRET)"
        with patch.object(subprocess, "run", side_effect=AssertionError("execution forbidden")), patch.object(subprocess, "Popen", side_effect=AssertionError("execution forbidden")), patch.object(socket, "create_connection", side_effect=AssertionError("network forbidden")), patch.object(urllib.request, "urlopen", side_effect=AssertionError("network forbidden")), patch.object(preflight.shutil, "which", side_effect=AssertionError("default lookup forbidden")):
            code, _, _ = self.run_cli({"servers": {"private": {"command": hostile}}})
        self.assertEqual(code, 0)
        self.assertFalse(marker.exists())
        self.assertEqual(self.report()["assessment"], "not-verified")

    def test_opt_in_runtime_lookup_is_bounded_and_path_not_exported(self):
        servers = {"a": {"command": "node"}, "b": {"command": "npx", "args": ["package@1.2.3"]}, "c": {"command": "/SECRET/bin/node"}, "d": {"command": "unknown"}}
        with patch.object(preflight.shutil, "which", side_effect=["/SECRET_RUNTIME_PATH/node", None]) as lookup:
            code, out, err = self.run_cli({"mcpServers": servers}, arguments=["--check-local-runtimes"])
        self.assertEqual(code, 0)
        self.assertEqual([call.args[0] for call in lookup.call_args_list], ["node", "npx"])
        self.assertNotIn("SECRET", out + err + (self.output / "report.json").read_text() + (self.output / "index.html").read_text())
        states = [item["local_runtime_lookup"] for item in self.report()["servers"]]
        self.assertEqual(states, ["found-on-this-path", "not-found-on-this-path", "not-checked", "not-checked"])

    def test_opt_in_runtime_lookup_does_not_execute_a_server(self):
        with patch.object(preflight.shutil, "which", return_value="/synthetic/node"), patch.object(subprocess, "Popen", side_effect=AssertionError("execution forbidden")):
            code, _, _ = self.run_cli({"mcpServers": {"private": {"command": "node"}}}, arguments=["--check-local-runtimes"])
        self.assertEqual(code, 0)
        self.assertEqual(self.report()["assessment"], "not-verified")

    def test_input_bytes_unchanged(self):
        self.config.write_bytes(b'{"mcpServers":{"private":{"command":"npx","args":["p@1.2.3"]}}}\n')
        original = self.config.read_bytes()
        code, _, _ = self.run_cli()
        self.assertEqual(code, 0)
        self.assertEqual(self.config.read_bytes(), original)

    def test_existing_output_directory_and_file_are_preserved(self):
        self.output.mkdir()
        sentinel = self.output / "report.json"
        sentinel.write_text("ORIGINAL")
        code, _, _ = self.run_cli({"mcpServers": {}})
        self.assertEqual(code, 2)
        self.assertEqual(sentinel.read_text(), "ORIGINAL")
        sentinel.unlink()
        self.output.rmdir()
        self.output.write_text("ORIGINAL_FILE")
        code, _, _ = self.run_cli({"mcpServers": {}})
        self.assertEqual(code, 2)
        self.assertEqual(self.output.read_text(), "ORIGINAL_FILE")

    def test_existing_and_broken_output_symlinks_are_preserved(self):
        for exists in (True, False):
            with self.subTest(target_exists=exists):
                target = self.root / ("target-existing" if exists else "target-missing")
                if exists:
                    target.mkdir()
                self.output.symlink_to(target, target_is_directory=True)
                code, _, _ = self.run_cli({"mcpServers": {}})
                self.assertEqual(code, 2)
                self.assertTrue(self.output.is_symlink())
                self.output.unlink()

    def test_unsupported_output_parent_is_fixed_error(self):
        self.output = self.root / "PRIVATE_MISSING_PARENT" / "new"
        code, out, err = self.run_cli({"servers": {}})
        self.assertEqual(code, 2)
        self.assertNotIn("PRIVATE_MISSING_PARENT", out + err)

    def test_known_certificate_flag_is_observed_without_change(self):
        config = {"mcpServers": {"private": {"command": "node", "env": {"NODE_TLS_REJECT_UNAUTHORIZED": "0", "TOKEN": "SECRET"}}}}
        code, _, _ = self.run_cli(config)
        self.assertEqual(code, 0)
        self.assertIn("certificate-verification-config", {item["code"] for item in self.report()["findings"]})
        self.assertEqual(json.loads(self.config.read_text()), config)

    def test_supported_runner_pins_are_conservative(self):
        for runner, args, expected in [("npx", ["--yes", "@scope/package@1.2.3"], True), ("npx", ["package@latest"], False), ("npx", ["--package", "p@1.2.3", "run"], False), ("npx", ["p@^1.2.3"], False), ("uvx", ["p==1.2.3"], True), ("uv", ["tool", "run", "p==1.2.3"], True), ("npm", ["exec", "p@1.2.3"], True), ("pipx", ["run", "p==1.2.3"], True), ("uvx", ["p==1.2.3garbage"], False), ("uvx", ["p==1.2.3-"], False), ("npm", ["exec", "p@1.2.3-."], False), ("npx", ["p@1.2.3-beta.1"], False)]:
            with self.subTest(runner=runner, args=args):
                self.assertEqual(preflight.direct_package_pin(args, runner), expected)

    def test_runner_cache_or_pin_does_not_claim_no_network(self):
        report = preflight.analyze({"private": {"command": "npx", "args": ["package@1.2.3"]}})
        self.assertEqual([f["code"] for f in report["findings"]], ["package-resolution"])
        self.assertIn("depending on its cache", report["findings"][0]["detail"])

    def test_log_rules_do_not_assert_shared_cause(self):
        code, _, _ = self.run_cli({"servers": {}}, "SELF_SIGNED_CERT_IN_CHAIN\nproxy denied\nregistry.npmjs.org\n403")
        self.assertEqual(code, 0)
        codes = {item["code"] for item in self.report()["findings"]}
        self.assertTrue({"certificate-log-signal", "proxy-log-signal", "registry-egress-log-signal"} <= codes)
        registry = next(item for item in self.report()["findings"] if item["code"] == "registry-egress-log-signal")
        self.assertIn("causal relationship", registry["detail"])

    def test_html_renderer_escapes_even_nonstandard_report_values(self):
        report = preflight.analyze({})
        report["assessment"] = '<script>alert("secret")</script>'
        rendered = preflight.render_html(report)
        self.assertNotIn("<script>", rendered)
        self.assertIn("&lt;script&gt;", rendered)
        self.assertIn("default-src 'none'", rendered)
        self.assertNotIn("<script ", rendered)

    def test_write_failure_cleans_only_own_new_files(self):
        original_render = preflight.render_html
        def fail_after_directory(report):
            raise OSError("SYNTHETIC_PRIVATE_PATH")
        with patch.object(preflight, "render_html", side_effect=fail_after_directory):
            code, out, err = self.run_cli({"mcpServers": {}})
        self.assertEqual(code, 2)
        self.assertFalse(self.output.exists())
        self.assertNotIn("SYNTHETIC_PRIVATE_PATH", out + err)


if __name__ == "__main__":
    unittest.main()
