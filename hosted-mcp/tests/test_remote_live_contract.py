"""Check the activated verifier's public contract without a live OAuth account."""

import contextlib
import importlib.util
import io
import json
import sys
import unittest
import urllib.error
from email.message import Message
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "verify_live_contract.py"
SPEC = importlib.util.spec_from_file_location("verify_live_contract", SCRIPT)
verifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verifier)
ISSUER = "https://issuer.example/"


class Response(io.BytesIO):
    status = 200


def fake_urlopen(request, timeout=30):
    if request.full_url.endswith(verifier.REMOTE_METADATA):
        return Response(json.dumps({
            "resource": verifier.REMOTE_RESOURCE,
            "authorization_servers": [ISSUER],
            "scopes_supported": sorted(verifier.REMOTE_SCOPES),
        }).encode())
    if request.full_url == "https://fixture.test/":
        return Response(b'{"endpoint":"/mcp"}')
    raise AssertionError(f"Unexpected public request: {request.full_url}")


def fake_rpc(_base, method, params, *, challenge=True):
    if method == "tools/list":
        tools = []
        for name in sorted(verifier.EXPECTED_TOOLS | verifier.REMOTE_TOOLS):
            schemes = ([{"type": "oauth2", "scopes": sorted(verifier.REMOTE_SCOPES)}]
                       if name in verifier.REMOTE_TOOLS else [{"type": "noauth"}])
            tools.append({"name": name, "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
                          "annotations": {"title": name, "readOnlyHint": True, "destructiveHint": False,
                                          "openWorldHint": name in {"nymrel_audit_website", "nymrel_find_domain"}},
                          "securitySchemes": schemes, "_meta": {"securitySchemes": schemes}})
        return {"result": {"tools": tools}}
    name = params["name"]
    if name == "nymrel_remote_list_devices":
        metadata = {"mcp/www_authenticate": [
            f'Bearer resource_metadata="{verifier.REMOTE_METADATA}", scope="devices:read tools:read"'
        ]} if challenge else {}
        return {"result": {"isError": True, "_meta": metadata}}
    if name == "nymrel_golf_bag_gap":
        if "carry_distance_yards" in params["arguments"]["clubs"][0]:
            payload = {"average_gap_yards": 22, "problem_gaps": ["22 yard gap"], "recommendations": []}
            return {"result": {"content": [{"type": "text", "text": json.dumps(payload)}],
                               "structuredContent": payload}}
        return {"result": {"isError": True, "content": [{"text": "carry_distance_yards required"}]}}
    raise AssertionError(f"Unexpected tool: {name}")


