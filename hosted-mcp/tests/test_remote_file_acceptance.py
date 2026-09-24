"""Fixture-only tests for the opt-in Remote file acceptance CLI."""

import contextlib
import hashlib
import importlib.util
import io
import json
import unittest
import warnings
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "accept_remote_file_read.py"
SPEC = importlib.util.spec_from_file_location("accept_remote_file_read", SCRIPT)
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)
ISSUER = "https://auth.example/"
TOKEN = "fixture-token-must-not-be-logged"
FILE_TEXT = "fixture file contents must not be logged"
FILE_SHA256 = hashlib.sha256(FILE_TEXT.encode()).hexdigest()
APPROVED = "approved.txt"
DENIED = "../credentials"


class Response(io.BytesIO):
    status = 200


class Opener:
    def __init__(self, handler):
        self.handler = handler

    def open(self, request, timeout=20):
        return self.handler(request, timeout)


class Terminal(io.StringIO):
    def isatty(self):
        return True


class RemoteFileAcceptanceTests(unittest.TestCase):
    def args(self):
        return ["--issuer", ISSUER, "--device-name", "ChatGPTStudio", "--approved-path", APPROVED,
                "--denied-path", DENIED, "--expected-sha256", FILE_SHA256]

    def metadata_open(self, request, timeout=20):
        self.assertEqual(request.full_url, probe.METADATA_URL)
        return Response(json.dumps({
            "resource": probe.RESOURCE,
            "authorization_servers": [ISSUER],
            "scopes_supported": ["devices:read", "tools:read"],
        }).encode())

    def test_exact_issuer_and_resource_are_preserved(self):
        metadata = {
            "resource": probe.RESOURCE,
            "authorization_servers": [ISSUER],
            "scopes_supported": ["devices:read", "tools:read"],
        }
        self.assertTrue(probe.metadata_matches(ISSUER, metadata))
        self.assertFalse(probe.metadata_matches(ISSUER.rstrip("/"), metadata))
        metadata["resource"] = "https://remote-backend.example/mcp"
        self.assertFalse(probe.metadata_matches(ISSUER, metadata))

    def test_completed_read_requires_exact_path_and_hash(self):
        result = {"isError": False, "structuredContent": {"path": APPROVED, "content": FILE_TEXT}}
        self.assertTrue(probe.completed_read_matches(result, APPROVED, FILE_SHA256))
        self.assertFalse(probe.completed_read_matches(result, APPROVED, "0" * 64))
        self.assertFalse(probe.completed_read_matches(result, "other.txt", FILE_SHA256))
        self.assertFalse(probe.completed_read_matches({"isError": False}, APPROVED, FILE_SHA256))

    def test_pending_and_generic_success_do_not_count_as_completed_reads(self):
        pending = {"isError": False, "structuredContent": {"pending": True, "call": {"id": "fixture-id"}}}
        empty_success = {"isError": False, "structuredContent": {"ok": True}}
        self.assertFalse(probe.completed_read_matches(pending, APPROVED, FILE_SHA256))
        self.assertFalse(probe.completed_read_matches(empty_success, APPROVED, FILE_SHA256))

    def test_denial_requires_path_bound_outside_directory_reason(self):
        good = {"isError": True, "structuredContent": {"path": DENIED, "error": "Path is outside allowed directory"}}
        exact_code = {"isError": True, "structuredContent": {"path": DENIED, "errorCode": "PATH_OUTSIDE_ALLOWED_DIRECTORY"}}
        exact_message = {"isError": True, "structuredContent": {"path": DENIED, "message": "Path is outside the allowed directory."}}
        generic = {"isError": True, "structuredContent": {"path": DENIED, "error": "read failed"}}
        embedded = {"isError": True, "structuredContent": {"path": DENIED, "error": f"ENOENT: {DENIED}/outside_allowed_directory"}}
        wrong_path = {"isError": True, "structuredContent": {"path": "other", "error": "outside allowed directory"}}
        self.assertTrue(probe.outside_allowed_directory_error(good, DENIED))
        self.assertTrue(probe.outside_allowed_directory_error(exact_code, DENIED))
        self.assertTrue(probe.outside_allowed_directory_error(exact_message, DENIED))
        self.assertFalse(probe.outside_allowed_directory_error(generic, DENIED))
        self.assertFalse(probe.outside_allowed_directory_error(embedded, DENIED))
        self.assertFalse(probe.outside_allowed_directory_error(wrong_path, DENIED))

    def test_token_prompt_refuses_non_tty_without_calling_getpass(self):
        output = io.StringIO()
        with (patch.object(probe.sys, "stdin", io.StringIO()),
              patch.object(probe.sys, "stderr", io.StringIO()),
              patch.object(probe.getpass, "getpass") as getpass_call,
              contextlib.redirect_stdout(output)):
            token = probe.read_hidden_token()
        self.assertIsNone(token)
        getpass_call.assert_not_called()
        self.assertIn("requires an interactive terminal", output.getvalue())

    def test_getpass_fallback_warning_aborts_before_token_is_returned(self):
        output = io.StringIO()
        token_read = False

        def fallback_warning(_prompt):
            nonlocal token_read
            warnings.warn("echo fallback", probe.getpass.GetPassWarning)
            token_read = True
            return TOKEN

        with (patch.object(probe.sys, "stdin", Terminal()),
              patch.object(probe.sys, "stderr", Terminal()),
              patch.object(probe.getpass, "getpass", side_effect=fallback_warning),
              contextlib.redirect_stdout(output)):
            token = probe.read_hidden_token()
        self.assertIsNone(token)
        self.assertFalse(token_read)
        self.assertNotIn(TOKEN, output.getvalue())
        self.assertIn("hidden token input unavailable", output.getvalue())

    def test_approved_read_device_and_denial_are_reported_without_secrets(self):
        calls = []
        output = io.StringIO()

        def fake_call(_opener, token, name, arguments):
            self.assertEqual(token, TOKEN)
            calls.append((name, arguments))
            if name == probe.DEVICES_TOOL:
                return {"isError": False, "structuredContent": {"devices": [{"name": "ChatGPTStudio", "id": "fixture-device"}]}}
            if arguments["path"] == APPROVED:
                return {"isError": False, "structuredContent": {"path": APPROVED, "content": FILE_TEXT}}
            return {"isError": True, "structuredContent": {"path": DENIED, "error": "outside allowed directory"}}

        with (patch.object(probe.urllib.request, "build_opener", return_value=Opener(self.metadata_open)),
              patch.object(probe.sys, "stdin", Terminal()),
              patch.object(probe.sys, "stderr", Terminal()),
              patch.object(probe.getpass, "getpass", return_value=TOKEN),
              patch.object(probe, "call_tool", side_effect=fake_call),
              contextlib.redirect_stdout(output)):
            result = probe.main(self.args())

        self.assertEqual(result, 0)
        self.assertEqual([item[0] for item in calls], [probe.DEVICES_TOOL, probe.READ_TOOL, probe.READ_TOOL])
        self.assertEqual(calls[1][1]["device"], "fixture-device")
        for secret in (TOKEN, FILE_TEXT, APPROVED, DENIED, "outside allowed directory"):
            self.assertNotIn(secret, output.getvalue())
        self.assertIn("matched exact path and content hash", output.getvalue())
        self.assertIn("was rejected outside the allowed directory", output.getvalue())

    def test_pending_read_is_not_validated_and_is_not_resubmitted(self):
        calls = []
        output = io.StringIO()

        def fake_call(_opener, _token, name, arguments):
            calls.append((name, arguments))
            if name == probe.DEVICES_TOOL:
                return {"structuredContent": {"devices": [{"name": "ChatGPTStudio", "id": "fixture-device"}]}}
            if name == probe.READ_TOOL and arguments["path"] == APPROVED:
                return {"isError": False, "structuredContent": {"pending": True, "call": {"id": "call-1"}}}
            if name == "nymrel_remote_get_read_result":
                return {"isError": False, "structuredContent": {"pending": True, "call": {"id": "call-1"}}}
            return {"isError": True, "structuredContent": {"path": DENIED, "error": "outside allowed directory"}}

        with (patch.object(probe.urllib.request, "build_opener", return_value=Opener(self.metadata_open)),
              patch.object(probe.sys, "stdin", Terminal()),
              patch.object(probe.sys, "stderr", Terminal()),
              patch.object(probe.getpass, "getpass", return_value=TOKEN),
              patch.object(probe, "call_tool", side_effect=fake_call),
              patch.object(probe.time, "sleep"),
              contextlib.redirect_stdout(output)):
            result = probe.main(self.args() + ["--pending-checks", "1"])

        self.assertEqual(result, 1)
        self.assertEqual([item[0] for item in calls], [probe.DEVICES_TOOL, probe.READ_TOOL, "nymrel_remote_get_read_result", probe.READ_TOOL])
        self.assertIn("not_validated", output.getvalue())

    def test_device_must_match_exactly_once(self):
        self.assertIsNone(probe.exact_device_id({"structuredContent": {"devices": []}}, "ChatGPTStudio"))
        self.assertIsNone(probe.exact_device_id({"structuredContent": {"devices": [
            {"name": "ChatGPTStudio", "id": "one"}, {"name": "ChatGPTStudio", "id": "two"}
        ]}}, "ChatGPTStudio"))

    def test_metadata_mismatch_stops_before_prompt_or_tool_calls(self):
        output = io.StringIO()

        def fake_open(_request, timeout=20):
            return Response(json.dumps({
                "resource": probe.RESOURCE,
                "authorization_servers": [ISSUER.rstrip("/")],
                "scopes_supported": ["devices:read", "tools:read"],
            }).encode())

        with (patch.object(probe.urllib.request, "build_opener", return_value=Opener(fake_open)),
              patch.object(probe.getpass, "getpass") as prompt,
              patch.object(probe, "call_tool") as call_tool,
              contextlib.redirect_stdout(output)):
            result = probe.main(self.args())

        self.assertEqual(result, 1)
        prompt.assert_not_called()
        call_tool.assert_not_called()
        self.assertIn("exact issuer", output.getvalue())


if __name__ == "__main__":
    unittest.main()