class ActivatedVerifierTests(unittest.TestCase):
    def run_verifier(self, *, challenge=True, status=401, http_header=True, mutate=None, extra_args=()):
        output = io.StringIO()
        def response(*args, **kwargs):
            result = fake_rpc(*args, **kwargs, challenge=challenge)
            if mutate:
                mutate(args[1], args[2], result)
            return result
        header = (f'Bearer resource_metadata="{verifier.REMOTE_METADATA}", scope="devices:read tools:read", '
                  'error="invalid_token", error_description="Connect to continue"')
        denied = {"result": {"isError": True, "_meta": {"mcp/www_authenticate": [header] if challenge else []}}}
        with (patch.object(sys, "argv", ["verify", "--remote-read", "--issuer", ISSUER, "https://fixture.test", *extra_args]),
              patch.object(verifier.urllib.request, "urlopen", side_effect=fake_urlopen),
              patch.object(verifier, "rpc", side_effect=response),
              patch.object(verifier, "remote_auth_probe", return_value=(status, header if http_header else "", denied)),
              contextlib.redirect_stdout(output)):
            result = verifier.main()
        return result, output.getvalue()

    def test_activated_catalog_metadata_and_challenge(self):
        result, output = self.run_verifier()
        self.assertEqual(result, 0, output)
        self.assertIn("private read requires caller OAuth", output)

    def test_new_output_contract_gate_rejects_legacy_schemas(self):
        result, output = self.run_verifier(extra_args=("--public-results",))
        self.assertEqual(result, 1, output)
        self.assertIn("FAIL nymrel_audit_website publishes the reviewed output schema", output)

    def test_new_output_contract_gate_accepts_reviewed_schemas(self):
        import public_results
        models = {"nymrel_audit_website": public_results.AuditSummary,
                  "nymrel_find_domain": public_results.DomainResult,
                  "nymrel_golf_bag_gap": public_results.GolfResult,
                  "nymrel_social_clip_score": public_results.ClipResult}

        def add_schemas(method, _params, result):
            if method == "tools/list":
                for tool in result["result"]["tools"]:
                    if tool["name"] in models:
                        tool["outputSchema"] = public_results.output_schema(models[tool["name"]])

        result, output = self.run_verifier(extra_args=("--public-results",), mutate=add_schemas)
        self.assertEqual(result, 0, output)

    def test_catalog_regressions_fail_closed(self):
        mutations = {
            "duplicate tool": lambda tools: tools.append(tools[0]),
            "false read-only": lambda tools: tools[0]["annotations"].update(readOnlyHint=False),
            "string read-only": lambda tools: tools[0]["annotations"].update(readOnlyHint="true"),
            "destructive": lambda tools: tools[0]["annotations"].update(destructiveHint=True),
            "missing reach": lambda tools: tools[0]["annotations"].pop("openWorldHint"),
            "wrong reach": lambda tools: tools[0]["annotations"].update(openWorldHint=False),
            "missing top-level auth": lambda tools: tools[0].pop("securitySchemes"),
            "missing mirror": lambda tools: tools[0].pop("_meta"),
            "conflicting mirror": lambda tools: tools[0]["_meta"].update(securitySchemes=[]),
        }
        for label, mutation in mutations.items():
            with self.subTest(label=label):
                def mutate(method, _params, result):
                    if method == "tools/list":
                        mutation(result["result"]["tools"])
                result, output = self.run_verifier(mutate=mutate)
                self.assertEqual(result, 1, output)

    def test_golf_requires_actual_consistent_result(self):
        payload = {"average_gap_yards": 22, "problem_gaps": [], "recommendations": []}
        invalid_results = [
            {"content": [{"type": "text", "text": "average_gap_yards unavailable"}]},
            {"content": [{"type": "text", "text": json.dumps({**payload, "average_gap_yards": 0})}]},
            {"content": [{"type": "text", "text": json.dumps({**payload, "average_gap_yards": "22"})}]},
            {"content": [{"type": "text", "text": "[]"}]},
            {"content": []},
            {"content": [{"type": "text", "text": json.dumps(payload)}],
             "structuredContent": {**payload, "average_gap_yards": 0}},
        ]
        for invalid in invalid_results:
            with self.subTest(result=invalid):
                def mutate(method, params, result):
                    if (method == "tools/call" and params["name"] == "nymrel_golf_bag_gap"
                            and "carry_distance_yards" in params["arguments"]["clubs"][0]):
                        result["result"] = invalid
                result, output = self.run_verifier(mutate=mutate)
                self.assertEqual(result, 1, output)
                self.assertIn("FAIL golf accepts the documented shape", output)

    def test_missing_private_challenge_fails(self):
        result, output = self.run_verifier(challenge=False)
        self.assertEqual(result, 1, output)
        self.assertIn("FAIL private read requires caller OAuth", output)

    def test_http_200_tool_challenge_is_not_transport_auth_success(self):
        result, output = self.run_verifier(status=200)
        self.assertEqual(result, 1, output)
        self.assertIn("FAIL private read requires caller OAuth", output)

    def test_missing_http_challenge_fails(self):
        result, output = self.run_verifier(http_header=False)
        self.assertEqual(result, 1, output)
        self.assertIn("FAIL invalid token returns HTTP OAuth challenge", output)

    def test_probe_reads_http_error_response(self):
        headers = Message()
        headers["WWW-Authenticate"] = "Bearer fixture"
        error = urllib.error.HTTPError("https://fixture.test/mcp", 401, "Unauthorized", headers,
                                       io.BytesIO(b'{"result":{"isError":true}}'))
        with patch.object(verifier.urllib.request, "urlopen", side_effect=error):
            status, header, payload = verifier.remote_auth_probe("https://fixture.test")
        self.assertEqual(status, 401)
        self.assertEqual(header, "Bearer fixture")
        self.assertTrue(payload["result"]["isError"])


if __name__ == "__main__":
    unittest.main()
